from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Month names used in BoE URL slugs
_MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

# Known BoE MPC meeting dates (YYYY-MM-DD, last day of meeting)
# Source: https://www.bankofengland.co.uk/monetary-policy/the-monetary-policy-committee
_KNOWN_MEETINGS: list[tuple[int, int, int]] = [
    # 2024
    (2024, 2, 1), (2024, 3, 21), (2024, 5, 9), (2024, 6, 20),
    (2024, 8, 1), (2024, 9, 19), (2024, 11, 7), (2024, 12, 19),
    # 2025
    (2025, 2, 6), (2025, 3, 20), (2025, 5, 8), (2025, 6, 19),
    (2025, 8, 7), (2025, 9, 18), (2025, 11, 6), (2025, 12, 18),
    # 2026
    (2026, 2, 5), (2026, 3, 19), (2026, 5, 7), (2026, 6, 18),
    (2026, 8, 6), (2026, 9, 17), (2026, 11, 5), (2026, 12, 17),
]


class BoEScraper(BaseScraper):
    """Bank of England scraper.

    BoE publishes statement and minutes as a single combined page per meeting:
      bankofengland.co.uk/monetary-policy-summary-and-minutes/{YYYY}/{month}-{YYYY}

    The index page lists all published decisions.
    """

    bank_id = "boe"
    base_url = "https://www.bankofengland.co.uk"
    rate_limit_seconds = 2.0

    INDEX_URL = (
        "https://www.bankofengland.co.uk/monetary-policy-summary-and-minutes/"
        "monetary-policy-summary-and-minutes"
    )

    def get_document_index(self) -> list[dict]:
        docs: list[dict] = []
        seen: set[str] = set()

        # Primary: scrape the index page for all listed links
        try:
            resp = self.fetch(self.INDEX_URL)
            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.find_all("a", href=True):
                href: str = a["href"]
                if not href.startswith("http"):
                    href = self.base_url + ("" if href.startswith("/") else "/") + href
                if "/monetary-policy-summary-and-minutes/" not in href:
                    continue
                # Must match /{YYYY}/{month}-{YYYY} pattern
                if not re.search(r"/\d{4}/[a-z]+-\d{4}$", href):
                    continue
                if href not in seen:
                    seen.add(href)
                    date = _boe_url_to_date(href)
                    if date:
                        docs.append({"url": href, "doc_type": "minutes", "meeting_date": date})
        except Exception:
            logger.warning("BoE index page unavailable", exc_info=True)

        # Supplement with known meetings not yet on the index page
        for year, month, day in _KNOWN_MEETINGS:
            month_name = _MONTHS[month - 1]
            url = (
                f"{self.base_url}/monetary-policy-summary-and-minutes"
                f"/{year}/{month_name}-{year}"
            )
            if url not in seen:
                seen.add(url)
                docs.append({
                    "url": url,
                    "doc_type": "minutes",
                    "meeting_date": f"{year:04d}-{month:02d}-{day:02d}",
                })

        logger.info("BoE index: %d documents found", len(docs))
        return docs

    def scrape_document(self, url: str, doc_type: str) -> dict:
        resp = self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        title = soup.find("h1") or soup.find("title")
        title_text = title.get_text(" ", strip=True) if title else ""

        content = (
            soup.find("div", class_=re.compile(r"page-content|content-wrapper|article"))
            or soup.find("main")
            or soup.find("article")
            or soup.body
        )
        text = content.get_text("\n", strip=True) if content else ""

        date = _boe_url_to_date(url) or ""

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


def _boe_url_to_date(url: str) -> str | None:
    """Extract meeting date from a BoE URL like /2024/march-2024."""
    m = re.search(r"/(\d{4})/([a-z]+)-\d{4}$", url)
    if not m:
        return None
    year = int(m.group(1))
    month_name = m.group(2)
    try:
        month = _MONTHS.index(month_name) + 1
    except ValueError:
        return None
    # We don't know the exact day from the URL; use day=1 as placeholder —
    # the scraper will try to extract it from the page content if needed.
    return f"{year:04d}-{month:02d}-01"
