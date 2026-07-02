import json
from pathlib import Path

from app.catalog.schema import CatalogItem
from app.services.reranker import rerank_candidates

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_catalog.json"


def load_sample_catalog():
    raw = json.loads(FIXTURE_PATH.read_text())
    return [CatalogItem(**entry) for entry in raw]


def test_reranker_returns_original_order_when_no_gemini():
    catalog = load_sample_catalog()
    candidates = catalog[:5]
    ordered = rerank_candidates(candidates, "SQL test for mid-level", "context")
    assert [c.url for c in ordered] == [c.url for c in candidates]
