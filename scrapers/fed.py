from __future__ import annotations

import io
import logging
import re
from datetime import datetime

import pdfplumber
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class FedScraper(BaseScraper):
    """Federal Reserve (FOMC) scraper.

    Discovers documents via:
      - fomccalendars.htm   – current year + ~2 years back
      - fomchistorical{Y}.htm – all years from HISTORICAL_START
    """

    bank_id = "fed"
    base_url = "https://www.federalreserve.gov"
    rate_limit_seconds = 2.0

    CALENDARS_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
    HISTORICAL_URL = "https://www.federalreserve.gov/monetarypolicy/fomchistorical{year}.htm"
    HISTORICAL_START = 1994  # press releases available from 1994 onward
    HISTORICAL_END = 2020    # fomchistorical pages only exist up through 2020;
                             # 2021+ is covered by fomccalendars.htm

    # URL patterns → doc_type
    _PATTERNS: list[tuple[re.Pattern, str]] = [
        (re.compile(r"/newsevents/pressreleases/monetary(\d{8})a\.htm", re.I), "statement"),
        (re.compile(r"/monetarypolicy/fomcminutes(\d{8})\.htm", re.I), "minutes"),
        (re.compile(r"FOMCpresconf(\d{8})\.pdf", re.I), "press_conference"),
    ]

    # ------------------------------------------------------------------
    # Index
    # ------------------------------------------------------------------

    def get_document_index(self) -> list[dict]:
        seen: set[str] = set()
        docs: list[dict] = []

        def _add(entries: list[dict]) -> None:
            for e in entries:
                if e["url"] not in seen:
                    seen.add(e["url"])
                    docs.append(e)

        _add(self._parse_page(self.CALENDARS_URL))

        for year in range(self.HISTORICAL_START, self.HISTORICAL_END + 1):
            url = self.HISTORICAL_URL.format(year=year)
            try:
                _add(self._parse_page(url))
            except Exception:
                logger.warning("Fed historical page unavailable: %s", url)

        logger.info("Fed index: %d documents found", len(docs))
        return docs

    def _parse_page(self, page_url: str) -> list[dict]:
        resp = self.fetch(page_url)
        soup = BeautifulSoup(resp.text, "lxml")
        docs: list[dict] = []

        for a in soup.find_all("a", href=True):
            href: str = a["href"]
            if not href.startswith("http"):
                href = self.base_url + ("" if href.startswith("/") else "/") + href

            for pattern, doc_type in self._PATTERNS:
                m = pattern.search(href)
                if m:
                    docs.append({
                        "url": href,
                        "doc_type": doc_type,
                        "meeting_date": _compact_to_iso(m.group(1)),
                    })
                    break

        return docs

    # ------------------------------------------------------------------
    # Scrape
    # ------------------------------------------------------------------

    def scrape_document(self, url: str, doc_type: str) -> dict:
        if url.lower().endswith(".pdf"):
            return self._scrape_pdf(url, doc_type)
        return self._scrape_html(url, doc_type)

    def _scrape_html(self, url: str, doc_type: str) -> dict:
        resp = self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        title = (soup.find("title") or soup.find("h1") or soup.find("h2"))
        title_text = title.get_text(" ", strip=True) if title else ""

        # Statements/minutes: body text is in div#article > div[2] (3rd top-level child).
        # This matches the extraction used by fed-statement-scraping and skips
        # the heading div[0] and the sidebar div[1].
        article = soup.find("div", id="article")
        if article:
            body_divs = article.find_all("div", recursive=False)
            content = body_divs[2] if len(body_divs) > 2 else article
        else:
            content = soup.find("div", id="content") or soup.body
        text = content.get_text("\n", strip=True) if content else ""

        date_iso = _extract_8digit_date(url)

        return {
            "bank_id": self.bank_id,
            "doc_type": doc_type,
            "meeting_date": date_iso,
            "published_date": date_iso,
            "title": title_text,
            "source_url": url,
            "language": "en",
            "content_type": "html",
            "text": text,
            "_raw_html": resp.text,
        }

    def _scrape_pdf(self, url: str, doc_type: str) -> dict:
        resp = self.fetch(url)
        date_iso = _extract_8digit_date(url)

        text = ""
        try:
            with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        except Exception:
            logger.warning("pdfplumber failed for %s", url, exc_info=True)

        return {
            "bank_id": self.bank_id,
            "doc_type": doc_type,
            "meeting_date": date_iso,
            "published_date": date_iso,
            "title": f"FOMC Press Conference Transcript {date_iso}",
            "source_url": url,
            "language": "en",
            "content_type": "pdf",
            "text": text,
            "_raw_bytes": resp.content,
        }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _compact_to_iso(s: str) -> str:
    return f"{s[:4]}-{s[4:6]}-{s[6:]}"


def _extract_8digit_date(url: str) -> str:
    m = re.search(r"(\d{8})", url)
    return _compact_to_iso(m.group(1)) if m else ""
