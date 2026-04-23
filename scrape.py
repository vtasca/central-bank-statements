"""Central bank document scraper.

Usage:
  python scrape.py                    # all banks, incremental (from last CSV date)
  python scrape.py --banks fed ecb    # specific banks
  python scrape.py --backfill         # full history for all banks
  python scrape.py --banks fed --backfill
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from scrapers.fed import FedScraper
from scrapers.ecb import ECBScraper
from scrapers.boe import BoEScraper
from scrapers.boj import BoJScraper
from scrapers.rba import RBAScraper
from scrapers.boc import BoCScaper
from scrapers.snb import SNBScraper
from scrapers.riksbank import RiksbankScraper

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

CALENDAR_FILE = Path(__file__).resolve().parent / "release_calendar.txt"


def is_release_day() -> bool:
    if not CALENDAR_FILE.exists():
        return False
    today = str(date.today())
    for line in CALENDAR_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and line == today:
            return True
    return False


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
        "--backfill",
        action="store_true",
        help="Scrape all historical documents (ignores release calendar gate).",
    )
    parser.add_argument(
        "--log-file",
        metavar="PATH",
        help="Append log output to this file in addition to stdout.",
    )
    args = parser.parse_args(argv)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if args.log_file:
        handlers.append(logging.FileHandler(args.log_file))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=handlers,
    )

    if not args.backfill and not is_release_day():
        print(f"Not a release day ({date.today()}), skipping. Use --backfill to force.")
        return 0

    total_new = 0

    for bank_id in args.banks:
        cls = SCRAPER_MAP.get(bank_id)
        if cls is None:
            logging.warning("Unknown bank %r — skipping. Valid: %s", bank_id, ", ".join(SCRAPER_MAP))
            continue

        scraper = cls()
        since = None if args.backfill else scraper._most_recent_date()
        logging.info("=== %s (since: %s) ===", bank_id.upper(), since or "beginning")
        results = scraper.scrape_new(since_date=since)
        logging.info("%s: %d new documents", bank_id, len(results))
        total_new += len(results)

    logging.info("Total new this run: %d", total_new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
