"""Tests for exchange-aware CCXT OHLCV pagination."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd
import pytest

from data.base import DownloadRequest
from data.ccxt_downloader import CCXTDownloader

MINUTE_MS = 60_000
START = pd.Timestamp("2024-01-01", tz="UTC")
START_MS = int(START.timestamp() * 1000)


class StubExchange:
    """Minimal exchange stub whose page behavior is supplied by each test."""

    timeframes = {"1m": "1m"}

    def __init__(self, fetch: Callable[..., list[list[Any]]]) -> None:
        self.fetch_ohlcv = fetch


def candle(timestamp: int) -> list[float]:
    return [timestamp, 1.0, 2.0, 0.5, 1.5, 10.0]


def request(*, end_minutes: int) -> DownloadRequest:
    end = START + pd.Timedelta(minutes=end_minutes)
    return DownloadRequest(
        symbol="BTC/USD",
        start_date=START.isoformat(),
        end_date=end.isoformat(),
        frequency="1min",
    )


def test_coinbase_300_row_pages_are_fully_concatenated() -> None:
    downloader = CCXTDownloader(exchange_id="coinbase")
    calls: list[int] = []

    def fetch(_symbol: str, _timeframe: str, *, since: int, limit: int) -> list[list[Any]]:
        calls.append(since)
        assert limit == 300
        offset = 0 if len(calls) == 1 else 300
        if len(calls) <= 2:
            return [candle(START_MS + minute * MINUTE_MS) for minute in range(offset, offset + 300)]
        return []

    downloader._exchange = StubExchange(fetch)

    result = downloader.download(request(end_minutes=599))

    assert len(result.data) == 600
    assert len(calls) == 2
    assert result.source == "ccxt_coinbase"


def test_leading_empty_page_advances_and_later_data_is_collected() -> None:
    downloader = CCXTDownloader(exchange_id="coinbase")
    calls: list[int] = []

    def fetch(_symbol: str, _timeframe: str, *, since: int, limit: int) -> list[list[Any]]:
        calls.append(since)
        if len(calls) == 1:
            return []
        if len(calls) == 2:
            return [candle(START_MS + 300 * MINUTE_MS), candle(START_MS + 301 * MINUTE_MS)]
        return []

    downloader._exchange = StubExchange(fetch)

    result = downloader.download(request(end_minutes=601))

    assert len(result.data) == 2
    assert calls[1] == START_MS + 300 * MINUTE_MS


def test_stuck_timestamp_guard_terminates() -> None:
    downloader = CCXTDownloader(exchange_id="coinbase")
    calls = 0

    def fetch(_symbol: str, _timeframe: str, *, since: int, limit: int) -> list[list[Any]]:
        nonlocal calls
        calls += 1
        return [candle(since)]

    downloader._exchange = StubExchange(fetch)

    result = downloader.download(request(end_minutes=10))

    assert len(result.data) == 1
    assert calls == 1


def test_coinbase_testnet_flag_is_a_noop() -> None:
    downloader = CCXTDownloader(exchange_id="coinbase", is_testnet=True)

    assert downloader.source_name == "ccxt_coinbase"
    assert downloader._exchange.rateLimit >= 100


def test_coinbase_public_downloader_does_not_attach_credentials() -> None:
    downloader = CCXTDownloader(
        exchange_id="coinbase",
        api_key="configured-key",
        api_secret="configured-secret",
    )

    assert downloader._exchange.apiKey == ""
    assert downloader._exchange.secret == ""


def test_end_date_filtering_is_unchanged() -> None:
    downloader = CCXTDownloader(exchange_id="coinbase")

    def fetch(_symbol: str, _timeframe: str, *, since: int, limit: int) -> list[list[Any]]:
        return [candle(START_MS + 10 * MINUTE_MS), candle(START_MS + 11 * MINUTE_MS)]

    downloader._exchange = StubExchange(fetch)

    result = downloader.download(request(end_minutes=10))

    assert list(result.data.index) == [START + pd.Timedelta(minutes=10)]


def test_coinbase_rejects_unsupported_timeframe() -> None:
    downloader = CCXTDownloader(exchange_id="coinbase")

    with pytest.raises(ValueError, match="does not support timeframe '4h'"):
        downloader._freq_to_ccxt("4h")


def test_transient_network_error_is_retried() -> None:
    downloader = CCXTDownloader(
        exchange_id="coinbase",
        max_retries=2,
        retry_backoff_seconds=0.0,
    )
    calls = 0

    def fetch(_symbol: str, _timeframe: str, *, since: int, limit: int) -> list[list[Any]]:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise downloader._ccxt.NetworkError("temporary Coinbase failure")
        return [candle(START_MS + MINUTE_MS)]

    downloader._exchange = StubExchange(fetch)

    result = downloader.download(request(end_minutes=1))

    assert calls == 3
    assert len(result.data) == 1
