from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class RBAScraper(BaseScraper):
    """Reserve Bank of Australia scraper.

    Decisions:  rba.gov.au/media-releases/{YYYY}/mr-{YY}-{NN}.html
    Index:      rba.gov.au/monetary-policy/int-rate-decisions/
    Minutes:    rba.gov.au/monetary-policy/rba-board-minutes/{YYYY}/
    """

    bank_id = "rba"
    base_url = "https://www.rba.gov.au"
    rate_limit_seconds = 2.0

    DECISION_INDEX = "https://www.rba.gov.au/monetary-policy/int-rate-decisions/"
    MINUTES_INDEX_TPL = "https://www.rba.gov.au/monetary-policy/rba-board-minutes/{year}/"
    START_YEAR = 1990

    def get_document_index(self) -> list[dict]:
        seen: set[str] = set()
        docs: list[dict] = []

        # Decision statements
        try:
            resp = self.fetch(self.DECISION_INDEX)
            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.find_all("a", href=True):
                href: str = a["href"]
                if not href.startswith("http"):
                    href = self.base_url + ("" if href.startswith("/") else "/") + href
                if "/media-releases/" in href and href.endswith(".html"):
                    if href not in seen:
                        seen.add(href)
                        date = _rba_media_release_date(href)
                        docs.append({
                            "url": href,
                            "doc_type": "decision",
                            "meeting_date": date,
                        })
        except Exception:
            logger.warning("RBA decision index unavailable", exc_info=True)

        # Board minutes by year
        current_year = datetime.now().year
        for year in range(self.START_YEAR, current_year + 1):
            url = self.MINUTES_INDEX_TPL.format(year=year)
            try:
                resp = self.fetch(url)
                soup = BeautifulSoup(resp.text, "lxml")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if not href.startswith("http"):
                        href = self.base_url + ("" if href.startswith("/") else "/") + href
                    if "/rba-board-minutes/" in href and href.endswith(".html"):
                        if href not in seen:
                            seen.add(href)
                            date = _rba_minutes_date(href)
                            docs.append({
                                "url": href,
                                "doc_type": "minutes",
                                "meeting_date": date,
                            })
            except Exception:
                logger.debug("RBA minutes index unavailable for %d", year)

        logger.info("RBA index: %d documents found", len(docs))
        return docs

    def scrape_document(self, url: str, doc_type: str) -> dict:
        resp = self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        title = soup.find("h1") or soup.find("title")
        title_text = title.get_text(" ", strip=True) if title else ""

        content = (
            soup.find("div", class_=re.compile(r"content|article|page-content"))
            or soup.find("main")
            or soup.body
        )
        text = content.get_text("\n", strip=True) if content else ""

        # dc.date meta tag (present on media-releases pages)
        meta_date = soup.find("meta", attrs={"name": "dc.date"})
        date = (meta_date["content"] if meta_date else None) or _rba_minutes_date(url) or ""

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


def _rba_media_release_date(url: str) -> str:
    # URL only has year (mr-26-08.html), so return empty and let scrape_document
    # extract the real date from the dc.date meta tag.
    return ""


def _rba_minutes_date(url: str) -> str:
    # 2015+ format: /2015/2015-12-01.html  (ISO date with dashes)
    m_iso = re.search(r"/(\d{4})-(\d{2})-(\d{2})\.html", url)
    if m_iso:
        return f"{m_iso.group(1)}-{m_iso.group(2)}-{m_iso.group(3)}"
    # 2011-2014 format: /2011/06122011.html  (DDMMYYYY)
    m = re.search(r"/(\d{8})\.html", url)
    if m:
        d = m.group(1)
        if d[:2] in ("19", "20"):  # YYYYMMDD
            return f"{d[:4]}-{d[4:6]}-{d[6:]}"
        return f"{d[4:]}-{d[2:4]}-{d[:2]}"  # DDMMYYYY → YYYY-MM-DD
    return ""
