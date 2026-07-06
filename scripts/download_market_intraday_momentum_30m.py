"""Download 30-minute Alpaca bars for market_intraday_momentum_v1."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.alpaca_downloader import AlpacaDownloader
from data.base import DownloadRequest
from data.validate import QualityResult, validate_ohlcv
from research.universes.market_intraday_momentum_v1 import all_symbols
from storage.parquet_io import read_bars, write_bars

DEFAULT_START = "2021-01-01"
DEFAULT_STORAGE_DIR = Path("data/parquet/market_intraday_momentum/alpaca_sip")
FREQUENCY = "30min"


def cache_path(symbol: str, storage_dir: Path) -> Path:
    return storage_dir / f"{symbol}_{FREQUENCY}.parquet"


def regular_session_only(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    local_index = df.index.tz_convert("America/New_York")
    mask = (local_index.time >= pd.Timestamp("09:30").time()) & (
        local_index.time <= pd.Timestamp("15:30").time()
    )
    return df.loc[mask].copy()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end")
    parser.add_argument("--storage-dir", default=str(DEFAULT_STORAGE_DIR))
    parser.add_argument("--feed", default="sip", choices=["sip", "iex"])
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    load_dotenv(".env")
    storage_dir = Path(args.storage_dir)
    downloader = AlpacaDownloader(feed=args.feed)
    if not downloader.is_available():
        print("BLOCKED: ALPACA_API_KEY/ALPACA_API_SECRET are not configured")
        return 2

    attempted = skipped = stored = 0
    failures: dict[str, str] = {}
    print("Market intraday momentum 30m downloader")
    print(f"symbols={all_symbols()}")
    print(f"feed={args.feed} start={args.start} end={args.end or 'now'}")

    for symbol in all_symbols():
        path = cache_path(symbol, storage_dir)
        if path.exists() and not args.refresh:
            df = read_bars(path)
            print(f"skip {symbol:5s} cached bars={len(df):5d} start={df.index.min()} end={df.index.max()}")
            skipped += 1
            continue
        attempted += 1
        try:
            result = downloader.download(
                DownloadRequest(
                    symbol=symbol,
                    start_date=args.start,
                    end_date=args.end,
                    frequency=FREQUENCY,
                )
            )
            df = regular_session_only(result.data)
            report = validate_ohlcv(
                df,
                symbol=symbol,
                source=f"alpaca_{args.feed}",
                frequency=FREQUENCY,
                is_live=False,
            )
            if report.result == QualityResult.FAIL:
                failures[symbol] = f"quality FAIL: {report.issues_json}"
                print(f"fail {symbol:5s} quality=FAIL issues={report.issues_json}")
                continue
            write_bars(df, path)
            stored += 1
            print(
                f"store {symbol:5s} bars={len(df):5d} start={df.index.min()} end={df.index.max()} quality={report.result.value}"
            )
        except Exception as exc:  # noqa: BLE001 - batch failures for operator report
            failures[symbol] = str(exc)
            print(f"fail {symbol:5s} error={exc}")

    print(f"summary attempted={attempted} skipped={skipped} stored={stored} failed={len(failures)}")
    if failures:
        print("BLOCKED failures:")
        for symbol, error in failures.items():
            print(f"  {symbol}: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
