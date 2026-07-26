"""Download a bounded Alpaca IEX Level-1 feasibility sample.

This is a data-feasibility scout, not a trading Experiment. It uses read-only historical
market-data endpoints and is hard-limited to the venue-local IEX feed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.alpaca_l1 import AlpacaHistoricalL1Client
from data.l1_validate import validate_quotes, validate_trades
from data.validate import QualityResult
from storage.microstructure_io import microstructure_path, write_events

DEFAULT_OUTPUT_DIR = Path("data/parquet/alpaca_iex_l1_feasibility")
SCHEMA_VERSION = "alpaca_iex_l1_feasibility:v1"
KNOWN_LIMITATIONS = [
    "IEX is one venue and does not represent consolidated US equity order flow.",
    "IEX quotes are venue-local top of book, not SIP National Best Bid and Offer.",
    "This artifact establishes data access and quality only; it is not alpha evidence.",
    "No full-depth orders, cancellations, or queue position are available.",
    "A current fixed symbol is suitable for plumbing only, not survivorship-safe validation.",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--date", required=True, help="US market session date (YYYY-MM-DD)")
    parser.add_argument("--start-time", default="09:30", help="America/New_York session time")
    parser.add_argument("--window-minutes", type=int, default=5, choices=range(1, 31))
    parser.add_argument("--page-size", type=int, default=10_000)
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--refresh", action="store_true")
    return parser.parse_args()


def _window_utc(session_date: str, start_time: str, minutes: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    date = pd.Timestamp(session_date).date().isoformat()
    start_local = pd.Timestamp(f"{date} {start_time}", tz="America/New_York")
    end_local = start_local + pd.Timedelta(minutes=minutes)
    open_local = pd.Timestamp(f"{date} 09:30", tz="America/New_York")
    close_local = pd.Timestamp(f"{date} 16:00", tz="America/New_York")
    if start_local < open_local or end_local > close_local:
        raise ValueError("Requested window must remain inside 09:30-16:00 America/New_York")
    return start_local.tz_convert("UTC"), end_local.tz_convert("UTC")


def _manifest_path(output_dir: Path, symbol: str, session_date: str) -> Path:
    trade_path = microstructure_path(
        output_dir,
        provider_feed="alpaca_iex",
        symbol=symbol,
        session_date=session_date,
        event_type="trades",
    )
    return trade_path.parent / "manifest.json"


def _relative_file_metadata(metadata: dict[str, int | str], root: Path) -> dict[str, int | str]:
    result = dict(metadata)
    result["path"] = Path(str(metadata["path"])).resolve().relative_to(root.resolve()).as_posix()
    return result


def main() -> int:
    args = _parse_args()
    if not 1 <= args.page_size <= 10_000:
        print("BLOCKED: --page-size must be between 1 and 10000")
        return 2
    if not 1 <= args.max_pages <= 100:
        print("BLOCKED: --max-pages must be between 1 and 100")
        return 2

    symbol = args.symbol.strip().upper()
    session_date = pd.Timestamp(args.date).date().isoformat()
    try:
        start, end = _window_utc(session_date, args.start_time, args.window_minutes)
    except ValueError as exc:
        print(f"BLOCKED: {exc}")
        return 2

    output_dir = args.output_dir.resolve()
    manifest_path = _manifest_path(output_dir, symbol, session_date)
    if manifest_path.exists() and not args.refresh:
        print(f"BLOCKED: artifact already exists; use --refresh to replace {manifest_path}")
        return 2

    load_dotenv(".env")
    client = AlpacaHistoricalL1Client(feed="iex")
    if not client.is_available():
        print("BLOCKED: ALPACA_API_KEY/ALPACA_API_SECRET are not configured")
        return 2

    print("Alpaca IEX Level-1 feasibility scout")
    print(
        f"symbol={symbol} feed=iex start={start.isoformat()} end={end.isoformat()} "
        f"page_size={args.page_size} max_pages={args.max_pages}"
    )

    trades = client.download_trades(
        symbol,
        start,
        end,
        page_size=args.page_size,
        max_pages=args.max_pages,
    )
    quotes = client.download_quotes(
        symbol,
        start,
        end,
        page_size=args.page_size,
        max_pages=args.max_pages,
    )
    if not (
        bool(trades.metadata["pagination_complete"])
        and bool(quotes.metadata["pagination_complete"])
    ):
        print("BLOCKED: pagination safety cap reached; no artifacts were written")
        return 1
    trade_quality = validate_trades(
        trades.data,
        symbol=symbol,
        pagination_complete=bool(trades.metadata["pagination_complete"]),
        requested_start=start,
        requested_end=end,
    )
    quote_quality = validate_quotes(
        quotes.data,
        symbol=symbol,
        pagination_complete=bool(quotes.metadata["pagination_complete"]),
        requested_start=start,
        requested_end=end,
    )

    trade_path = microstructure_path(
        output_dir,
        provider_feed="alpaca_iex",
        symbol=symbol,
        session_date=session_date,
        event_type="trades",
    )
    quote_path = microstructure_path(
        output_dir,
        provider_feed="alpaca_iex",
        symbol=symbol,
        session_date=session_date,
        event_type="quotes",
    )
    trade_file = _relative_file_metadata(write_events(trades.data, trade_path), manifest_path.parent)
    quote_file = _relative_file_metadata(write_events(quotes.data, quote_path), manifest_path.parent)

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "purpose": "data feasibility only; not a strategy Experiment or alpha claim",
        "provider": "alpaca",
        "feed": "iex",
        "feed_scope": "IEX venue-local trades and top of book; not SIP/NBBO",
        "symbol": symbol,
        "session_date": session_date,
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "credentials_recorded": False,
        "downloads": {
            "trades": trades.metadata,
            "quotes": quotes.metadata,
        },
        "quality": {
            "trades": trade_quality.to_dict(),
            "quotes": quote_quality.to_dict(),
        },
        "files": {
            "trades": trade_file,
            "quotes": quote_file,
        },
        "known_limitations": KNOWN_LIMITATIONS,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    temporary_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary_manifest.replace(manifest_path)

    print(
        f"trades rows={len(trades.data)} pages={trades.metadata['pages_fetched']} "
        f"quality={trade_quality.result.value}"
    )
    print(
        f"quotes rows={len(quotes.data)} pages={quotes.metadata['pages_fetched']} "
        f"quality={quote_quality.result.value}"
    )
    print(f"manifest={manifest_path}")

    if trade_quality.result == QualityResult.FAIL or quote_quality.result == QualityResult.FAIL:
        print("SCOUT BLOCKED: Level-1 data quality or pagination failed")
        return 1
    print("DATA FEASIBILITY PASS: venue-local IEX events downloaded and validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
