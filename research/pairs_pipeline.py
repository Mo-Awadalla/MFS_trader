"""Pairs v1 research + validation pipeline."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from config.schema import CostModelConfig
from experiments.artifacts import ArtifactManager
from experiments.models import Experiment
from experiments.registry import ExperimentRegistry
from research.cross_sectional_pipeline import (
    CrossSectionalBacktestResult,
    CrossSectionalValidationReport,
    backtest_cross_sectional,
    format_cross_sectional_gauntlet_report,
    make_no_tuning_wfa_fns,
    run_no_tuning_cross_sectional_validation,
    run_no_tuning_sweep,
)
from research.cross_sectional_pipeline import (
    build_returns_matrix as build_cross_sectional_returns_matrix,
)
from research.pairs_experiment import STRATEGY_NAME, build_pairs_experiment_draft
from strategies.pairs.signal import (
    PairsParams,
    default_params,
    generate_signals,
    params_to_dict,
)

PARAM_COLUMNS = [
    "formation_window_days",
    "entry_zscore",
    "exit_zscore",
    "stop_zscore",
    "rebalance_frequency",
    "pair_test",
]
PairsBacktestResult = CrossSectionalBacktestResult
PairsValidationReport = CrossSectionalValidationReport


def backtest_pairs(
    df: pd.DataFrame,
    params: PairsParams | None = None,
    *,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
) -> CrossSectionalBacktestResult:
    """Run a vectorized cross-sectional Pairs v1 backtest."""
    return backtest_cross_sectional(
        df,
        params or default_params(),
        strategy_name=STRATEGY_NAME,
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        cost_config=cost_config,
        initial_capital=initial_capital,
    )


def run_pairs_sweep(
    df: pd.DataFrame,
    *,
    params: PairsParams | None = None,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
) -> pd.DataFrame:
    """Return the single canonical Pairs v1 result row."""
    return run_no_tuning_sweep(
        df,
        params or default_params(),
        strategy_name=STRATEGY_NAME,
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        sweep_metadata={"rebalance_frequency": "monthly", "pair_test": "engle_granger"},
        cost_config=cost_config,
        initial_capital=initial_capital,
    )


def make_pairs_wfa_fns(
    df: pd.DataFrame,
    *,
    params: PairsParams | None = None,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
) -> tuple[Any, Any]:
    """Build WFA train/test callables for no-tuning Pairs v1."""
    return make_no_tuning_wfa_fns(
        df,
        params or default_params(),
        strategy_name=STRATEGY_NAME,
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        cost_config=cost_config,
        initial_capital=initial_capital,
    )


def build_returns_matrix(
    df: pd.DataFrame,
    *,
    params: PairsParams | None = None,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
) -> np.ndarray:
    return build_cross_sectional_returns_matrix(
        df,
        params or default_params(),
        strategy_name=STRATEGY_NAME,
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        cost_config=cost_config,
        initial_capital=initial_capital,
    )


def run_pairs_validation_gauntlet(
    df: pd.DataFrame,
    *,
    params: PairsParams | None = None,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
    seed: int = 42,
    registry: ExperimentRegistry | None = None,
    experiment: Experiment | None = None,
    experiment_label: str | None = None,
    data_source: str = "research_panel",
    config_version: str = "research.toml@0.1.0",
    artifacts: ArtifactManager | None = None,
    write_artifacts: bool = True,
    mc_num_paths: int = 10000,
    mc_block_size: int = 20,
) -> CrossSectionalValidationReport:
    """Run Pairs v1 research and full Validation Gauntlet."""
    return run_no_tuning_cross_sectional_validation(
        df,
        params or default_params(),
        strategy_name=STRATEGY_NAME,
        report_title="Pairs v1 Validation Report",
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        build_experiment_draft=build_pairs_experiment_draft,
        param_columns=PARAM_COLUMNS,
        sweep_metadata={"rebalance_frequency": "monthly", "pair_test": "engle_granger"},
        replay_reason=(
            "engine replay is currently single-symbol; Pairs evidence uses deterministic "
            "vectorized pair-spread target weights with explicit pair lifecycle diagnostics"
        ),
        cost_config=cost_config,
        initial_capital=initial_capital,
        seed=seed,
        registry=registry,
        experiment=experiment,
        experiment_label=experiment_label,
        data_source=data_source,
        config_version=config_version,
        artifacts=artifacts,
        write_artifacts=write_artifacts,
        mc_num_paths=mc_num_paths,
        mc_block_size=mc_block_size,
    )


def format_pairs_gauntlet_report(report: CrossSectionalValidationReport) -> str:
    return format_cross_sectional_gauntlet_report(report)
