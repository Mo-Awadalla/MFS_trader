"""Tests for the persisted Massive ETF daily download path."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from data.base import BaseDownloader, DownloadRequest, DownloadResult
from scripts.download_etf_tsm_massive_daily import download_and_store
from storage.parquet_io import parquet_path, read_bars


class _StubMassiveDownloader(BaseDownloader):
    @property
    def source_name(self) -> str:
        return "massive_rest"

    def is_available(self) -> bool:
        return True

    def download(self, request: DownloadRequest) -> DownloadResult:
        data = pd.DataFrame(
            {
                "open": [100.0, 101.0],
                "high": [101.0, 102.0],
                "low": [99.0, 100.0],
                "close": [100.5, 101.5],
                "volume": [1000.0, 1100.0],
            },
            index=pd.date_range("2024-01-02", periods=2, tz="UTC", name="timestamp"),
        )
        return DownloadResult(
            symbol=request.symbol,
            source=self.source_name,
            data=data,
            metadata={
                "source": self.source_name,
                "request": {"symbol": request.symbol},
                "content_sha256": "a" * 64,
            },
        )


def test_massive_download_persists_bars_and_redacted_manifest(tmp_path: Path) -> None:
    summary = download_and_store(
        _StubMassiveDownloader(),
        start="2024-01-02",
        end="2024-01-03",
        storage_dir=tmp_path,
        symbols=("SPY",),
    )

    path = parquet_path(tmp_path, "SPY", "1d", source="massive_rest")
    manifest = tmp_path / "massive_rest" / "manifest.json"
    assert summary["status"] == "complete"
    assert path.exists()
    assert read_bars(path).shape == (2, 5)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["symbols"]["SPY"]["status"] == "stored"
    assert "quality_issues" in payload["symbols"]["SPY"]
    assert payload["symbols"]["SPY"]["provenance"]["content_sha256"] == "a" * 64
    assert "apiKey" not in manifest.read_text(encoding="utf-8")
