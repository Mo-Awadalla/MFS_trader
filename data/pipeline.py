"""Data pipeline coordinator — download → validate → store to Parquet.

This is the main entry point for fetching and storing OHLCV data.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from config.schema import AssetClass, DataConfig
from data.alpaca_downloader import AlpacaDownloader
from data.base import BaseDownloader, DownloadRequest
from data.ccxt_downloader import CCXTDownloader
from data.resample import resample_to
from data.validate import QualityResult, validate_ohlcv
from storage.parquet_io import append_bars, parquet_path

log = structlog.get_logger(__name__)


def build_downloader(data_config: DataConfig, api_key: str, api_secret: str, is_paper: bool = True) -> BaseDownloader:
    """Construct the appropriate downloader for an asset class."""
    if data_config.asset_class == AssetClass.EQUITY:
        return AlpacaDownloader(api_key=api_key, api_secret=api_secret)
    elif data_config.asset_class == AssetClass.CRYPTO:
        return CCXTDownloader(
            exchange_id=data_config.exchange or "coinbase",
            api_key=api_key,
            api_secret=api_secret,
            is_testnet=is_paper,
        )
    else:
        raise ValueError(f"Unknown asset class: {data_config.asset_class}")


def download_and_store(
    data_config: DataConfig,
    downloader: BaseDownloader,
    environment: str = "research",
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Download bars for all symbols, validate, and store to Parquet.

    Returns a summary dict with per-symbol results.
    """
    summary: dict[str, Any] = {"symbols": {}, "source": downloader.source_name}

    for symbol in data_config.symbols:
        log.info("downloading", symbol=symbol, source=downloader.source_name)
        request = DownloadRequest(
            symbol=symbol,
            start_date=data_config.start_date,
            end_date=data_config.end_date,
            frequency=data_config.bar_frequency_raw,
        )

        try:
            result = downloader.download(request)
        except Exception as e:
            log.error("download_failed", symbol=symbol, error=str(e))
            summary["symbols"][symbol] = {"status": "error", "error": str(e)}
            continue

        # Validate
        report = validate_ohlcv(
            result.data,
            symbol=symbol,
            source=downloader.source_name,
            frequency=data_config.bar_frequency_raw,
            is_live=(environment == "live"),
        )

        log.info(
            "validated",
            symbol=symbol,
            result=report.result.value,
            bars=report.bars_checked,
            issues=len(report.issues),
        )

        # Store to Parquet (only if PASS or WARN, never FAIL)
        stored = False
        if report.result != QualityResult.FAIL:
            path = parquet_path(
                data_config.storage_dir,
                symbol,
                data_config.bar_frequency_raw,
                source=downloader.source_name,
            )
            append_bars(result.data, path)
            stored = True

            # Also resample and store target frequencies
            for freq in data_config.target_frequencies:
                resampled = resample_to(result.data, freq)
                resampled_path = parquet_path(
                    data_config.storage_dir, symbol, freq, source=downloader.source_name
                )
                append_bars(resampled, resampled_path)

        # Log to data_quality table if DB provided
        if conn is not None:
            _log_quality(conn, report, environment, data_config.bar_frequency_raw, data_config)

        summary["symbols"][symbol] = {
            "status": report.result.value,
            "bars": report.bars_checked,
            "stored": stored,
            "issues": len(report.issues),
        }

    return summary


def _log_quality(
    conn: sqlite3.Connection,
    report: Any,
    environment: str,
    frequency: str,
    data_config: DataConfig,
) -> None:
    from storage.event_logger import utc_now_iso

    conn.execute(
        """INSERT INTO data_quality
           (timestamp, symbol, asset_class, source, exchange, result, bar_frequency,
            checks_run, issues_json, bars_checked, bars_failed, latest_bar_timestamp, environment)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            utc_now_iso(),
            report.symbol,
            data_config.asset_class.value,
            report.source,
            data_config.exchange,
            report.result.value,
            frequency,
            json.dumps(report.checks_run),
            json.dumps(report.issues_json),
            report.bars_checked,
            report.bars_failed,
            report.latest_bar_timestamp,
            environment,
        ),
    )
    conn.commit()


def load_bars(
    storage_dir: str | Path,
    symbol: str,
    frequency: str,
    source: str = "",
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Load bars from Parquet for a symbol at a given frequency."""
    from storage.parquet_io import read_bars

    path = parquet_path(storage_dir, symbol, frequency, source=source)
    if not path.exists():
        raise FileNotFoundError(f"No Parquet file at {path}")
    df = read_bars(path)
    if start:
        df = df[df.index >= pd.Timestamp(start, tz="UTC")]
    if end:
        df = df[df.index <= pd.Timestamp(end, tz="UTC")]
    return df
