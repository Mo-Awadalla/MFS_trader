from __future__ import annotations

import pandas as pd
import pytest
import responses

from config.schema import AssetClass, DataConfig
from data.alpaca_downloader import AlpacaDownloader
from data.base import DownloadRequest, DownloadResult
from data.equity_contract import equity_request_bounds, equity_session_coverage
from data.pipeline import download_and_store
from scripts.download_etf_tsm_yahoo_daily import _parse_yahoo_chart_result


def test_date_bounds_include_last_new_york_day_and_preserve_dst():
    start, end = equity_request_bounds("2025-03-09", "2025-03-09")
    assert start.isoformat() == "2025-03-09T05:00:00+00:00"
    assert end.isoformat() == "2025-03-10T03:59:59.999999999+00:00"
    assert end - start + pd.Timedelta(nanoseconds=1) == pd.Timedelta(hours=23)
    assert (
        equity_request_bounds("2025-12-31", "2025-12-31")[1].tz_convert("America/New_York").day
        == 31
    )


def test_explicit_offset_end_is_not_expanded():
    start, end = equity_request_bounds("2025-01-02T09:30:00-05:00", "2025-01-02T10:00:00-05:00")
    assert end - start == pd.Timedelta(minutes=30)
    with pytest.raises(ValueError, match="precedes"):
        equity_request_bounds("2025-01-03", "2025-01-02")


def test_session_coverage_detects_whole_missing_day_holiday_and_early_close():
    start, end = equity_request_bounds("2025-07-03", "2025-07-07")
    index = pd.date_range(
        "2025-07-03 09:30",
        "2025-07-03 13:00",
        freq="30min",
        inclusive="left",
        tz="America/New_York",
    )
    frame = pd.DataFrame(index=index)
    audit = equity_session_coverage(frame, start, end, "30min")
    assert audit["complete_sessions_requested"] == 2  # July 4 holiday, then weekend.
    assert audit["incomplete_sessions"] == {"2025-07-07": 13}
    assert audit["expected_bars"] == 20
    with pytest.raises(ValueError, match="Duplicate"):
        equity_session_coverage(pd.concat([frame, frame]), start, end, "30min")


@responses.activate
def test_downloader_rejects_empty_complete_session_and_consumes_all_pages():
    url = "https://data.alpaca.markets/v2/stocks/SPY/bars"
    responses.add(responses.GET, url, json={"bars": [], "next_page_token": "next"})
    responses.add(responses.GET, url, json={"bars": [], "next_page_token": None})
    with pytest.raises(ValueError, match="Incomplete"):
        AlpacaDownloader(api_key="test", api_secret="test").download(
            DownloadRequest("SPY", "2025-01-02", "2025-01-02", "1d")
        )
    assert len(responses.calls) == 2
    assert "page_token=next" in responses.calls[1].request.url


@pytest.mark.parametrize("adjusted", [None, [], [None], [0], [float("inf")], [100, 101]])
def test_yahoo_never_silently_substitutes_raw_close(adjusted):
    result = {
        "timestamp": [1735833600],
        "indicators": {
            "quote": [{"open": [100], "high": [101], "low": [99], "close": [100], "volume": [1000]}]
        },
    }
    if adjusted is not None:
        result["indicators"]["adjclose"] = [{"adjclose": adjusted}]
    with pytest.raises(RuntimeError, match="adjusted"):
        _parse_yahoo_chart_result(result, "SPY")


def test_incomplete_equity_result_cannot_be_published(tmp_path):
    frame = pd.DataFrame(
        {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [1000.0]},
        index=pd.DatetimeIndex(["2025-01-02T14:30:00Z"], name="timestamp"),
    )

    class IncompleteDownloader:
        source_name = "alpaca"

        def download(self, request):
            return DownloadResult(
                request.symbol,
                self.source_name,
                frame,
                {"session_coverage": {"complete": False, "missing_bars": 389}},
            )

    config = DataConfig(
        symbols=["SPY"],
        asset_class=AssetClass.EQUITY,
        start_date="2025-01-02",
        end_date="2025-01-02",
        target_frequencies=[],
        storage_dir=str(tmp_path),
    )
    result = download_and_store(config, IncompleteDownloader())
    assert result["symbols"]["SPY"]["status"] == "FAIL"
    assert result["symbols"]["SPY"]["stored"] is False
    assert not list(tmp_path.rglob("*.parquet"))


def test_cached_stock_runner_rejects_missing_final_session(tmp_path, monkeypatch):
    from scripts import run_vs_icsm_alpaca_sip_validation as runner

    path = tmp_path / "SPY_1h.parquet"
    path.touch()
    frame = pd.DataFrame(
        index=pd.date_range("2025-12-30 09:00", periods=7, freq="1h", tz="America/New_York")
    )
    monkeypatch.setattr(runner, "cache_path", lambda symbol: path)
    monkeypatch.setattr(runner, "read_bars", lambda path: frame)
    monkeypatch.setattr(runner, "START", "2025-12-30")
    monkeypatch.setattr(runner, "END", "2025-12-31")
    with pytest.raises(ValueError, match="Cached SPY is incomplete"):
        runner.load_or_download("SPY", None)
