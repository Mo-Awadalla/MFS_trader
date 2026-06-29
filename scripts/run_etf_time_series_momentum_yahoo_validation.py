"""Run ETFTimeSeriesMomentumVolTarget-v1 validation on long-history Yahoo daily bars.

This is a new data-version Experiment for the same frozen strategy rules. It is
not a parameter or universe change.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.artifacts import ArtifactManager
from experiments.models import DuplicateExperimentError
from experiments.registry import ExperimentRegistry
from research.etf_time_series_momentum_experiment import (
    build_etf_time_series_momentum_experiment_draft,
)
from research.etf_time_series_momentum_pipeline import (
    format_etf_time_series_momentum_gauntlet_report,
    run_etf_time_series_momentum_validation_gauntlet,
)
from research.universes.etf_tactical_v1 import all_symbols
from storage.parquet_io import read_bars

SYMBOLS = all_symbols()
CACHE_DIR = Path("data/parquet/equity/yahoo_chart")
LABEL = "ETFTimeSeriesMomentumVolTarget-v1-YahooAdjustedDaily-2005-2026"
DATA_SOURCE = "yahoo_chart_static_etf_tsm_v1_adjusted_cached"
DATA_VERSION = "yahoo_chart_adjusted_ohlc_static_etf_tsm_v1_2005_2026"


def cache_path(symbol: str) -> Path:
    return CACHE_DIR / f"{symbol}_1d.parquet"


def load_symbol(symbol: str) -> pd.DataFrame:
    path = cache_path(symbol)
    if not path.exists():
        raise FileNotFoundError(f"missing cached Yahoo daily bars for {symbol}: {path}")
    df = read_bars(path)
    print(f"cache {symbol:5s} bars={len(df):5d} start={df.index.min()} end={df.index.max()}")
    return df


def build_panel(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    ordered = []
    for symbol in sorted(frames):
        df = frames[symbol][["open", "high", "low", "close", "volume"]].copy()
        df.columns = pd.MultiIndex.from_product([[symbol], df.columns], names=["symbol", "field"])
        ordered.append(df)
    panel = pd.concat(ordered, axis=1, sort=True).sort_index()
    panel = panel.loc[~panel.index.duplicated(keep="last")]
    return panel


def main() -> int:
    print("ETF time-series momentum vol-target validation: Yahoo adjusted long-history")
    print(f"symbols={len(SYMBOLS)} {SYMBOLS}")
    print("planned_requests=0 (cached daily bars only)")
    print("strategy_rules=unchanged_from_ETFTimeSeriesMomentumVolTarget-v1")

    frames: dict[str, pd.DataFrame] = {}
    failures: dict[str, str] = {}
    for symbol in SYMBOLS:
        try:
            frames[symbol] = load_symbol(symbol)
        except Exception as exc:  # noqa: BLE001 - batch symbol failures for operator report
            failures[symbol] = str(exc)
            print(f"fail  {symbol:5s} error={exc}")

    print(f"load_summary loaded={len(frames)} failed={len(failures)}")
    if failures:
        print("BLOCKED: missing required cached Yahoo ETF data")
        for symbol, error in failures.items():
            print(f"  {symbol}: {error}")
        print("Run: .venv/Scripts/python scripts/download_etf_tsm_yahoo_daily.py")
        return 2

    panel = build_panel(frames)
    print(f"panel_shape={panel.shape} start={panel.index.min()} end={panel.index.max()}")

    registry = ExperimentRegistry("experiments")
    artifacts = ArtifactManager(registry.root)
    try:
        experiment = None
        try:
            draft = build_etf_time_series_momentum_experiment_draft(
                panel,
                label=LABEL,
                data_source=DATA_SOURCE,
                data_version=f"{DATA_VERSION}@{len(panel)}x{len(SYMBOLS)}",
                storage_dir="data/parquet/equity/yahoo_chart",
                random_seed=42,
            )
            experiment = registry.create(draft)
        except DuplicateExperimentError as exc:
            experiment = registry.get(exc.existing_uuid)
            print(f"reusing_existing_experiment={experiment.uuid}")

        report = run_etf_time_series_momentum_validation_gauntlet(
            panel,
            registry=registry,
            artifacts=artifacts,
            experiment=experiment,
            experiment_label=LABEL,
            data_source=DATA_SOURCE,
            seed=42,
            mc_num_paths=10000,
            mc_block_size=20,
        )
        print(format_etf_time_series_momentum_gauntlet_report(report))
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
