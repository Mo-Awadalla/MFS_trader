"""Read-only Binance USDⓈ-M funding distribution study.

Optionally extends the lake from Binance REST, then writes the complete study
document. It never reads prices or computes post-settlement outcomes.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

from data.base import DownloadRequest
from data.binance_vision_downloader import (
    BinanceVisionDownloader,
    VisionDataset,
    validate_funding_schedule,
)
from storage.parquet_io import parquet_path, read_timeseries, write_timeseries

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
LISTING_START = {
    "BTCUSDT": pd.Timestamp("2019-09-01", tz="UTC"),
    "ETHUSDT": pd.Timestamp("2019-11-01", tz="UTC"),
    "SOLUSDT": pd.Timestamp("2020-09-01", tz="UTC"),
}
OI_TESTABLE_START = pd.Timestamp("2021-12-21", tz="UTC")
REST_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
THRESHOLDS_BPS = (2.5, 5.0, 7.5, 10.0, 15.0, 20.0)
PERCENTILES = (0.001, 0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99, 0.999)


def funding_path(root: Path, symbol: str) -> Path:
    return parquet_path(
        root / "crypto_futures",
        symbol,
        "funding",
        source="binance_vision_futures_um_fundingRate",
    )


def fetch_funding_rest(
    symbol: str,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Fetch inclusive funding history with deterministic forward pagination."""
    client = session or requests.Session()
    cursor = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    rows: list[dict[str, Any]] = []
    while cursor <= end_ms:
        response = client.get(
            REST_URL,
            params={"symbol": symbol, "startTime": cursor, "endTime": end_ms, "limit": 1000},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            raise RuntimeError(f"Binance REST error for {symbol}: {payload}")
        if not payload:
            break
        rows.extend(payload)
        last = int(payload[-1]["fundingTime"])
        if last < cursor:
            raise RuntimeError(f"Binance REST pagination moved backward for {symbol}")
        cursor = last + 1
        if len(payload) < 1000:
            break
    if not rows:
        return pd.DataFrame(
            columns=["funding_rate"],
            index=pd.DatetimeIndex([], name="timestamp", tz="UTC"),
        )
    frame = pd.DataFrame(rows)
    timestamp = pd.to_datetime(frame["fundingTime"], unit="ms", utc=True)
    result = pd.DataFrame(
        {"funding_rate": pd.to_numeric(frame["fundingRate"], errors="raise").to_numpy()},
        index=pd.DatetimeIndex(timestamp, name="timestamp"),
    )
    return result[~result.index.duplicated(keep="last")].sort_index()


def extend_lake_from_rest(root: Path, symbol: str, *, end: pd.Timestamp) -> str:
    path = funding_path(root, symbol)
    existing = read_timeseries(path)
    try:
        fetched = fetch_funding_rest(symbol, start=LISTING_START[symbol], end=end)
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        return f"unavailable: {exc}"
    combined = pd.concat([existing, fetched]).sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]
    write_timeseries(combined, path)
    return f"merged {len(fetched)} REST rows"


def extend_lake_from_vision(root: Path, symbol: str) -> int:
    """Merge all official Vision funding archives available before the local series."""
    path = funding_path(root, symbol)
    existing = read_timeseries(path)
    observed_start = existing.index.min().floor("D")
    if observed_start <= LISTING_START[symbol]:
        return 0
    downloader = BinanceVisionDownloader(
        dataset=VisionDataset.FUNDING_RATE,
        market="futures/um",
        period="monthly",
    )
    result = downloader.download(
        DownloadRequest(
            symbol=symbol,
            start_date=LISTING_START[symbol].isoformat(),
            end_date=(observed_start - pd.Timedelta(seconds=1)).isoformat(),
        )
    )
    combined = pd.concat([existing, result.data]).sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]
    write_timeseries(combined, path)
    return len(result.data)


def load_funding(root: Path, symbol: str) -> pd.DataFrame:
    frame = read_timeseries(funding_path(root, symbol))[["funding_rate"]].copy()
    frame.index = frame.index.floor("s")
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    # The frozen study concerns scheduled 00/08/16 UTC observations. Extra
    # exchange-directed settlements remain in the lake but not in these tables.
    scheduled = (frame.index.minute == 0) & frame.index.hour.isin([0, 8, 16])
    return frame.loc[scheduled]


