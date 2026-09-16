"""BB research + validation pipeline.

Wires BB signals into research backtests, parameter sweeps, WFA, and the
Validation Gauntlet (WFA + MC + DSR + stability). No paper trading here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from config.schema import AssetClass, CostModelConfig
from experiments.models import Experiment, PromotionStatus
from experiments.registry import ExperimentRegistry
from research.bb_defaults import default_cost_config
from research.bb_experiment import build_bb_experiment_draft
from research.runner import BacktestResult, print_report, run_single_asset_backtest
from strategies.bb.signal import (
    BBParams,
    default_params,
    params_from_dict,
    params_to_dict,
    sweep_grid,
)
from strategies.registry import get_strategy, strategy_template_version
from validation.gauntlet import GauntletResult, run_gauntlet
from validation.wfa.engine import PRESETS, WFATier

STRATEGY_NAME = "bollinger_bands"
_BB_STRATEGY = get_strategy(STRATEGY_NAME)
PARAM_COLUMNS = ["window", "std_mult", "width_mode"]


def backtest_bb(
    df: pd.DataFrame,
    params: BBParams,
    *,
    symbol: str = "AAPL",
    asset_class: AssetClass = AssetClass.EQUITY,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
) -> BacktestResult:
    """Run a single BB backtest on OHLCV data."""
    cost_config = cost_config or default_cost_config()
    signals = _BB_STRATEGY.generate_signals(df, params)
    return run_single_asset_backtest(
        df,
        signals,
        strategy_name=STRATEGY_NAME,
        symbol=symbol,
        asset_class=asset_class,
        cost_config=cost_config,
        initial_capital=initial_capital,
        params={
            **params_to_dict(params),
            "strategy_template_version": strategy_template_version(STRATEGY_NAME),
        },
    )


def run_bb_sweep(
    df: pd.DataFrame,
    *,
    grid: list[BBParams] | None = None,
    symbol: str = "AAPL",
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
) -> pd.DataFrame:
    """Sweep BB parameters and return a results DataFrame for DSR/stability."""
    cost_config = cost_config or default_cost_config()
    grid = grid or sweep_grid()
    rows: list[dict[str, Any]] = []

    for params in grid:
        result = backtest_bb(
            df,
            params,
            symbol=symbol,
            cost_config=cost_config,
            initial_capital=initial_capital,
        )
        row = {
            **params_to_dict(params),
            **result.metrics,
            "trade_count": result.trade_count,
        }
        rows.append(row)

    return pd.DataFrame(rows)


def make_bb_wfa_fns(
    *,
    cost_config: CostModelConfig | None = None,
    grid: list[BBParams] | None = None,
    symbol: str = "AAPL",
    initial_capital: float = 10000.0,
) -> tuple[Callable[..., dict[str, Any]], Callable[..., dict[str, Any]]]:
    """Build WFA train/test callables for BB."""
    cost_config = cost_config or default_cost_config()
    grid = grid or sweep_grid()

    def train_fn(train_df: pd.DataFrame, **kwargs: Any) -> dict[str, Any]:
        best_params = default_params()
        best_sharpe = float("-inf")
        for params in grid:
            result = backtest_bb(
                train_df,
                params,
                symbol=symbol,
                cost_config=cost_config,
                initial_capital=initial_capital,
            )
            sharpe = float(result.metrics.get("sharpe", 0.0))
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_params = params
        return params_to_dict(best_params)

    def test_fn(test_df: pd.DataFrame, fitted_params: dict[str, Any]) -> dict[str, Any]:
        params = params_from_dict(fitted_params)
        result = backtest_bb(
            test_df,
            params,
            symbol=symbol,
            cost_config=cost_config,
            initial_capital=initial_capital,
        )
        metrics = dict(result.metrics)
        metrics["returns"] = result.returns
        return metrics

    return train_fn, test_fn


def build_returns_matrix(
    df: pd.DataFrame,
    sweep_df: pd.DataFrame,
    *,
    cost_config: CostModelConfig | None = None,
    symbol: str = "AAPL",
    initial_capital: float = 10000.0,
) -> np.ndarray:
    """Build a full-sweep returns matrix for DSR trial-scope evidence."""
    if sweep_df.empty:
        return np.empty((0, 0))

    cost_config = cost_config or default_cost_config()
    series_list: list[pd.Series] = []

    for _, row in sweep_df.sort_values("sharpe", ascending=False, kind="stable").iterrows():
        params = params_from_dict(row.to_dict())
        result = backtest_bb(
            df,
            params,
            symbol=symbol,
            cost_config=cost_config,
            initial_capital=initial_capital,
        )
        returns = result.returns.reindex(df.index, fill_value=0.0).fillna(0.0)
        series_list.append(returns.rename(f"{params.window}_{params.std_mult}_{params.width_mode}"))

    matrix = pd.concat(series_list, axis=1).fillna(0.0)
    return matrix.to_numpy()


def _selected_sweep_trial_index(
    sweep_df: pd.DataFrame,
    params: BBParams,
) -> tuple[int | None, str | None]:
    """Locate the frozen parameter set in build_returns_matrix column order."""
    if sweep_df.empty:
        return None, "the BB sweep is empty"
    target = params_to_dict(params)
    missing = [name for name in target if name not in sweep_df.columns]
    if missing:
        return None, f"the BB sweep lacks frozen parameter fields: {', '.join(missing)}"

    matches = pd.Series(True, index=sweep_df.index)
    for name, value in target.items():
        column = sweep_df[name]
        if isinstance(value, float):
            matches &= pd.to_numeric(column, errors="coerce").eq(value)
        else:
            matches &= column.eq(value)
    match_count = int(matches.sum())
    if match_count != 1:
        return None, f"the frozen BB parameter set matches {match_count} sweep rows; expected exactly one"

    selected_position = int(np.flatnonzero(matches.to_numpy())[0])
    ordered_positions = (
        sweep_df.assign(_dsr_position=np.arange(len(sweep_df)))
        .sort_values("sharpe", ascending=False, kind="stable")["_dsr_position"]
        .to_numpy()
    )
    return int(np.flatnonzero(ordered_positions == selected_position)[0]), None


@dataclass
class BBValidationReport:
    """Full BB validation artifact: research + gauntlet."""

    symbol: str
    frequency: str
    params: BBParams
    research: BacktestResult
    sweep: pd.DataFrame
    gauntlet: GauntletResult
    replay_attribution: dict[str, Any] = field(default_factory=dict)
    experiment_uuid: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "frequency": self.frequency,
            "experiment_uuid": self.experiment_uuid,
            "strategy_template_version": strategy_template_version(STRATEGY_NAME),
            "params": params_to_dict(self.params),
            "research": {
                "metrics": self.research.metrics,
                "trade_count": self.research.trade_count,
                "bar_count": self.research.bar_count,
            },
            "sweep_rows": len(self.sweep),
            "gauntlet": self.gauntlet.to_dict(),
            "replay_attribution": self.replay_attribution,
        }


def run_bb_research_report(
    df: pd.DataFrame,
    *,
    params: BBParams | None = None,
    symbol: str = "AAPL",
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
) -> BacktestResult:
    """Run the boring first BB experiment research report."""
    params = params or default_params()
    return backtest_bb(
        df,
        params,
        symbol=symbol,
        cost_config=cost_config,
        initial_capital=initial_capital,
    )


def run_bb_validation_gauntlet(
    df: pd.DataFrame,
    *,
    params: BBParams | None = None,
    symbol: str = "AAPL",
    sweep_grid_override: list[BBParams] | None = None,
    wfa_grid_override: list[BBParams] | None = None,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
    seed: int = 42,
    registry: ExperimentRegistry | None = None,
    experiment: Experiment | None = None,
    experiment_label: str | None = None,
    data_source: str = "synthetic",
) -> BBValidationReport:
    """Run BB research, sweep, and full Validation Gauntlet.

    When ``registry`` is provided, registers the experiment (or uses ``experiment``)
    and records validation outcome in promotion_status.
    """
    params = params or default_params()
    cost_config = cost_config or default_cost_config()
    sweep_grid_list = sweep_grid_override or sweep_grid()
    wfa_grid_list = wfa_grid_override or sweep_grid_list

    active_experiment = experiment
    if registry is not None:
        if active_experiment is None:
            if experiment_label is None:
                raise ValueError("experiment_label required when registry is provided without experiment")
            draft = build_bb_experiment_draft(
                df,
                label=experiment_label,
                params=params,
                symbol=symbol,
                data_source=data_source,
                random_seed=seed,
                cost_config=cost_config,
            )
            active_experiment = registry.create(draft)
        registry.transition_promotion_status(
            active_experiment.uuid,
            PromotionStatus.VALIDATION_RUNNING,
        )

    research = run_bb_research_report(
        df,
        params=params,
        symbol=symbol,
        cost_config=cost_config,
        initial_capital=initial_capital,
    )
    sweep_df = run_bb_sweep(
        df,
        grid=sweep_grid_list,
        symbol=symbol,
        cost_config=cost_config,
        initial_capital=initial_capital,
    )
    train_fn, test_fn = make_bb_wfa_fns(
        cost_config=cost_config,
        grid=wfa_grid_list,
        symbol=symbol,
        initial_capital=initial_capital,
    )
    returns_matrix = build_returns_matrix(
        df,
        sweep_df,
        cost_config=cost_config,
        symbol=symbol,
        initial_capital=initial_capital,
    )
    selected_trial_index, dsr_selection_error = _selected_sweep_trial_index(sweep_df, params)
    selected_sharpe = float(research.metrics.get("sharpe", 0.0))
    matrix_covers_sweep = returns_matrix.ndim == 2 and returns_matrix.shape[1] == len(sweep_df)
    if dsr_selection_error is None and not matrix_covers_sweep:
        dsr_selection_error = "returns_matrix does not contain exactly one column for every BB sweep row"

    gauntlet = run_gauntlet(
        STRATEGY_NAME,
        df,
        train_fn,
        test_fn,
        sweep_df,
        PARAM_COLUMNS,
        best_sharpe=selected_sharpe,
        returns_matrix=returns_matrix,
        dsr_selected_trial_index=selected_trial_index,
        dsr_selected_returns=(
            returns_matrix[:, selected_trial_index]
            if selected_trial_index is not None
            and matrix_covers_sweep
            and selected_trial_index < returns_matrix.shape[1]
            else None
        ),
        dsr_search_scope="complete Bollinger Bands parameter sweep used for this validation run",
        dsr_selection_error=dsr_selection_error,
        dsr_sharpe_annualization_factor=252.0,
        initial_capital=initial_capital,
        wfa_config=PRESETS[WFATier.PRIMARY],
        seed=seed,
    )

    if registry is not None and active_experiment is not None:
        final_status = (
            PromotionStatus.VALIDATION_PASSED
            if gauntlet.passed
            else PromotionStatus.VALIDATION_FAILED
        )
        registry.transition_promotion_status(active_experiment.uuid, final_status)

    return BBValidationReport(
        symbol=symbol,
        frequency="1d",
        params=params,
        research=research,
        sweep=sweep_df,
        gauntlet=gauntlet,
        experiment_uuid=active_experiment.uuid if active_experiment else None,
    )


def format_bb_gauntlet_report(report: BBValidationReport) -> str:
    """Render a human-readable BB validation summary."""
    lines = [
        "=" * 60,
        f"  BB Validation Report: {report.symbol} {report.frequency}",
        "=" * 60,
        f"  Params: {params_to_dict(report.params)}",
        f"  Research Sharpe: {report.research.metrics.get('sharpe', 0):.4f}",
        f"  Research trades: {report.research.trade_count}",
        f"  Sweep rows: {len(report.sweep)}",
        f"  Gauntlet passed: {report.gauntlet.passed}",
    ]
    if report.gauntlet.failure_reasons:
        lines.append("  Failures:")
        for reason in report.gauntlet.failure_reasons:
            lines.append(f"    - {reason}")
    lines.append("=" * 60)
    return "\n".join(lines)


def print_bb_validation_report(report: BBValidationReport) -> None:
    """Print research + gauntlet summaries."""
    print_report(report.research)
    print(format_bb_gauntlet_report(report))
