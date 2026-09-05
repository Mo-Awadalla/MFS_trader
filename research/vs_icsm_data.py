"""Data helpers for the VS-ICSM candidate."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import requests

from research.csmr_data import OHLCV_FIELDS
from storage.parquet_io import append_bars, read_bars, write_bars

DEFAULT_METADATA_PATH = Path("experiments/6ed472a7-a361-46b2-bdb9-2a196c459cca/metadata.json")
DEFAULT_STORAGE_DIR = Path("data/parquet/equity")
DEFAULT_SUMMARY_PATH = Path("runs/vs_icsm_data/massive_1h_2021_07_present_summary.json")
DEFAULT_FLATFILES_SUMMARY_PATH = Path("runs/vs_icsm_data/massive_flatfiles_1h_summary.json")
MIXED_SOURCE_BOUNDARY = pd.Timestamp("2021-07-01 00:00:00", tz="UTC")


def load_universe_symbols(metadata_path: str | Path = DEFAULT_METADATA_PATH) -> list[str]:
    metadata = json.loads(Path(metadata_path).read_text())
    universe = metadata.get("universe", {})
    symbols = universe.get("symbols") if isinstance(universe, dict) else universe
    if not isinstance(symbols, list):
        raise ValueError(f"{metadata_path} does not contain universe symbols")
    return [str(symbol) for symbol in symbols]


def download_massive_1h_universe(
    symbols: list[str],
    *,
    api_key: str,
    storage_dir: str | Path = DEFAULT_STORAGE_DIR,
    summary_path: str | Path = DEFAULT_SUMMARY_PATH,
    start: str = "2021-07-01",
    end: str | None = None,
    sleep_seconds: float = 0.0,
    force: bool = False,
) -> dict[str, Any]:
    storage_root = Path(storage_dir) / "massive"
    summary = _load_summary(summary_path)
    summary.update(
        {
            "source": "massive",
            "timeframe": "1h",
            "start": pd.Timestamp(start, tz="UTC").isoformat(),
            "end": pd.Timestamp(end, tz="UTC").isoformat()
            if end
            else pd.Timestamp.now(tz="UTC").isoformat(),
            "requested_symbols": len(symbols),
            "symbols": summary.get("symbols", {}),
        }
    )
    session = requests.Session()
    for index, symbol in enumerate(symbols, start=1):
        path = storage_root / f"{symbol.replace('/', '_')}_1h.parquet"
        existing = summary["symbols"].get(symbol, {})
        if path.exists() and existing.get("status") == "ok" and not force:
            continue
        try:
            df, pages = fetch_massive_1h_bars(
                symbol,
                api_key=api_key,
                start=start,
                end=end,
                session=session,
            )
            if not df.empty:
                write_bars(df, path)
            summary["symbols"][symbol] = {
                "bars": int(len(df)),
                "error": None,
                "pages": pages,
                "status": "ok",
                "stored": bool(not df.empty),
            }
        except requests.HTTPError as exc:
            response = exc.response
            summary["symbols"][symbol] = {
                "bars": 0,
                "error": response.text[:500] if response is not None else str(exc),
                "pages": 0,
                "status": f"http_{response.status_code}" if response is not None else "http_error",
                "stored": False,
            }
        except Exception as exc:
            summary["symbols"][symbol] = {
                "bars": 0,
                "error": str(exc),
                "pages": 0,
                "status": "error",
                "stored": False,
            }
        _write_summary(summary_path, summary)
        if index % 10 == 0:
            ok = sum(1 for item in summary["symbols"].values() if item.get("status") == "ok")
            print(f"massive progress {index}/{len(symbols)} symbols, ok={ok}", flush=True)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    return summary


def download_massive_flatfiles_1h_universe(
    symbols: list[str],
    *,
    access_key_id: str,
    secret_access_key: str,
    storage_dir: str | Path = DEFAULT_STORAGE_DIR,
    summary_path: str | Path = DEFAULT_FLATFILES_SUMMARY_PATH,
    start: str = "2021-07-01",
    end: str | None = None,
    endpoint_url: str = "https://files.massive.com",
    bucket: str = "flatfiles",
    force: bool = False,
) -> dict[str, Any]:
    import boto3
    from botocore.config import Config

    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC") if end else pd.Timestamp.now(tz="UTC")
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        config=Config(signature_version="s3v4"),
    )
    keys = list_massive_minute_agg_keys(s3, bucket=bucket, start=start_ts, end=end_ts)
    summary = _load_summary(summary_path)
    completed = set(summary.get("completed_keys", []))
    summary.update(
        {
            "source": "massive_flatfiles",
            "timeframe": "1h",
            "start": start_ts.isoformat(),
            "end": end_ts.isoformat(),
            "requested_symbols": len(symbols),
            "completed_keys": sorted(completed),
            "daily_files": summary.get("daily_files", {}),
        }
    )
    raw_dir = Path("runs/vs_icsm_data/massive_flatfiles_raw")
    raw_dir.mkdir(parents=True, exist_ok=True)
    storage_root = Path(storage_dir) / "massive_flatfiles"
    month_frames: dict[str, list[pd.DataFrame]] = {}
    current_month: str | None = None
    for index, key in enumerate(keys, start=1):
        month = "/".join(key.split("/")[:4])
        if current_month is None:
            current_month = month
        if month != current_month:
            _flush_symbol_frames(month_frames, storage_root)
            month_frames = {}
            current_month = month
        if key in completed and not force:
            continue
        local = raw_dir / Path(key).name
        try:
            s3.download_file(bucket, key, str(local))
            daily = _hourly_from_minute_csv(local, set(symbols))
            for symbol, df in daily.items():
                month_frames.setdefault(symbol, []).append(df)
            completed.add(key)
            summary["completed_keys"] = sorted(completed)
            summary["daily_files"][key] = {
                "status": "ok",
                "symbols": len(daily),
                "rows": int(sum(len(df) for df in daily.values())),
                "size": int(local.stat().st_size),
            }
        except Exception as exc:
            summary["daily_files"][key] = {"status": "error", "error": str(exc)}
        finally:
            local.unlink(missing_ok=True)
            _write_summary(summary_path, summary)
        if index % 25 == 0:
            print(f"flatfiles progress {index}/{len(keys)} files", flush=True)
    _flush_symbol_frames(month_frames, storage_root)
    _write_summary(summary_path, summary)
    return summary


def list_massive_minute_agg_keys(
    s3: Any,
    *,
    bucket: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[str]:
    keys: list[str] = []
    for month_start in pd.date_range(start.normalize().replace(day=1), end.normalize(), freq="MS"):
        prefix = f"us_stocks_sip/minute_aggs_v1/{month_start:%Y/%m}/"
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.endswith(".csv.gz"):
                    continue
                date_text = Path(key).name.removesuffix(".csv.gz")
                date = pd.Timestamp(date_text, tz="UTC")
                if start.normalize() <= date <= end.normalize():
                    keys.append(key)
    return sorted(keys)


def fetch_massive_1h_bars(
    symbol: str,
    *,
    api_key: str,
    start: str,
    end: str | None = None,
    session: requests.Session | None = None,
) -> tuple[pd.DataFrame, int]:
    client = session or requests.Session()
    end_date = end or pd.Timestamp.now(tz="UTC").date().isoformat()
    url = f"https://api.massive.com/v2/aggs/ticker/{symbol}/range/1/hour/{start}/{end_date}"
    params: dict[str, Any] = {
        "adjusted": "true",
        "sort": "asc",
        "limit": 50000,
        "apiKey": api_key,
    }
    rows: list[dict[str, Any]] = []
    pages = 0
    while url:
        response = _get_with_retry(client, url, params=params)
        response.raise_for_status()
        payload = response.json()
        rows.extend(payload.get("results", []))
        pages += 1
        next_url = payload.get("next_url")
        if not next_url:
            break
        url = _massive_next_url(next_url)
        params = {"apiKey": api_key}
    return _massive_results_to_frame(rows), pages


def _get_with_retry(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any],
    attempts: int = 5,
) -> requests.Response:
    delay = 1.0
    last_error: requests.RequestException | None = None
    for attempt in range(attempts):
        try:
            response = session.get(url, params=params, timeout=60)
            if response.status_code not in {429, 500, 502, 503, 504}:
                return response
            if attempt == attempts - 1:
                return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt == attempts - 1:
                raise
        time.sleep(delay)
        delay *= 2.0
    if last_error is not None:
        raise last_error
    raise RuntimeError("Massive request retry loop exited unexpectedly")


def load_vs_icsm_mixed_panel(
    symbols: list[str],
    *,
    storage_dir: str | Path = DEFAULT_STORAGE_DIR,
    boundary: pd.Timestamp = MIXED_SOURCE_BOUNDARY,
    end: str | None = None,
) -> pd.DataFrame:
    frames: dict[str, pd.DataFrame] = {}
    root = Path(storage_dir)
    end_ts = pd.Timestamp(end, tz="UTC") if end else None
    for symbol in symbols:
        alpaca_path = root / "alpaca" / f"{symbol.replace('/', '_')}_1h.parquet"
        massive_path = root / "massive_flatfiles" / f"{symbol.replace('/', '_')}_1h.parquet"
        rest_massive_path = root / "massive" / f"{symbol.replace('/', '_')}_1h.parquet"
        parts: list[pd.DataFrame] = []
        if alpaca_path.exists():
            alpaca = read_bars(alpaca_path)
            parts.append(alpaca[alpaca.index < boundary])
        if not massive_path.exists() and rest_massive_path.exists():
            massive_path = rest_massive_path
        if massive_path.exists():
            massive = read_bars(massive_path)
            parts.append(massive[massive.index >= boundary])
        if not parts:
            continue
        df = pd.concat(parts).sort_index()
        df = df[~df.index.duplicated(keep="last")]
        if end_ts is not None:
            df = df[df.index <= end_ts]
        missing = set(OHLCV_FIELDS) - set(df.columns)
        if missing:
            raise ValueError(f"{symbol} missing OHLCV columns: {sorted(missing)}")
        frames[symbol] = df.loc[:, list(OHLCV_FIELDS)].astype(float)
    if not frames:
        columns = pd.MultiIndex.from_arrays([[], []], names=["symbol", "field"])
        return pd.DataFrame(columns=columns)
    panel = pd.concat(frames, axis=1)
    panel.columns = pd.MultiIndex.from_tuples(
        [(str(symbol), str(field)) for symbol, field in panel.columns],
        names=["symbol", "field"],
    )
    return panel.sort_index()


def _hourly_from_minute_csv(path: Path, symbols: set[str]) -> dict[str, pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    for chunk in pd.read_csv(path, compression="gzip", chunksize=500_000):
        chunk = chunk[chunk["ticker"].isin(symbols)]
        if chunk.empty:
            continue
        chunk["timestamp"] = pd.to_datetime(chunk["window_start"], unit="ns", utc=True)
        frames.append(
            chunk.loc[:, ["ticker", "timestamp", "open", "high", "low", "close", "volume"]]
        )
    if not frames:
        return {}
    minute = pd.concat(frames, ignore_index=True)
    result: dict[str, pd.DataFrame] = {}
    for symbol, df in minute.groupby("ticker"):
        hourly = (
            df.set_index("timestamp")
            .sort_index()
            .resample("1h")
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
            .dropna(subset=["open", "high", "low", "close"])
        )
        result[str(symbol)] = hourly.loc[:, list(OHLCV_FIELDS)].astype(float)
    return result


def _flush_symbol_frames(frames: dict[str, list[pd.DataFrame]], storage_root: Path) -> None:
    for symbol, parts in frames.items():
        if not parts:
            continue
        df = pd.concat(parts).sort_index()
        df = df[~df.index.duplicated(keep="last")]
        append_bars(df, storage_root / f"{symbol.replace('/', '_')}_1h.parquet")


def _massive_results_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        df = pd.DataFrame(columns=list(OHLCV_FIELDS))
        df.index = pd.DatetimeIndex([], name="timestamp", tz="UTC")
        return df
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["t"], unit="ms", utc=True)
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    df = df[["timestamp", *OHLCV_FIELDS]].set_index("timestamp").sort_index()
    return df.astype(float)


def _massive_next_url(next_url: str) -> str:
    parsed = urlparse(next_url)
    if parsed.netloc:
        return next_url
    return f"https://api.massive.com{next_url}"


def _load_summary(summary_path: str | Path) -> dict[str, Any]:
    path = Path(summary_path)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _write_summary(summary_path: str | Path, summary: dict[str, Any]) -> None:
    path = Path(summary_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Massive 1h bars for VS-ICSM.")
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA_PATH))
    parser.add_argument("--start", default="2021-07-01")
    parser.add_argument("--end")
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--flatfiles", action="store_true")
    args = parser.parse_args()
    symbols = load_universe_symbols(args.metadata)
    if args.flatfiles:
        access_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
        secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
        if not access_key_id or not secret_access_key:
            raise SystemExit("AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required")
        summary = download_massive_flatfiles_1h_universe(
            symbols,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            start=args.start,
            end=args.end,
            force=args.force,
        )
        print(f"processed {len(summary.get('completed_keys', []))} Massive flat files")
        return
    api_key = os.environ.get("MASSIVE_API_KEY")
    if not api_key:
        raise SystemExit("MASSIVE_API_KEY is required")
    summary = download_massive_1h_universe(
        symbols,
        api_key=api_key,
        start=args.start,
        end=args.end,
        sleep_seconds=args.sleep_seconds,
        force=args.force,
    )
    ok = sum(1 for item in summary["symbols"].values() if item.get("status") == "ok")
    print(f"downloaded Massive 1h bars for {ok}/{len(symbols)} symbols")


if __name__ == "__main__":
    main()
