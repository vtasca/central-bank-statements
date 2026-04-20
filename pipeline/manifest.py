from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

COLUMNS = [
    "bank_id",
    "doc_type",
    "meeting_date",
    "published_date",
    "source_url",
    "scraped_at",
    "filepath",
]


class Manifest:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._urls: set[str] | None = None  # lazy-loaded cache

    # ------------------------------------------------------------------

    def already_scraped(self, url: str) -> bool:
        if self._urls is None:
            self._urls = self._load_urls()
        return url in self._urls

    def add(self, doc: dict, filepath: Path) -> None:
        is_new_file = not self.path.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
            if is_new_file:
                writer.writeheader()
            writer.writerow({
                "bank_id": doc.get("bank_id", ""),
                "doc_type": doc.get("doc_type", ""),
                "meeting_date": doc.get("meeting_date", ""),
                "published_date": doc.get("published_date", ""),
                "source_url": doc.get("source_url", ""),
                "scraped_at": doc.get("scraped_at", datetime.now(timezone.utc).isoformat()),
                "filepath": str(filepath),
            })
        if self._urls is not None:
            self._urls.add(doc.get("source_url", ""))

    def summary(self) -> dict[str, dict[str, int]]:
        """Return {bank_id: {doc_type: count}} tallied from the manifest."""
        if not self.path.exists():
            return {}
        counts: dict[str, dict[str, int]] = {}
        with self.path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                b, d = row["bank_id"], row["doc_type"]
                counts.setdefault(b, {}).setdefault(d, 0)
                counts[b][d] += 1
        return counts

    def date_range(self, bank_id: str) -> tuple[str, str]:
        """Return (earliest, latest) meeting_date for a given bank."""
        dates: list[str] = []
        if self.path.exists():
            with self.path.open(newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    if row["bank_id"] == bank_id and row["meeting_date"]:
                        dates.append(row["meeting_date"])
        return (min(dates), max(dates)) if dates else ("", "")

    # ------------------------------------------------------------------

    def _load_urls(self) -> set[str]:
        if not self.path.exists():
            return set()
        with self.path.open(newline="", encoding="utf-8") as fh:
            return {row["source_url"] for row in csv.DictReader(fh)}
