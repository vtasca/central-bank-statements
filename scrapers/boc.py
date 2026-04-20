from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class BoCScaper(BaseScraper):
    """Bank of Canada scraper.

    Decision press releases are listed at:
      bankofcanada.ca/core-functions/monetary-policy/key-interest-rate/

    Individual press releases follow the pattern:
      bankofcanada.ca/YYYY/MM/fad-statement-{month}-{DD}-{YYYY}/
    """

    bank_id = "boc"
    base_url = "https://www.bankofcanada.ca"
    rate_limit_seconds = 2.0

    DECISION_INDEX = (
        "https://www.bankofcanada.ca/core-functions/monetary-policy/key-interest-rate/"
    )

    def get_document_index(self) -> list[dict]:
        seen: set[str] = set()
        docs: list[dict] = []

        try:
            resp = self.fetch(self.DECISION_INDEX)
            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.find_all("a", href=True):
                href: str = a["href"]
                if not href.startswith("http"):
                    href = self.base_url + ("" if href.startswith("/") else "/") + href
                # Match BoC FAD statement URLs: /YYYY/MM/fad-statement-...
                if re.search(r"/\d{4}/\d{2}/fad-statement", href) and href not in seen:
                    seen.add(href)
                    date = _boc_url_to_date(href)
                    docs.append({"url": href, "doc_type": "statement", "meeting_date": date})
        except Exception:
            logger.warning("BoC decision index unavailable", exc_info=True)

        logger.info("BoC index: %d documents found", len(docs))
        return docs

    def scrape_document(self, url: str, doc_type: str) -> dict:
        resp = self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        title = soup.find("h1") or soup.find("title")
        title_text = title.get_text(" ", strip=True) if title else ""

        content = (
            soup.find("div", class_=re.compile(r"page-content|entry-content|post-content"))
            or soup.find("main")
            or soup.body
        )
        text = content.get_text("\n", strip=True) if content else ""

        date = _boc_url_to_date(url)

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


_MONTH_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}


def _boc_url_to_date(url: str) -> str:
    # /2024/01/fad-statement-january-24-2024/
    m = re.search(r"/(\d{4})/\d{2}/fad-statement-([a-z]+)-(\d{1,2})-(\d{4})", url)
    if m:
        year = m.group(1)
        month = _MONTH_MAP.get(m.group(2), "01")
        day = m.group(3).zfill(2)
        return f"{year}-{month}-{day}"
    # Fallback: pull YYYY/MM from path
    m2 = re.search(r"/(\d{4})/(\d{2})/", url)
    if m2:
        return f"{m2.group(1)}-{m2.group(2)}-01"
    return ""
