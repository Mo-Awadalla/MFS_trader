from __future__ import annotations

from typing import Any

import pandas as pd

from data.alpaca_event_bars import AlpacaEventBarsDownloader


class _Response:
    def __init__(
        self,
        payload: dict[str, Any],
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class _Session:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def get(self, _url: str, **kwargs: Any) -> _Response:
        self.calls.append(kwargs)
        page_token = kwargs["params"].get("page_token")
        if page_token is None:
            return _Response(
                {
                    "bars": {
                        "AAPL": [
                            {
                                "t": "2024-06-03T13:30:00Z",
                                "o": 100,
                                "h": 101,
                                "l": 99,
                                "c": 100.5,
                                "v": 1000,
                                "n": 20,
                                "vw": 100.2,
                            }
                        ]
                    },
                    "next_page_token": "next",
                }
            )
        return _Response(
            {
                "bars": {
                    "SPY": [
                        {
                            "t": "2024-06-03T20:00:00Z",
                            "o": 500,
                            "h": 500,
                            "l": 500,
                            "c": 500,
                            "v": 1,
                            "n": 1,
                            "vw": 500,
                        },
                        {
                            "t": "2024-06-03T19:55:00Z",
                            "o": 500,
                            "h": 501,
                            "l": 499,
                            "c": 500.5,
                            "v": 2000,
                            "n": 40,
                            "vw": 500.2,
                        },
                    ]
                },
                "next_page_token": None,
            }
        )


def test_event_downloader_paginates_normalizes_and_filters_regular_session() -> None:
    session = _Session()
    downloader = AlpacaEventBarsDownloader(
        "key",
        "secret",
        session=session,
        feed="iex",
    )

    bars = downloader.download_session("2024-06-03", ["SPY", "AAPL"])

    assert len(session.calls) == 2
    assert session.calls[0]["params"]["symbols"] == "AAPL,SPY"
    assert session.calls[1]["params"]["page_token"] == "next"
    assert bars["symbol"].tolist() == ["AAPL", "SPY"]
    assert bars["timestamp"].tolist() == [
        pd.Timestamp("2024-06-03T13:30:00Z"),
        pd.Timestamp("2024-06-03T19:55:00Z"),
    ]
    assert bars["feed"].eq("iex").all()


def test_event_downloader_retries_rate_limit_response(monkeypatch: Any) -> None:
    responses = [
        _Response({}, status_code=429, headers={"Retry-After": "0"}),
        _Response({"bars": {}, "next_page_token": None}),
    ]

    class RateLimitSession:
        def get(self, _url: str, **_kwargs: Any) -> _Response:
            return responses.pop(0)

    monkeypatch.setattr("data.alpaca_event_bars.time.sleep", lambda _seconds: None)
    downloader = AlpacaEventBarsDownloader(
        "key",
        "secret",
        session=RateLimitSession(),
        delay_seconds=0.0,
        maximum_rate_limit_retries=1,
    )

    bars = downloader.download_session("2024-06-03", ["AAPL"])

    assert bars.empty
    assert not responses
