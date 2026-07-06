"""Run ResidualReversalStatArb v1 validation on cached Tiingo daily bars."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.artifacts import ArtifactManager
from experiments.models import DuplicateExperimentError
from experiments.registry import ExperimentRegistry
from research.csmr_data import load_csmr_panel
from research.residual_reversal_experiment import build_residual_reversal_experiment_draft
from research.residual_reversal_pipeline import (
    format_residual_reversal_gauntlet_report,
    run_residual_reversal_validation_gauntlet,
)
from research.universes.residual_reversal_v1 import all_symbols, factor_symbols, stock_symbols
from storage.parquet_io import parquet_path

LABEL = "ResidualReversalStatArb-v1-LiquidLargeCapDaily-AlpacaSIP-2018-2026"
DATA_SOURCE = "alpaca_sip_static_residual_reversal_v1_adjusted_cached"
STORAGE_DIR = Path("data/parquet/equity")
SOURCE = "alpaca_sip"
FREQUENCY = "1d"
START = "2018-01-01"
MIN_STOCKS_WITH_DATA = 100


def cached_path(symbol: str) -> Path:
    return parquet_path(STORAGE_DIR, symbol, FREQUENCY, source=SOURCE)


def main() -> int:
    symbols = all_symbols()
    factors = set(factor_symbols())
    print("ResidualReversalStatArb v1 validation")
    print(f"label={LABEL}")
    print(f"data_source={DATA_SOURCE}")
    print(f"symbols={len(symbols)} stocks={len(stock_symbols())} factors={tuple(factor_symbols())}")
    print("planned_requests=0 (cached Alpaca SIP daily bars only)")

    paths: list[Path] = []
    missing: dict[str, str] = {}
    for symbol in symbols:
        path = cached_path(symbol)
        if path.exists():
            paths.append(path)
        else:
            missing[symbol] = str(path)

    missing_factors = sorted(symbol for symbol in missing if symbol in factors)
    loaded_stocks = sorted(symbol for symbol in symbols if symbol not in factors and symbol not in missing)
    print(f"cache_summary paths={len(paths)} loaded_stocks={len(loaded_stocks)} missing={len(missing)}")
    if missing:
        print("missing_symbols:")
        for symbol, path in missing.items():
            print(f"  {symbol}: {path}")

    if missing_factors:
        print(f"BLOCKED: missing required factor symbols: {missing_factors}")
        print("Run: python scripts/download_residual_reversal_tiingo_daily.py")
        return 2
    if len(loaded_stocks) < MIN_STOCKS_WITH_DATA:
        print(
            f"BLOCKED: need at least {MIN_STOCKS_WITH_DATA} stock symbols with data; "
            f"got {len(loaded_stocks)}"
        )
        print("Run: python scripts/download_residual_reversal_tiingo_daily.py")
        return 2

    panel = load_csmr_panel(paths, start=START, normalize_daily_index=True)
    print(f"panel_shape={panel.shape} start={panel.index.min()} end={panel.index.max()}")

    registry = ExperimentRegistry("experiments")
    artifacts = ArtifactManager(registry.root)
    try:
        experiment = None
        try:
            draft = build_residual_reversal_experiment_draft(
                panel,
                label=LABEL,
                data_source=DATA_SOURCE,
                storage_dir=str(STORAGE_DIR / SOURCE),
                random_seed=42,
            )
            experiment = registry.create(draft)
        except DuplicateExperimentError as exc:
            experiment = registry.get(exc.existing_uuid)
            print(f"reusing_existing_experiment={experiment.uuid}")

        report = run_residual_reversal_validation_gauntlet(
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
        print(format_residual_reversal_gauntlet_report(report))
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
