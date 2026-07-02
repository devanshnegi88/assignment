"""
CLI entrypoint for scraping the SHL Individual Test Solutions catalog.

Run it interactively:

    python -m app.catalog.cli

    It will prompt:  Enter the SHL product catalog URL:
    Paste: https://www.shl.com/products/product-catalog/

Or non-interactively:

    python -m app.catalog.cli --url "https://www.shl.com/products/product-catalog/" \
        --output data/catalog.json

Useful flags:
    --limit N          Only scrape the first N items (fast smoke test)
    --skip-details      Only scrape the listing table (name/url/test_type),
                         skip visiting each detail page (much faster, less data)
    --delay 1.5          Seconds to wait between requests (be polite to shl.com)
    --max-pages 60       Safety cap on number of listing pages to fetch
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from urllib.parse import urlparse

from app.catalog.scraper import SHLCatalogScraper, ScrapeConfig

DEFAULT_OUTPUT = "data/catalog.json"


def _looks_like_shl_catalog_url(url: str) -> bool:
    parsed = urlparse(url)
    return bool(parsed.scheme) and "shl.com" in parsed.netloc


def prompt_for_url() -> str:
    while True:
        url = input("Enter the SHL product catalog URL: ").strip()
        if not url:
            print("A URL is required. Example: https://www.shl.com/products/product-catalog/")
            continue
        if not _looks_like_shl_catalog_url(url):
            confirm = input(
                f"'{url}' doesn't look like a shl.com URL. Use it anyway? [y/N]: "
            ).strip().lower()
            if confirm != "y":
                continue
        return url


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape the SHL Individual Test Solutions catalog.")
    parser.add_argument("--url", help="SHL product catalog URL. If omitted, you'll be prompted for it.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help=f"Output JSON path (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between requests (default: 1.0)")
    parser.add_argument("--max-pages", type=int, default=60, help="Safety cap on listing pages (default: 60)")
    parser.add_argument("--limit", type=int, default=None, help="Cap total items scraped (for quick tests)")
    parser.add_argument("--skip-details", action="store_true", help="Skip per-item detail pages")
    parser.add_argument("--verbose", action="store_true", help="Verbose (DEBUG) logging")
    return parser


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    url = args.url or prompt_for_url()

    config = ScrapeConfig(
        base_url=url,
        delay_seconds=args.delay,
        max_pages=args.max_pages,
        fetch_details=not args.skip_details,
        limit=args.limit,
        checkpoint_path=Path(args.output).with_suffix(".partial.json"),
    )

    scraper = SHLCatalogScraper(config)
    print(f"Scraping Individual Test Solutions from: {url}")
    if config.fetch_details:
        print("This visits each assessment's detail page too, so it will take a while "
              "(one request per item, with a polite delay). Use --skip-details for a "
              "quick listing-only pass, or --limit N to test on a handful first.")

    items = scraper.scrape_all()

    if not items:
        print("No items were scraped. Check the URL and your network connection, "
              "or re-run with --verbose to see what happened.", file=sys.stderr)
        return 1

    scraper.save_json(items, args.output)
    print(f"Done. Scraped {len(items)} individual test solutions -> {args.output}")

    missing_desc = sum(1 for i in items if not i.description)
    if missing_desc and config.fetch_details:
        print(f"Note: {missing_desc}/{len(items)} items are missing a description "
              f"(detail page fetch may have failed or the page layout differs from "
              f"what the parser expects -- rerun with --verbose to investigate).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
