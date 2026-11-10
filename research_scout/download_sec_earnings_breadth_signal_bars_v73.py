"""Download only free 2021-2023 Alpaca IEX signal bars needed by v73."""

from __future__ import annotations

import bisect
import concurrent.futures
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from research.universes.residual_reversal_v1 import stock_symbols

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ROOT / "data" / "parquet" / "sec_filings" / "sec_filing_events.parquet"
CALENDAR = ROOT / "data" / "parquet" / "equity" / "alpaca_sip" / "SPY_1d.parquet"
OUTPUT_DIR = ROOT / "external_artifacts" / "alpaca_iex_sec_earnings_v73"
OUTPUT = OUTPUT_DIR / "signal_bars_30min_2021_2023.parquet"
MANIFEST = OUTPUT_DIR / "manifest.json"
START = "2021-01-01T00:00:00Z"
END = "2024-01-01T00:00:00Z"


def load_dotenv_without_overwrite() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def item_tokens(value: Any) -> set[str]:
    return {token for token in re.split(r"[,;\s]+", str(value).strip()) if token}


def event_map() -> tuple[pd.DataFrame, set[tuple[str, str]]]:
    calendar = pd.read_parquet(CALENDAR)
    sessions = sorted(
        pd.to_datetime(calendar["timestamp"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.date.astype(str)
        .unique()
        .tolist()
    )
    session_set = set(sessions)
    events = pd.read_parquet(EVENTS)
    events["symbol"] = events["symbol"].astype(str).str.upper()
    events["acceptance_local"] = pd.to_datetime(
        events["acceptance_datetime"], utc=True, errors="coerce"
    ).dt.tz_convert("America/New_York")
    events = events[
        events["form"].astype(str).str.upper().isin(["8-K", "8-K/A"])
        & events["items"].map(lambda value: "2.02" in item_tokens(value))
        & events["symbol"].isin(stock_symbols())
        & events["acceptance_local"].notna()
    ].copy()

    def assign(timestamp: pd.Timestamp) -> str | None:
        day = timestamp.date().isoformat()
        clock = timestamp.hour * 3600 + timestamp.minute * 60 + timestamp.second
        if day in session_set and clock <= 9 * 3600 + 25 * 60:
            return day
        if clock >= 16 * 3600:
            position = bisect.bisect_right(sessions, day)
            return sessions[position] if position < len(sessions) else None
        return None

    events["session_date"] = events["acceptance_local"].map(assign)
    events = events[
        events["session_date"].astype(str).between("2021-01-01", "2023-12-31")
    ].sort_values(
        ["session_date", "symbol", "acceptance_local", "accession_number"],
        kind="stable",
    )
    events = events.drop_duplicates(["session_date", "symbol"], keep="first")
    pairs = set(zip(events["session_date"], events["symbol"]))
    for day in events["session_date"].unique():
        pairs.add((str(day), "SPY"))
    return events, pairs


def request_session(
    session_date: str, symbols: list[str], headers: dict[str, str]
) -> list[dict[str, Any]]:
    url = "https://data.alpaca.markets/v2/stocks/bars"
    start = pd.Timestamp(f"{session_date} 09:30", tz="America/New_York").tz_convert("UTC")
    end = pd.Timestamp(f"{session_date} 10:30", tz="America/New_York").tz_convert("UTC")
    page_token: str | None = None
    selected: list[dict[str, Any]] = []
    while True:
        params: dict[str, Any] = {
            "symbols": ",".join(symbols),
            "timeframe": "30Min",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "limit": 10000,
            "adjustment": "all",
            "feed": "iex",
            "sort": "asc",
        }
        if page_token:
            params["page_token"] = page_token
        for attempt in range(7):
            response = requests.get(url, headers=headers, params=params, timeout=60)
            if response.status_code != 429:
                response.raise_for_status()
                break
            time.sleep(float(response.headers.get("Retry-After", 2 ** attempt)))
        else:
            raise RuntimeError("Alpaca rate limit persisted after retries")
        payload = response.json()
        for symbol, bars in payload.get("bars", {}).items():
            for bar in bars:
                selected.append(
                    {
                        "symbol": symbol,
                        "timestamp": bar["t"],
                        "open": bar["o"],
                        "high": bar["h"],
                        "low": bar["l"],
                        "close": bar["c"],
                        "volume": bar["v"],
                        "trade_count": bar.get("n"),
                        "vwap": bar.get("vw"),
                    }
                )
        page_token = payload.get("next_page_token")
        if not page_token:
            return selected


def main() -> None:
    load_dotenv_without_overwrite()
    key = os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_API_SECRET", "")
    if not key or not secret:
        raise RuntimeError("Alpaca credentials are not configured")
    events, required_pairs = event_map()
    symbols = sorted(set(events["symbol"]).union({"SPY"}))
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    rows: list[dict[str, Any]] = []
    requests_by_day = {
        str(day): sorted(set(group["symbol"]).union({"SPY"}))
        for day, group in events.groupby("session_date", sort=True)
    }
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(request_session, day, day_symbols, headers): day
            for day, day_symbols in requests_by_day.items()
        }
        for future in concurrent.futures.as_completed(futures):
            rows.extend(future.result())
    frame = pd.DataFrame(rows)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    local = frame["timestamp"].dt.tz_convert("America/New_York")
    frame["session_date"] = local.dt.date.astype(str)
    frame["local_clock"] = local.dt.strftime("%H:%M")
    frame = frame[
        frame["local_clock"].isin(["09:30", "10:00"])
        & pd.Series(
            list(zip(frame["session_date"], frame["symbol"])),
            index=frame.index,
        ).isin(required_pairs)
    ].sort_values(["session_date", "symbol", "timestamp"])
    if frame.duplicated(["session_date", "symbol", "local_clock"]).any():
        raise RuntimeError("Duplicate signal bars")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(OUTPUT, index=False)
    manifest = {
        "candidate": "v73",
        "source": "Alpaca Historical Stock Bars API",
        "feed": "iex",
        "timeframe": "30Min",
        "adjustment": "all",
        "requested_start": START,
        "requested_end": END,
        "paid_data": False,
        "databento_call": False,
        "event_rows": int(len(events)),
        "event_sessions": int(events["session_date"].nunique()),
        "symbols_requested": len(symbols),
        "stored_rows": int(len(frame)),
        "output_sha256": sha256(OUTPUT),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