def distribution_rows(symbol: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for window, subset in _windows(frame).items():
        years: list[int | str] = ["ALL", *sorted(set(subset.index.year))]
        for year in years:
            sample = subset if year == "ALL" else subset[subset.index.year == year]
            if sample.empty:
                continue
            bps = sample["funding_rate"] * 10_000.0
            row: dict[str, Any] = {
                "symbol": symbol,
                "window": window,
                "year": year,
                "n": len(bps),
                "min_bps": bps.min(),
                "max_bps": bps.max(),
                "mean_bps": bps.mean(),
            }
            row.update({f"p{100*q:g}_bps": bps.quantile(q) for q in PERCENTILES})
            rows.append(row)
    return rows


def threshold_rows(symbol: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for window, subset in _windows(frame).items():
        years: list[int | str] = ["ALL", *sorted(set(subset.index.year))]
        for year in years:
            sample = subset if year == "ALL" else subset[subset.index.year == year]
            bps = sample["funding_rate"] * 10_000.0
            for threshold in THRESHOLDS_BPS:
                rows.append(
                    {
                        "symbol": symbol,
                        "window": window,
                        "year": year,
                        "threshold_bps": threshold,
                        "positive_count": int((bps > threshold).sum()),
                        "negative_count": int((bps < -threshold).sum()),
                    }
                )
    return rows


def clustering_rows(symbol: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for window, subset in _windows(frame).items():
        bps = subset["funding_rate"] * 10_000.0
        for threshold in THRESHOLDS_BPS:
            for sign, mask in (("positive", bps > threshold), ("negative", bps < -threshold)):
                lengths = _run_lengths(mask)
                cluster_starts = mask & ~mask.shift(fill_value=False)
                rolling_clusters = cluster_starts.rolling("30D").sum()
                rows.append(
                    {
                        "symbol": symbol,
                        "window": window,
                        "sign": sign,
                        "threshold_bps": threshold,
                        "events": int(mask.sum()),
                        "clusters": len(lengths),
                        "mean_run": float(np.mean(lengths)) if lengths else 0.0,
                        "max_run": max(lengths, default=0),
                        "lag1_autocorr": _indicator_autocorrelation(mask),
                        "max_30d_clusters": int(rolling_clusters.max()) if len(rolling_clusters) else 0,
                    }
                )
    return rows


def extreme_rows(symbol: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
    bps = frame["funding_rate"] * 10_000.0
    rows: list[dict[str, Any]] = []
    for sign, sample in (("positive", bps.nlargest(10)), ("negative", bps.nsmallest(10))):
        for rank, (timestamp, value) in enumerate(sample.items(), start=1):
            rows.append(
                {"symbol": symbol, "sign": sign, "rank": rank,
                 "timestamp_utc": timestamp.isoformat(), "funding_bps": value}
            )
    return rows


def _windows(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "full_history": frame,
        "oi_testable": frame.loc[frame.index >= OI_TESTABLE_START],
    }


def _run_lengths(mask: pd.Series) -> list[int]:
    groups = (mask != mask.shift(fill_value=False)).cumsum()
    return [int(value) for value in mask[mask].groupby(groups[mask]).size().tolist()]


def _indicator_autocorrelation(mask: pd.Series) -> float:
    numeric = mask.astype(float)
    if len(numeric) < 2 or numeric.nunique() < 2:
        return 0.0
    value = numeric.autocorr(lag=1)
    return 0.0 if pd.isna(value) else float(value)


def render_document(
    *,
    coverage: pd.DataFrame,
    distributions: pd.DataFrame,
    thresholds: pd.DataFrame,
    clusters: pd.DataFrame,
    extremes: pd.DataFrame,
) -> str:
    full_20 = thresholds[(thresholds["window"] == "full_history")
                         & (thresholds["year"] == "ALL")
                         & (thresholds["threshold_bps"] == 20.0)]
    oi_20 = thresholds[(thresholds["window"] == "oi_testable")
                       & (thresholds["year"] == "ALL")
                       & (thresholds["threshold_bps"] == 20.0)]
    full_text = ", ".join(
        f"{row.symbol} +{int(row.positive_count)}/−{int(row.negative_count)}"
        for row in full_20.itertuples()
    )
    oi_text = ", ".join(
        f"{row.symbol} +{int(row.positive_count)}/−{int(row.negative_count)}"
        for row in oi_20.itertuples()
    )
    lines = [
        "### Coverage",
        "",
        _markdown(coverage),
        "",
        "Rows before 2021-12-21 are outside the OI-testable window. `full_history` means all "
        "funding observations currently recovered in the lake; `oi_testable` begins after the "
        "20-day OI z-score warmup.",
        "",
        "### Signed distribution",
        "",
        _markdown(distributions),
        "",
        "### Threshold feasibility",
        "",
        _markdown(thresholds),
        "",
        "Counts are strict: `positive_count` is F > t and `negative_count` is F < −t.",
        "",
        "### Extreme clustering",
        "",
        _markdown(clusters),
        "",
        "Runs use consecutive scheduled settlements. `max_30d_clusters` counts distinct run "
        "starts in a trailing 30-day window.",
        "",
        "### Top extreme prints",
        "",
        _markdown(extremes),
        "",
        "### Factual summary",
        "",
        f"At the strict 20 bp threshold, full recovered-history positive/negative counts are: "
        f"{full_text}. In the OI-testable window they are: {oi_text}. The clustering table "
        "reports consecutive-settlement runs and the observed maximum number of distinct run "
        "starts in any trailing 30 days. This document makes no threshold recommendation and "
        "does not assess conditional strategy outcomes.",
        "",
    ]
    return "\n".join(lines)


def _markdown(frame: pd.DataFrame) -> str:
    formatted = frame.copy()
    for column in formatted.select_dtypes(include=["float"]).columns:
        formatted[column] = formatted[column].map(lambda value: f"{value:.6f}")
    columns = [str(column) for column in formatted.columns]
    rows = ["| " + " | ".join(columns) + " |",
            "|" + "|".join("---" for _ in columns) + "|"]
    for values in formatted.itertuples(index=False, name=None):
        cells = [str(value).replace("|", "\\|").replace("\n", " ") for value in values]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def run(root: Path, output: Path, *, extend_rest: bool) -> None:
    rest_status = dict.fromkeys(SYMBOLS, "not requested")
    for symbol in SYMBOLS:
        extend_lake_from_vision(root, symbol)
    if extend_rest:
        end = pd.Timestamp.now(tz="UTC")
        for symbol in SYMBOLS:
            rest_status[symbol] = extend_lake_from_rest(root, symbol, end=end)

    coverage_rows: list[dict[str, Any]] = []
    distribution_data: list[dict[str, Any]] = []
    threshold_data: list[dict[str, Any]] = []
    clustering_data: list[dict[str, Any]] = []
    extreme_data: list[dict[str, Any]] = []
    for symbol in SYMBOLS:
        frame = load_funding(root, symbol)
        validate_funding_schedule(frame, symbol=symbol)
        coverage_rows.append(
            {
                "symbol": symbol,
                "requested_listing_start": LISTING_START[symbol].date().isoformat(),
                "observed_start": frame.index.min().date().isoformat(),
                "observed_end": frame.index.max().date().isoformat(),
                "scheduled_rows": len(frame),
                "listing_complete": frame.index.min() <= LISTING_START[symbol],
                "rest_status": rest_status[symbol],
            }
        )
        distribution_data.extend(distribution_rows(symbol, frame))
        threshold_data.extend(threshold_rows(symbol, frame))
        clustering_data.extend(clustering_rows(symbol, frame))
        extreme_data.extend(extreme_rows(symbol, frame))

    generated = render_document(
        coverage=pd.DataFrame(coverage_rows),
        distributions=pd.DataFrame(distribution_data),
        thresholds=pd.DataFrame(threshold_data),
        clusters=pd.DataFrame(clustering_data),
        extremes=pd.DataFrame(extreme_data),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    marker = "## Generated results"
    if output.exists() and marker in output.read_text(encoding="utf-8"):
        preamble = output.read_text(encoding="utf-8").split(marker, maxsplit=1)[0]
    else:
        preamble = (
            "# Funding Distribution Study\n\n"
            "This is a read-only base-rate study. Binance raw `0.0001` equals `1 bp`.\n\n"
        )
    output.write_text(f"{preamble.rstrip()}\n\n{marker}\n\n{generated}", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/parquet"))
    parser.add_argument("--output", type=Path,
                        default=Path("docs/research/funding_distribution_study.md"))
    parser.add_argument("--extend-rest", action="store_true",
                        help="Attempt Binance REST pagination and atomically merge it into the lake")
    args = parser.parse_args()
    run(args.root, args.output, extend_rest=args.extend_rest)
    print("units audit: raw funding_rate 0.0001 = 1.0 bp")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
