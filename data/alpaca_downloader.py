"""Alpaca data downloader — US equity OHLCV bars.

Uses the Alpaca Markets Historical Bars API v2.
Requires ALPACA_API_KEY and ALPACA_API_SECRET environment variables.
"""

from __future__ import annotations

import os
from typing import Any

import pandas as pd
import requests

from data.base import BaseDownloader, DownloadRequest, DownloadResult


class AlpacaDownloader(BaseDownloader):
    """Downloads 1-min (or other frequency) bars from Alpaca Historical Data API."""

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        data_url: str = "https://data.alpaca.markets",
        feed: str | None = "iex",
    ):
        self._api_key = api_key or os.environ.get("ALPACA_API_KEY", "")
        self._api_secret = api_secret or os.environ.get("ALPACA_API_SECRET", "")
        self._data_url = data_url.rstrip("/")
        self._feed = feed

    @property
    def source_name(self) -> str:
        return "alpaca"

    def is_available(self) -> bool:
        return bool(self._api_key and self._api_secret)

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._api_secret,
        }

    def _freq_to_alpaca(self, frequency: str) -> str:
        mapping = {
            "1min": "1Min",
            "5min": "5Min",
            "15min": "15Min",
            "30min": "30Min",
            "1h": "1Hour",
            "1d": "1Day",
        }
        if frequency not in mapping:
            raise ValueError(f"Unsupported Alpaca frequency: {frequency}")
        return mapping[frequency]

    def download(self, request: DownloadRequest) -> DownloadResult:
        if not self.is_available():
            raise RuntimeError("Alpaca API credentials not configured")

        timeframe = self._freq_to_alpaca(request.frequency)
        start = pd.Timestamp(request.start_date, tz="UTC")
        end = pd.Timestamp(request.end_date, tz="UTC") if request.end_date else pd.Timestamp.now(tz="UTC")

        all_bars: list[dict[str, Any]] = []
        next_page_token: str | None = None

        url = f"{self._data_url}/v2/stocks/{request.symbol}/bars"

        while True:
            params: dict[str, Any] = {
                "timeframe": timeframe,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": 10000,
                "adjustment": "all",  # split + dividend adjusted
            }
            if self._feed:
                params["feed"] = self._feed
            if next_page_token:
                params["page_token"] = next_page_token

            resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            bars = data.get("bars", [])
            all_bars.extend(bars)

            next_page_token = data.get("next_page_token")
            if not next_page_token:
                break

        if not all_bars:
            df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
            df.index = pd.DatetimeIndex([], name="timestamp", tz="UTC")
        else:
            df = pd.DataFrame(all_bars)
            df["timestamp"] = pd.to_datetime(df["t"], utc=True)
            df = df[["timestamp", "o", "h", "l", "c", "v"]]
            df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
            df = df.set_index("timestamp").sort_index()
            df = df.astype(float)

        return DownloadResult(
            symbol=request.symbol,
            source=self.source_name,
            data=df,
            metadata={
                "frequency": request.frequency,
                "adjustment": "split_dividend",
                "feed": self._feed,
                "bar_count": len(df),
                "start": str(start),
                "end": str(end),
            },
        )
