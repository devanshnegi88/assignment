from pathlib import Path

import pytest

from app.catalog import loader as catalog_loader
from app.core.config import settings
from app.services import pipeline as pipeline_module

SAMPLE_CATALOG_PATH = Path(__file__).parent / "fixtures" / "sample_catalog.json"


@pytest.fixture(autouse=True)
def use_sample_catalog(monkeypatch):
    """Every test runs against the small, hand-verified sample catalog
    fixture rather than requiring a real scrape to exist on disk."""
    monkeypatch.setattr(settings, "catalog_path", SAMPLE_CATALOG_PATH)
    catalog_loader.get_catalog.cache_clear()
    pipeline_module.get_retriever.cache_clear()
    yield
    catalog_loader.get_catalog.cache_clear()
    pipeline_module.get_retriever.cache_clear()
