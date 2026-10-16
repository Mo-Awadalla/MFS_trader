from __future__ import annotations

import pytest
import responses
from responses import matchers

from data.alpaca_downloader import AlpacaDownloader
from data.base import DownloadRequest


@responses.activate
def test_alpaca_downloader_uses_iex_feed_by_default():
    downloader = AlpacaDownloader(api_key="key", api_secret="secret")
    responses.add(
        responses.GET,
        "https://data.alpaca.markets/v2/stocks/AAPL/bars",
        json={
            "bars": [
                {
                    "t": "2024-01-02T14:30:00Z",
                    "o": 185.08,
                    "h": 185.89,
                    "l": 184.58,
                    "c": 185.65,
                    "v": 48100,
                }
            ]
        },
        match=[
            matchers.query_param_matcher(
                {
                    "timeframe": "1Min",
                    "start": "2024-01-02T00:00:00+00:00",
                    "end": "2024-01-03T00:00:00+00:00",
                    "limit": "10000",
                    "adjustment": "all",
                    "feed": "iex",
                }
            )
        ],
    )

    result = downloader.download(
        DownloadRequest(
            symbol="AAPL",
            start_date="2024-01-02",
            end_date="2024-01-03",
            frequency="1min",
        )
    )

    assert result.metadata["feed"] == "iex"
    assert len(result.data) == 1


@pytest.mark.parametrize("location", [
    "https://untrusted.example/bars", "http://data.alpaca.markets/bars",
])
@responses.activate
def test_credential_bearing_download_refuses_redirect(location):
    origin = "https://data.alpaca.markets/v2/stocks/AAPL/bars"
    responses.get(origin, status=302, headers={"Location": location})
    responses.get(location, json={"bars": []})
    downloader = AlpacaDownloader(api_key="offline-key", api_secret="offline-secret")
    with pytest.raises(RuntimeError, match="redirect"):
        downloader.download(DownloadRequest(
            symbol="AAPL", start_date="2024-01-02", end_date="2024-01-03", frequency="1d",
        ))
    assert [call.request.url.split("?")[0] for call in responses.calls] == [origin]
