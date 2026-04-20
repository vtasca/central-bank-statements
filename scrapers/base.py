from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    bank_id: str
    base_url: str
    rate_limit_seconds: float = 2.0

    def __init__(self, data_dir: Path, manifest_path: Path) -> None:
        self.data_dir = data_dir / self.bank_id
        self.manifest_path = manifest_path
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "CentralBankResearchScraper/1.0 "
                "(academic/research; github.com/vtasca/central-bank-statements)"
            )
        })
        self._last_request_time: float = 0.0

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def get_document_index(self) -> list[dict]:
        """Return [{url, doc_type, meeting_date}, ...] for all known documents."""

    @abstractmethod
    def scrape_document(self, url: str, doc_type: str) -> dict:
        """Fetch one document and return a normalized dict ready for saving."""

    # ------------------------------------------------------------------
    # Concrete helpers
    # ------------------------------------------------------------------

    def scrape_new(self, since_date: str | None = None) -> list[dict]:
        """Fetch every document not already present in the manifest."""
        from pipeline.manifest import Manifest

        manifest = Manifest(self.manifest_path)
        index = self.get_document_index()
        results: list[dict] = []

        for entry in index:
            url = entry["url"]
            if manifest.already_scraped(url):
                logger.debug("skip (already scraped) %s", url)
                continue
            if since_date and entry.get("meeting_date", "") < since_date:
                continue
            try:
                doc = self.scrape_document(url, entry["doc_type"])
                # Index-level meeting_date wins when scraper can't detect it
                if not doc.get("meeting_date"):
                    doc["meeting_date"] = entry.get("meeting_date", "")
                filepath = self._save_document(doc)
                manifest.add(doc, filepath)
                results.append(doc)
                logger.info(
                    "scraped %-10s %-20s %s",
                    self.bank_id,
                    entry["doc_type"],
                    entry.get("meeting_date", ""),
                )
            except Exception:
                logger.exception("failed to scrape %s", url)

        return results

    def already_scraped(self, url: str) -> bool:
        from pipeline.manifest import Manifest

        return Manifest(self.manifest_path).already_scraped(url)

    def fetch(self, url: str, **kwargs) -> requests.Response:
        """Rate-limited GET request."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.rate_limit_seconds:
            time.sleep(self.rate_limit_seconds - elapsed)
        resp = self.session.get(url, timeout=30, **kwargs)
        self._last_request_time = time.monotonic()
        resp.raise_for_status()
        return resp

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_document(self, doc: dict) -> Path:
        """Write raw content + JSON sidecar; return path relative to repo root."""
        from pipeline.normalize import normalize

        doc = normalize(doc)

        doc_dir = self.data_dir / _subdir(doc["doc_type"])
        doc_dir.mkdir(parents=True, exist_ok=True)

        slug = doc["meeting_date"].replace("-", "")

        if doc["content_type"] == "pdf":
            raw_path = doc_dir / f"{slug}.pdf"
            raw_bytes: bytes | None = doc.pop("_raw_bytes", None)
            if raw_bytes:
                raw_path.write_bytes(raw_bytes)
        else:
            raw_path = doc_dir / f"{slug}.html"
            raw_html: str | None = doc.pop("_raw_html", None)
            if raw_html:
                raw_path.write_text(raw_html, encoding="utf-8")

        # Strip any remaining private keys before writing the sidecar
        clean = {k: v for k, v in doc.items() if not k.startswith("_")}

        sidecar_path = doc_dir / f"{slug}.json"
        sidecar_path.write_text(
            json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Path relative to repo root (data_dir is <repo>/data/<bank_id>)
        repo_root = self.data_dir.parent.parent
        return sidecar_path.relative_to(repo_root)


def _subdir(doc_type: str) -> str:
    return {
        "statement": "statements",
        "minutes": "minutes",
        "press_conference": "press_conferences",
        "account": "accounts",
        "decision": "decisions",
        "summary_opinions": "summary_opinions",
    }.get(doc_type, doc_type)
