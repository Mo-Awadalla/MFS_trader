"""Download free Massive ES futures bars and build a point-in-time roll map.

Only endpoints documented as included in Massive Futures Basic ($0) are used:
contract reference and aggregate bars. The client is intentionally rate-limited
below the free plan's five-calls-per-minute allowance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import pandas as pd
import requests

BASE_URL = "https://api.massive.com"
NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
QUARTER_CODES = ("H", "M", "U", "Z")


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _api_key(dotenv_path: Path) -> str:
    key = os.environ.get("MASSIVE_API_KEY") or _read_dotenv(dotenv_path).get(
        "MASSIVE_API_KEY"
    )
    if not key:
        raise RuntimeError("MASSIVE_API_KEY is not set")
    return key


@dataclass
class MassiveClient:
    api_key: str
    min_interval_seconds: float = 12.5

    def __post_init__(self) -> None:
        self._last_request = 0.0
        self._session = requests.Session()

    def get(self, path_or_url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval_seconds:
            time.sleep(self.min_interval_seconds - elapsed)

        url = (
            path_or_url
            if urlparse(path_or_url).scheme
            else f"{BASE_URL}{path_or_url}"
        )
        query = dict(params or {})
        query["apiKey"] = self.api_key
        response = self._session.get(url, params=query, timeout=90)
        self._last_request = time.monotonic()
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "60"))
            time.sleep(max(retry_after, 60.0))
            response = self._session.get(url, params=query, timeout=90)
            self._last_request = time.monotonic()
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") not in {None, "OK"}:
            raise RuntimeError(f"Massive API status: {payload.get('status')}")
        return payload

    def paginated(
        self, path: str, params: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], int]:
        rows: list[dict[str, Any]] = []
        calls = 0
        next_url: str | None = path
        next_params: dict[str, Any] | None = params
        while next_url:
            payload = self.get(next_url, next_params)
            calls += 1
            rows.extend(payload.get("results", []))
            next_url = payload.get("next_url")
            next_params = None
            print(f"Massive calls={calls}; accumulated rows={len(rows)}", flush=True)
        return rows, calls


def _quarterly_tickers(year: int) -> list[str]:
    short = str(year)[-1]
    following = str(year + 1)[-1]
    return [f"ES{code}{short}" for code in QUARTER_CODES] + [f"ESH{following}"]


def _session_bars(
    client: MassiveClient, ticker: str, start: date, end: date
) -> tuple[list[dict[str, Any]], int]:
    return client.paginated(
        f"/futures/v1/aggs/{ticker}",
        {
            "resolution": "1session",
            "window_start.gte": (start - timedelta(days=10)).isoformat(),
            "window_start.lt": end.isoformat(),
            "limit": 50_000,
            "sort": "window_start.asc",
        },
    )


def _point_in_time_map(session_frame: pd.DataFrame, year: int) -> pd.DataFrame:
    frame = session_frame.copy()
    frame["session_end_date"] = pd.to_datetime(frame["session_end_date"]).dt.date
    volume = frame.pivot_table(
        index="session_end_date",
        columns="ticker",
        values="volume",
        aggfunc="sum",
        fill_value=0,
    ).sort_index()
    start = date(year, 1, 1)
    end = date(year + 1, 1, 1)
    rows: list[dict[str, Any]] = []
    for target in pd.date_range(start=start, end=end - timedelta(days=1), freq="B"):
        target_date = target.date()
        prior = volume.loc[volume.index < target_date]
        if prior.empty:
            continue
        prior_volume = prior.iloc[-1]
        if prior_volume.max() <= 0:
            continue
        rows.append(
            {
                "session_end_date": target_date,
                "ticker": str(prior_volume.idxmax()),
            }
        )
    return pd.DataFrame(rows)


def _mapping_intervals(mapping: pd.DataFrame) -> list[dict[str, Any]]:
    intervals: list[dict[str, Any]] = []
    for ticker, group in mapping.groupby(
        mapping["ticker"].ne(mapping["ticker"].shift()).cumsum(), sort=False
    ):
        del ticker
        intervals.append(
            {
                "ticker": str(group["ticker"].iloc[0]),
                "first_session": group["session_end_date"].min(),
                "last_session": group["session_end_date"].max(),
                "sessions": int(len(group)),
            }
        )
    return intervals


def _ny_midnight_ns(value: date) -> int:
    timestamp = datetime.combine(value, datetime.min.time(), tzinfo=NY).astimezone(UTC)
    return int(timestamp.timestamp() * 1_000_000_000)


def _minute_bars(
    client: MassiveClient, ticker: str, start: date, end_inclusive: date
) -> tuple[list[dict[str, Any]], int]:
    return client.paginated(
        f"/futures/v1/aggs/{ticker}",
        {
            "resolution": "1min",
            "window_start.gte": _ny_midnight_ns(start),
            "window_start.lt": _ny_midnight_ns(end_inclusive + timedelta(days=1)),
            "limit": 50_000,
            "sort": "window_start.asc",
        },
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--dotenv", type=Path, default=Path(".env"))
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("external_artifacts/massive_es_futures"),
    )
    args = parser.parse_args()

    key = _api_key(args.dotenv)
    client = MassiveClient(key)
    year_start = date(args.year, 1, 1)
    year_end = date(args.year + 1, 1, 1)
    tickers = _quarterly_tickers(args.year)

    session_rows: list[dict[str, Any]] = []
    api_calls = 0
    for ticker in tickers:
        rows, calls = _session_bars(client, ticker, year_start, year_end)
        session_rows.extend(rows)
        api_calls += calls
    if not session_rows:
        raise RuntimeError("Massive returned no ES session bars")

    session_frame = pd.DataFrame(session_rows).drop_duplicates(
        subset=["ticker", "window_start"], keep="last"
    )
    mapping = _point_in_time_map(session_frame, args.year)
    intervals = _mapping_intervals(mapping)
    if not intervals:
        raise RuntimeError("Could not derive a point-in-time ES roll map")
    if len(intervals) > 12:
        raise RuntimeError(f"Implausibly fragmented roll map: {len(intervals)} intervals")

    minute_rows: list[dict[str, Any]] = []
    for interval in intervals:
        rows, calls = _minute_bars(
            client,
            interval["ticker"],
            interval["first_session"],
            interval["last_session"],
        )
        minute_rows.extend(rows)
        api_calls += calls
    minute_frame = pd.DataFrame(minute_rows).drop_duplicates(
        subset=["ticker", "window_start"], keep="last"
    )
    mapping_keys = mapping.assign(
        session_end_date=mapping["session_end_date"].astype(str),
        _selected=True,
    )[["session_end_date", "ticker", "_selected"]]
    minute_frame["session_end_date"] = minute_frame["session_end_date"].astype(str)
    minute_frame = (
        minute_frame.merge(
            mapping_keys,
            on=["session_end_date", "ticker"],
            how="inner",
            validate="many_to_one",
        )
        .drop(columns="_selected")
        .sort_values("window_start")
    )

    output_root = args.output_root / str(args.year)
    output_root.mkdir(parents=True, exist_ok=True)
    session_path = output_root / "candidate_session_bars.parquet"
    mapping_path = output_root / "previous_session_volume_roll_map.parquet"
    minute_path = output_root / "selected_contract_1min.parquet"
    session_frame.to_parquet(session_path, index=False)
    mapping.to_parquet(mapping_path, index=False)
    minute_frame.to_parquet(minute_path, index=False)

    manifest = {
        "source": "Massive Futures Basic ($0) REST API",
        "year": args.year,
        "candidate_tickers": tickers,
        "roll_rule": "highest prior-session aggregate volume among candidate contracts",
        "intervals": [
            {
                **interval,
                "first_session": interval["first_session"].isoformat(),
                "last_session": interval["last_session"].isoformat(),
            }
            for interval in intervals
        ],
        "api_calls": api_calls,
        "session_rows": int(len(session_frame)),
        "mapping_sessions": int(len(mapping)),
        "minute_rows": int(len(minute_frame)),
        "files": {
            path.name: {
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in (session_path, mapping_path, minute_path)
        },
    }
    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
