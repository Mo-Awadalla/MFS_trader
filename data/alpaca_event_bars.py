"""Event-session Alpaca bar downloader for bounded intraday scouts.

The downloader requests only symbols needed on a given event date, caches each
session independently, and preserves the provider feed in normalized output.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd
import requests

_BAR_COLUMNS = [
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trade_count",
    "vwap",
    "feed",
]


class AlpacaEventBarsDownloader:
    """Download regular-session bars for a small symbol set on one session."""

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        *,
        data_url: str = "https://data.alpaca.markets",
        feed: str = "iex",
        session: requests.Session | None = None,
        delay_seconds: float = 0.4,
        maximum_rate_limit_retries: int = 6,
    ) -> None:
        self.api_key = api_key or os.environ.get("ALPACA_API_KEY", "")
        self.api_secret = api_secret or os.environ.get("ALPACA_API_SECRET", "")
        self.data_url = data_url.rstrip("/")
        self.feed = str(feed)
        self.session = session or requests.Session()
        self.delay_seconds = max(0.0, float(delay_seconds))
        self.maximum_rate_limit_retries = max(0, int(maximum_rate_limit_retries))
        self._request_count = 0

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
        }

    def download_session(
        self,
        session_date: str,
        symbols: Iterable[str],
        *,
        frequency: str = "5min",
        adjustment: str = "all",
        timezone: str = "America/New_York",
    ) -> pd.DataFrame:
        if not self.is_available():
            raise RuntimeError("Alpaca API credentials not configured")
        normalized_symbols = sorted(
            {str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()}
        )
        if not normalized_symbols:
            raise ValueError("at least one symbol is required")
        timeframe = _alpaca_timeframe(frequency)
        start = pd.Timestamp(f"{session_date} 09:30:00", tz=timezone).tz_convert("UTC")
        end = pd.Timestamp(f"{session_date} 16:00:00", tz=timezone).tz_convert("UTC")
        url = f"{self.data_url}/v2/stocks/bars"
        rows: list[dict[str, Any]] = []
        next_page_token: str | None = None

        while True:
            params: dict[str, Any] = {
                "symbols": ",".join(normalized_symbols),
                "timeframe": timeframe,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": 10000,
                "adjustment": adjustment,
                "feed": self.feed,
                "sort": "asc",
            }
            if next_page_token:
                params["page_token"] = next_page_token
            response = self._request_with_rate_limit_retry(url, params)
            response.raise_for_status()
            payload = response.json()
            bars_by_symbol = payload.get("bars", {})
            if not isinstance(bars_by_symbol, dict):
                raise ValueError("Alpaca bars payload must contain a symbol mapping")
            for symbol, bars in bars_by_symbol.items():
                if not isinstance(bars, list):
                    continue
                rows.extend(_normalize_rows(str(symbol).upper(), bars, feed=self.feed))
            token = payload.get("next_page_token")
            next_page_token = str(token) if token else None
            if not next_page_token:
                break

        frame = pd.DataFrame(rows, columns=_BAR_COLUMNS)
        if frame.empty:
            return _empty_bars()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
        if frame["timestamp"].isna().any():
            raise ValueError("Alpaca returned invalid bar timestamps")
        local = frame["timestamp"].dt.tz_convert(timezone)
        clock_seconds = local.dt.hour * 3600 + local.dt.minute * 60 + local.dt.second
        frame = frame.loc[
            local.dt.date.astype(str).eq(str(session_date))
            & clock_seconds.between(9 * 3600 + 30 * 60, 16 * 3600 - 1)
        ]
        numeric = ["open", "high", "low", "close", "volume", "trade_count", "vwap"]
        frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
        frame = frame.drop_duplicates(["symbol", "timestamp"], keep="last")
        return frame.sort_values(["timestamp", "symbol"], kind="stable").reset_index(drop=True)

    def _request_with_rate_limit_retry(
        self,
        url: str,
        params: dict[str, Any],
    ) -> requests.Response:
        for attempt in range(self.maximum_rate_limit_retries + 1):
            if self._request_count and self.delay_seconds:
                time.sleep(self.delay_seconds)
            response = self.session.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=30,
            )
            self._request_count += 1
            if getattr(response, "status_code", 200) != 429:
                return response
            if attempt == self.maximum_rate_limit_retries:
                return response
            retry_after = getattr(response, "headers", {}).get("Retry-After")
            wait = float(retry_after) if retry_after else min(60.0, 2.0 ** (attempt + 1))
            time.sleep(max(wait, self.delay_seconds))
        raise RuntimeError("unreachable Alpaca retry state")


def _alpaca_timeframe(frequency: str) -> str:
    mapping = {
        "1min": "1Min",
        "5min": "5Min",
        "15min": "15Min",
        "30min": "30Min",
        "1h": "1Hour",
    }
    try:
        return mapping[frequency]
    except KeyError as exc:
        raise ValueError(f"unsupported Alpaca frequency: {frequency}") from exc


def _normalize_rows(symbol: str, bars: list[Any], *, feed: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        rows.append(
            {
                "symbol": symbol,
                "timestamp": bar.get("t"),
                "open": bar.get("o"),
                "high": bar.get("h"),
                "low": bar.get("l"),
                "close": bar.get("c"),
                "volume": bar.get("v"),
                "trade_count": bar.get("n"),
                "vwap": bar.get("vw"),
                "feed": feed,
            }
        )
    return rows


def _empty_bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": pd.Series(dtype="object"),
            "timestamp": pd.Series(dtype="datetime64[ns, UTC]"),
            "open": pd.Series(dtype="float64"),
            "high": pd.Series(dtype="float64"),
            "low": pd.Series(dtype="float64"),
            "close": pd.Series(dtype="float64"),
            "volume": pd.Series(dtype="float64"),
            "trade_count": pd.Series(dtype="float64"),
            "vwap": pd.Series(dtype="float64"),
            "feed": pd.Series(dtype="object"),
        }
    )


def download_event_sessions(
    events: pd.DataFrame,
    downloader: AlpacaEventBarsDownloader,
    *,
    cache_dir: str | Path,
    benchmark: str,
    frequency: str,
    adjustment: str,
    timezone: str,
    refresh: bool = False,
) -> pd.DataFrame:
    """Download/cache one exact regular-session slice per event date."""
    required = {"session_date", "symbol"}
    missing = required.difference(events.columns)
    if missing:
        raise ValueError(f"events missing required columns: {sorted(missing)}")
    root = Path(cache_dir)
    frames: list[pd.DataFrame] = []
    grouped = events.groupby("session_date", sort=True)
    total = grouped.ngroups
    for index, (session_date, group) in enumerate(grouped, start=1):
        date_text = str(session_date)
        required_symbols = {
            *group["symbol"].astype(str).str.upper().tolist(),
            str(benchmark).upper(),
        }
        path = root / f"date={date_text}" / "bars.parquet"
        cached: pd.DataFrame | None = None
        if path.exists() and not refresh:
            cached = pd.read_parquet(path)
            cached_symbols = set(cached.get("symbol", pd.Series(dtype="object")).astype(str))
            if not required_symbols.issubset(cached_symbols):
                cached = None
        if cached is None:
            cached = downloader.download_session(
                date_text,
                required_symbols,
                frequency=frequency,
                adjustment=adjustment,
                timezone=timezone,
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            cached.to_parquet(path, index=False)
        frames.append(cached)
        print(f"[{index}/{total}] {date_text} symbols={len(required_symbols)} bars={len(cached)}")
    if not frames:
        return _empty_bars()
    combined = pd.concat(frames, ignore_index=True)
    return (
        combined.drop_duplicates(["symbol", "timestamp"], keep="last")
        .sort_values(["timestamp", "symbol"], kind="stable")
        .reset_index(drop=True)
    )
