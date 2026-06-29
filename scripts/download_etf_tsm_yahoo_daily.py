"""Download long-history Yahoo Chart daily bars for ETFTimeSeriesMomentumVolTarget-v1.

This is a bounded, no-credential data refresh for a new data-version experiment.
It does not change the frozen ETF TSM strategy rules.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.validate import QualityResult, validate_ohlcv
from research.universes.etf_tactical_v1 import all_symbols
from storage.parquet_io import append_bars, parquet_path

SOURCE = "yahoo_chart"
DEFAULT_STORAGE_DIR = "data/parquet/equity"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


def _epoch_seconds(date_text: str) -> int:
    return int(pd.Timestamp(date_text, tz="UTC").timestamp())


def _download_yahoo_chart(symbol: str, start: str, end: str | None) -> pd.DataFrame:
    params: dict[str, Any] = {
        "period1": _epoch_seconds(start),
        "period2": _epoch_seconds(end) if end else int(time.time()),
        "interval": "1d",
        "events": "history|div|split",
        "includeAdjustedClose": "true",
    }
    response = requests.get(
        YAHOO_CHART_URL.format(symbol=symbol),
        params=params,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    chart = payload.get("chart", {})
    error = chart.get("error")
    if error:
        raise RuntimeError(f"Yahoo chart error for {symbol}: {error}")
    results = chart.get("result") or []
    if not results:
        raise RuntimeError(f"Yahoo chart returned no result for {symbol}")
    return _parse_yahoo_chart_result(results[0], symbol)


def _parse_yahoo_chart_result(result: dict[str, Any], symbol: str) -> pd.DataFrame:
    timestamps = result.get("timestamp") or []
    quote_list = result.get("indicators", {}).get("quote") or []
    adjclose_list = result.get("indicators", {}).get("adjclose") or []
    if not timestamps or not quote_list:
        raise RuntimeError(f"Yahoo chart result has no OHLCV data for {symbol}")

    quote = quote_list[0]
    raw = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(timestamps, unit="s", utc=True),
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "close": quote.get("close"),
            "volume": quote.get("volume"),
        }
    )
    if adjclose_list:
        raw["adj_close"] = adjclose_list[0].get("adjclose")
    else:
        raw["adj_close"] = raw["close"]

    raw = raw.dropna(subset=["timestamp", "open", "high", "low", "close", "adj_close"])
    if raw.empty:
        raise RuntimeError(f"Yahoo chart result has no complete adjusted OHLC rows for {symbol}")

    factor = raw["adj_close"] / raw["close"]
    adjusted = pd.DataFrame(
        {
            "open": (raw["open"] * factor).to_numpy(),
            "high": (raw["high"] * factor).to_numpy(),
            "low": (raw["low"] * factor).to_numpy(),
            "close": raw["adj_close"].to_numpy(),
            "volume": raw["volume"].fillna(0.0).to_numpy(),
        },
        index=raw["timestamp"],
    )
    adjusted.index.name = "timestamp"
    adjusted = adjusted.astype(float).sort_index()
    adjusted = adjusted.loc[~adjusted.index.duplicated(keep="last")]
    return adjusted


def main() -> int:
    parser = argparse.ArgumentParser(description="Download ETF TSM v1 long-history Yahoo daily bars")
    parser.add_argument("--start", default="2005-01-01")
    parser.add_argument("--end")
    parser.add_argument("--storage-dir", default=DEFAULT_STORAGE_DIR)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    symbols = list(all_symbols())
    attempted = skipped = stored = 0
    failed: dict[str, str] = {}
    warned: dict[str, int] = {}

    print(f"source={SOURCE}")
    print(f"symbols_total={len(symbols)}")
    print(f"daily_bar_requests_planned_at_most={len(symbols)}")
    print(f"start={args.start}")
    print(f"end={args.end or ''}")

    for symbol in symbols:
        path = parquet_path(args.storage_dir, symbol, "1d", source=SOURCE)
        if path.exists() and not args.refresh:
            skipped += 1
            print(f"SKIP cached {symbol} {path}")
            continue

        attempted += 1
        try:
            df = _download_yahoo_chart(symbol, args.start, args.end)
            report = validate_ohlcv(
                df,
                symbol=symbol,
                source=SOURCE,
                frequency="1d",
                expected_interval_seconds=86_400,
                is_live=False,
            )
            if report.result == QualityResult.FAIL:
                failed[symbol] = f"quality_FAIL issues={len(report.issues)}"
                print(f"FAIL quality {symbol} issues={len(report.issues)}")
                continue
            new_rows = append_bars(df, path)
            stored += 1
            if report.result == QualityResult.WARN:
                warned[symbol] = len(report.issues)
            print(
                f"STORE {symbol} bars={len(df)} new_rows={new_rows} quality={report.result.value} "
                f"start={df.index.min()} end={df.index.max()} path={path}"
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
