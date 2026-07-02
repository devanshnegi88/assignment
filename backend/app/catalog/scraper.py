"""
Scraper for the SHL product catalog (Individual Test Solutions only).

Usage (as a library):

    from app.catalog.scraper import SHLCatalogScraper

    scraper = SHLCatalogScraper(base_url="https://www.shl.com/products/product-catalog/")
    items = scraper.scrape_all()
    scraper.save_json(items, "data/catalog.json")

Usage (CLI): see app/catalog/cli.py -- that's the "enter the link" entrypoint.

Design notes
------------
The catalog page renders two tables: "Pre-packaged Job Solutions" (type=2)
and "Individual Test Solutions" (type=1). The assignment is explicit that
only Individual Test Solutions are in scope, so this scraper only ever
requests type=1 pages and, as a second safety net, tags/filters by the
table header text when parsing -- if SHL ever reorders the tables, we still
grab the right one instead of silently scraping job solutions.

The "Remote Testing" and "Adaptive/IRT" columns in the table, and the
"Remote Testing" line on the detail page, are rendered as an icon (svg/img)
with no text -- there's no "Yes"/"No" string to read. We treat "an icon
element is present in the cell" as True and "empty cell" as False. This is
a heuristic based on the markup pattern SHL uses; if SHL changes that
markup, this is the single place to fix it (see `_cell_has_icon`).
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List, Optional
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode

import requests
from bs4 import BeautifulSoup

from app.catalog.schema import CatalogItem

logger = logging.getLogger("shl_scraper")

USER_AGENT = (
    "Mozilla/5.0 (compatible; SHL-Assessment-Recommender-Bot/1.0; "
    "+educational-take-home-assignment)"
)

ITEMS_PER_PAGE = 12  # observed page size on the SHL catalog table
INDIVIDUAL_TEST_SOLUTIONS_TYPE = 1
PREPACKAGED_JOB_SOLUTIONS_TYPE = 2


@dataclass
class ScrapeConfig:
    base_url: str
    delay_seconds: float = 1.0          # politeness delay between requests
    max_pages: int = 60                 # hard safety cap (60*12 = 720 rows)
    max_retries: int = 3
    timeout_seconds: int = 20
    fetch_details: bool = True
    limit: Optional[int] = None         # cap total items, useful for testing
    checkpoint_path: Optional[Path] = None
    checkpoint_every: int = 25


class SHLCatalogScraper:
    def __init__(self, config: ScrapeConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    # ------------------------------------------------------------------ #
    # HTTP
    # ------------------------------------------------------------------ #
    def _fetch(self, url: str) -> Optional[str]:
        last_error = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                resp = self.session.get(url, timeout=self.config.timeout_seconds)
                if resp.status_code == 200:
                    return resp.text
                if resp.status_code == 404:
                    logger.warning("404 for %s -- skipping", url)
                    return None
                last_error = f"HTTP {resp.status_code}"
            except requests.RequestException as exc:
                last_error = str(exc)
            wait = 2 ** attempt
            logger.warning(
                "Fetch failed (%s) for %s, attempt %d/%d, retrying in %ds",
                last_error, url, attempt, self.config.max_retries, wait,
            )
            time.sleep(wait)
        logger.error("Giving up on %s after %d attempts: %s",
                      url, self.config.max_retries, last_error)
        return None

    def _polite_sleep(self) -> None:
        if self.config.delay_seconds > 0:
            time.sleep(self.config.delay_seconds)

    # ------------------------------------------------------------------ #
    # URL helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _with_query(url: str, **params) -> str:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        for k, v in params.items():
            query[k] = [str(v)]
        new_query = urlencode(query, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    def _listing_page_url(self, start: int) -> str:
        return self._with_query(
            self.config.base_url, start=start, type=INDIVIDUAL_TEST_SOLUTIONS_TYPE
        )

    # ------------------------------------------------------------------ #
    # Parsing: listing pages
    # ------------------------------------------------------------------ #
    @staticmethod
    def _cell_has_icon(cell) -> bool:
        """True if a table cell contains an icon element (svg/img/i tag),
        which on shl.com's catalog table means 'yes' for that column."""
        if cell is None:
            return False
        if cell.find(["svg", "img"]) is not None:
            return True
        # Some SHL pages use icon-font <i class="..."> or <span class="icon...">
        icon_like = cell.find(lambda tag: tag.name in ("i", "span") and tag.get("class"))
        return icon_like is not None

    def _find_individual_test_solutions_table(self, soup: BeautifulSoup):
        """Locate the correct table by its header text rather than assuming
        table order, since the page always renders both tables."""
        for table in soup.find_all("table"):
            header_text = table.get_text(" ", strip=True)[:80].lower()
            if "individual test solutions" in header_text:
                return table
        return None

    def parse_listing_page(self, html: str) -> List[dict]:
        """Parse one listing page into partial records (no description yet)."""
        soup = BeautifulSoup(html, "lxml")
        table = self._find_individual_test_solutions_table(soup)
        if table is None:
            logger.warning("Could not find 'Individual Test Solutions' table on page")
            return []

        rows = table.find_all("tr")
        records = []
        for row in rows:
            link = row.find("a", href=True)
            if not link:
                continue  # header row or malformed row
            name = link.get_text(strip=True)
            if not name:
                continue
            url = urljoin(self.config.base_url, link["href"])

            cells = row.find_all("td")
            remote_testing = None
            adaptive_irt = None
            test_type_codes: List[str] = []

            if len(cells) >= 4:
                remote_testing = self._cell_has_icon(cells[1])
                adaptive_irt = self._cell_has_icon(cells[2])
                type_text = cells[3].get_text(" ", strip=True)
                test_type_codes = type_text.split()
            elif len(cells) >= 1:
                # Fallback: at minimum, try to pull single-letter codes out
                # of the last cell's text.
                type_text = cells[-1].get_text(" ", strip=True)
                test_type_codes = re.findall(r"\b[A-E,K,P,S]\b", type_text)

            records.append({
                "name": name,
                "url": url,
                "remote_testing": remote_testing,
                "adaptive_irt": adaptive_irt,
                "test_type_codes": test_type_codes,
            })
        return records

    def iter_listing_pages(self) -> Iterator[List[dict]]:
        """Yield parsed rows page by page, stopping when a page comes back
        empty (end of catalog) or the safety cap is hit."""
        empty_pages_in_a_row = 0
        for page_index in range(self.config.max_pages):
            start = page_index * ITEMS_PER_PAGE
            url = self._listing_page_url(start)
            logger.info("Fetching listing page %d (start=%d): %s",
                        page_index + 1, start, url)
            html = self._fetch(url)
            self._polite_sleep()

            if html is None:
                empty_pages_in_a_row += 1
                if empty_pages_in_a_row >= 2:
                    logger.info("Two consecutive failed pages, stopping pagination.")
                    break
                continue

            records = self.parse_listing_page(html)
            if not records:
                empty_pages_in_a_row += 1
                logger.info("Page %d had no rows -- assuming end of catalog.", page_index + 1)
                if empty_pages_in_a_row >= 2:
                    break
                continue

            empty_pages_in_a_row = 0
            yield records

    # ------------------------------------------------------------------ #
    # Parsing: detail pages
    # ------------------------------------------------------------------ #
    @staticmethod
    def _text_after_label(soup: BeautifulSoup, label: str) -> Optional[str]:
        """Find a heading/strong/dt element whose text matches `label` and
        return the text content of the element immediately following it."""
        candidate = soup.find(
            lambda tag: tag.name in ("h1", "h2", "h3", "h4", "h5", "strong", "b", "dt", "p")
            and tag.get_text(strip=True).lower().rstrip(":") == label.lower()
        )
        if candidate is None:
            return None
        nxt = candidate.find_next_sibling()
        if nxt is not None:
            text = nxt.get_text(" ", strip=True)
            if text:
                return text
        # Some templates put label + value in the same parent, label as a
        # bold prefix followed by plain text -- fall back to parent text
        # with the label stripped off.
        parent_text = candidate.parent.get_text(" ", strip=True) if candidate.parent else ""
        stripped = re.sub(rf"^{re.escape(candidate.get_text(strip=True))}\s*", "", parent_text)
        return stripped or None

    def parse_detail_page(self, html: str, url: str) -> dict:
        soup = BeautifulSoup(html, "lxml")
        full_text = soup.get_text("\n", strip=True)

        description = self._text_after_label(soup, "Description")

        job_levels_raw = self._text_after_label(soup, "Job levels") or ""
        job_levels = [j.strip() for j in job_levels_raw.split(",") if j.strip()]

        languages_raw = self._text_after_label(soup, "Languages") or ""
        languages = [l.strip() for l in languages_raw.split(",") if l.strip()]

        duration_minutes = None
        duration_match = re.search(
            r"Approximate Completion Time in minutes\s*=\s*(\d+)", full_text
        )
        if duration_match:
            duration_minutes = int(duration_match.group(1))

        test_type_match = re.search(r"Test Type:\s*([A-EKPS](?:\s*,?\s*[A-EKPS])*)", full_text)
        test_type_codes = test_type_match.group(1).split() if test_type_match else []

        remote_testing = None
        remote_label = soup.find(string=re.compile(r"^\s*Remote Testing\s*:?\s*$"))
        if remote_label is not None:
            container = remote_label.find_parent()
            remote_testing = self._cell_has_icon(container) if container else None

        downloads = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().endswith(".pdf") or "fact" in a.get_text(strip=True).lower():
                downloads.append(urljoin(url, href))

        return {
            "description": description,
            "job_levels": job_levels,
            "languages": languages,
            "duration_minutes": duration_minutes,
            "test_type_codes_detail": test_type_codes,
            "remote_testing_detail": remote_testing,
            "downloads": list(dict.fromkeys(downloads)),  # dedupe, keep order
        }

    # ------------------------------------------------------------------ #
    # Orchestration
    # ------------------------------------------------------------------ #
    def scrape_all(self) -> List[CatalogItem]:
        items: List[CatalogItem] = []
        seen_urls = set()

        for page_records in self.iter_listing_pages():
            for record in page_records:
                if record["url"] in seen_urls:
                    continue
                seen_urls.add(record["url"])

                item = CatalogItem(
                    name=record["name"],
                    url=record["url"],
                    remote_testing=record.get("remote_testing"),
                    adaptive_irt=record.get("adaptive_irt"),
                    test_type_codes=record.get("test_type_codes", []),
                )

                if self.config.fetch_details:
                    logger.info("Fetching detail page: %s", item.url)
                    html = self._fetch(item.url)
                    self._polite_sleep()
                    if html:
                        detail = self.parse_detail_page(html, item.url)
                        item.description = detail["description"]
                        item.job_levels = detail["job_levels"]
                        item.languages = detail["languages"]
                        item.duration_minutes = detail["duration_minutes"]
                        item.downloads = detail["downloads"]
                        # Prefer detail-page test type / remote testing if the
                        # listing page didn't give us anything usable.
                        if not item.test_type_codes and detail["test_type_codes_detail"]:
                            item.test_type_codes = detail["test_type_codes_detail"]
                        if item.remote_testing is None:
                            item.remote_testing = detail["remote_testing_detail"]
                        item.detail_scraped = True
                    else:
                        logger.warning("Detail fetch failed for %s -- keeping listing-only record", item.url)

                item.with_labels()
                items.append(item)

                if self.config.checkpoint_path and len(items) % self.config.checkpoint_every == 0:
                    self.save_json(items, self.config.checkpoint_path)
                    logger.info("Checkpoint saved: %d items so far", len(items))

                if self.config.limit and len(items) >= self.config.limit:
                    logger.info("Reached configured limit of %d items, stopping.", self.config.limit)
                    return items

        return items

    @staticmethod
    def save_json(items: Iterable[CatalogItem], path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [item.model_dump() for item in items]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Saved %d catalog items to %s", len(data), path)
