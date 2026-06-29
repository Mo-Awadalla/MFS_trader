"""ETF time-series momentum research + validation pipeline."""

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
    write_validation_artifacts,
)
from research.cross_sectional_pipeline import (
    build_returns_matrix as build_cross_sectional_returns_matrix,
)
from research.etf_time_series_momentum_experiment import (
    STRATEGY_NAME,
    build_etf_time_series_momentum_experiment_draft,
)
from strategies.etf_time_series_momentum.signal import (
    ETFTimeSeriesMomentumParams,
    default_params,
    generate_signals,
    params_to_dict,
    sweep_grid,
)
from validation.gauntlet import run_gauntlet
from validation.wfa.engine import PRESETS, WFATier

PARAM_COLUMNS = [
    "momentum_lookback_days",
    "vol_lookback_days",
    "top_n",
    "max_symbol_weight",
]
ETFTimeSeriesMomentumBacktestResult = CrossSectionalBacktestResult
ETFTimeSeriesMomentumValidationReport = CrossSectionalValidationReport


def backtest_etf_time_series_momentum(
    df: pd.DataFrame,
    params: ETFTimeSeriesMomentumParams | None = None,
    *,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
) -> CrossSectionalBacktestResult:
    """Run a vectorized ETF time-series momentum backtest."""

    return backtest_cross_sectional(
        df,
        params or default_params(),
        strategy_name=STRATEGY_NAME,
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        cost_config=cost_config or default_cost_config(),
        initial_capital=initial_capital,
    )


def run_etf_time_series_momentum_sweep(
    df: pd.DataFrame,
    *,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
) -> pd.DataFrame:
    """Run the predeclared stability grid."""

    rows: list[dict[str, Any]] = []
    for i, params in enumerate(sweep_grid()):
        result = backtest_etf_time_series_momentum(
            df,
            params,
            cost_config=cost_config,
            initial_capital=initial_capital,
        )
        rows.append(
            {
                **params_to_dict(params),
                "grid_index": i,
                "rebalance_frequency": "monthly",
                "bucket_rule": "positive_absolute_momentum_top_n_inverse_vol_vol_target",
                **result.metrics,
                "trade_count": result.trade_count,
            }
        )
    return pd.DataFrame(rows)


def make_etf_time_series_momentum_wfa_fns(
    df: pd.DataFrame,
    *,
    params: ETFTimeSeriesMomentumParams | None = None,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
) -> tuple[Any, Any]:
    """Build WFA train/test callables for frozen ETF TSM v1."""

    return make_no_tuning_wfa_fns(
        df,
        params or default_params(),
        strategy_name=STRATEGY_NAME,
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        cost_config=cost_config or default_cost_config(),
        initial_capital=initial_capital,
    )


def build_returns_matrix(
    df: pd.DataFrame,
    *,
    params: ETFTimeSeriesMomentumParams | None = None,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
) -> np.ndarray:
    return build_cross_sectional_returns_matrix(
        df,
        params or default_params(),
        strategy_name=STRATEGY_NAME,
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        cost_config=cost_config or default_cost_config(),
        initial_capital=initial_capital,
    )


def run_etf_time_series_momentum_validation_gauntlet(
    df: pd.DataFrame,
    *,
    params: ETFTimeSeriesMomentumParams | None = None,
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
    """Run ETF TSM research and full Validation Gauntlet."""

    params = params or default_params()
    cost_config = cost_config or default_cost_config()
    active_experiment = experiment
    if registry is not None:
        from experiments.models import PromotionStatus

        if active_experiment is None:
            if experiment_label is None:
                raise ValueError("experiment_label required when registry is provided without experiment")
            draft = build_etf_time_series_momentum_experiment_draft(
                df,
                label=experiment_label,
                params=params,
                data_source=data_source,
                random_seed=seed,
                cost_config=cost_config,
                config_version=config_version,
            )
            active_experiment = registry.create(draft)
        registry.transition_promotion_status(active_experiment.uuid, PromotionStatus.VALIDATION_RUNNING)

    research = backtest_etf_time_series_momentum(
        df,
        params,
        cost_config=cost_config,
        initial_capital=initial_capital,
    )
    sweep_df = run_etf_time_series_momentum_sweep(
        df,
        cost_config=cost_config,
        initial_capital=initial_capital,
    )
    train_fn, test_fn = make_etf_time_series_momentum_wfa_fns(
        df,
        params=params,
        cost_config=cost_config,
        initial_capital=initial_capital,
    )
    returns_matrix = build_returns_matrix(
        df,
        params=params,
        cost_config=cost_config,
        initial_capital=initial_capital,
    )
    best_sharpe = float(research.metrics.get("sharpe", 0.0))
    gauntlet = run_gauntlet(
        STRATEGY_NAME,
        df,
        train_fn,
        test_fn,
        sweep_df,
        PARAM_COLUMNS,
        best_sharpe=best_sharpe,
        returns_matrix=returns_matrix,
        initial_capital=initial_capital,
        wfa_config=PRESETS[WFATier.PRIMARY],
        mc_num_paths=mc_num_paths,
        mc_block_size=mc_block_size,
        seed=seed,
    )

    replay_attribution = {
        "mode": "vectorized_cross_sectional_replay",
        "engine_replay_available": False,
        "reason": "engine replay is currently single-symbol; ETF TSM evidence uses deterministic vectorized ETF target weights",
        "execution_alignment": "signals use data before rebalance; target weights are held from the next bar",
    }
    if registry is not None and active_experiment is not None:
        from experiments.models import PromotionStatus

        registry.transition_promotion_status(
            active_experiment.uuid,
            PromotionStatus.VALIDATION_PASSED if gauntlet.passed else PromotionStatus.VALIDATION_FAILED,
        )

    report = CrossSectionalValidationReport(
        strategy_name=STRATEGY_NAME,
        report_title="ETF Time-Series Momentum Vol Target v1 Validation Report",
        params=params,
        params_dict=params_to_dict(params),
        research=research,
        sweep=sweep_df,
        gauntlet=gauntlet,
        replay_attribution=replay_attribution,
        experiment_uuid=active_experiment.uuid if active_experiment else None,
    )
    if write_artifacts and artifacts is not None and active_experiment is not None:
        write_validation_artifacts(artifacts, active_experiment.uuid, report)
    return report


def format_etf_time_series_momentum_gauntlet_report(
    report: CrossSectionalValidationReport,
) -> str:
    return format_cross_sectional_gauntlet_report(report)
