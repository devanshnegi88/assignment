import json
from pathlib import Path

from app.catalog.schema import CatalogItem
from app.retrieval.hybrid import HybridRetriever, RetrievalConstraints

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_catalog.json"


def load_sample_catalog():
    raw = json.loads(FIXTURE_PATH.read_text())
    return [CatalogItem(**entry) for entry in raw]


def test_search_only_returns_catalog_items():
    catalog = load_sample_catalog()
    retriever = HybridRetriever(catalog)
    results = retriever.search("SQL database knowledge test", top_k=5)
    catalog_urls = {item.url for item in catalog}
    assert all(r.url in catalog_urls for r in results), "every recommendation must be a real catalog item"


def test_relevant_query_ranks_matching_item_highly():
    catalog = load_sample_catalog()
    retriever = HybridRetriever(catalog)
    results = retriever.search("SQL query database knowledge test", top_k=3)
    names = [r.name for r in results]
    assert "SQL (New)" in names


def test_constraint_filter_by_job_level():
    catalog = load_sample_catalog()
    retriever = HybridRetriever(catalog)
    constraints = RetrievalConstraints(job_levels=["Graduate"])
    results = retriever.search("knowledge test", constraints=constraints, top_k=10)
    # Only Marketing (New) and Human Resources (New) list "Graduate" in the fixture
    assert results
    for r in results:
        assert "Graduate" in r.job_levels


def test_constraint_filter_degrades_gracefully_when_over_constrained():
    catalog = load_sample_catalog()
    retriever = HybridRetriever(catalog)
    # No item in the fixture has a 1-minute duration -- retrieval should
    # still return *something* rather than an empty list.
    constraints = RetrievalConstraints(max_duration_minutes=1)
    results = retriever.search("knowledge test", constraints=constraints, top_k=5)
    assert len(results) > 0


def test_top_k_is_capped_at_ten():
    catalog = load_sample_catalog() * 3  # simulate a larger catalog
    retriever = HybridRetriever(catalog)
    results = retriever.search("knowledge test", top_k=50)
    assert len(results) <= 10
