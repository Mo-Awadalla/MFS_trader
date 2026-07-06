"""Download the static Global Dual Momentum Defensive v1 daily-bar universe.

Conservative API use: daily bars only, static eight-symbol universe, skip cached
files unless --refresh is passed.
"""

from __future__ import annotations

import argparse

from dotenv import load_dotenv

from data.alpaca_downloader import AlpacaDownloader
from data.base import DownloadRequest
from data.validate import QualityResult, validate_ohlcv
from research.universes.global_dual_momentum_v1 import all_symbols
from storage.parquet_io import append_bars, parquet_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Global Dual Momentum v1 daily bars")
    parser.add_argument("--start", default="2010-01-01")
    parser.add_argument("--end")
    parser.add_argument("--storage-dir", default="data/parquet/equity")
    parser.add_argument("--source", default="alpaca")
    parser.add_argument("--feed", default="iex")
    parser.add_argument("--refresh", action="store_true")
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

    print(f"symbols_total={len(symbols)}")
    print(f"daily_bar_requests_planned_at_most={len(symbols)}")
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
                is_live=False,
            )
            if report.result == QualityResult.FAIL:
                failed[symbol] = f"quality_FAIL issues={len(report.issues)}"
                print(f"FAIL quality {symbol} issues={len(report.issues)}")
                continue
            new_rows = append_bars(result.data, path)
            stored += 1
            if report.result == QualityResult.WARN:
                warned[symbol] = len(report.issues)
            print(
                f"STORE {symbol} bars={len(result.data)} new_rows={new_rows} "
                f"quality={report.result.value} path={path}"
            )
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
