"""Embedding providers: local sentence-transformers with FAISS support,
and a deterministic hashing fallback used when heavy dependencies are
unavailable.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import List, Optional

logger = logging.getLogger("embedding_provider")


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    def build_faiss_index(self, vectors: List[List[float]]):
        return None


class HashingEmbeddingProvider(EmbeddingProvider):
    """Deterministic hashing fallback that requires no external packages."""

    def __init__(self, dim: int = 256):
        import hashlib
        import math

        self.dim = dim
        self._hashlib = hashlib
        self._math = math

    def _embed_one(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        tokens = text.lower().split()
        for token in tokens:
            digest = self._hashlib.md5(token.encode("utf-8")).hexdigest()
            bucket = int(digest, 16) % self.dim
            vec[bucket] += 1.0
        norm = self._math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_one(t) for t in texts]


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    """Uses sentence-transformers locally and can optionally build FAISS."""

    PREFERRED = "BAAI/bge-small-en-v1.5"
    FALLBACK = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self, preferred: Optional[str] = None):
        self.model_name = preferred or self.PREFERRED
        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np
        except Exception as exc:
            logger.warning("sentence-transformers unavailable (%s)", exc)
            raise

        try:
            self._model = SentenceTransformer(self.model_name)
            logger.info("Loaded embedding model: %s", self.model_name)
        except Exception:
            logger.warning("Preferred model %s unavailable; loading fallback %s", self.model_name, self.FALLBACK)
            self.model_name = self.FALLBACK
            self._model = SentenceTransformer(self.model_name)

        self._np = __import__("numpy")
        self._faiss_index = None

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        embs = self._model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        if hasattr(embs, "tolist"):
            return embs.tolist()
        return [list(map(float, v)) for v in embs]

    def build_faiss_index(self, vectors: List[List[float]]):
        try:
            import faiss
            import numpy as np
        except Exception as exc:
            logger.warning("faiss unavailable (%s); skipping FAISS index build", exc)
            return None

        if not vectors:
            return None

        arr = np.array(vectors, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True) or 1.0
        arr = arr / (norms + 1e-12)

        dim = arr.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(arr)
        self._faiss_index = index
        logger.info("Built FAISS index with %d vectors (dim=%d)", arr.shape[0], dim)
        return index


def get_embedding_provider() -> EmbeddingProvider:
    try:
        provider = SentenceTransformerEmbeddingProvider()
        return provider
    except Exception:
        logger.info("Using HashingEmbeddingProvider fallback for embeddings")
        return HashingEmbeddingProvider()
