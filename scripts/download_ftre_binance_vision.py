"""Backfill FTRE v1 Binance Vision inputs into deterministic Parquet paths."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from data.base import DownloadRequest
from data.binance_vision_downloader import (
    BinanceVisionDownloader,
    VisionDataset,
    validate_funding_schedule,
)
from data.validate import QualityResult, validate_ohlcv
from storage.parquet_io import parquet_path, write_bars, write_timeseries

LISTING_START = {"BTCUSDT": "2019-09-01", "ETHUSDT": "2019-11-01", "SOLUSDT": "2020-09-01"}


def backfill_symbol(symbol: str, *, start: str, end: str | None,
                    root: Path = Path("data/parquet"),
                    include_context_mark: bool = False) -> dict[str, int]:
    request = DownloadRequest(symbol=symbol, start_date=start, end_date=end, frequency="1min")
    counts: dict[str, int] = {}
    datasets = [VisionDataset.KLINES, VisionDataset.PREMIUM_INDEX_KLINES,
                VisionDataset.FUNDING_RATE]
    if include_context_mark:
        datasets.insert(1, VisionDataset.MARK_PRICE_KLINES)
    for dataset in datasets:
        downloader = BinanceVisionDownloader(dataset=dataset, market="futures/um", period="monthly")
        result = downloader.download(request)
        path = parquet_path(root / "crypto_futures", symbol,
                            "1min" if dataset != VisionDataset.FUNDING_RATE else "funding",
                            source=downloader.source_name)
        if path.exists():
            counts[dataset.value] = -1
            continue
        if dataset == VisionDataset.FUNDING_RATE:
            validate_funding_schedule(result.data, symbol=symbol)
            write_timeseries(result.data, path)
        elif dataset == VisionDataset.KLINES:
            report = validate_ohlcv(result.data, symbol, downloader.source_name,
                                    frequency="1min", expected_interval_seconds=60)
            if report.result == QualityResult.FAIL:
                raise ValueError(f"{symbol} {dataset.value}: OHLCV validation failed: {report.issues_json}")
            write_bars(result.data, path)
            counts[f"{dataset.value}_gaps"] = _gap_count(result.data)
        else:
            counts[f"{dataset.value}_gaps"] = _validate_derived_price_series(
                result.data, symbol=symbol, dataset=dataset
            )
            write_bars(result.data, path)
        counts[dataset.value] = len(result.data)

    spot = BinanceVisionDownloader(dataset=VisionDataset.KLINES, market="spot", period="monthly")
    spot_path = parquet_path(root / "crypto", symbol, "1min", source=spot.source_name)
    if spot_path.exists():
        counts["spot_klines"] = -1
    else:
        spot_result = spot.download(request)
        spot_report = validate_ohlcv(spot_result.data, symbol, spot.source_name,
                                     frequency="1min", expected_interval_seconds=60)
        if spot_report.result == QualityResult.FAIL:
            raise ValueError(f"{symbol} spot: OHLCV validation failed: {spot_report.issues_json}")
        write_bars(spot_result.data, spot_path)
        counts["spot_klines"] = len(spot_result.data)
        counts["spot_klines_gaps"] = _gap_count(spot_result.data)

    # OI/taker metrics exist only as daily archives and begin materially later than listings.
    metrics_start = max(start, "2021-12-01")
    metrics = BinanceVisionDownloader(dataset=VisionDataset.METRICS,
                                      market="futures/um", period="daily")
    metrics_path = parquet_path(root / "crypto_futures", symbol, "metrics",
                                source=metrics.source_name)
    if metrics_path.exists():
        counts["metrics"] = -1
    else:
        metrics_result = metrics.download(DownloadRequest(symbol, metrics_start, end, "5min"))
        write_timeseries(metrics_result.data, metrics_path)
        counts["metrics"] = len(metrics_result.data)
    return counts


def _validate_derived_price_series(
    df: pd.DataFrame, *, symbol: str, dataset: VisionDataset
) -> int:
    # Mark/premium-index archives intentionally have zero volume; premium values may be negative.
    if df.empty:
        raise ValueError(f"{symbol} {dataset.value}: empty derived-price archive")
    if df.index.tz is None or str(df.index.tz) != "UTC":
        raise ValueError(f"{symbol} {dataset.value}: timestamps must be UTC")
    if df.index.has_duplicates:
        raise ValueError(f"{symbol} {dataset.value}: duplicate timestamps")
    return _gap_count(df)


def _gap_count(df: pd.DataFrame) -> int:
    gaps = df.index.to_series().diff().dropna() > pd.Timedelta(seconds=90)
    return int(gaps.sum())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", choices=tuple(LISTING_START), action="append")
    parser.add_argument("--start", help="Override listing start (YYYY-MM-DD)")
    parser.add_argument("--end", help="Inclusive end timestamp")
    parser.add_argument("--root", type=Path, default=Path("data/parquet"))
    parser.add_argument("--include-context-mark", action="store_true",
                        help="Also ingest non-blocking mark-price context")
    args = parser.parse_args()
    symbols = args.symbol or list(LISTING_START)
    for symbol in symbols:
        counts = backfill_symbol(symbol, start=args.start or LISTING_START[symbol],
                                 end=args.end, root=args.root,
                                 include_context_mark=args.include_context_mark)
        print(symbol, counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
