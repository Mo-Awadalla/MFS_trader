"""CSMR research + validation pipeline."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from config.schema import CostModelConfig
from experiments.artifacts import ArtifactManager
from experiments.models import Experiment
from experiments.registry import ExperimentRegistry
from research.bb_defaults import default_cost_config
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
from research.csmr_experiment import STRATEGY_NAME, build_csmr_experiment_draft
from strategies.csmr.signal import (
    CSMRParams,
    default_params,
    generate_signals,
    params_to_dict,
)

PARAM_COLUMNS = ["lookback_days", "rebalance_frequency", "bucket_rule"]
CSMRBacktestResult = CrossSectionalBacktestResult
CSMRValidationReport = CrossSectionalValidationReport


def backtest_csmr(
    df: pd.DataFrame,
    params: CSMRParams | None = None,
    *,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
) -> CrossSectionalBacktestResult:
    """Run a vectorized cross-sectional CSMR backtest."""
    return backtest_cross_sectional(
        df,
        params or default_params(),
        strategy_name=STRATEGY_NAME,
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        cost_config=cost_config,
        initial_capital=initial_capital,
    )


def run_csmr_sweep(
    df: pd.DataFrame,
    *,
    params: CSMRParams | None = None,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
) -> pd.DataFrame:
    """Return the single canonical CSMR v1 result row."""
    return run_no_tuning_sweep(
        df,
        params or default_params(),
        strategy_name=STRATEGY_NAME,
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        sweep_metadata={"rebalance_frequency": "weekly", "bucket_rule": "quartile"},
        cost_config=cost_config,
        initial_capital=initial_capital,
    )


def make_csmr_wfa_fns(
    df: pd.DataFrame | None = None,
    *,
    params: CSMRParams | None = None,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
) -> tuple[Any, Any]:
    """Build WFA train/test callables for no-tuning CSMR v1."""
    params = params or default_params()
    context_df = df
    if context_df is None:
        context_df = pd.DataFrame()

    if context_df.empty:
        cost_config = cost_config or default_cost_config()

        def train_fn(train_df: pd.DataFrame, **kwargs: Any) -> dict[str, Any]:
            return params_to_dict(params)

        def test_fn(test_df: pd.DataFrame, fitted_params: dict[str, Any]) -> dict[str, Any]:
            result = backtest_csmr(
                test_df,
                params,
                cost_config=cost_config,
                initial_capital=initial_capital,
            )
            metrics = dict(result.metrics)
            metrics["returns"] = result.returns
            return metrics

        return train_fn, test_fn

    return make_no_tuning_wfa_fns(
        context_df,
        params,
        strategy_name=STRATEGY_NAME,
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        cost_config=cost_config,
        initial_capital=initial_capital,
    )


def build_returns_matrix(
    df: pd.DataFrame,
    *,
    params: CSMRParams | None = None,
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


def run_csmr_validation_gauntlet(
    df: pd.DataFrame,
    *,
    params: CSMRParams | None = None,
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
    """Run CSMR research and full Validation Gauntlet."""
    return run_no_tuning_cross_sectional_validation(
        df,
        params or default_params(),
        strategy_name=STRATEGY_NAME,
        report_title="CSMR v1 Validation Report",
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        build_experiment_draft=build_csmr_experiment_draft,
        param_columns=PARAM_COLUMNS,
        sweep_metadata={"rebalance_frequency": "weekly", "bucket_rule": "quartile"},
        replay_reason="engine replay is currently single-symbol; CSMR evidence uses deterministic vectorized cross-sectional weights",
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


def format_csmr_gauntlet_report(report: CrossSectionalValidationReport) -> str:
    return format_cross_sectional_gauntlet_report(report)
