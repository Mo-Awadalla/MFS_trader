"""Shared no-tuning cross-sectional research and validation pipeline."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

import numpy as np
import pandas as pd

from config.schema import CostModelConfig
from experiments.artifacts import ArtifactKind, ArtifactManager
from experiments.models import Experiment, ExperimentDraft, PromotionStatus
from experiments.registry import ExperimentRegistry
from research.bb_defaults import default_cost_config
from research.runner import compute_metrics
from strategies.registry import strategy_template_version as registered_strategy_template_version
from validation.gauntlet import GauntletResult, run_gauntlet
from validation.wfa.engine import PRESETS, WFATier

ParamsToDict = Callable[[Any], dict[str, Any]]
GenerateSignals = Callable[[pd.DataFrame, Any], pd.DataFrame]
BuildExperimentDraft = Callable[..., ExperimentDraft]


@dataclass
class CrossSectionalBacktestResult:
    """Container for one vectorized cross-sectional portfolio backtest."""

    strategy_name: str
    template_version: str
    params: dict[str, Any]
    equity_curve: pd.Series
    returns: pd.Series
    weights: pd.DataFrame
    trades: pd.DataFrame
    metrics: dict[str, float] = field(default_factory=dict)
    bar_count: int = 0
    rebalance_count: int = 0
    skipped_rebalance_count: int = 0
    trade_count: int = 0


@dataclass
class CrossSectionalValidationReport:
    """Full no-tuning cross-sectional validation artifact."""

    strategy_name: str
    report_title: str
    params: Any
    params_dict: dict[str, Any]
    research: CrossSectionalBacktestResult
    sweep: pd.DataFrame
    gauntlet: GauntletResult
    replay_attribution: dict[str, Any]
    experiment_uuid: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_uuid": self.experiment_uuid,
            "strategy": self.strategy_name,
            "strategy_template_version": self.research.template_version,
            "params": self.params_dict,
            "research": {
                "metrics": self.research.metrics,
                "bar_count": self.research.bar_count,
                "rebalance_count": self.research.rebalance_count,
                "skipped_rebalance_count": self.research.skipped_rebalance_count,
                "trade_count": self.research.trade_count,
            },
            "sweep_rows": len(self.sweep),
            "gauntlet": self.gauntlet.to_dict(),
            "replay_attribution": self.replay_attribution,
        }


def backtest_cross_sectional(
    df: pd.DataFrame,
    params: Any,
    *,
    strategy_name: str,
    generate_signals: GenerateSignals,
    params_to_dict: ParamsToDict,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
    entry_on_open: bool = False,
    template_version: str | None = None,
) -> CrossSectionalBacktestResult:
    """Run a deterministic target-weight cross-sectional backtest.

    With ``entry_on_open=False`` (the historical default), targets become
    active on the following close-to-close bar.  ``entry_on_open=True`` is
    for strategies whose signal is known at the current session's open: it
    holds the current target from that open to that close and charges both
    legs of the daily round trip.
    """
    cost_config = cost_config or default_cost_config()
    resolved_template_version = template_version or registered_strategy_template_version(strategy_name)
    signals = generate_signals(df, params)
    weights = signals.xs("weight", axis=1, level="field").astype(float)
    trades = signals.xs("trade", axis=1, level="field").astype(float)
    close = df.xs("close", axis=1, level=1).astype(float)
    if entry_on_open:
        open_prices = df.xs("open", axis=1, level=1).astype(float)
        asset_returns = (close / open_prices - 1.0).replace([np.inf, -np.inf], np.nan)
        asset_returns = asset_returns.fillna(0.0)
        held_weights = weights.fillna(0.0)
        # Same-session execution is flat overnight, so every nonzero target
        # enters at the open and exits at the close.  Generic ``trade`` fields
        # can be target deltas and therefore cannot determine this turnover.
        executed_trades = held_weights
        gross_returns = (held_weights * asset_returns).sum(axis=1)
        costs = round_trip_trade_costs(executed_trades, cost_config)
    else:
        asset_returns = close.pct_change(fill_method=None).fillna(0.0)
        held_weights = weights.shift(1).fillna(0.0)
        executed_trades = trades.shift(1).fillna(0.0)
        gross_returns = (held_weights * asset_returns).sum(axis=1)
        costs = trade_costs(executed_trades, cost_config)
    borrow = borrow_costs(held_weights, cost_config)
    strategy_returns = gross_returns - costs - borrow
    equity = (1.0 + strategy_returns).cumprod() * initial_capital
    metrics = compute_metrics(strategy_returns, equity, initial_capital)

    trade_frame = trade_frame_from_weight_deltas(executed_trades)
    rebalances = signals[("portfolio", "is_rebalance")].astype(bool)
    skipped = signals[("portfolio", "rebalance_skipped")].astype(bool)
    return CrossSectionalBacktestResult(
        strategy_name=strategy_name,
        template_version=resolved_template_version,
        params={
            **params_to_dict(params),
            "strategy_template_version": resolved_template_version,
        },
        equity_curve=equity,
        returns=strategy_returns,
        weights=held_weights,
        trades=trade_frame,
        metrics=metrics,
        bar_count=len(df),
        rebalance_count=int(rebalances.sum()),
        skipped_rebalance_count=int(skipped.sum()),
        trade_count=len(trade_frame),
    )


def run_no_tuning_sweep(
    df: pd.DataFrame,
    params: Any,
    *,
    strategy_name: str,
    generate_signals: GenerateSignals,
    params_to_dict: ParamsToDict,
    sweep_metadata: dict[str, Any],
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
    entry_on_open: bool = False,
    template_version: str | None = None,
) -> pd.DataFrame:
    """Return the single canonical result row for a frozen hypothesis."""
    result = backtest_cross_sectional(
        df,
        params,
        strategy_name=strategy_name,
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        cost_config=cost_config,
        initial_capital=initial_capital,
        entry_on_open=entry_on_open,
        template_version=template_version,
    )
    return pd.DataFrame(
        [
            {
                **params_to_dict(params),
                **sweep_metadata,
                **result.metrics,
                "trade_count": result.trade_count,
            }
        ]
    )


def make_no_tuning_wfa_fns(
    df: pd.DataFrame,
    params: Any,
    *,
    strategy_name: str,
    generate_signals: GenerateSignals,
    params_to_dict: ParamsToDict,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
    entry_on_open: bool = False,
    template_version: str | None = None,
) -> tuple[Any, Any]:
    """Build WFA callables for a frozen no-tuning cross-sectional hypothesis."""
    cost_config = cost_config or default_cost_config()
    full_result = backtest_cross_sectional(
        df,
        params,
        strategy_name=strategy_name,
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        cost_config=cost_config,
        initial_capital=initial_capital,
        entry_on_open=entry_on_open,
        template_version=template_version,
    )

    def train_fn(train_df: pd.DataFrame, **kwargs: Any) -> dict[str, Any]:
        return params_to_dict(params)

    def test_fn(test_df: pd.DataFrame, fitted_params: dict[str, Any]) -> dict[str, Any]:
        if test_df.empty:
            return {}
        test_start = test_df.index.min()
        test_end = test_df.index.max()
        oos_returns = full_result.returns.loc[test_start:test_end]
        oos_equity = (1.0 + oos_returns).cumprod() * initial_capital
        metrics = compute_metrics(oos_returns, oos_equity, initial_capital)
        metrics["returns"] = oos_returns
        return metrics

    return train_fn, test_fn


def build_returns_matrix(
    df: pd.DataFrame,
    params: Any,
    *,
    strategy_name: str,
    generate_signals: GenerateSignals,
    params_to_dict: ParamsToDict,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
    entry_on_open: bool = False,
    template_version: str | None = None,
) -> np.ndarray:
    result = backtest_cross_sectional(
        df,
        params,
        strategy_name=strategy_name,
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        cost_config=cost_config,
        initial_capital=initial_capital,
        entry_on_open=entry_on_open,
        template_version=template_version,
    )
    return cast(np.ndarray, result.returns.to_frame(f"{strategy_name}_v1").to_numpy())


def run_no_tuning_cross_sectional_validation(
    df: pd.DataFrame,
    params: Any,
    *,
    strategy_name: str,
    report_title: str,
    generate_signals: GenerateSignals,
    params_to_dict: ParamsToDict,
    build_experiment_draft: BuildExperimentDraft,
    param_columns: list[str],
    sweep_metadata: dict[str, Any],
    replay_reason: str,
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
    entry_on_open: bool = False,
    template_version: str | None = None,
) -> CrossSectionalValidationReport:
    """Run research, registry transitions, artifacts, and the Validation Gauntlet."""
    cost_config = cost_config or default_cost_config()
    active_experiment = experiment

    if registry is not None:
        if active_experiment is None:
            if experiment_label is None:
                raise ValueError("experiment_label required when registry is provided without experiment")
            draft = build_experiment_draft(
                df,
                label=experiment_label,
                params=params,
                data_source=data_source,
                random_seed=seed,
                cost_config=cost_config,
                config_version=config_version,
            )
            active_experiment = registry.create(draft)
        registry.transition_promotion_status(
            active_experiment.uuid,
            PromotionStatus.VALIDATION_RUNNING,
        )

    research = backtest_cross_sectional(
        df,
        params,
        strategy_name=strategy_name,
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        cost_config=cost_config,
        initial_capital=initial_capital,
        entry_on_open=entry_on_open,
        template_version=template_version,
    )
    sweep_df = run_no_tuning_sweep(
        df,
        params,
        strategy_name=strategy_name,
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        sweep_metadata=sweep_metadata,
        cost_config=cost_config,
        initial_capital=initial_capital,
        entry_on_open=entry_on_open,
        template_version=template_version,
    )
    train_fn, test_fn = make_no_tuning_wfa_fns(
        df,
        params,
        strategy_name=strategy_name,
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        cost_config=cost_config,
        initial_capital=initial_capital,
        entry_on_open=entry_on_open,
        template_version=template_version,
    )
    returns_matrix = build_returns_matrix(
        df,
        params,
        strategy_name=strategy_name,
        generate_signals=generate_signals,
        params_to_dict=params_to_dict,
        cost_config=cost_config,
        initial_capital=initial_capital,
        entry_on_open=entry_on_open,
        template_version=template_version,
    )
    best_sharpe = float(sweep_df["sharpe"].max()) if not sweep_df.empty else None

    gauntlet = run_gauntlet(
        strategy_name,
        df,
        train_fn,
        test_fn,
        sweep_df,
        param_columns,
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
        "reason": replay_reason,
        "execution_alignment": "signals use data before rebalance; target weights are held from the next bar",
    }

    if registry is not None and active_experiment is not None:
        final_status = (
            PromotionStatus.VALIDATION_PASSED
            if gauntlet.passed
            else PromotionStatus.VALIDATION_FAILED
        )
        registry.transition_promotion_status(active_experiment.uuid, final_status)

    report = CrossSectionalValidationReport(
        strategy_name=strategy_name,
        report_title=report_title,
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


def format_cross_sectional_gauntlet_report(report: CrossSectionalValidationReport) -> str:
    lines = [
        "=" * 72,
        f"  {report.report_title}",
        "=" * 72,
        f"  Experiment UUID: {report.experiment_uuid}",
        f"  Params: {report.params_dict}",
        f"  Research Sharpe: {report.research.metrics.get('sharpe', 0):.4f}",
        f"  Research total return: {report.research.metrics.get('total_return', 0):.4f}",
        f"  Rebalances: {report.research.rebalance_count}",
        f"  Skipped rebalances: {report.research.skipped_rebalance_count}",
        f"  Gauntlet passed: {report.gauntlet.passed}",
    ]
    if report.gauntlet.failure_reasons:
        lines.append("  Failures:")
        for reason in report.gauntlet.failure_reasons:
            lines.append(f"    - {reason}")
    lines.append("=" * 72)
    return "\n".join(lines)


def write_validation_artifacts(
    artifacts: ArtifactManager,
    experiment_uuid: str,
    report: CrossSectionalValidationReport,
) -> None:
    artifacts.write_json(experiment_uuid, ArtifactKind.VALIDATION_REPORT_JSON, report.to_dict())
    artifacts.write_text(
        experiment_uuid,
        ArtifactKind.VALIDATION_REPORT_MD,
        format_cross_sectional_gauntlet_report(report) + "\n",
    )
    verdict = "PASS\n" if report.gauntlet.passed else "FAIL\n"
    artifacts.write_text(experiment_uuid, ArtifactKind.VALIDATION_VERDICT_TXT, verdict)
    artifacts.write_json(
        experiment_uuid,
        ArtifactKind.REPLAY_ATTRIBUTION_JSON,
        report.replay_attribution,
    )
    artifacts.write_json(
        experiment_uuid,
        ArtifactKind.DIAGNOSTICS_SIGNALS_JSON,
        validation_diagnostics(report),
    )


def validation_diagnostics(report: CrossSectionalValidationReport) -> dict[str, Any]:
    """Return postmortem-oriented diagnostics for validation evidence."""
    terminal_verdict = "validation_passed" if report.gauntlet.passed else "validation_failed"
    rebalance_count = report.research.rebalance_count
    skipped_count = report.research.skipped_rebalance_count
    skipped_pct = skipped_count / rebalance_count if rebalance_count else 0.0
    return {
        "experiment_uuid": report.experiment_uuid,
        "strategy": report.strategy_name,
        "terminal_verdict": terminal_verdict,
        "postmortem": {
            "failure_reasons": list(report.gauntlet.failure_reasons),
            "summary": (
                "Validation failed; archive this Experiment without parameter tuning."
                if not report.gauntlet.passed
                else "Validation passed; eligible for Paper Ops review only."
            ),
        },
        "signal_activity": {
            "bar_count": report.research.bar_count,
            "rebalance_count": rebalance_count,
            "skipped_rebalance_count": skipped_count,
            "skipped_rebalance_pct": skipped_pct,
            "trade_count": report.research.trade_count,
        },
        "research_metrics": report.research.metrics,
        "returns": [
            {"timestamp": str(ts), "return": float(value)}
            for ts, value in report.research.returns.items()
        ],
        "replay_attribution": report.replay_attribution,
    }


def trade_costs(
    executed_trades: pd.DataFrame,
    cost_config: CostModelConfig,
) -> pd.Series:
    buy_cost_pct = cost_config.slippage_fixed_pct + cost_config.commission_pct
    sell_cost_pct = (
        cost_config.slippage_fixed_pct
        + cost_config.commission_pct
        + cost_config.sec_fee_per_dollar_sold
        + 0.0001
    )
    buy_notional = executed_trades.clip(lower=0.0).sum(axis=1)
    sell_notional = (-executed_trades.clip(upper=0.0)).sum(axis=1)

    variable_cost = pd.Series(0.0, index=executed_trades.index)
    if cost_config.slippage_variable_coeff:
        variable_cost = executed_trades.abs().sum(axis=1) * cost_config.slippage_fixed_pct

    return buy_notional * buy_cost_pct + sell_notional * sell_cost_pct + variable_cost


def round_trip_trade_costs(
    entry_weights: pd.DataFrame,
    cost_config: CostModelConfig,
) -> pd.Series:
    """Charge entry and close-out costs for same-session open-to-close trades."""
    return trade_costs(entry_weights, cost_config) + trade_costs(-entry_weights, cost_config)


def borrow_costs(held_weights: pd.DataFrame, cost_config: CostModelConfig) -> pd.Series:
    short_exposure = (-held_weights.clip(upper=0.0)).sum(axis=1)
    return short_exposure * (cost_config.borrow_cost_annual_pct / 252.0)


def trade_frame_from_weight_deltas(executed_trades: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for ts, row in executed_trades.iterrows():
        changed = row[row.abs() > 1e-12]
        for symbol, delta in changed.items():
            rows.append(
                {
                    "timestamp": ts,
                    "symbol": symbol,
                    "weight_delta": float(delta),
                    "side": "buy" if delta > 0 else "sell",
                }
            )
    return pd.DataFrame(rows, columns=["timestamp", "symbol", "weight_delta", "side"])
