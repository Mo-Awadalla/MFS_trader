"""Download free signal-only 30-minute IEX bars for v75."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from research.universes.residual_reversal_v1 import stock_symbols

ROOT = Path(__file__).resolve().parents[1]
CALENDAR = ROOT / "data" / "parquet" / "equity" / "alpaca_sip" / "SPY_1d.parquet"
OUT_DIR = ROOT / "external_artifacts" / "alpaca_iex_breadth_v75"
OUTPUT = OUT_DIR / "signal_bars_30min_2021_2023.parquet"
MANIFEST = OUT_DIR / "manifest.json"


def load_env() -> None:
    for raw in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if raw.strip() and not raw.lstrip().startswith("#") and "=" in raw:
            key, value = raw.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def one_day(day: str, symbols: list[str], headers: dict[str, str]) -> list[dict[str, Any]]:
    start = pd.Timestamp(f"{day} 09:30", tz="America/New_York").tz_convert("UTC")
    end = pd.Timestamp(f"{day} 10:30", tz="America/New_York").tz_convert("UTC")
    url = "https://data.alpaca.markets/v2/stocks/bars"
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
    for attempt in range(7):
        response = requests.get(url, headers=headers, params=params, timeout=60)
        if response.status_code != 429:
            response.raise_for_status()
            break
        time.sleep(float(response.headers.get("Retry-After", 2 ** attempt)))
    else:
        raise RuntimeError("rate limit")
    rows = []
    for symbol, bars in response.json().get("bars", {}).items():
        for bar in bars:
            rows.append(
                {
                    "session_date": day,
                    "symbol": symbol,
                    "timestamp": bar["t"],
                    "open": bar["o"],
                    "close": bar["c"],
                }
            )
    return rows


def main() -> None:
    load_env()
    headers = {
        "APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"],
        "APCA-API-SECRET-KEY": os.environ["ALPACA_API_SECRET"],
    }
    daily = pd.read_parquet(CALENDAR)
    dates = (
        pd.to_datetime(daily["timestamp"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.date.astype(str)
    )
    dates = sorted(set(day for day in dates if "2021-01-01" <= day <= "2023-12-31"))
    symbols = sorted(set(stock_symbols()).union({"SPY"}))
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(one_day, day, symbols, headers) for day in dates]
        for future in concurrent.futures.as_completed(futures):
            rows.extend(future.result())
    frame = pd.DataFrame(rows)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["local_clock"] = frame["timestamp"].dt.tz_convert(
        "America/New_York"
    ).dt.strftime("%H:%M")
    frame = frame[frame["local_clock"].isin(["09:30", "10:00"])].sort_values(
        ["session_date", "symbol", "local_clock"]
    )
    if frame.duplicated(["session_date", "symbol", "local_clock"]).any():
        raise RuntimeError("duplicate bars")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(OUTPUT, index=False)
    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest().upper()
    manifest = {
        "candidate": "v75",
        "source": "Alpaca Historical Stock Bars API",
        "feed": "iex",
        "timeframe": "30Min",
        "sessions_requested": len(dates),
        "symbols_requested": len(symbols),
        "rows": len(frame),
        "sha256": digest,
        "paid_data": False,
        "databento_call": False,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
