"""Tests for the Massive adjusted daily-bar downloader."""

from __future__ import annotations

import json

import pandas as pd
import pytest
import responses
from responses import matchers

from data.base import DownloadRequest
from data.massive_downloader import MassiveDownloader


@responses.activate
def test_massive_downloader_normalizes_daily_bars_and_records_safe_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MASSIVE_API_KEY", "test-secret")
    responses.add(
        responses.GET,
        "https://api.massive.test/v2/aggs/ticker/SPY/range/1/day/2024-01-02/2024-01-03",
        json={
            "status": "OK",
            "request_id": "req-1",
            "results": [
                {
                    "t": 1704153600000,
                    "o": 101.0,
                    "h": 103.0,
                    "l": 100.0,
                    "c": 102.0,
                    "v": 2000,
                },
                {
                    "t": 1704067200000,
                    "o": 99.0,
                    "h": 101.0,
                    "l": 98.0,
                    "c": 100.0,
                    "v": 1000,
                },
            ],
        },
        match=[
            matchers.query_param_matcher(
                {
                    "adjusted": "true",
                    "sort": "asc",
                    "limit": "50000",
                    "apiKey": "test-secret",
                }
            )
        ],
    )

    result = MassiveDownloader(base_url="https://api.massive.test").download(
        DownloadRequest(
            symbol="SPY",
            start_date="2024-01-02",
            end_date="2024-01-03",
            frequency="1d",
        )
    )

    assert list(result.data.columns) == ["open", "high", "low", "close", "volume"]
    assert result.data.index.tz == pd.Timestamp.now(tz="UTC").tz
    assert result.data.index.is_monotonic_increasing
    assert result.data.index[0] == pd.Timestamp("2024-01-01", tz="UTC")
    assert result.data.iloc[0].to_dict() == {
        "open": 99.0,
        "high": 101.0,
        "low": 98.0,
        "close": 100.0,
        "volume": 1000.0,
    }
    assert result.metadata["source"] == "massive_rest"
    assert result.metadata["request"]["parameters"] == {
        "adjusted": "true",
        "sort": "asc",
        "limit": 50000,
    }
    assert result.metadata["adjustment_semantics"] == (
        "Massive adjusted=true; split-adjusted prices, not dividend-adjusted"
    )
    assert result.metadata["row_count"] == 2
    assert result.metadata["range"] == {
        "start": "2024-01-01T00:00:00+00:00",
        "end": "2024-01-02T00:00:00+00:00",
    }
    assert len(result.metadata["content_sha256"]) == 64
    assert "test-secret" not in json.dumps(result.metadata)


@responses.activate
def test_massive_downloader_follows_pagination_without_persisting_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MASSIVE_API_KEY", "test-secret")
    url = "https://api.massive.test/v2/aggs/ticker/SPY/range/1/day/2024-01-02/2024-01-03"
    responses.add(
        responses.GET,
        url,
        json={
            "status": "OK",
            "request_id": "req-1",
            "results": [{"t": 1704067200000, "o": 99, "h": 101, "l": 98, "c": 100, "v": 1000}],
            "next_url": "/v2/aggs/ticker/SPY/range/1/day/2024-01-02/2024-01-03?cursor=page-2",
        },
        match=[
            matchers.query_param_matcher(
                {"adjusted": "true", "sort": "asc", "limit": "50000", "apiKey": "test-secret"}
            )
        ],
    )
    responses.add(
        responses.GET,
        url,
        json={
            "status": "OK",
            "request_id": "req-2",
            "results": [{"t": 1704153600000, "o": 101, "h": 103, "l": 100, "c": 102, "v": 2000}],
        },
        match=[
            matchers.query_param_matcher(
                {
                    "adjusted": "true",
                    "sort": "asc",
                    "limit": "50000",
                    "apiKey": "test-secret",
                    "cursor": "page-2",
                }
            )
        ],
    )

    result = MassiveDownloader(base_url="https://api.massive.test").download(
        DownloadRequest(symbol="SPY", start_date="2024-01-02", end_date="2024-01-03", frequency="1d")
    )

    assert len(result.data) == 2
    assert result.metadata["pages"] == 2
    assert result.metadata["request_ids"] == ["req-1", "req-2"]
    assert "test-secret" not in json.dumps(result.metadata)


def test_massive_downloader_requires_daily_frequency_and_environment_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    downloader = MassiveDownloader()
    request = DownloadRequest(symbol="SPY", start_date="2024-01-02", frequency="1d")

    assert not downloader.is_available()
    with pytest.raises(RuntimeError, match="MASSIVE_API_KEY"):
        downloader.download(request)
    with pytest.raises(ValueError, match="only 1d"):
        downloader.download(
            DownloadRequest(symbol="SPY", start_date="2024-01-02", frequency="1h")
        )


@responses.activate
def test_massive_request_errors_do_not_echo_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MASSIVE_API_KEY", "test-secret")
    responses.add(
        responses.GET,
        "https://api.massive.test/v2/aggs/ticker/SPY/range/1/day/2024-01-02/2024-01-03",
        status=500,
    )

    with pytest.raises(RuntimeError) as exc_info:
        MassiveDownloader(base_url="https://api.massive.test").download(
            DownloadRequest(symbol="SPY", start_date="2024-01-02", end_date="2024-01-03", frequency="1d")
        )

    assert "test-secret" not in str(exc_info.value)
