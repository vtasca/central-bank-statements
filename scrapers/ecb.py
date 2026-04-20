from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class ECBScraper(BaseScraper):
    """European Central Bank scraper.

    ECB document lists are lazily loaded via year-specific include files:
      {section}/{YYYY}/html/index_include.en.html

    We resolve those URLs directly rather than parsing the JavaScript-heavy
    main index pages, which only contain navigation links.
    """

    bank_id = "ecb"
    base_url = "https://www.ecb.europa.eu"
    rate_limit_seconds = 2.0

    # Section → (doc_type, include URL template, path fragment to keep, filename prefix)
    # Path fragment + filename prefix uniquely identify each document type across
    # cross-linked include files that embed related doc types side-by-side.
    _SECTIONS: dict[str, tuple[str, str, str]] = {
        "decision": (
            "https://www.ecb.europa.eu/press/govcdec/mopo"
            "/{year}/html/index_include.en.html",
            "/press/pr/date/",
            "ecb.mp",
        ),
        "statement": (
            "https://www.ecb.europa.eu/press/press_conference"
            "/monetary-policy-statement/{year}/html/index_include.en.html",
            "/press_conference/monetary-policy-statement/",
            "ecb.is",
        ),
        "account": (
            "https://www.ecb.europa.eu/press/accounts"
            "/{year}/html/index_include.en.html",
            "/press/accounts/",
            "ecb.mg",
        ),
    }

    # Decision docs available from 1999; accounts from 2015
    SECTION_START = {
        "decision": 1999,
        "statement": 1999,
        "account": 2015,
    }

    # ------------------------------------------------------------------
    # Index
    # ------------------------------------------------------------------

    def get_document_index(self) -> list[dict]:
        seen: set[str] = set()
        docs: list[dict] = []
        current_year = datetime.now().year

        for doc_type, (tpl, path_frag, fname_prefix) in self._SECTIONS.items():
            start = self.SECTION_START[doc_type]
            for year in range(start, current_year + 1):
                include_url = tpl.format(year=year)
                try:
                    entries = self._parse_include(include_url, doc_type, path_frag, fname_prefix)
                    for e in entries:
                        if e["url"] not in seen:
                            seen.add(e["url"])
                            docs.append(e)
                except Exception:
                    logger.debug("ECB include unavailable: %s", include_url)

        logger.info("ECB index: %d documents found", len(docs))
        return docs

    def _parse_include(
        self, include_url: str, doc_type: str, path_frag: str, fname_prefix: str
    ) -> list[dict]:
        resp = self.fetch(include_url)
        soup = BeautifulSoup(resp.text, "lxml")
        docs: list[dict] = []

        for a in soup.find_all("a", href=True):
            href: str = a["href"]
            # English only — each doc is linked once per language, ~20 times
            if not href.endswith(".en.html"):
                continue
            # Only keep links matching this section's path and filename prefix
            if path_frag not in href:
                continue
            if fname_prefix not in href:
                continue
            if not href.startswith("http"):
                href = self.base_url + ("" if href.startswith("/") else "/") + href

            date = _extract_ecb_date(href)
            if not date:
                continue

            docs.append({"url": href, "doc_type": doc_type, "meeting_date": date})

        # Deduplicate within this include (link text variants may repeat same href)
        seen: set[str] = set()
        unique: list[dict] = []
        for d in docs:
            if d["url"] not in seen:
                seen.add(d["url"])
                unique.append(d)
        return unique

    # ------------------------------------------------------------------
    # Scrape
    # ------------------------------------------------------------------

    def scrape_document(self, url: str, doc_type: str) -> dict:
        resp = self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        title = soup.find("title")
        title_text = title.get_text(" ", strip=True) if title else ""

        # ECB content wrapper classes (varies by era)
        content = (
            soup.find("div", class_=re.compile(
                r"ecb-pressContent|press-content|releaseHeadline|ecb-publicationDetail"
            ))
            or soup.find("main")
            or soup.find("article")
            or soup.body
        )
        text = content.get_text("\n", strip=True) if content else ""

        date = _extract_ecb_date(url) or ""

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


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

# ECB filenames: ecb.mp251218~hash.en.html  or  ecb.is240201~hash.en.html
# 2-4 letter prefix followed by YYMMDD then ~
_ECB_DATE_RE = re.compile(r"ecb\.\w{2,4}(\d{2})(\d{2})(\d{2})~")


def _extract_ecb_date(url: str) -> str | None:
    m = _ECB_DATE_RE.search(url)
    if m:
        return f"20{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # Fallback: bare 8-digit date in path
    m2 = re.search(r"(\d{4})(\d{2})(\d{2})", url)
    if m2:
        return f"{m2.group(1)}-{m2.group(2)}-{m2.group(3)}"
    return None
