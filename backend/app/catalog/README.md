# SHL Catalog Scraper

Scrapes the **Individual Test Solutions** table from the SHL product catalog
(`https://www.shl.com/products/product-catalog/`) into a normalized JSON file
that the rest of the project (retrieval, RAG, `/chat`) builds on.

Pre-packaged Job Solutions are explicitly excluded, per the assignment.

## Why you run this locally, not inside this chat

This project was built inside a sandboxed dev environment whose network
egress only allows a fixed set of package-registry domains (pypi, npm,
github, etc.) -- `shl.com` isn't on that list, so the live scrape can't be
executed from in here. The parsing logic itself **is** tested (see
`tests/test_scraper.py`, run against fixtures built from the real page
markup), so you're getting verified code, not a guess -- it just needs to
make its HTTP requests from your machine or your deployment host, where
normal internet access exists.

## Setup

```bash
cd backend
pip install -r requirements.txt
```

## Run it

Interactively (it will prompt you for the link):

```bash
python -m app.catalog.cli
# Enter the SHL product catalog URL: https://www.shl.com/products/product-catalog/
```

Or pass the link directly:

```bash
python -m app.catalog.cli --url "https://www.shl.com/products/product-catalog/" \
  --output ../data/catalog.json
```

Useful flags while iterating:

```bash
# Quick smoke test: only scrape 5 items, skip detail pages (fast)
python -m app.catalog.cli --url "https://www.shl.com/products/product-catalog/" \
  --limit 5 --skip-details

# Full run, polite 1.5s delay between requests, verbose logging
python -m app.catalog.cli --url "https://www.shl.com/products/product-catalog/" \
  --delay 1.5 --verbose
```

A full run fetches ~32 listing pages plus one detail page per assessment
(SHL's catalog currently has on the order of a few hundred Individual Test
Solutions), so with the default 1s politeness delay it'll take several
minutes. Progress is checkpointed to `<output>.partial.json` every 25 items
in case it gets interrupted.

## Output shape

Each item in the output JSON matches `app/catalog/schema.py::CatalogItem`:

```json
{
  "name": ".NET Framework 4.5",
  "url": "https://www.shl.com/products/product-catalog/view/net-framework-4-5/",
  "solution_type": "individual_test_solution",
  "test_type_codes": ["K"],
  "test_type_labels": ["Knowledge & Skills"],
  "remote_testing": true,
  "adaptive_irt": false,
  "description": "The .NET Framework 4.5 test measures knowledge of .NET environment...",
  "job_levels": ["Professional Individual Contributor", "Mid-Professional"],
  "languages": ["English (USA)"],
  "duration_minutes": 30,
  "downloads": ["https://service.shl.com/docs/Fact_Sheet-dotnet_framework_4.5.pdf"],
  "detail_scraped": true
}
```

## If SHL's page markup has changed since this was written

Two spots are the most likely to need adjustment, since they rely on an
assumption about the current markup rather than a text label:

1. **`_cell_has_icon` / `_find_individual_test_solutions_table`** in
   `scraper.py` -- the Remote Testing / Adaptive-IRT columns render as an
   icon with no alt text, not a "Yes"/"No" string. The scraper currently
   assumes "an `<svg>` or `<img>` is present in the cell" means true. If SHL
   switches to a different icon pattern (e.g. a CSS class with no child
   tag), run with `--verbose` and inspect a saved page to update the check.
2. **`_text_after_label`** -- pulls "Description", "Job levels",
   "Languages" etc. by matching the heading text and reading the next
   sibling. If SHL restructures the detail page layout, this is the
   function to adjust.

Run `pytest tests/test_scraper.py -v` after any changes -- it exercises both
functions against fixtures built from the real page structure.

## Verifying against the real site (do this first)

Before a full run, do a `--limit 3` pass and open a couple of the resulting
detail URLs in your browser to confirm `description`, `job_levels`, and
`duration_minutes` came out right. This project intentionally never
fabricates catalog URLs or data, so it's worth confirming the parser is
reading the live page correctly before trusting a full run.
