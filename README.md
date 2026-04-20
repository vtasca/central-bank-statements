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

Run `python -m pipeline.run` to see live document counts in the manifest summary.

## Document schema

Every scraped document is saved as a JSON sidecar alongside the raw HTML or PDF:

```json
{
  "bank_id": "ecb",
  "doc_type": "statement",
  "meeting_date": "2025-12-18",
  "published_date": "2025-12-18",
  "title": "Monetary policy decisions",
  "source_url": "https://...",
  "scraped_at": "2026-04-20T20:00:00+00:00",
  "language": "en",
  "content_type": "html",
  "text": "..."
}
```

Valid `doc_type` values: `statement`, `minutes`, `press_conference`, `account`, `decision`, `summary_opinions`.

## Repo structure

```
scrapers/          One module per bank (+ abstract base)
pipeline/
  run.py           Entry point — scrape all or specific banks
  normalize.py     Enforce unified schema
  manifest.py      CSV index of every scraped document
data/
  manifest.csv     Master index: bank, type, date, URL, filepath
  fed/statements/  {YYYYMMDD}.json + {YYYYMMDD}.html per doc
  ecb/decisions/
  ...
schedules/
  meeting_calendar.json   Known meeting dates for all 8 banks (2024-2026)
.github/workflows/
  scheduled.yml    Daily scrape at 20:00 UTC + manual dispatch
  backfill.yml     Full historical backfill (manual trigger)
```

## Quick start

```bash
# Install dependencies (uv)
uv sync

# Or with pip
pip install -r requirements.txt

# Scrape all banks, incremental (skip already-scraped)
python -m pipeline.run

# Scrape specific banks
python -m pipeline.run --banks fed ecb

# Scrape everything since a date
python -m pipeline.run --since 2025-01-01

# Full historical backfill (all banks, all time)
python -m pipeline.run --backfill

# Verbose output
python -m pipeline.run --banks fed --verbose
```

## GitHub Actions

**Scheduled scrape** (`scheduled.yml`): runs daily at 20:00 UTC, commits any new documents, supports `workflow_dispatch` with optional `banks` and `since` inputs.

**Backfill** (`backfill.yml`): manual trigger only, runs with `--backfill` flag, 6-hour timeout, optional `banks` input. Trigger this once to populate the archive.

Required repository permissions: `contents: write` (already set in the workflow files).

## Manifest

`data/manifest.csv` tracks every scraped document:

| Column | Description |
|--------|-------------|
| `bank_id` | `fed`, `ecb`, `boe`, etc. |
| `doc_type` | `statement`, `minutes`, etc. |
| `meeting_date` | YYYY-MM-DD of the policy meeting |
| `published_date` | YYYY-MM-DD when the document was published |
| `source_url` | Original URL |
| `scraped_at` | ISO timestamp of when it was scraped |
| `filepath` | Relative path to the JSON sidecar |

## Implementation notes

- **Rate limiting**: 2s delay between requests (configurable per scraper via `rate_limit_seconds`)
- **Deduplication**: manifest tracks URLs; `scrape_new()` skips anything already present
- **PDF extraction**: `pdfplumber` used for BoJ statements and Fed press conference transcripts
- **HTML parsing**: `lxml` via BeautifulSoup4
- **ECB**: Uses year-specific `index_include.en.html` files (lazily loaded by the browser) rather than the JS-heavy index pages
- **BoE**: Statement and minutes are a single combined page; saved as `doc_type: minutes`

## Adding a new bank

1. Create `scrapers/{bank_id}.py` subclassing `BaseScraper`
2. Implement `get_document_index()` → list of `{url, doc_type, meeting_date}`
3. Implement `scrape_document(url, doc_type)` → normalized dict
4. Register in `pipeline/run.py`'s `SCRAPER_MAP` and `scrapers/__init__.py`
5. Add meeting dates to `schedules/meeting_calendar.json`
6. Create `data/{bank_id}/` subdirectories
