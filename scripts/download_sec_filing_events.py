"""Download normalized SEC material-filing events for a fixed symbol set."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from data.sec_filings import DEFAULT_CACHE_DIR, SecFilingDownloader


def _symbols(values: list[str]) -> list[str]:
    symbols = {
        symbol.strip().upper()
        for value in values
        for symbol in value.split(",")
        if symbol.strip()
    }
    return sorted(symbols)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download point-in-time SEC filing events")
    parser.add_argument(
        "--symbols",
        nargs="+",
        required=True,
        help="Symbols separated by spaces and/or commas",
    )
    parser.add_argument("--start", required=True, help="Inclusive filing date (YYYY-MM-DD)")
    parser.add_argument("--end", help="Inclusive filing date (YYYY-MM-DD)")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Ignore raw JSON cache and fetch current SEC submissions",
    )
    args = parser.parse_args()

    symbols = _symbols(args.symbols)
    if not symbols:
        parser.error("--symbols must contain at least one symbol")
    user_agent = os.environ.get("SEC_USER_AGENT", "")
    if not user_agent.strip():
        parser.error("SEC_USER_AGENT environment variable is required")

    downloader = SecFilingDownloader(
        user_agent=user_agent,
        cache_dir=args.cache_dir,
        refresh=args.refresh,
    )
    events = downloader.download(symbols, start=args.start, end=args.end)
    output_path = (args.cache_dir / "sec_filing_events.parquet").resolve()
    print(f"symbols={len(symbols)}")
    print(f"material_filings={len(events)}")
    print(f"output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
