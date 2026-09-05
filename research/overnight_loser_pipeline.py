"""Overnight loser research + validation pipeline.

Execution model: signal at the regular-session open (overnight return =
open / prior close - 1), enter at that open, exit at the same close. All
backtests run with ``entry_on_open=True`` (open-to-close returns, full daily
round-trip costs).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config.schema import CostModelConfig
from experiments.artifacts import ArtifactManager
from experiments.models import Experiment
from experiments.registry import ExperimentRegistry
from research.candidate_metrics import (
    dsr_check,
    mc_check,
    standard_metrics,
    stress_window_report,
    wfa_check,
)
from research.candidate_registry import get_candidate
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
from research.overnight_loser_cost import overnight_loser_cost_config
from research.overnight_loser_data import load_overnight_loser_panel
from research.overnight_loser_experiment import (
    STRATEGY_NAME,
    build_overnight_loser_experiment_draft,
)
from strategies.overnight_loser.signal import (
    TEMPLATE_VERSION,
    OvernightLoserParams,
    default_params,
    generate_signals,
    params_from_dict,
    params_to_dict,
)

PARAM_COLUMNS = ["universe", "num_long_positions", "spread_bps", "delay_bps"]
SWEEP_METADATA = {"rebalance_frequency": "daily", "bucket_rule": "fixed_count"}
INITIAL_CAPITAL = 10_000.0
OvernightLoserBacktestResult = CrossSectionalBacktestResult
OvernightLoserValidationReport = CrossSectionalValidationReport


def backtest_overnight_loser(
    df: pd.DataFrame,
    params: OvernightLoserParams | None = None,
    *,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = INITIAL_CAPITAL,
) -> CrossSectionalBacktestResult:
    """Run a vectorized open-to-close overnight loser backtest."""
    params = params or default_params()
    return backtest_cross_sectional(
        df,
        params,
        strategy_name=STRATEGY_NAME,
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        cost_config=cost_config or overnight_loser_cost_config(params),
        initial_capital=initial_capital,
        entry_on_open=True,
        template_version=TEMPLATE_VERSION,
    )


def run_overnight_loser_sweep(
    df: pd.DataFrame,
    *,
    params: OvernightLoserParams | None = None,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = INITIAL_CAPITAL,
) -> pd.DataFrame:
    """Return the single canonical overnight loser v1 result row."""
    params = params or default_params()
    return run_no_tuning_sweep(
        df,
        params,
        strategy_name=STRATEGY_NAME,
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        sweep_metadata=SWEEP_METADATA,
        cost_config=cost_config or overnight_loser_cost_config(params),
        initial_capital=initial_capital,
        entry_on_open=True,
        template_version=TEMPLATE_VERSION,
    )


def make_overnight_loser_wfa_fns(
    df: pd.DataFrame,
    *,
    params: OvernightLoserParams | None = None,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = INITIAL_CAPITAL,
) -> tuple[Any, Any]:
    """Build WFA train/test callables for no-tuning overnight loser v1."""
    params = params or default_params()
    return make_no_tuning_wfa_fns(
        df,
        params,
        strategy_name=STRATEGY_NAME,
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        cost_config=cost_config or overnight_loser_cost_config(params),
        initial_capital=initial_capital,
        entry_on_open=True,
        template_version=TEMPLATE_VERSION,
    )


def build_returns_matrix(
    df: pd.DataFrame,
    *,
    params: OvernightLoserParams | None = None,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = INITIAL_CAPITAL,
) -> np.ndarray:
    params = params or default_params()
    return build_cross_sectional_returns_matrix(
        df,
        params,
        strategy_name=STRATEGY_NAME,
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        cost_config=cost_config or overnight_loser_cost_config(params),
        initial_capital=initial_capital,
        entry_on_open=True,
        template_version=TEMPLATE_VERSION,
    )


def run_overnight_loser_validation_gauntlet(
    df: pd.DataFrame,
    *,
    params: OvernightLoserParams | None = None,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = INITIAL_CAPITAL,
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
    """Run overnight loser research and full Validation Gauntlet."""
    params = params or default_params()
    return run_no_tuning_cross_sectional_validation(
        df,
        params,
        strategy_name=STRATEGY_NAME,
        report_title="Overnight Loser v1 Validation Report",
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        build_experiment_draft=build_overnight_loser_experiment_draft,
        param_columns=PARAM_COLUMNS,
        sweep_metadata=SWEEP_METADATA,
        replay_reason=(
            "engine replay is currently single-symbol; overnight loser evidence uses "
            "deterministic vectorized open-to-close cross-sectional weights"
        ),
        cost_config=cost_config or overnight_loser_cost_config(params),
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
        entry_on_open=True,
        template_version=TEMPLATE_VERSION,
    )


def format_overnight_loser_gauntlet_report(report: CrossSectionalValidationReport) -> str:
    return format_cross_sectional_gauntlet_report(report)


def run_variant(candidate_id: str) -> dict[str, Any]:
    """One-command evaluation of a pre-declared overnight loser candidate."""
    spec = get_candidate(candidate_id)
    params = params_from_dict(spec.parameters)
    cost_config = overnight_loser_cost_config(params)
    panel = load_overnight_loser_panel(params.universe)
    result = backtest_overnight_loser(panel, params, cost_config=cost_config)
    gross_result = backtest_overnight_loser(
        panel,
        params,
        cost_config=CostModelConfig(
            slippage_fixed_pct=0.0,
            slippage_variable_coeff=0.0,
            commission_pct=0.0,
            sec_fee_per_dollar_sold=0.0,
            finra_taf_per_share_sold=0.0,
            borrow_cost_annual_pct=0.0,
        ),
    )
    net_metrics = standard_metrics(
        result.returns,
        weights=result.weights,
        initial_capital=INITIAL_CAPITAL,
    )

    def _returns_fn(context: pd.DataFrame) -> pd.Series:
        return backtest_overnight_loser(context, params, cost_config=cost_config).returns

    artifact: dict[str, Any] = {
        "candidate": candidate_id,
        "family": spec.family,
        "status": "research_backtest_complete",
        "verdict": "not_promoted",
        "promotion_status": "research",
        "hypothesis": spec.hypothesis,
        "data": {
            **spec.data_requirements,
            "rows": int(len(panel)),
            "start": str(panel.index.min()),
            "end": str(panel.index.max()),
        },
        "execution_assumptions": {
            "signal": "regular-session open using open / prior close - 1",
            "execution": "enter at same open, exit at same close, flat overnight",
            "returns": "open-to-close intraday",
            "costs": (
                "5 bps slippage + 5 bps commission per side, plus spread_bps and "
                "delay_bps folded into slippage; full round trip charged every bar"
            ),
            "delay_limitation": (
                "delay_bps is a fixed-cost proxy for late entry; precise delay "
                "sensitivity requires 1-minute bars"
            ),
        },
        "params": params_to_dict(params),
        "gross_metrics": standard_metrics(gross_result.returns, initial_capital=INITIAL_CAPITAL),
        "net_metrics": net_metrics,
        "rebalance_count": result.rebalance_count,
        "skipped_rebalance_count": result.skipped_rebalance_count,
        "trade_count": result.trade_count,
        "stress_windows": stress_window_report(result.returns, initial_capital=INITIAL_CAPITAL),
        "wfa_primary": wfa_check(panel, _returns_fn, initial_capital=INITIAL_CAPITAL),
        "monte_carlo": mc_check(result.returns, initial_capital=INITIAL_CAPITAL),
        "dsr": dsr_check(
            result.returns,
            net_metrics.get("sharpe", 0.0),
            candidate=candidate_id,
        ),
        "required_next_step": "run_validation_gauntlet_before_paper_ops",
    }
    if spec.artifact_path:
        path = Path(spec.artifact_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(artifact, indent=2, default=str))
    return artifact
