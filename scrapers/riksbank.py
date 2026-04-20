from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class RiksbankScraper(BaseScraper):
    """Riksbank (Sweden) scraper.

    Decisions and minutes are listed at:
      riksbank.se/en-gb/monetary-policy/monetary-policy-decisions/
    """

    bank_id = "riksbank"
    base_url = "https://www.riksbank.se"
    rate_limit_seconds = 2.0

    DECISIONS_INDEX = (
        "https://www.riksbank.se/en-gb/monetary-policy/monetary-policy-decisions/"
    )

    def get_document_index(self) -> list[dict]:
        seen: set[str] = set()
        docs: list[dict] = []

        try:
            resp = self.fetch(self.DECISIONS_INDEX)
            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.find_all("a", href=True):
                href: str = a["href"]
                if not href.startswith("http"):
                    href = self.base_url + ("" if href.startswith("/") else "/") + href
                if "/monetary-policy/monetary-policy-decisions/" not in href:
                    continue
                # Skip the index page itself
                if href.rstrip("/") == self.DECISIONS_INDEX.rstrip("/"):
                    continue
                if href not in seen:
                    seen.add(href)
                    date = _riksbank_url_date(href)
                    doc_type = "minutes" if "minutes" in href.lower() else "statement"
                    docs.append({"url": href, "doc_type": doc_type, "meeting_date": date})
        except Exception:
            logger.warning("Riksbank decisions index unavailable", exc_info=True)

        logger.info("Riksbank index: %d documents found", len(docs))
        return docs

    def scrape_document(self, url: str, doc_type: str) -> dict:
        resp = self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        title = soup.find("h1") or soup.find("title")
        title_text = title.get_text(" ", strip=True) if title else ""

        content = (
            soup.find("div", class_=re.compile(r"page-content|article-content|content"))
            or soup.find("main")
            or soup.find("article")
            or soup.body
        )
        text = content.get_text("\n", strip=True) if content else ""

        date = _riksbank_url_date(url)

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


def _riksbank_url_date(url: str) -> str:
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m2 = re.search(r"(\d{8})", url)
    if m2:
        d = m2.group(1)
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return ""
