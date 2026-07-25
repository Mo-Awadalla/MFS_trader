from __future__ import annotations

import json

import pytest
import responses
from responses import matchers

from data.alpaca_l1 import AlpacaHistoricalL1Client

URL = "https://data.alpaca.markets/v2/stocks/AAPL/trades"
BASE_PARAMS = {
    "start": "2026-07-08T13:30:00+00:00",
    "end": "2026-07-08T13:35:00+00:00",
    "limit": "1",
    "feed": "iex",
    "sort": "asc",
    "asof": "2026-07-08",
}


def _trade(timestamp: str, trade_id: int) -> dict[str, object]:
    return {
        "t": timestamp,
        "i": trade_id,
        "x": 2,
        "p": 210.5,
        "s": 100,
        "c": [0],
        "z": "C",
    }


@responses.activate
def test_trade_download_paginates_and_keeps_credentials_out_of_metadata():
    responses.add(
        responses.GET,
        URL,
        json={
            "trades": [_trade("2026-07-08T13:30:00.123456789Z", 1)],
            "next_page_token": "opaque-token",
        },
        headers={"X-Request-ID": "request-1"},
        match=[matchers.query_param_matcher(BASE_PARAMS)],
    )
    responses.add(
        responses.GET,
        URL,
        json={"trades": [_trade("2026-07-08T13:30:01.987654321Z", 2)]},
        headers={"X-Request-ID": "request-2"},
        match=[matchers.query_param_matcher({**BASE_PARAMS, "page_token": "opaque-token"})],
    )

    client = AlpacaHistoricalL1Client(api_key="key", api_secret="secret")
    result = client.download_trades(
        "AAPL",
        "2026-07-08T13:30:00Z",
        "2026-07-08T13:35:00Z",
        page_size=1,
        max_pages=2,
    )

    assert len(result.data) == 2
    assert str(result.data["timestamp"].dtype) == "datetime64[ns, UTC]"
    assert result.data.iloc[0]["timestamp"].nanosecond == 789
    assert result.data["page_index"].tolist() == [0, 1]
    assert result.data["row_index"].tolist() == [0, 0]
    assert result.data["ingestion_run_id"].nunique() == 1
    assert result.metadata["pagination_complete"] is True
    assert result.metadata["request_ids"] == ["request-1", "request-2"]
    serialized = json.dumps(result.metadata)
    assert "key" not in serialized
    assert "secret" not in serialized


@responses.activate
def test_page_cap_marks_download_incomplete():
    responses.add(
        responses.GET,
        URL,
        json={
            "trades": [_trade("2026-07-08T13:30:00Z", 1)],
            "next_page_token": "more",
        },
        match=[matchers.query_param_matcher(BASE_PARAMS)],
    )
    client = AlpacaHistoricalL1Client(api_key="key", api_secret="secret")

    result = client.download_trades(
        "AAPL",
        "2026-07-08T13:30:00Z",
        "2026-07-08T13:35:00Z",
        page_size=1,
        max_pages=1,
    )

    assert result.metadata["pagination_complete"] is False
    assert result.metadata["next_page_token_present"] is True


@responses.activate
def test_repeated_page_token_is_rejected():
    responses.add(
        responses.GET,
        URL,
        json={"trades": [], "next_page_token": "cycle"},
        match=[matchers.query_param_matcher(BASE_PARAMS)],
    )
    responses.add(
        responses.GET,
        URL,
        json={"trades": [], "next_page_token": "cycle"},
        match=[matchers.query_param_matcher({**BASE_PARAMS, "page_token": "cycle"})],
    )
    client = AlpacaHistoricalL1Client(api_key="key", api_secret="secret")

    with pytest.raises(RuntimeError, match="repeated page token"):
        client.download_trades(
            "AAPL",
            "2026-07-08T13:30:00Z",
            "2026-07-08T13:35:00Z",
            page_size=1,
            max_pages=3,
        )
