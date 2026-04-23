from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_VALID_DOC_TYPES = {
    "statement", "minutes", "press_conference",
    "account", "decision", "summary_opinions",
}

_REPO_ROOT = Path(__file__).resolve().parent.parent


class BaseScraper(ABC):
    bank_id: str
    base_url: str
    rate_limit_seconds: float = 2.0

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "CentralBankResearchScraper/1.0 "
                "(academic/research; github.com/vtasca/central-bank-statements)"
            )
        })
        self._last_request_time: float = 0.0
        self._csv_cache: pd.DataFrame | None = None

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def get_document_index(self) -> list[dict]:
        """Return [{url, doc_type, meeting_date}, ...] for all known documents."""

    @abstractmethod
    def scrape_document(self, url: str, doc_type: str) -> dict:
        """Fetch one document and return a dict with meeting_date, published_date, doc_type, text."""

    # ------------------------------------------------------------------
    # CSV state
    # ------------------------------------------------------------------

    @property
    def _csv_path(self) -> Path:
        return _REPO_ROOT / f"communications_{self.bank_id}.csv"

    def _load_csv(self) -> pd.DataFrame:
        if self._csv_cache is not None:
            return self._csv_cache
        if self._csv_path.exists():
            df = pd.read_csv(self._csv_path)
        else:
            df = pd.DataFrame(columns=["Date", "Release Date", "Type", "Text"])
        self._csv_cache = df
        return df

    def _most_recent_date(self) -> str | None:
        df = self._load_csv()
        if df.empty:
            return None
        return df["Date"].max()

    def _already_scraped(self, url: str) -> bool:
        # URL dedup is not tracked in the CSV; rely on date-based filtering in scrape_new.
        # This keeps us consistent with the fed repo approach.
        return False

    def _append_to_csv(self, doc: dict) -> None:
        row = {
            "Date": _coerce_date(doc.get("meeting_date", "")),
            "Release Date": _coerce_date(doc.get("published_date", "")),
            "Type": doc.get("doc_type", ""),
            "Text": doc.get("text", ""),
        }
        df = self._load_csv()
        new_row = pd.DataFrame([row])
        df = pd.concat([df, new_row], ignore_index=True)
        df = df.sort_values("Date", ascending=False).drop_duplicates(
            subset=["Date", "Release Date", "Type"]
        ).reset_index(drop=True)
        df.to_csv(self._csv_path, index=False)
        self._csv_cache = df

    # ------------------------------------------------------------------
    # Scraping orchestration
    # ------------------------------------------------------------------

    def scrape_new(self, since_date: str | None = None) -> list[dict]:
        """Fetch every document newer than since_date and append to CSV.

        Pass since_date=None to scrape all history (full backfill).
        """
        index = self.get_document_index()
        results: list[dict] = []

        for entry in index:
            meeting_date = entry.get("meeting_date", "")
            if since_date and meeting_date and meeting_date <= since_date:
                logger.debug("skip (already have up to %s) %s", since_date, entry["url"])
                continue
            try:
                doc = self.scrape_document(entry["url"], entry["doc_type"])
                if not doc.get("meeting_date"):
                    doc["meeting_date"] = meeting_date
                if doc.get("doc_type") not in _VALID_DOC_TYPES:
                    logger.warning("unknown doc_type %r, skipping", doc.get("doc_type"))
                    continue
                self._append_to_csv(doc)
                results.append(doc)
                logger.info(
                    "scraped %-10s %-20s %s",
                    self.bank_id,
                    entry["doc_type"],
                    meeting_date,
                )
            except Exception:
                logger.exception("failed to scrape %s", entry["url"])

        return results

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def fetch(self, url: str, **kwargs) -> requests.Response:
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.rate_limit_seconds:
            time.sleep(self.rate_limit_seconds - elapsed)
        resp = self.session.get(url, timeout=30, **kwargs)
        self._last_request_time = time.monotonic()
        resp.raise_for_status()
        return resp


def _coerce_date(value: str) -> str:
    if not value:
        return value
    # YYYYMMDD → YYYY-MM-DD
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    # YYMMDD → YYYY-MM-DD (assume 2000s)
    if len(value) == 6 and value.isdigit():
        return f"20{value[:2]}-{value[2:4]}-{value[4:]}"
    return value
