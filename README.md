# Central Bank Statements

Automated scraper for primary post-meeting communications from 8 major central banks. Collects policy decision statements, meeting minutes, and press conference transcripts directly from official websites.

## Coverage

| Bank | Meetings/yr | Doc types | History from | Source |
|------|------------|-----------|-------------|--------|
| **Fed** (USA) | 8 | statement, minutes, press_conference | 1994 | federalreserve.gov |
| **ECB** (Eurozone) | 8 | decision, statement, account | 1999 | ecb.europa.eu |
| **BoE** (UK) | 8 | minutes | 2024 | bankofengland.co.uk |
| **BoJ** (Japan) | 8 | statement (PDF), minutes, summary_opinions | 1999 | boj.or.jp |
| **RBA** (Australia) | 8 | decision, minutes | 1990 | rba.gov.au |
| **BoC** (Canada) | 8 | statement | 2010 | bankofcanada.ca |
| **SNB** (Switzerland) | 4 | statement | 2000 | snb.ch |
| **Riksbank** (Sweden) | 6 | statement, minutes | 2010 | riksbank.se |

## Output

Each bank produces a CSV file at the repo root:

```
communications_fed.csv
communications_ecb.csv
communications_boe.csv
communications_boj.csv
communications_rba.csv
communications_boc.csv
communications_snb.csv
communications_riksbank.csv
```

Schema (matches [fed-statement-scraping](https://github.com/vtasca/fed-statement-scraping)):

| Column | Description |
|--------|-------------|
| `Date` | YYYY-MM-DD of the policy meeting |
| `Release Date` | YYYY-MM-DD when the document was published |
| `Type` | `statement`, `minutes`, `press_conference`, `account`, `decision`, `summary_opinions` |
| `Text` | Extracted plain text of the document |

## Repo structure

```
scrapers/                  One module per bank (+ abstract base)
schedules/
  meeting_calendar.json    Known meeting dates for all 8 banks (2024-2026)
scrape.py                  Entry point
update_release_calendar.py Rebuilds release_calendar.txt from meeting schedules
release_calendar.txt       T+1 run dates for all banks (GitHub Actions gate)
communications_*.csv       Scraped data (one file per bank)
.github/workflows/
  main.yml                 Calendar-gated daily scrape at 20:00 UTC
  update_calendar.yml      Quarterly calendar refresh (Jan 1, Jul 1)
```

## Quick start

```bash
uv sync

# Full historical backfill (all banks)
uv run python scrape.py --backfill

# Backfill specific banks
uv run python scrape.py --banks fed ecb --backfill

# Incremental update (runs only if today is in release_calendar.txt)
uv run python scrape.py

# Rebuild release_calendar.txt
uv run python update_release_calendar.py
```

## GitHub Actions

**Scrape** (`main.yml`): runs daily at 20:00 UTC. Checks `release_calendar.txt` and skips if today is not a T+1 release date. Commits updated CSVs if new rows were added. Supports `workflow_dispatch` with optional `banks` and `backfill` inputs.

**Update calendar** (`update_calendar.yml`): runs quarterly (Jan 1, Jul 1). Fetches live Fed calendar data and reads `schedules/meeting_calendar.json` for other banks. Commits updated `release_calendar.txt` if changed. Can also be triggered manually.

Required repository permissions: `contents: write` (already set in the workflow files).

## Implementation notes

- **Rate limiting**: 2s delay between requests (configurable per scraper via `rate_limit_seconds`)
- **Deduplication**: new rows are skipped if `meeting_date <= max(Date)` in the existing CSV
- **PDF extraction**: `pdfplumber` used for BoJ statements and Fed press conference transcripts
- **HTML parsing**: `lxml` via BeautifulSoup4
- **ECB**: Uses year-specific `index_include.en.html` files (lazily loaded by the browser) rather than the JS-heavy index pages
- **BoE**: Statement and minutes are a single combined page; saved as `doc_type: minutes`

## Adding a new bank

1. Create `scrapers/{bank_id}.py` subclassing `BaseScraper`
2. Implement `get_document_index()` → list of `{url, doc_type, meeting_date}`
3. Implement `scrape_document(url, doc_type)` → dict with `meeting_date`, `published_date`, `doc_type`, `text`
4. Register in `scrape.py`'s `SCRAPER_MAP` and `scrapers/__init__.py`
5. Add meeting dates to `schedules/meeting_calendar.json`
