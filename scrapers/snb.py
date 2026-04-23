from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

_CALENDAR_PATH = Path(__file__).resolve().parent.parent / "schedules" / "meeting_calendar.json"


class SNBScraper(BaseScraper):
    """Swiss National Bank scraper.

    Monetary policy assessment press releases are published at:
      snb.ch/en/publications/communication/press-releases-restricted/pre_{YYYYMMDD}

    The public listing page is JS-rendered and useless for indexing.
    Instead we drive from the meeting calendar and try each known date.
    """

    bank_id = "snb"
    base_url = "https://www.snb.ch"
    rate_limit_seconds = 2.0

    def get_document_index(self) -> list[dict]:
        dates = _load_snb_dates()
        docs: list[dict] = []

        for date in dates:
            compact = date.replace("-", "")  # YYYYMMDD
            url = f"{self.base_url}/en/publications/communication/press-releases-restricted/pre_{compact}"
            docs.append({"url": url, "doc_type": "statement", "meeting_date": date})

        logger.info("SNB index: %d candidate dates", len(docs))
        return docs

    def scrape_document(self, url: str, doc_type: str) -> dict:
        resp = self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        title = soup.find("h1") or soup.find("title")
        title_text = title.get_text(" ", strip=True) if title else ""

        content = (
            soup.find("div", class_=re.compile(r"content|article|press-release"))
            or soup.find("main")
            or soup.body
        )
        text = content.get_text("\n", strip=True) if content else ""

        date = _snb_url_date(url)

        return {
            "bank_id": self.bank_id,
            "doc_type": doc_type,
            "meeting_date": date,
            "published_date": date,
            "title": title_text,
            "source_url": url,
            "language": "en",
            "content_type": "html",
            "text": text,
            "_raw_html": resp.text,
        }


def _load_snb_dates() -> list[str]:
    if not _CALENDAR_PATH.exists():
        return []
    with _CALENDAR_PATH.open() as f:
        data = json.load(f)
    snb_data = data.get("snb", {})
    dates: list[str] = []
    for key, val in snb_data.items():
        if key.isdigit() and isinstance(val, list):
            dates.extend(val)
    return sorted(dates)


def _snb_url_date(url: str) -> str:
    m = re.search(r"(\d{8})", url)
    if m:
        d = m.group(1)
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return ""
