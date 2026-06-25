"""CCXT crypto data downloader — OHLCV candles from Binance (and other exchanges).

Requires the `ccxt` package. Uses BINANCE_API_KEY / BINANCE_API_SECRET env vars
but works for public historical data without auth (read-only).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from data.base import BaseDownloader, DownloadRequest, DownloadResult


class CCXTDownloader(BaseDownloader):
    """Downloads OHLCV candles from a CCXT-supported exchange (default: Binance)."""

    def __init__(
        self,
        exchange_id: str = "binance",
        api_key: str | None = None,
        api_secret: str | None = None,
        is_testnet: bool = False,
    ):
        try:
            import ccxt
        except ImportError as e:
            raise ImportError("ccxt is required for crypto data. Install: pip install ccxt") from e

        self._exchange_id = exchange_id
        self._ccxt = ccxt

        exchange_class = getattr(ccxt, exchange_id)
        self._exchange = exchange_class(
            {
                "apiKey": api_key or "",
                "secret": api_secret or "",
                "enableRateLimit": True,
            }
        )
        if is_testnet and hasattr(self._exchange, "set_sandbox_mode"):
            self._exchange.set_sandbox_mode(True)

    @property
    def source_name(self) -> str:
        return f"ccxt_{self._exchange_id}"

    def is_available(self) -> bool:
        return self._exchange is not None

    def _freq_to_ccxt(self, frequency: str) -> str:
        mapping = {
            "1min": "1m",
            "5min": "5m",
            "15min": "15m",
            "30min": "30m",
            "1h": "1h",
            "4h": "4h",
            "1d": "1d",
        }
        if frequency not in mapping:
            raise ValueError(f"Unsupported CCXT frequency: {frequency}")
        return mapping[frequency]

    def download(self, request: DownloadRequest) -> DownloadResult:
        timeframe = self._freq_to_ccxt(request.frequency)
        since = int(pd.Timestamp(request.start_date, tz="UTC").timestamp() * 1000)
        end_ms = (
            int(pd.Timestamp(request.end_date, tz="UTC").timestamp() * 1000)
            if request.end_date
            else int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
        )

        all_ohlcv: list[list[Any]] = []
        limit = 1000  # Binance max per request

        while since < end_ms:
            ohlcv = self._exchange.fetch_ohlcv(request.symbol, timeframe, since=since, limit=limit)
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            # Move since to the last timestamp + 1ms
            since = ohlcv[-1][0] + 1
            if len(ohlcv) < limit:
                break

        # Filter to end_ms
        all_ohlcv = [row for row in all_ohlcv if row[0] <= end_ms]

        if not all_ohlcv:
            df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
            df.index = pd.DatetimeIndex([], name="timestamp", tz="UTC")
        else:
            df = pd.DataFrame(all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df = df.set_index("timestamp").sort_index()
            df = df.astype(float)

        return DownloadResult(
            symbol=request.symbol,
            source=self.source_name,
            data=df,
            metadata={
                "frequency": request.frequency,
                "exchange": self._exchange_id,
                "bar_count": len(df),
                "start": request.start_date,
                "end": request.end_date or "now",
            },
        )
