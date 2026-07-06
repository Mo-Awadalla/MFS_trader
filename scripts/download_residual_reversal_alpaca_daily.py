"""Download Alpaca SIP adjusted daily bars for ResidualReversalStatArb v1."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.alpaca_downloader import AlpacaDownloader
from data.base import DownloadRequest
from data.validate import QualityResult, validate_ohlcv
from research.universes.residual_reversal_v1 import all_symbols
from storage.parquet_io import append_bars, parquet_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download ResidualReversal v1 Alpaca daily bars")
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end")
    parser.add_argument("--storage-dir", default="data/parquet/equity")
    parser.add_argument("--source", default="alpaca_sip")
    parser.add_argument("--feed", default="sip")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.05)
    args = parser.parse_args()

    load_dotenv(".env")
    symbols = list(all_symbols())
    downloader = AlpacaDownloader(feed=args.feed)
    if not downloader.is_available():
        print("BLOCKED: ALPACA_API_KEY/ALPACA_API_SECRET are not configured")
        return 2

    attempted = skipped = stored = 0
    failed: dict[str, str] = {}
    warned: dict[str, int] = {}

    print("ResidualReversalStatArb v1 Alpaca daily downloader")
    print(f"symbols_total={len(symbols)}")
    print(f"daily_bar_requests_planned_at_most={len(symbols)}")
    print(f"feed={args.feed}")
    print(f"source={args.source}")
    print(f"start={args.start}")
    print(f"end={args.end or ''}")

    for symbol in symbols:
        path = parquet_path(args.storage_dir, symbol, "1d", source=args.source)
        if path.exists() and not args.refresh:
            skipped += 1
            print(f"SKIP cached {symbol} {path}")
            continue
        attempted += 1
        try:
            result = downloader.download(
                DownloadRequest(
                    symbol=symbol,
                    start_date=args.start,
                    end_date=args.end,
                    frequency="1d",
                )
            )
            report = validate_ohlcv(
                result.data,
                symbol=symbol,
                source=args.source,
                frequency="1d",
                expected_interval_seconds=86_400,
                is_live=False,
            )
            if report.result == QualityResult.FAIL:
                failed[symbol] = f"quality_FAIL issues={len(report.issues)}"
                print(f"FAIL quality {symbol} bars={len(result.data)} issues={len(report.issues)}")
                continue
            new_rows = append_bars(result.data, path)
            stored += 1
            if report.result == QualityResult.WARN:
                warned[symbol] = len(report.issues)
            print(
                f"STORE {symbol:5s} bars={len(result.data):5d} new_rows={new_rows:5d} "
                f"quality={report.result.value} path={path}"
            )
            if args.sleep > 0:
                time.sleep(args.sleep)
        except Exception as exc:  # noqa: BLE001 - bounded batch should report per-symbol failures.
            failed[symbol] = str(exc)
            print(f"ERROR {symbol}: {exc}")

    print("SUMMARY")
    print(f"attempted={attempted}")
    print(f"skipped={skipped}")
    print(f"stored={stored}")
    print(f"warned={len(warned)}")
    print(f"failed={len(failed)}")
    if failed:
        print("FAILED_SYMBOLS")
        for symbol, error in failed.items():
            print(f"  {symbol}: {error}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
