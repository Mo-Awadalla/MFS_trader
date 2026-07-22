"""CCXT crypto data downloader — OHLCV candles from supported exchanges.

Requires the `ccxt` package. Coinbase configs use COINBASE_API_KEY /
COINBASE_SECRET, but public historical data works without auth (read-only).
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
import structlog

from data.base import BaseDownloader, DownloadRequest, DownloadResult

log = structlog.get_logger(__name__)


class CCXTDownloader(BaseDownloader):
    """Download OHLCV candles from a CCXT-supported exchange."""

    def __init__(
        self,
        exchange_id: str = "coinbase",
        api_key: str | None = None,
        api_secret: str | None = None,
        is_testnet: bool = False,
        max_retries: int = 5,
        retry_backoff_seconds: float = 1.0,
    ):
        try:
            import ccxt
        except ImportError as e:
            raise ImportError("ccxt is required for crypto data. Install: pip install ccxt") from e

        self._exchange_id = exchange_id
        self._ccxt = ccxt
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds

        exchange_class = getattr(ccxt, exchange_id)
        # Coinbase's market loader calls a private fee-summary endpoint whenever
        # credentials are attached. Historical OHLCV is public, so keep this
        # read-only data client unauthenticated.
        use_credentials = exchange_id != "coinbase"
        self._exchange = exchange_class(
            {
                "apiKey": api_key if use_credentials and api_key else "",
                "secret": api_secret if use_credentials and api_secret else "",
                "enableRateLimit": True,
            }
        )
        if exchange_id == "coinbase":
            self._exchange.rateLimit = max(self._exchange.rateLimit, 100)
        if is_testnet and "test" in self._exchange.urls:
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
        timeframe = mapping[frequency]
        if self._exchange.timeframes and timeframe not in self._exchange.timeframes:
            raise ValueError(
                f"CCXT exchange {self._exchange_id!r} does not support timeframe {timeframe!r}"
            )
        return timeframe

    def download(self, request: DownloadRequest) -> DownloadResult:
        timeframe = self._freq_to_ccxt(request.frequency)
        since = int(pd.Timestamp(request.start_date, tz="UTC").timestamp() * 1000)
        end_ms = (
            int(pd.Timestamp(request.end_date, tz="UTC").timestamp() * 1000)
            if request.end_date
            else int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
        )

        all_ohlcv: list[list[Any]] = []
        limit = {"binance": 1000, "coinbase": 300}.get(self._exchange_id, 1000)
        timeframe_ms = self._ccxt.Exchange.parse_timeframe(timeframe) * 1000

        while since < end_ms:
            previous_since = since
            ohlcv = self._fetch_ohlcv_page(
                request.symbol,
                timeframe,
                since=since,
                limit=limit,
            )
            if not ohlcv:
                since += limit * timeframe_ms
                continue
            all_ohlcv.extend(ohlcv)
            last_timestamp = ohlcv[-1][0]
            if last_timestamp <= previous_since:
                break
            # Move since to the last timestamp + 1ms
            since = last_timestamp + 1

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

    def _fetch_ohlcv_page(
        self,
        symbol: str,
        timeframe: str,
        *,
        since: int,
        limit: int,
    ) -> list[list[Any]]:
        """Fetch one page with bounded retries for transient CCXT network errors."""
        for retry in range(self._max_retries + 1):
            try:
                return self._exchange.fetch_ohlcv(
                    symbol,
                    timeframe,
                    since=since,
                    limit=limit,
                )
            except self._ccxt.NetworkError as exc:
                if retry >= self._max_retries:
                    raise
                delay = self._retry_backoff_seconds * (2**retry)
                log.warning(
                    "ccxt_page_retry",
                    symbol=symbol,
                    exchange=self._exchange_id,
                    since=since,
                    retry=retry + 1,
                    max_retries=self._max_retries,
                    delay_seconds=delay,
                    error=str(exc),
                )
                if delay > 0:
                    time.sleep(delay)

        raise RuntimeError("unreachable CCXT retry state")
