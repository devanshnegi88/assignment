"""
Hybrid retrieval: fuses TF-IDF keyword scores with embedding cosine
similarity, and applies hard constraint filters (job level, language,
duration, test type) extracted from the conversation.

Every recommendation produced here is grounded in the offline catalog loaded
from `catalog.json` via the reusable CatalogService.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from app.catalog.loader import CatalogService
from app.catalog.schema import CatalogItem
from app.core.config import settings
from app.retrieval.embedding import EmbeddingProvider, get_embedding_provider
from app.retrieval.keyword import KeywordRetriever, _searchable_text


@dataclass
class RetrievalConstraints:
    job_levels: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)
    max_duration_minutes: Optional[int] = None
    test_type_codes: List[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.job_levels or self.languages or self.max_duration_minutes or self.test_type_codes)


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
    norm_b = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (norm_a * norm_b)


def _normalize(scores: List[float]) -> List[float]:
    if not scores:
        return scores
    lo, hi = min(scores), max(scores)
    if hi - lo < 1e-9:
        return [0.0 for _ in scores]
    return [(s - lo) / (hi - lo) for s in scores]


class HybridRetriever:
    def __init__(
        self,
        catalog: Optional[List[CatalogItem]] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
        keyword_weight: float = settings.hybrid_keyword_weight,
        catalog_service: Optional[CatalogService] = None,
    ):
        if catalog_service is not None:
            self.catalog_service = catalog_service
            self.catalog = catalog_service.get_items()
            self.keyword_retriever = catalog_service.keyword_retriever
            self.embedding_provider = embedding_provider or getattr(catalog_service, "embedding_provider", None) or get_embedding_provider()
            self._catalog_embeddings = catalog_service.embedding_vectors
        else:
            self.catalog_service = None
            self.catalog = catalog or []
            self.keyword_retriever = KeywordRetriever(self.catalog)
            self.embedding_provider = embedding_provider or get_embedding_provider()
            texts = [_searchable_text(item) for item in self.catalog]
            self._catalog_embeddings = self.embedding_provider.embed(texts) if texts else []

        self.keyword_weight = keyword_weight

    def _matches_constraints(self, item: CatalogItem, constraints: RetrievalConstraints) -> bool:
        if constraints.job_levels:
            item_levels = {lvl.lower() for lvl in item.job_levels}
            wanted = {lvl.lower() for lvl in constraints.job_levels}
            if not (item_levels & wanted):
                return False
        if constraints.languages:
            item_langs = {l.lower() for l in item.languages}
            wanted = {l.lower() for l in constraints.languages}
            if item_langs and not (item_langs & wanted):
                return False
        if constraints.max_duration_minutes is not None and item.duration_minutes:
            if item.duration_minutes > constraints.max_duration_minutes:
                return False
        if constraints.test_type_codes:
            if not (set(item.test_type_codes) & set(constraints.test_type_codes)):
                return False
        return True

    def _semantic_scores(self, query: str) -> List[float]:
        # Prefer FAISS nearest-neighbour search when available (fast, prebuilt
        # at startup). Fall back to in-Python cosine scores if FAISS isn't
        # present.
        n = len(self.catalog)
        if not self._catalog_embeddings:
            return [0.0] * n

        # Try FAISS if the embedding provider built one
        faiss_index = getattr(self.embedding_provider, "_faiss_index", None)
        if faiss_index is not None:
            try:
                import numpy as np
            except Exception:
                faiss_index = None

        if faiss_index is not None:
            try:
                import numpy as np
                # Embed and normalize query vector
                qvec = self.embedding_provider.embed([query])[0]
                arr = np.array(qvec, dtype=np.float32)
                norm = np.linalg.norm(arr) or 1.0
                arr = (arr / (norm + 1e-12)).astype(np.float32)
                D, I = faiss_index.search(arr.reshape(1, -1), n)
                # D are inner products; convert to list aligned to catalog
                scores = [0.0] * n
                for score, idx in zip(D[0].tolist(), I[0].tolist()):
                    if idx >= 0 and idx < n:
                        scores[idx] = float(score)
                return scores
            except Exception:
                # Fall back to in-Python scoring
                pass

        [query_vec] = self.embedding_provider.embed([query])
        return [_cosine(query_vec, vec) for vec in self._catalog_embeddings]

    def search(
        self,
        query: str,
        constraints: Optional[RetrievalConstraints] = None,
        top_k: int = settings.default_top_k,
    ) -> List[CatalogItem]:
        constraints = constraints or RetrievalConstraints()
        # Get raw scores from BM25 (keyword retriever) and semantic search
        keyword_scores_raw = list(self.keyword_retriever.score_all(query))
        semantic_scores_raw = self._semantic_scores(query)

        n = len(self.catalog)

        # Build candidate set: top N from each component
        top_n = max(50, top_k * 5)
        # indices sorted desc
        kw_ranked_idx = sorted(range(n), key=lambda i: keyword_scores_raw[i], reverse=True)[:top_n]
        sem_ranked_idx = sorted(range(n), key=lambda i: semantic_scores_raw[i], reverse=True)[:top_n]
        candidate_idx = list(dict.fromkeys(kw_ranked_idx + sem_ranked_idx))  # preserve order

        # Reciprocal Rank Fusion (RRF)
        k_rrf = 60.0
        scores = {}
        for rank, idx in enumerate(kw_ranked_idx, start=1):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k_rrf + rank)
        for rank, idx in enumerate(sem_ranked_idx, start=1):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k_rrf + rank)

        # Convert scores into candidate list and apply constraints
        candidates = []
        for idx in sorted(candidate_idx, key=lambda i: scores.get(i, 0.0), reverse=True):
            item = self.catalog[idx]
            sc = scores.get(idx, 0.0)
            if self._matches_constraints(item, constraints):
                candidates.append((item, sc))

        pool = candidates if candidates else [(self.catalog[i], scores.get(i, 0.0)) for i in candidate_idx]
        ranked = sorted(pool, key=lambda pair: pair[1], reverse=True)
        top_k = max(settings.min_recommendations, min(top_k, settings.max_recommendations))
        top_slice = ranked[:top_k]
        nonzero = [item for item, score in top_slice if score > 0]
        return nonzero or [item for item, _ in top_slice]
