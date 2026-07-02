from pathlib import Path

import pytest

from app.catalog.scraper import SHLCatalogScraper, ScrapeConfig

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def scraper():
    config = ScrapeConfig(base_url="https://www.shl.com/products/product-catalog/")
    return SHLCatalogScraper(config)


def test_parse_listing_page_only_returns_individual_test_solutions(scraper):
    html = (FIXTURES / "listing_sample.html").read_text()
    records = scraper.parse_listing_page(html)

    names = [r["name"] for r in records]
    assert "Account Manager Solution" not in names, (
        "Pre-packaged Job Solutions must never leak into scraped results"
    )
    assert names == [
        ".NET Framework 4.5",
        "Accounts Payable Simulation (New)",
        "Global Skills Development Report",
    ]


def test_parse_listing_page_extracts_test_type_codes(scraper):
    html = (FIXTURES / "listing_sample.html").read_text()
    records = scraper.parse_listing_page(html)

    by_name = {r["name"]: r for r in records}
    assert by_name[".NET Framework 4.5"]["test_type_codes"] == ["K"]
    assert by_name["Global Skills Development Report"]["test_type_codes"] == [
        "A", "E", "B", "C", "D", "P",
    ]


def test_parse_listing_page_extracts_icon_flags(scraper):
    html = (FIXTURES / "listing_sample.html").read_text()
    records = scraper.parse_listing_page(html)

    by_name = {r["name"]: r for r in records}
    net_framework = by_name[".NET Framework 4.5"]
    assert net_framework["remote_testing"] is True
    assert net_framework["adaptive_irt"] is False

    sim = by_name["Accounts Payable Simulation (New)"]
    assert sim["remote_testing"] is False
    assert sim["adaptive_irt"] is True


def test_parse_listing_page_resolves_relative_urls(scraper):
    html = (FIXTURES / "listing_sample.html").read_text()
    records = scraper.parse_listing_page(html)
    for r in records:
        assert r["url"].startswith("https://www.shl.com/")


def test_parse_listing_page_empty_table_returns_empty_list(scraper):
    html = "<html><body><table><tr><th>Nothing here</th></tr></table></body></html>"
    records = scraper.parse_listing_page(html)
    assert records == []


def test_parse_detail_page_extracts_all_fields(scraper):
    html = (FIXTURES / "detail_sample.html").read_text()
    detail = scraper.parse_detail_page(
        html, "https://www.shl.com/products/product-catalog/view/net-framework-4-5/"
    )

    assert detail["description"].startswith("The .NET Framework 4.5 test measures")
    assert detail["job_levels"] == ["Professional Individual Contributor", "Mid-Professional"]
    assert detail["languages"] == ["English (USA)"]
    assert detail["duration_minutes"] == 30
    assert detail["test_type_codes_detail"] == ["K"]
    assert detail["remote_testing_detail"] is True
    assert detail["downloads"] == [
        "https://service.shl.com/docs/Fact_Sheet-dotnet_framework_4.5.pdf"
    ]


def test_scrape_all_merges_listing_and_detail(scraper, monkeypatch):
    """End-to-end (offline): stub out network fetches with fixture HTML and
    make sure a full CatalogItem comes out the other end correctly merged."""
    listing_html = (FIXTURES / "listing_sample.html").read_text()
    detail_html = (FIXTURES / "detail_sample.html").read_text()

    call_count = {"listing": 0}

    def fake_fetch(url):
        if "start=" in url or url == scraper.config.base_url:
            call_count["listing"] += 1
            if call_count["listing"] == 1:
                return listing_html
            return None  # end pagination after first page
        return detail_html

    monkeypatch.setattr(scraper, "_fetch", fake_fetch)
    monkeypatch.setattr(scraper, "_polite_sleep", lambda: None)

    items = scraper.scrape_all()

    assert len(items) == 3
    net_item = next(i for i in items if i.name == ".NET Framework 4.5")
    assert net_item.detail_scraped is True
    assert net_item.duration_minutes == 30
    assert net_item.test_type_labels == ["Knowledge & Skills"]
    assert net_item.solution_type == "individual_test_solution"


def test_scrape_all_respects_limit(scraper, monkeypatch):
    listing_html = (FIXTURES / "listing_sample.html").read_text()
    detail_html = (FIXTURES / "detail_sample.html").read_text()
    scraper.config.limit = 2

    def fake_fetch(url):
        if "start=" in url or url == scraper.config.base_url:
            return listing_html
        return detail_html

    monkeypatch.setattr(scraper, "_fetch", fake_fetch)
    monkeypatch.setattr(scraper, "_polite_sleep", lambda: None)

    items = scraper.scrape_all()
    assert len(items) == 2
