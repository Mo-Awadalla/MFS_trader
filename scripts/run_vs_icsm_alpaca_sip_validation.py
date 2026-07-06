"""Run bounded VS-ICSM validation on cached/downloaded Alpaca SIP 1-hour bars.

This is a real-data validation runner, but the default symbol list is a bounded
static liquid-stock panel for API-budget reasons. It is not a full PIT top-200
universe reconstruction unless the caller supplies that universe externally.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.alpaca_downloader import AlpacaDownloader
from data.base import DownloadRequest
from experiments.artifacts import ArtifactManager
from experiments.models import DuplicateExperimentError
from experiments.registry import ExperimentRegistry
from research.vs_icsm_experiment import build_vs_icsm_experiment_draft
from research.vs_icsm_pipeline import (
    format_vs_icsm_gauntlet_report,
    run_vs_icsm_validation_gauntlet,
)
from storage.parquet_io import read_bars, write_bars
from strategies.vs_icsm.signal import default_params

SYMBOLS = (
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "GOOG",
    "TSLA",
    "AVGO",
    "JPM",
    "LLY",
    "UNH",
    "XOM",
    "V",
    "MA",
    "COST",
    "NFLX",
    "AMD",
    "CRM",
    "ORCL",
)
START = "2021-01-01"
END = "2025-12-31"
CACHE_DIR = Path("data/parquet/vs_icsm_static20/alpaca_sip")


def cache_path(symbol: str) -> Path:
    return CACHE_DIR / f"{symbol}_1h.parquet"


def load_or_download(symbol: str, downloader: AlpacaDownloader, refresh: bool = False) -> pd.DataFrame:
    path = cache_path(symbol)
    if path.exists() and not refresh:
        df = read_bars(path)
        print(f"cache {symbol:5s} bars={len(df):6d} start={df.index.min()} end={df.index.max()}")
        return df

    request = DownloadRequest(symbol=symbol, start_date=START, end_date=END, frequency="1h")
    result = None
    for attempt in range(1, 4):
        try:
            result = downloader.download(request)
            break
        except Exception as exc:  # noqa: BLE001 - batch symbol failures but back off 429s
            if "429" not in str(exc) or attempt == 3:
                raise
            wait_seconds = 75 * attempt
            print(f"rate_limit {symbol:5s} attempt={attempt} sleeping={wait_seconds}s")
            time.sleep(wait_seconds)
    if result is None:
        raise RuntimeError(f"download did not return a result for {symbol}")
    df = result.data
    write_bars(df, path)
    print(f"store {symbol:5s} bars={len(df):6d} start={df.index.min()} end={df.index.max()}")
    return df


def build_panel(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    ordered = []
    for symbol in sorted(frames):
        df = frames[symbol][["open", "high", "low", "close", "volume"]].copy()
        df.columns = pd.MultiIndex.from_product([[symbol], df.columns], names=["symbol", "field"])
        ordered.append(df)
    panel = pd.concat(ordered, axis=1).sort_index()
    panel = panel.loc[~panel.index.duplicated(keep="last")]
    return panel


def main() -> int:
    refresh = "--refresh" in sys.argv
    downloader = AlpacaDownloader(feed="sip")
    if not downloader.is_available():
        print("BLOCKED: ALPACA_API_KEY/ALPACA_API_SECRET are not configured")
        return 2

    print("VS-ICSM Alpaca SIP validation")
    print(f"symbols={len(SYMBOLS)} start={START} end={END} refresh={refresh}")
    print("planned_requests=0 (all cached)" if all(cache_path(s).exists() and not refresh for s in SYMBOLS) else f"planned_requests<={len(SYMBOLS)}")

    frames: dict[str, pd.DataFrame] = {}
    failures: dict[str, str] = {}
    for symbol in SYMBOLS:
        try:
            df = load_or_download(symbol, downloader, refresh=refresh)
            if not df.empty:
                frames[symbol] = df
        except Exception as exc:  # noqa: BLE001 - batch symbol failures for operator report
            failures[symbol] = str(exc)
            print(f"fail  {symbol:5s} error={exc}")

    print(f"download_summary stored_or_loaded={len(frames)} failed={len(failures)}")
    if failures:
        print("failures:")
        for symbol, error in failures.items():
            print(f"  {symbol}: {error}")
    if len(frames) < default_params().top_k:
        print(f"BLOCKED: need at least top_k={default_params().top_k} symbols with data; got {len(frames)}")
        return 2

    panel = build_panel(frames)
    print(f"panel_shape={panel.shape} start={panel.index.min()} end={panel.index.max()}")

    registry = ExperimentRegistry("experiments")
    artifacts = ArtifactManager(registry.root)
    try:
        experiment = None
        try:
            draft = build_vs_icsm_experiment_draft(
                panel,
                label="VS-ICSM-v1-static20-Alpaca-SIP-2021-2025",
                data_source="alpaca_sip_static20",
                random_seed=42,
            )
            experiment = registry.create(draft)
        except DuplicateExperimentError as exc:
            experiment = registry.get(exc.existing_uuid)
            print(f"reusing_existing_experiment={experiment.uuid}")

        report = run_vs_icsm_validation_gauntlet(
            panel,
            registry=registry,
            artifacts=artifacts,
            experiment=experiment,
            experiment_label="VS-ICSM-v1-static20-Alpaca-SIP-2021-2025",
            data_source="alpaca_sip_static20",
            seed=42,
            mc_num_paths=10000,
            mc_block_size=5,
        )
        print(format_vs_icsm_gauntlet_report(report))
        print("gauntlet_summary=", report.gauntlet.to_dict())
        print("experiment_uuid=", report.experiment_uuid)
        if report.experiment_uuid:
            print("validation_report=", registry.root / report.experiment_uuid / "validation" / "report.json")
            print("validation_verdict=", registry.root / report.experiment_uuid / "validation" / "verdict.txt")
    finally:
        registry.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
