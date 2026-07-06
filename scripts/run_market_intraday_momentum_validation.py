"""Run market_intraday_momentum_v1 validation on cached 30-minute bars."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.artifacts import ArtifactManager
from experiments.models import DuplicateExperimentError
from experiments.registry import ExperimentRegistry
from research.market_intraday_momentum_experiment import (
    build_market_intraday_momentum_experiment_draft,
)
from research.market_intraday_momentum_pipeline import (
    format_market_intraday_momentum_gauntlet_report,
    run_market_intraday_momentum_validation_gauntlet,
)
from research.universes.market_intraday_momentum_v1 import all_symbols
from storage.parquet_io import read_bars

SYMBOLS = all_symbols()
DEFAULT_CACHE_DIR = Path("data/parquet/market_intraday_momentum/alpaca_sip")
DEFAULT_LABEL = "MarketIntradayMomentum-v1-AlpacaSIP-30m-2021-2026"
DEFAULT_DATA_SOURCE = "alpaca_sip_static_market_intraday_momentum_v1_30m_cached"
DEFAULT_DATA_VERSION_PREFIX = "alpaca_sip_adjusted_30m_static_market_intraday_momentum_v1"


def cache_path(symbol: str, cache_dir: Path) -> Path:
    return cache_dir / f"{symbol}_30min.parquet"


def load_symbol(symbol: str, cache_dir: Path) -> pd.DataFrame:
    path = cache_path(symbol, cache_dir)
    if not path.exists():
        raise FileNotFoundError(f"missing cached 30m bars for {symbol}: {path}")
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
    # Require complete synchronized ETF bars. Missing bars would break opening/close session semantics.
    panel = panel.dropna(how="any")
    return panel


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--label", default=DEFAULT_LABEL)
    parser.add_argument("--data-source", default=DEFAULT_DATA_SOURCE)
    parser.add_argument("--data-version-prefix", default=DEFAULT_DATA_VERSION_PREFIX)
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir)
    print("Market intraday momentum v1 validation: cached 30m bars")
    print(f"symbols={len(SYMBOLS)} {SYMBOLS}")
    print(f"cache_dir={cache_dir}")
    print(f"data_source={args.data_source}")
    print("strategy_rules=frozen from docs/research_scout/SwingDayTradingStrategySources-v1.md")

    frames: dict[str, pd.DataFrame] = {}
    failures: dict[str, str] = {}
    for symbol in SYMBOLS:
        try:
            frames[symbol] = load_symbol(symbol, cache_dir)
        except Exception as exc:  # noqa: BLE001 - batch failures for operator report
            failures[symbol] = str(exc)
            print(f"fail  {symbol:5s} error={exc}")

    if failures:
        print("BLOCKED: missing required cached 30m data")
        for symbol, error in failures.items():
            print(f"  {symbol}: {error}")
        print("Run: python scripts/download_market_intraday_momentum_30m.py --feed sip")
        return 2

    panel = build_panel(frames)
    print(f"panel_shape={panel.shape} start={panel.index.min()} end={panel.index.max()}")
    if panel.empty:
        print("BLOCKED: synchronized 30m panel is empty")
        return 2

    registry = ExperimentRegistry("experiments")
    artifacts = ArtifactManager(registry.root)
    try:
        experiment = None
        try:
            draft = build_market_intraday_momentum_experiment_draft(
                panel,
                label=args.label,
                data_source=args.data_source,
                data_version=f"{args.data_version_prefix}@{len(panel)}x{len(SYMBOLS)}",
                storage_dir=str(cache_dir),
                random_seed=42,
            )
            experiment = registry.create(draft)
        except DuplicateExperimentError as exc:
            experiment = registry.get(exc.existing_uuid)
            print(f"reusing_existing_experiment={experiment.uuid}")
            existing_report = registry.root / experiment.uuid / "validation" / "report.json"
            existing_verdict = registry.root / experiment.uuid / "validation" / "verdict.txt"
            if existing_report.exists():
                print("existing immutable validation evidence found; not rerunning")
                print("promotion_status=", experiment.promotion_status.value)
                print("validation_report=", existing_report)
                print("validation_verdict=", existing_verdict)
                return 0

        report = run_market_intraday_momentum_validation_gauntlet(
            panel,
            registry=registry,
            artifacts=artifacts,
            experiment=experiment,
            experiment_label=args.label,
            data_source=args.data_source,
            seed=42,
            mc_num_paths=10000,
            mc_block_size=13,
        )
        print(format_market_intraday_momentum_gauntlet_report(report))
        print("gauntlet_summary=", report.gauntlet.to_dict())
        print("intraday_summary=", report.intraday.to_dict() if report.intraday else None)
        print("experiment_uuid=", report.experiment_uuid)
        if report.experiment_uuid:
            print("validation_report=", registry.root / report.experiment_uuid / "validation" / "report.json")
            print("validation_verdict=", registry.root / report.experiment_uuid / "validation" / "verdict.txt")
    finally:
        registry.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
