"""Entry point: scrape all or specified central banks.

Usage examples:
  python -m pipeline.run                         # scrape all, incremental
  python -m pipeline.run --banks fed ecb         # specific banks, incremental
  python -m pipeline.run --backfill              # all history, all banks
  python -m pipeline.run --banks fed --since 2024-01-01
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from scrapers.fed import FedScraper
from scrapers.ecb import ECBScraper
from scrapers.boe import BoEScraper
from scrapers.boj import BoJScraper
from scrapers.rba import RBAScraper
from scrapers.boc import BoCScaper
from scrapers.snb import SNBScraper
from scrapers.riksbank import RiksbankScraper
from pipeline.manifest import Manifest

SCRAPER_MAP = {
    "fed": FedScraper,
    "ecb": ECBScraper,
    "boe": BoEScraper,
    "boj": BoJScraper,
    "rba": RBAScraper,
    "boc": BoCScaper,
    "snb": SNBScraper,
    "riksbank": RiksbankScraper,
}

_REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = _REPO_ROOT / "data"
MANIFEST_PATH = DATA_DIR / "manifest.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Central bank document scraper")
    parser.add_argument(
        "--banks",
        nargs="*",
        default=list(SCRAPER_MAP),
        metavar="BANK",
        help=f"Banks to scrape. Choices: {', '.join(SCRAPER_MAP)}. Default: all.",
    )
    parser.add_argument(
        "--since",
        default=None,
        metavar="YYYY-MM-DD",
        help="Only fetch documents with meeting_date >= this value.",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Scrape all historical documents (ignores --since).",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )

    since = None if args.backfill else args.since
    total_new = 0

    for bank_id in args.banks:
        cls = SCRAPER_MAP.get(bank_id)
        if cls is None:
            logging.warning("Unknown bank %r — skipping. Valid: %s", bank_id, ", ".join(SCRAPER_MAP))
            continue

        scraper = cls(DATA_DIR, MANIFEST_PATH)
        logging.info("=== %s ===", bank_id.upper())
        results = scraper.scrape_new(since_date=since)
        logging.info("%s: %d new documents scraped", bank_id, len(results))
        total_new += len(results)

    manifest = Manifest(MANIFEST_PATH)
    summary = manifest.summary()
    logging.info("--- Manifest summary ---")
    for bank, counts in sorted(summary.items()):
        for doc_type, n in sorted(counts.items()):
            logging.info("  %-10s %-20s %d", bank, doc_type, n)
    logging.info("Total new this run: %d", total_new)

    return 0


if __name__ == "__main__":
    sys.exit(main())
