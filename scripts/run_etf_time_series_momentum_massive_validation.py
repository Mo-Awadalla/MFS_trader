"""Run ETF TSM validation as a successor Experiment on Massive daily data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from data.massive_downloader import MASSIVE_ETF_TSM_SYMBOLS
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
from storage.parquet_io import read_bars

SYMBOLS = MASSIVE_ETF_TSM_SYMBOLS
CACHE_DIR = Path("data/parquet/equity/massive_rest")
LABEL = "ETFTimeSeriesMomentumVolTarget-v1-MassiveSplitAdjustedDaily-2021-2026"
DATA_SOURCE = "massive_rest_adjusted_daily_etf_tsm_v1"
DATA_VERSION = "massive_rest_split_adjusted_ohlcv_etf_tsm_v1_2021_2026"


def build_panel() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for symbol in SYMBOLS:
        path = CACHE_DIR / f"{symbol}_1d.parquet"
        if not path.exists():
            raise FileNotFoundError(f"missing Massive daily bars for {symbol}: {path}")
        data = read_bars(path).loc[:, ["open", "high", "low", "close", "volume"]].astype(float)
        data.columns = pd.MultiIndex.from_product([[symbol], data.columns], names=["symbol", "field"])
        frames.append(data)
    panel = pd.concat(frames, axis=1, sort=True).sort_index()
    return panel.loc[~panel.index.duplicated(keep="last")]


def main() -> int:
    print("ETF time-series momentum vol-target validation: Massive split-adjusted daily")
    print(f"symbols={len(SYMBOLS)} {SYMBOLS}")

    try:
        panel = build_panel()
    except FileNotFoundError as exc:
        print(f"BLOCKED: {exc}")
        return 2

    print(f"panel_shape={panel.shape} start={panel.index.min()} end={panel.index.max()}")
    registry = ExperimentRegistry("experiments")
    artifacts = ArtifactManager(registry.root)
    try:
        try:
            draft = build_etf_time_series_momentum_experiment_draft(
                panel,
                label=LABEL,
                data_source=DATA_SOURCE,
                data_version=f"{DATA_VERSION}@{len(panel)}x{len(SYMBOLS)}",
                adjustment="split",
                storage_dir=str(CACHE_DIR),
                random_seed=42,
            )
            experiment = registry.create(draft)
        except DuplicateExperimentError as exc:
            experiment = registry.get(exc.existing_uuid)
            print(f"reusing_existing_experiment={experiment.uuid}")

        existing_report = registry.root / experiment.uuid / "validation" / "report.json"
        if existing_report.exists():
            print(f"existing immutable validation evidence found: {existing_report}")
            return 0

        report = run_etf_time_series_momentum_validation_gauntlet(
            panel,
            registry=registry,
            experiment=experiment,
            experiment_label=LABEL,
            data_source=DATA_SOURCE,
            artifacts=artifacts,
            seed=42,
            mc_num_paths=10_000,
            mc_block_size=20,
        )
        print(format_etf_time_series_momentum_gauntlet_report(report))
        print(f"experiment_uuid={report.experiment_uuid}")
        print(f"validation_report={registry.root / experiment.uuid / 'validation' / 'report.json'}")
        return 0
    finally:
        registry.close()


if __name__ == "__main__":
    raise SystemExit(main())
