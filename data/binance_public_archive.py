"""Download and normalize checksum-verified Binance public monthly kline archives."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import requests

BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"
INTERVAL_DELTAS = {
    "5m": pd.Timedelta(minutes=5),
    "30m": pd.Timedelta(minutes=30),
}
KLINE_COLUMNS = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
)


@dataclass(frozen=True)
class ArchiveResult:
    data: pd.DataFrame
    metadata: dict[str, Any]


def month_keys(start: str, end: str) -> list[str]:
    """Return inclusive YYYY-MM archive keys covering two date bounds."""
    start_period = pd.Period(pd.Timestamp(start), freq="M")
    end_period = pd.Period(pd.Timestamp(end), freq="M")
    if end_period < start_period:
        raise ValueError("end must not precede start")
    return [str(period) for period in pd.period_range(start_period, end_period, freq="M")]


def _interval_delta(interval: str) -> pd.Timedelta:
    try:
        return INTERVAL_DELTAS[interval]
    except KeyError as exc:
        raise ValueError(f"unsupported validation interval: {interval}") from exc


def _to_utc_timestamp(values: pd.Series) -> pd.Series:
    """Parse Binance epoch values, including archives spanning ms/us migration."""
    numeric = pd.to_numeric(values, errors="raise").astype("int64")
    microseconds = numeric.abs().ge(10**15)
    result = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns, UTC]")
    if (~microseconds).any():
        result.loc[~microseconds] = pd.to_datetime(
            numeric.loc[~microseconds], unit="ms", utc=True
        )
    if microseconds.any():
        result.loc[microseconds] = pd.to_datetime(
            numeric.loc[microseconds], unit="us", utc=True
        )
    return result


def normalize_kline_csv(content: bytes, *, symbol: str, interval: str) -> pd.DataFrame:
    """Normalize one Binance kline CSV and validate its bar layout."""
    frame = pd.read_csv(io.BytesIO(content), header=None, names=KLINE_COLUMNS)
    # Binance added header rows to newer public archives while older archives
    # remain headerless. Accept the documented header, but no arbitrary schema.
    if not frame.empty and str(frame.iloc[0]["open_time"]).strip().lower() == "open_time":
        observed = tuple(str(value).strip().lower() for value in frame.iloc[0].tolist())
        documented_header = (
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "count",
            "taker_buy_volume",
            "taker_buy_quote_volume",
            "ignore",
        )
        if observed not in {KLINE_COLUMNS, documented_header}:
            raise ValueError(f"unexpected Binance kline header: {observed}")
        frame = frame.iloc[1:].reset_index(drop=True)
    if frame.empty:
        raise ValueError("Binance archive contains no rows")
    frame["open_time"] = _to_utc_timestamp(frame["open_time"])
    frame["close_time"] = _to_utc_timestamp(frame["close_time"])
    numeric = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
    ]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="raise")
    frame.insert(0, "symbol", symbol)
    frame.insert(1, "interval", interval)
    frame = frame.drop(columns=["ignore"]).sort_values("open_time", kind="stable")
    if frame["open_time"].duplicated().any():
        raise ValueError("duplicate Binance kline open timestamps")
    interval_delta = _interval_delta(interval)
    interval_minutes = int(interval_delta.total_seconds() // 60)
    grid_aligned = (
        frame["open_time"].dt.minute.mod(interval_minutes).eq(0)
        & frame["open_time"].dt.second.eq(0)
        & frame["open_time"].dt.microsecond.eq(0)
    )
    off_grid_bar_count = int((~grid_aligned).sum())
    frame = frame.loc[grid_aligned].copy()
    differences = frame["open_time"].diff().dropna()
    if (differences < interval_delta).any() or not (differences % interval_delta).eq(
        pd.Timedelta(0)
    ).all():
        raise ValueError(f"archive timestamps are not aligned to a {interval} grid")
    expected_close_boundary = frame["open_time"] + interval_delta
    close_offset = expected_close_boundary - frame["close_time"]
    complete_bar = close_offset.isin(
        [pd.Timedelta(0), pd.Timedelta(microseconds=1), pd.Timedelta(milliseconds=1)]
    )
    incomplete_bar_count = int((~complete_bar).sum())
    frame = frame.loc[complete_bar].copy()
    if (frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("invalid OHLC high")
    if (frame["low"] > frame[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("invalid OHLC low")
    frame = frame.reset_index(drop=True)
    frame.attrs["incomplete_bar_count"] = incomplete_bar_count
    frame.attrs["off_grid_bar_count"] = off_grid_bar_count
    return frame


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def download_month(
    session: requests.Session,
    *,
    symbol: str,
    interval: str,
    month: str,
    raw_dir: Path,
    refresh: bool = False,
) -> ArchiveResult:
    """Download, verify, cache, and normalize one official monthly archive."""
    filename = f"{symbol}-{interval}-{month}.zip"
    url = f"{BASE_URL}/{symbol}/{interval}/{filename}"
    archive_path = raw_dir / filename
    checksum_path = raw_dir / f"{filename}.CHECKSUM"
    raw_dir.mkdir(parents=True, exist_ok=True)
    if refresh or not archive_path.exists() or not checksum_path.exists():
        archive_response = session.get(url, timeout=120)
        archive_response.raise_for_status()
        checksum_response = session.get(f"{url}.CHECKSUM", timeout=120)
        checksum_response.raise_for_status()
        archive_path.write_bytes(archive_response.content)
        checksum_path.write_bytes(checksum_response.content)
    archive = archive_path.read_bytes()
    checksum_text = checksum_path.read_text(encoding="utf-8").strip()
    expected_sha256 = checksum_text.split()[0].lower()
    actual_sha256 = _sha256(archive)
    if expected_sha256 != actual_sha256:
        raise ValueError(f"checksum mismatch for {filename}")
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        members = zipped.namelist()
        if len(members) != 1 or not members[0].endswith(".csv"):
            raise ValueError(f"unexpected archive members for {filename}: {members}")
        frame = normalize_kline_csv(zipped.read(members[0]), symbol=symbol, interval=interval)
    metadata = {
        "month": month,
        "source_url": url,
        "checksum_url": f"{url}.CHECKSUM",
        "source_checksum_text": checksum_text,
        "expected_sha256": expected_sha256,
        "actual_sha256": actual_sha256,
        "bytes": len(archive),
        "rows": len(frame),
        "incomplete_bar_count": int(frame.attrs.get("incomplete_bar_count", 0)),
        "off_grid_bar_count": int(frame.attrs.get("off_grid_bar_count", 0)),
        "missing_bar_count": int(
            (frame["open_time"].diff().dropna() / pd.Timedelta(minutes=30) - 1).sum()
        ),
        "first_open_time": frame["open_time"].min().isoformat(),
        "last_open_time": frame["open_time"].max().isoformat(),
        "raw_archive": str(archive_path),
    }
    return ArchiveResult(frame, metadata)


def combine_months(
    results: Iterable[ArchiveResult], *, start: str, end: str, interval: str = "30m"
) -> pd.DataFrame:
    """Combine archives, enforce continuity, and apply inclusive date bounds."""
    frames = [result.data for result in results]
    if not frames:
        raise ValueError("no archive results")
    frame = pd.concat(frames, ignore_index=True).sort_values("open_time", kind="stable")
    if frame["open_time"].duplicated().any():
        raise ValueError("duplicate open timestamps across monthly archives")
    start_ts = pd.Timestamp(start, tz="UTC")
    end_exclusive = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    frame = frame.loc[(frame["open_time"] >= start_ts) & (frame["open_time"] < end_exclusive)]
    differences = frame["open_time"].diff().dropna()
    interval_delta = _interval_delta(interval)
    if (differences < interval_delta).any() or not (differences % interval_delta).eq(
        pd.Timedelta(0)
    ).all():
        raise ValueError(f"combined archive timestamps are not aligned to a {interval} grid")
    return frame.reset_index(drop=True)


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
