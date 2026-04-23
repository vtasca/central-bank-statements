"""Build release_calendar.txt from bank meeting calendars.

For each bank meeting date, writes the T+1 date (meeting date + 1 day).
The Fed calendar is fetched live from the Federal Reserve JSON API;
all other banks are read from schedules/meeting_calendar.json.

Usage:
  python update_release_calendar.py
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent
CALENDAR_JSON = REPO_ROOT / "schedules" / "meeting_calendar.json"
OUTPUT_FILE = REPO_ROOT / "release_calendar.txt"

FED_CALENDAR_URL = "https://www.federalreserve.gov/json/calendar.json"
HEADERS = {
    "User-Agent": (
        "CentralBankResearchScraper/1.0 "
        "(academic/research; github.com/vtasca/central-bank-statements)"
    )
}


def fetch_fed_dates() -> list[str]:
    """Fetch FOMC meeting dates from the Federal Reserve JSON calendar API."""
    try:
        resp = requests.get(FED_CALENDAR_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        import json as _json
        data = _json.loads(resp.content.decode("utf-8-sig"))
        events = data.get("events", [])
        dates: list[str] = []
        for event in events:
            if event.get("title") != "FOMC Meeting":
                continue
            month = event.get("month", "")   # YYYY-MM
            day = event.get("days", "").strip()
            if month and day:
                try:
                    dates.append(f"{month}-{int(day):02d}")
                except ValueError:
                    pass
        return sorted(set(dates))
    except Exception as e:
        print(f"Warning: could not fetch Fed calendar ({e}), using local data only.")
        return []


def load_local_dates() -> dict[str, list[str]]:
    """Read all meeting dates from schedules/meeting_calendar.json."""
    if not CALENDAR_JSON.exists():
        return {}
    with CALENDAR_JSON.open() as f:
        data = json.load(f)
    result: dict[str, list[str]] = {}
    for bank_id, info in data.items():
        if bank_id.startswith("_"):
            continue
        all_dates: list[str] = []
        for key, val in info.items():
            if key.isdigit() and isinstance(val, list):
                all_dates.extend(val)
        result[bank_id] = sorted(all_dates)
    return result


def main() -> None:
    local = load_local_dates()
    fed_live = fetch_fed_dates()

    all_meeting_dates: set[str] = set()

    # All banks from local calendar
    for bank_dates in local.values():
        all_meeting_dates.update(bank_dates)

    # Supplement/override Fed dates with live data
    all_meeting_dates.update(fed_live)

    # Compute T+1 run dates
    run_dates = sorted(
        {str(date.fromisoformat(d) + timedelta(days=1)) for d in all_meeting_dates},
        reverse=True,
    )

    lines = [
        f"# Source: schedules/meeting_calendar.json + {FED_CALENDAR_URL}",
        f"# Updated: {date.today()}",
        *run_dates,
    ]
    OUTPUT_FILE.write_text("\n".join(lines) + "\n")
    print(f"Wrote {len(run_dates)} T+1 run dates to {OUTPUT_FILE.name}")


if __name__ == "__main__":
    main()
