"""Keyword retrieval using BM25 (rank-bm25).

BM25 provides robust lexical matching and is the designated keyword
component for the hybrid retriever.
"""
from __future__ import annotations

from typing import List, Tuple

from rank_bm25 import BM25Okapi

from app.catalog.schema import CatalogItem


def _searchable_text(item: CatalogItem) -> str:
    parts = [
        item.name,
        item.description or "",
        " ".join(item.job_levels),
        " ".join(item.languages),
        " ".join(item.test_type_labels),
    ]
    return " ".join(p for p in parts if p)


class KeywordRetriever:
    def __init__(self, catalog: List[CatalogItem]):
        self.catalog = catalog
        self._corpus = [_searchable_text(item) for item in catalog]
        # Tokenize by whitespace for BM25
        self._tokenized = [doc.lower().split() for doc in self._corpus]
        self._bm25 = BM25Okapi(self._tokenized) if self._tokenized else None

    def score_all(self, query: str) -> List[float]:
        if not query.strip() or self._bm25 is None:
            return [0.0] * len(self.catalog)
        tokens = query.lower().split()
        scores = self._bm25.get_scores(tokens)
        return list(scores)

    def search(self, query: str, top_k: int = 10) -> List[Tuple[CatalogItem, float]]:
        scores = self.score_all(query)
        ranked = sorted(zip(self.catalog, scores), key=lambda pair: pair[1], reverse=True)
        return [(item, float(score)) for item, score in ranked[:top_k] if score > 0]
