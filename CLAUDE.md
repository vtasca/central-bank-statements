# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                                          # install dependencies

uv run python scrape.py                          # incremental update (only runs on release days)
uv run python scrape.py --backfill               # full historical scrape, all banks
uv run python scrape.py --banks fed ecb          # specific banks, incremental
uv run python scrape.py --banks fed --backfill   # specific banks, full history

uv run python update_release_calendar.py         # rebuild release_calendar.txt
```

There are no tests or linting configured.

## Architecture

**Entry point**: `scrape.py` — parses CLI args, checks `release_calendar.txt` to gate incremental runs, then instantiates the appropriate scraper class(es) from `SCRAPER_MAP` and calls `scraper.scrape_new(since_date)`.

**Base class** (`scrapers/base.py`): `BaseScraper` handles the shared concerns:
- `get_document_index()` → list of `{url, doc_type, meeting_date}` (implemented per bank)
- `scrape_document(url, doc_type)` → dict (implemented per bank)
- `scrape_new(since_date)` — orchestrates index + scrape, skips docs where `meeting_date <= since_date`, appends to CSV
- `_append_to_csv()` — deduplicates on `(Date, Release Date, Type)`, sorts descending by date
- `fetch()` — rate-limited HTTP with a shared `requests.Session`

**Per-bank scrapers** (`scrapers/{bank_id}.py`): one class per bank, each sets `bank_id`, `base_url`, and `rate_limit_seconds`. Each implements the two abstract methods.

**Output**: one CSV per bank at repo root — `communications_{bank_id}.csv` — with columns `Date`, `Release Date`, `Type`, `Text`.

**Release calendar gate**: `release_calendar.txt` contains T+1 dates (day after each meeting). The daily GitHub Actions workflow skips the scrape if today isn't in that file. `update_release_calendar.py` rebuilds it by fetching live Fed dates from the Federal Reserve JSON API and reading `schedules/meeting_calendar.json` for all other banks.

## Notable implementation details

- **ECB**: index pages are JavaScript-rendered; instead, year-specific `index_include.en.html` files are fetched directly per section (`decision`, `statement`, `account`). URL patterns differ across eras (pre-2017, 2017-18, 2019+).
- **Fed**: discovers docs from `fomccalendars.htm` (recent years) and `fomchistorical{year}.htm` (1994–2020). Press conference transcripts are PDFs, extracted with `pdfplumber`.
- **BoJ**: statements are also PDFs; `pdfplumber` used there too.
- **BoE**: statement and minutes are a single combined page; always saved as `doc_type: minutes`.
- HTML parsed with `BeautifulSoup` + `lxml` backend.

## Adding a new bank

1. Create `scrapers/{bank_id}.py` subclassing `BaseScraper`
2. Implement `get_document_index()` → list of `{url, doc_type, meeting_date}`
3. Implement `scrape_document(url, doc_type)` → dict with `meeting_date`, `published_date`, `doc_type`, `text`
4. Register in `scrape.py`'s `SCRAPER_MAP` and `scrapers/__init__.py`
5. Add meeting dates to `schedules/meeting_calendar.json`
