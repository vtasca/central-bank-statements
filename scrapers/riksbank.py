from __future__ import annotations

import io
import logging
import re

import pdfplumber
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class RiksbankScraper(BaseScraper):
    """Riksbank (Sweden) scraper.

    Minutes (PDF):    riksbank.se/.../minutes-of-the-executive-boards-monetary-policy-meetings/
    Statements (PDF): riksbank.se/.../monetary-policy-decision-documents/

    Both index pages list PDF links with a "DD/MM/YYYY" prefix in the link text.
    """

    bank_id = "riksbank"
    base_url = "https://www.riksbank.se"
    rate_limit_seconds = 2.0

    MINUTES_INDEX = (
        "https://www.riksbank.se/en-gb/monetary-policy/monetary-policy-report"
        "/minutes-of-the-executive-boards-monetary-policy-meetings/"
    )
    DECISIONS_INDEX = (
        "https://www.riksbank.se/en-gb/monetary-policy/monetary-policy-report"
        "/monetary-policy-decision-documents/"
    )

    def get_document_index(self) -> list[dict]:
        seen: set[str] = set()
        docs: list[dict] = []

        for index_url, doc_type in (
            (self.MINUTES_INDEX, "minutes"),
            (self.DECISIONS_INDEX, "statement"),
        ):
            try:
                resp = self.fetch(index_url)
                soup = BeautifulSoup(resp.text, "lxml")
                for a in soup.find_all("a", href=True):
                    href: str = a["href"]
                    if not href.endswith(".pdf"):
                        continue
                    if not href.startswith("http"):
                        href = self.base_url + href
                    if href in seen:
                        continue
                    seen.add(href)
                    date = _riksbank_link_date(a.get_text(strip=True))
                    docs.append({"url": href, "doc_type": doc_type, "meeting_date": date})
            except Exception:
                logger.warning("Riksbank index unavailable: %s", index_url, exc_info=True)

        logger.info("Riksbank index: %d documents found", len(docs))
        return docs

    def scrape_document(self, url: str, doc_type: str) -> dict:
        resp = self.fetch(url)
        date = _riksbank_url_date(url)

        text = ""
        try:
            with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        except Exception:
            logger.warning("pdfplumber failed for %s", url, exc_info=True)

        return {
            "bank_id": self.bank_id,
            "doc_type": doc_type,
            "meeting_date": date,
            "published_date": date,
            "title": "",
            "source_url": url,
            "language": "en",
            "content_type": "pdf",
            "text": text,
            "_raw_bytes": resp.content,
        }


def _riksbank_link_date(link_text: str) -> str:
    """Extract date from link text prefix 'DD/MM/YYYY...'."""
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", link_text)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return ""


def _riksbank_url_date(url: str) -> str:
    """Fallback: extract any YYYY-style date from the PDF path."""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m2 = re.search(r"(\d{8})", url)
    if m2:
        d = m2.group(1)
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return ""
