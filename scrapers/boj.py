from __future__ import annotations

import io
import logging
import re
from datetime import datetime

import pdfplumber
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class BoJScraper(BaseScraper):
    """Bank of Japan scraper.

    Statements are published as PDFs:
      boj.or.jp/en/mopo/mpmdeci/mpr_{YYYY}/index.htm

    Minutes and Summary of Opinions are HTML:
      boj.or.jp/en/mopo/mpmsche_minu/minu_{YYYY}/
      boj.or.jp/en/mopo/mpmsche_minu/opinion_{YYYY}/
    """

    bank_id = "boj"
    base_url = "https://www.boj.or.jp"
    rate_limit_seconds = 2.0

    START_YEAR = 1999  # English materials available from 1999

    STATEMENT_INDEX_TPL = "https://www.boj.or.jp/en/mopo/mpmdeci/mpr_{year}/index.htm"
    MINUTES_INDEX_TPL = "https://www.boj.or.jp/en/mopo/mpmsche_minu/minu_{year}/"
    OPINIONS_INDEX_TPL = "https://www.boj.or.jp/en/mopo/mpmsche_minu/opinion_{year}/"

    def get_document_index(self) -> list[dict]:
        seen: set[str] = set()
        docs: list[dict] = []
        current_year = datetime.now().year

        for year in range(self.START_YEAR, current_year + 1):
            for tpl, doc_type in (
                (self.STATEMENT_INDEX_TPL, "statement"),
                (self.MINUTES_INDEX_TPL, "minutes"),
                (self.OPINIONS_INDEX_TPL, "summary_opinions"),
            ):
                url = tpl.format(year=year)
                try:
                    entries = self._parse_boj_index(url, doc_type)
                    for e in entries:
                        if e["url"] not in seen:
                            seen.add(e["url"])
                            docs.append(e)
                except Exception:
                    logger.debug("BoJ index unavailable: %s", url)

        logger.info("BoJ index: %d documents found", len(docs))
        return docs

    def _parse_boj_index(self, index_url: str, doc_type: str) -> list[dict]:
        resp = self.fetch(index_url)
        soup = BeautifulSoup(resp.text, "lxml")
        docs: list[dict] = []

        for a in soup.find_all("a", href=True):
            href: str = a["href"]
            if not href.startswith("http"):
                base = index_url.rsplit("/", 1)[0]
                href = base + "/" + href.lstrip("/")

            # BoJ PDF statements: mpr{YYYYMMDD}.pdf  or  k{YYYYMMDD}.pdf
            # BoJ HTML minutes:   minu{YYYYMMDD}.htm
            # BoJ HTML opinions:  opinion{YYYYMMDD}.htm
            m = re.search(r"(\d{8})\.(pdf|htm)", href, re.I)
            if not m:
                continue

            date = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}"
            docs.append({"url": href, "doc_type": doc_type, "meeting_date": date})

        return docs

    def scrape_document(self, url: str, doc_type: str) -> dict:
        if url.lower().endswith(".pdf"):
            return self._scrape_pdf(url, doc_type)
        return self._scrape_html(url, doc_type)

    def _scrape_html(self, url: str, doc_type: str) -> dict:
        resp = self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        title = soup.find("title") or soup.find("h1")
        title_text = title.get_text(" ", strip=True) if title else ""

        content = soup.find("div", id=re.compile(r"main|content")) or soup.body
        text = content.get_text("\n", strip=True) if content else ""

        m = re.search(r"(\d{8})", url)
        date = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}" if m else ""

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

    def _scrape_pdf(self, url: str, doc_type: str) -> dict:
        resp = self.fetch(url)

        m = re.search(r"(\d{8})", url)
        date = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}" if m else ""

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
            "title": f"BoJ Statement {date}",
            "source_url": url,
            "language": "en",
            "content_type": "pdf",
            "text": text,
            "_raw_bytes": resp.content,
        }
