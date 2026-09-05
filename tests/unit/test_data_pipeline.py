"""Tests for durable incremental crypto downloads."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import responses
from responses import matchers

from config.schema import AssetClass, DataConfig
from data.base import DownloadRequest, DownloadResult
from data.pipeline import _download_ccxt_symbol_incrementally, build_downloader
from storage.parquet_io import parquet_path, read_bars


class ScriptedDownloader:
    source_name = "ccxt_coinbase"

    def __init__(self, download: Callable[[DownloadRequest], DownloadResult]) -> None:
        self.download = download


def _bars(request: DownloadRequest) -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [pd.Timestamp(request.start_date), pd.Timestamp(request.end_date)],
        name="timestamp",
    )
    return pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [10.0, 11.0],
        },
        index=index,
    )


def _result(request: DownloadRequest) -> DownloadResult:
    return DownloadResult(
        symbol=request.symbol,
        source="ccxt_coinbase",
        data=_bars(request),
        metadata={},
    )


def test_incremental_crypto_download_resumes_after_failed_chunk(tmp_path) -> None:
    config = DataConfig(
        symbols=["LTC/USD"],
        asset_class=AssetClass.CRYPTO,
        start_date="2024-01-01T00:00:00+00:00",
        end_date="2024-01-04T00:00:00+00:00",
        target_frequencies=[],
        exchange="coinbase",
        storage_dir=str(tmp_path),
    )
    first_calls: list[DownloadRequest] = []

    def fail_second_chunk(request: DownloadRequest) -> DownloadResult:
        first_calls.append(request)
        if len(first_calls) == 2:
            raise RuntimeError("simulated terminal network failure")
        return _result(request)

    first = _download_ccxt_symbol_incrementally(
        config,
        ScriptedDownloader(fail_second_chunk),
        "LTC/USD",
        environment="research",
        conn=None,
        chunk_days=1,
    )

    raw_path = parquet_path(tmp_path, "LTC/USD", "1min", source="ccxt_coinbase")
    checkpoint = read_bars(raw_path)
    assert first["status"] == "error"
    assert first["stored"] is True
    assert len(checkpoint) == 2

    resumed_calls: list[DownloadRequest] = []

    def complete(request: DownloadRequest) -> DownloadResult:
        resumed_calls.append(request)
        return _result(request)

    resumed = _download_ccxt_symbol_incrementally(
        config,
        ScriptedDownloader(complete),
        "LTC/USD",
        environment="research",
        conn=None,
        chunk_days=1,
    )

    assert pd.Timestamp(resumed_calls[0].start_date) > checkpoint.index.max()
    assert resumed["stored"] is True
    assert resumed["bars"] > len(checkpoint)


@responses.activate
def test_build_downloader_passes_explicit_equity_feed_and_adjustment() -> None:
    config = DataConfig(
        symbols=["SPY"],
        asset_class=AssetClass.EQUITY,
        feed="sip",
        adjustment="raw",
    )
    responses.add(
        responses.GET,
        "https://data.alpaca.markets/v2/stocks/SPY/bars",
        json={"bars": []},
        match=[
            matchers.query_param_matcher(
                {
                    "timeframe": "1Min",
                    "start": "2024-01-02T00:00:00+00:00",
                    "end": "2024-01-03T00:00:00+00:00",
                    "limit": "10000",
                    "adjustment": "raw",
                    "feed": "sip",
                }
            )
        ],
    )

    downloader = build_downloader(config, api_key="key", api_secret="secret")
    downloader.download(
        DownloadRequest(
            symbol="SPY",
            start_date="2024-01-02",
            end_date="2024-01-03",
            frequency="1min",
        )
    )
