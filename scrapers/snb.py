from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class SNBScraper(BaseScraper):
    """Swiss National Bank scraper.

    Press releases (quarterly monetary policy assessments):
      snb.ch/en/publications/communication/press-releases/
    """

    bank_id = "snb"
    base_url = "https://www.snb.ch"
    rate_limit_seconds = 2.0

    PRESS_INDEX = "https://www.snb.ch/en/publications/communication/press-releases/"

    def get_document_index(self) -> list[dict]:
        seen: set[str] = set()
        docs: list[dict] = []

        try:
            resp = self.fetch(self.PRESS_INDEX)
            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.find_all("a", href=True):
                href: str = a["href"]
                if not href.startswith("http"):
                    href = self.base_url + ("" if href.startswith("/") else "/") + href
                # SNB monetary policy press releases contain "snb-news" or specific paths
                # Filter to monetary policy assessment press releases
                link_text = a.get_text(strip=True).lower()
                is_mpa = any(kw in link_text for kw in (
                    "monetary policy assessment",
                    "quarterly assessment",
                    "interest rate",
                ))
                if not is_mpa:
                    continue
                if href not in seen:
                    seen.add(href)
                    date = _snb_url_date(href)
                    docs.append({"url": href, "doc_type": "statement", "meeting_date": date})
        except Exception:
            logger.warning("SNB press index unavailable", exc_info=True)

        logger.info("SNB index: %d documents found", len(docs))
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


def _snb_url_date(url: str) -> str:
    m = re.search(r"(\d{8})", url)
    if m:
        d = m.group(1)
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    m2 = re.search(r"(\d{4})/(\d{2})/", url)
    if m2:
        return f"{m2.group(1)}-{m2.group(2)}-01"
    return ""
