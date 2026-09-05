from __future__ import annotations

import io
import zipfile

import pandas as pd
import pytest

from data.base import DownloadRequest
from data.binance_vision_downloader import (
    BinanceVisionDownloader,
    VisionDataset,
    assert_funding_overlap_exact,
    validate_funding_schedule,
)


def _zip_csv(csv: str) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("data.csv", csv)
    return stream.getvalue()


def test_monthly_kline_path_and_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    downloader = BinanceVisionDownloader()
    timestamp = int(pd.Timestamp("2025-01-01", tz="UTC").timestamp() * 1000)
    payload = _zip_csv(f"{timestamp},1,3,0.5,2,10,0,20,4,6,12,0\n")
    monkeypatch.setattr(downloader, "_fetch_zip", lambda _url: payload)
    result = downloader.download(DownloadRequest("BTCUSDT", "2025-01-01", "2025-01-01"))
    assert result.data.iloc[0][["open", "high", "low", "close", "volume"]].to_dict() == {
        "open": 1.0, "high": 3.0, "low": 0.5, "close": 2.0, "volume": 10.0
    }
    assert result.data.iloc[0]["taker_buy_volume"] == 6.0
    assert downloader.archives(DownloadRequest("BTCUSDT", "2025-01-01", "2025-01-02"))[0].url.endswith(
        "/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2025-01.zip"
    )


def test_funding_schedule_and_exact_overlap() -> None:
    index = pd.date_range("2025-01-01", periods=4, freq="8h", tz="UTC")
    vision = pd.DataFrame({"funding_rate": [0.1, 0.2, 0.3, 0.4]}, index=index)
    validate_funding_schedule(vision, symbol="BTCUSDT")
    assert_funding_overlap_exact(vision, vision.copy())
    with pytest.raises(ValueError, match="missing=1"):
        validate_funding_schedule(vision.drop(index[1]), symbol="BTCUSDT")
    extra = pd.concat([vision, pd.DataFrame({"funding_rate": [0.5]},
                                            index=[pd.Timestamp("2025-01-01 04:00", tz="UTC")])])
    validate_funding_schedule(extra.sort_index(), symbol="BTCUSDT")


def test_metrics_must_use_daily_archives() -> None:
    with pytest.raises(ValueError, match="daily"):
        BinanceVisionDownloader(dataset=VisionDataset.METRICS, period="monthly")
