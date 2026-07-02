"""
Offline catalog loading service for the SHL assessment catalog.

The application uses `data/catalog.json` as the only source of truth for
recommendations, comparisons, and metadata. The service validates the JSON,
builds in-memory indexes, and exposes catalog lookups without scraping or
making network requests during runtime.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.catalog.schema import CatalogItem, TEST_TYPE_LABEL_TO_CODE
from app.core.config import settings
from app.retrieval.embedding import EmbeddingProvider, HashingEmbeddingProvider
from app.retrieval.keyword import KeywordRetriever

logger = logging.getLogger("catalog_loader")


class CatalogUnavailable(RuntimeError):
    """Raised when the catalog file is missing, empty, or unparseable."""


class CatalogService:
    """Reusable offline catalog service backed by catalog.json."""

    def __init__(
        self, catalog_path: Path | None = None, embedding_provider: Optional[EmbeddingProvider] = None
    ):
        self.catalog_path = Path(catalog_path or settings.catalog_path)
        self.embedding_provider = embedding_provider or HashingEmbeddingProvider()
        self._items: List[CatalogItem] = []
        self._by_name: Dict[str, CatalogItem] = {}
        self._by_url: Dict[str, CatalogItem] = {}
        self._keyword_retriever: Optional[KeywordRetriever] = None
        self._embedding_vectors: List[List[float]] = []
        self._loaded = False

    @property
    def items(self) -> List[CatalogItem]:
        if not self._loaded:
            self.load()
        return self._items

    @property
    def keyword_retriever(self) -> KeywordRetriever:
        if not self._loaded:
            self.load()
        return self._keyword_retriever or KeywordRetriever(self._items)

    @property
    def embedding_vectors(self) -> List[List[float]]:
        if not self._loaded:
            self.load()
        return self._embedding_vectors

    def load(self, catalog_path: Path | None = None) -> List[CatalogItem]:
        path = Path(catalog_path or self.catalog_path)
        self.catalog_path = path

        if not path.exists():
            raise CatalogUnavailable(
                f"Catalog file not found at {path}. The application requires an offline catalog.json and will not scrape the SHL website."
            )

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CatalogUnavailable(f"Catalog file at {path} is not valid JSON: {exc}") from exc

        if not isinstance(raw, list) or not raw:
            raise CatalogUnavailable(f"Catalog file at {path} contains no items.")

        entries: List[CatalogItem] = []
        skipped = 0
        for entry in raw:
            if not isinstance(entry, dict):
                skipped += 1
                continue
            normalized_entry = _normalize_catalog_entry(entry)
            if not _is_valid_catalog_entry(normalized_entry):
                skipped += 1
                continue
            try:
                item = CatalogItem(**normalized_entry)
            except Exception as exc:  # malformed single row shouldn't kill the whole catalog
                logger.warning("Skipping malformed catalog entry: %s", exc)
                skipped += 1
                continue
            if item.solution_type != "individual_test_solution":
                skipped += 1
                continue
            entries.append(item)

        if not entries:
            raise CatalogUnavailable(
                f"Catalog file at {path} had no valid Individual Test Solution entries."
            )

        self._items = entries
        self._by_name = {item.name.lower(): item for item in self._items}
        self._by_url = {_normalize_url(item.url): item for item in self._items}
        self._keyword_retriever = KeywordRetriever(self._items)
        self._embedding_vectors = self._build_embedding_index()
        # Allow embedding provider to optionally build a FAISS index for fast NN search
        try:
            if hasattr(self.embedding_provider, "build_faiss_index") and self._embedding_vectors:
                self.embedding_provider.build_faiss_index(self._embedding_vectors)
        except Exception:
            logger.warning("Failed to build FAISS index; continuing without it")
        self._loaded = True
        logger.info("Loaded %d catalog entries from %s", len(self._items), path)
        if skipped:
            logger.info("Loaded catalog with %d items (%d skipped)", len(self._items), skipped)
        return self._items

    def reload(self, catalog_path: Path | None = None) -> List[CatalogItem]:
        self._loaded = False
        return self.load(catalog_path)

    def get_items(self) -> List[CatalogItem]:
        return self.items

    def get_by_name(self, name: str) -> Optional[CatalogItem]:
        if not name:
            return None
        return self._by_name.get(name.strip().lower())

    def get_by_url(self, url: str) -> Optional[CatalogItem]:
        if not url:
            return None
        return self._by_url.get(_normalize_url(url))

    def search(self, query: str, constraints: Any | None = None, top_k: int = 5) -> List[CatalogItem]:
        from app.retrieval.hybrid import HybridRetriever

        return HybridRetriever(catalog_service=self).search(query, constraints, top_k)

    def _build_embedding_index(self) -> List[List[float]]:
        texts = [_searchable_text(item) for item in self._items]
        return self.embedding_provider.embed(texts) if texts else []


_CATALOG_SERVICE: Optional[CatalogService] = None


def get_catalog_service(
    catalog_path: Path | None = None, embedding_provider: Optional[EmbeddingProvider] = None
) -> CatalogService:
    global _CATALOG_SERVICE
    if catalog_path is not None and _CATALOG_SERVICE is not None and _CATALOG_SERVICE.catalog_path != Path(catalog_path):
        _CATALOG_SERVICE = None
    if _CATALOG_SERVICE is None:
        _CATALOG_SERVICE = CatalogService(catalog_path=catalog_path, embedding_provider=embedding_provider)
        _CATALOG_SERVICE.load()
    return _CATALOG_SERVICE


@lru_cache(maxsize=1)
def get_catalog(path: Path | None = None) -> List[CatalogItem]:
    return get_catalog_service(path).get_items()


def reload_catalog(path: Path | None = None) -> List[CatalogItem]:
    global _CATALOG_SERVICE
    _CATALOG_SERVICE = None
    get_catalog.cache_clear()
    return get_catalog(path)


def _normalize_url(url: str) -> str:
    return str(url).rstrip("/").lower()


def _parse_duration_minutes(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value)
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else None


def _normalize_catalog_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(entry)

    if "url" not in normalized and "link" in normalized:
        normalized["url"] = normalized["link"]

    if "test_type_labels" not in normalized and "keys" in normalized:
        normalized["test_type_labels"] = normalized["keys"]

    if "test_type_codes" not in normalized:
        labels = normalized.get("test_type_labels") or []
        if isinstance(labels, list):
            codes = []
            for label in labels:
                if not isinstance(label, str):
                    continue
                code = TEST_TYPE_LABEL_TO_CODE.get(label.strip())
                if code and code not in codes:
                    codes.append(code)
            normalized["test_type_codes"] = codes

    if "remote_testing" not in normalized and "remote" in normalized:
        remote = str(normalized["remote"]).strip().lower()
        normalized["remote_testing"] = remote.startswith("y") or remote == "yes"

    if "adaptive_irt" not in normalized and "adaptive" in normalized:
        adaptive = str(normalized["adaptive"]).strip().lower()
        normalized["adaptive_irt"] = adaptive.startswith("y") or adaptive == "yes"

    if "duration_minutes" not in normalized:
        normalized["duration_minutes"] = _parse_duration_minutes(normalized.get("duration"))

    if "solution_type" not in normalized:
        normalized["solution_type"] = "individual_test_solution"

    return normalized


def _is_valid_catalog_entry(entry: Dict[str, Any]) -> bool:
    required_fields = {"name", "url", "test_type_codes"}
    if not required_fields.issubset(entry.keys()):
        return False
    if not isinstance(entry["name"], str) or not entry["name"].strip():
        return False
    if not isinstance(entry["url"], str) or not entry["url"].strip():
        return False
    if not isinstance(entry["test_type_codes"], list):
        return False
    return True


def _searchable_text(item: CatalogItem) -> str:
    parts = [
        item.name,
        item.description or "",
        " ".join(item.job_levels),
        " ".join(item.languages),
        " ".join(item.test_type_labels),
    ]
    return " ".join(p for p in parts if p)
