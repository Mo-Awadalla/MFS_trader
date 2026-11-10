"""Download frozen, bounded historical SIP stock ticks for the HFT falsification scout."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.alpaca_l1 import AlpacaHistoricalL1Client
from data.l1_validate import validate_quotes, validate_trades
from data.validate import QualityResult
from storage.microstructure_io import microstructure_path, write_events

SPEC_PATH = Path("research_scout/sip_stock_hft_v1.json")
OUTPUT_ROOT = Path("data/parquet/sip_stock_hft_v1")


def _utc_window(day: str, spec: dict) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(f"{day} {spec['data_window_et'][0]}", tz="America/New_York")
    end = pd.Timestamp(f"{day} {spec['data_window_et'][1]}", tz="America/New_York")
    return start.tz_convert("UTC"), end.tz_convert("UTC")


def _relative_file(metadata: dict, parent: Path) -> dict:
    result = dict(metadata)
    result["path"] = Path(str(metadata["path"])).resolve().relative_to(parent.resolve()).as_posix()
    return result


def download_day(day: str, spec: dict, client: AlpacaHistoricalL1Client) -> dict:
    symbol = spec["symbol"]
    start, end = _utc_window(day, spec)
    quote_path = microstructure_path(
        OUTPUT_ROOT, provider_feed="alpaca_sip", symbol=symbol,
        session_date=day, event_type="quotes",
    )
    manifest_path = quote_path.with_name("manifest.json")
    if manifest_path.exists():
        return {"date": day, "status": "already_exists", "manifest": str(manifest_path)}

    trades = client.download_trades(symbol, start, end, max_pages=100)
    quotes = client.download_quotes(symbol, start, end, max_pages=100)
    if not trades.metadata["pagination_complete"] or not quotes.metadata["pagination_complete"]:
        raise RuntimeError(f"incomplete pagination for {day}; no files written")
    trade_quality = validate_trades(
        trades.data, symbol=symbol, source="alpaca_sip", requested_start=start,
        requested_end=end,
    )
    quote_quality = validate_quotes(
        quotes.data, symbol=symbol, source="alpaca_sip", requested_start=start,
        requested_end=end,
    )
    if trade_quality.result == QualityResult.FAIL or quote_quality.result == QualityResult.FAIL:
        detail = {
            "trades": [issue.check for issue in trade_quality.issues],
            "quotes": [issue.check for issue in quote_quality.issues],
        }
        raise RuntimeError(f"tick quality did not pass for {day}: {detail}; no files written")

    trade_path = microstructure_path(
        OUTPUT_ROOT, provider_feed="alpaca_sip", symbol=symbol,
        session_date=day, event_type="trades",
    )
    trade_file = _relative_file(write_events(trades.data, trade_path), manifest_path.parent)
    quote_file = _relative_file(write_events(quotes.data, quote_path), manifest_path.parent)
    manifest = {
        "schema_version": "alpaca_sip_stock_hft_session:v1",
        "specification_id": spec["specification_id"],
        "provider": "alpaca",
        "feed": "sip",
        "feed_scope": "historical consolidated SIP, delayed at least 15 minutes",
        "symbol": symbol,
        "session_date": day,
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "credentials_recorded": False,
        "downloads": {"trades": trades.metadata, "quotes": quotes.metadata},
        "quality": {"trades": trade_quality.to_dict(), "quotes": quote_quality.to_dict()},
        "files": {"trades": trade_file, "quotes": quote_file},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {
        "date": day, "status": "downloaded", "trades": len(trades.data),
        "quotes": len(quotes.data), "manifest": str(manifest_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    dates = parser.add_mutually_exclusive_group(required=True)
    dates.add_argument("--date", help="one frozen development session")
    dates.add_argument("--all-development", action="store_true")
    parser.add_argument("--load-dotenv", action="store_true", help="Load credentials from .env explicitly")
    args = parser.parse_args()
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    allowed = spec["development_dates"]
    selected = allowed if args.all_development else [args.date]
    if any(day not in allowed for day in selected):
        raise ValueError("requested date is outside the frozen development list")
    if args.load_dotenv:
        load_dotenv(".env")
    client = AlpacaHistoricalL1Client(
        feed="sip", max_total_bytes=100_000_000, max_duration_seconds=180,
    )
    if not client.is_available():
        raise RuntimeError("Alpaca market-data credentials are not configured")
    for day in selected:
        print(json.dumps(download_day(day, spec, client)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
