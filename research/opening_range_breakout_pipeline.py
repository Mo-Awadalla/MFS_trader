"""OpeningRangeBreakoutETF-v1 research + validation pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from config.schema import CostModelConfig
from experiments.artifacts import ArtifactKind, ArtifactManager
from experiments.models import Experiment, PromotionStatus
from experiments.registry import ExperimentRegistry
from research.cross_sectional_pipeline import (
    CrossSectionalBacktestResult,
    CrossSectionalValidationReport,
    format_cross_sectional_gauntlet_report,
    trade_costs,
)
from research.opening_range_breakout_experiment import (
    STRATEGY_NAME,
    build_opening_range_breakout_experiment_draft,
    default_opening_range_breakout_cost_config,
)
from strategies.opening_range_breakout.signal import (
    OpeningRangeBreakoutParams,
    default_params,
    generate_signals,
    params_to_dict,
)
from validation.gauntlet import run_gauntlet
from validation.intraday import (
    IntradayValidationConfig,
    IntradayValidationResult,
    evaluate_intraday_constraints,
    intraday_performance_metrics,
)
from validation.wfa.engine import WFAConfig, WFATier

PARAM_COLUMNS = [
    "opening_range_bars",
    "exit_before_close_bars",
    "breakout_buffer_pct",
    "rebalance_frequency",
]
INTRADAY_WFA_CONFIG = WFAConfig(WFATier.PRIMARY, "180d", "60d", "30d")
OpeningRangeBreakoutBacktestResult = CrossSectionalBacktestResult


@dataclass
class OpeningRangeBreakoutValidationReport(CrossSectionalValidationReport):
    """Validation report with day-trading-specific diagnostics."""

    intraday: IntradayValidationResult | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["intraday"] = self.intraday.to_dict() if self.intraday else None
        return payload


def backtest_opening_range_breakout(
    df: pd.DataFrame,
    params: OpeningRangeBreakoutParams | None = None,
    *,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 25_000.0,
) -> CrossSectionalBacktestResult:
    """Run vectorized 30-minute ETF opening-range breakout backtest."""
    params = params or default_params()
    cost_config = cost_config or default_opening_range_breakout_cost_config()
    signals = generate_signals(df, params)
    weights = signals.xs("weight", axis=1, level="field").astype(float)
    trades = signals.xs("trade", axis=1, level="field").astype(float)
    close = df.xs("close", axis=1, level=1).astype(float)

    asset_returns = close.pct_change(fill_method=None).fillna(0.0)
    held_weights = weights.shift(1).fillna(0.0)
    executed_trades = trades.shift(1).fillna(0.0)
    gross_returns = (held_weights * asset_returns).sum(axis=1)
    costs = trade_costs(executed_trades, cost_config)
    strategy_returns = gross_returns - costs
    equity = (1.0 + strategy_returns).cumprod() * initial_capital
    metrics = intraday_performance_metrics(
        strategy_returns,
        equity,
        initial_capital=initial_capital,
        bars_per_session=params.bars_per_session,
    )
    trade_frame = _trade_frame_from_weight_deltas(executed_trades, gross_returns)
    rebalances = signals[("portfolio", "is_rebalance")].astype(bool)
    skipped = signals[("portfolio", "rebalance_skipped")].astype(bool)
    return CrossSectionalBacktestResult(
        strategy_name=STRATEGY_NAME,
        template_version=f"{STRATEGY_NAME}:v1",
        params={
            **params_to_dict(params),
            "strategy_template_version": f"{STRATEGY_NAME}:v1",
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


def run_opening_range_breakout_sweep(
    df: pd.DataFrame,
    *,
    params: OpeningRangeBreakoutParams | None = None,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 25_000.0,
) -> pd.DataFrame:
    params = params or default_params()
    result = backtest_opening_range_breakout(
        df,
        params,
        cost_config=cost_config or default_opening_range_breakout_cost_config(),
        initial_capital=initial_capital,
    )
    return pd.DataFrame([
        {
            **params_to_dict(params),
            "rebalance_frequency": "intraday_30min",
            "flat_by_close": True,
            **result.metrics,
            "trade_count": result.trade_count,
        }
    ])


def make_opening_range_breakout_wfa_fns(
    df: pd.DataFrame,
    *,
    params: OpeningRangeBreakoutParams | None = None,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 25_000.0,
) -> tuple[Any, Any]:
    params = params or default_params()
    cost_config = cost_config or default_opening_range_breakout_cost_config()
    full_result = backtest_opening_range_breakout(
        df,
        params,
        cost_config=cost_config,
        initial_capital=initial_capital,
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
        metrics = intraday_performance_metrics(
            oos_returns,
            oos_equity,
            initial_capital=initial_capital,
            bars_per_session=params.bars_per_session,
        )
        metrics["returns"] = oos_returns
        return metrics

    return train_fn, test_fn


def build_returns_matrix(
    df: pd.DataFrame,
    *,
    params: OpeningRangeBreakoutParams | None = None,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 25_000.0,
) -> np.ndarray:
    result = backtest_opening_range_breakout(
        df,
        params or default_params(),
        cost_config=cost_config,
        initial_capital=initial_capital,
    )
    return result.returns.to_frame(f"{STRATEGY_NAME}_v1").to_numpy()


def run_opening_range_breakout_validation_gauntlet(
    df: pd.DataFrame,
    *,
    params: OpeningRangeBreakoutParams | None = None,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 25_000.0,
    seed: int = 42,
    registry: ExperimentRegistry | None = None,
    experiment: Experiment | None = None,
    experiment_label: str | None = None,
    data_source: str = "alpaca_sip_30m_panel",
    config_version: str = "research.toml@0.1.0",
    artifacts: ArtifactManager | None = None,
    write_artifacts: bool = True,
    mc_num_paths: int = 10000,
    mc_block_size: int = 13,
) -> OpeningRangeBreakoutValidationReport:
    """Run ORB research and full gauntlet plus intraday gates."""
    params = params or default_params()
    cost_config = cost_config or default_opening_range_breakout_cost_config()
    active_experiment = experiment
    if registry is not None:
        if active_experiment is None:
            if experiment_label is None:
                raise ValueError("experiment_label required when registry is provided without experiment")
            draft = build_opening_range_breakout_experiment_draft(
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

    research = backtest_opening_range_breakout(
        df,
        params,
        cost_config=cost_config,
        initial_capital=initial_capital,
    )
    sweep_df = run_opening_range_breakout_sweep(
        df,
        params=params,
        cost_config=cost_config,
        initial_capital=initial_capital,
    )
    train_fn, test_fn = make_opening_range_breakout_wfa_fns(
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
    gauntlet = run_gauntlet(
        STRATEGY_NAME,
        df,
        train_fn,
        test_fn,
        sweep_df,
        PARAM_COLUMNS,
        best_sharpe=float(research.metrics.get("sharpe", 0.0)),
        returns_matrix=returns_matrix,
        initial_capital=initial_capital,
        max_dd_limit=-0.20,
        mc_num_paths=mc_num_paths,
        mc_block_size=mc_block_size,
        wfa_config=INTRADAY_WFA_CONFIG,
        seed=seed,
    )
    intraday = evaluate_intraday_constraints(
        returns=research.returns,
        trades=research.trades,
        positions=research.weights,
        config=IntradayValidationConfig(
            bars_per_session=params.bars_per_session,
            min_trades=100,
            min_trading_sessions=60,
            max_holding_period_bars=params.bars_per_session - params.opening_range_bars - params.exit_before_close_bars,
            require_flat_by_session_close=True,
            max_trades_per_session=10,
            max_turnover_per_session=6.0,
            max_single_session_profit_share=0.20,
            min_profit_factor=1.05,
            min_expectancy_per_trade=0.0,
            max_exposure_fraction=0.80,
            allow_short=False,
        ),
    )
    if not intraday.passed:
        gauntlet.failure_reasons.extend([f"Intraday: {reason}" for reason in intraday.failures])
        gauntlet.passed = False
        gauntlet.summary = gauntlet.to_dict()

    if registry is not None and active_experiment is not None:
        registry.transition_promotion_status(
            active_experiment.uuid,
            PromotionStatus.VALIDATION_PASSED if gauntlet.passed else PromotionStatus.VALIDATION_FAILED,
        )

    report = OpeningRangeBreakoutValidationReport(
        strategy_name=STRATEGY_NAME,
        report_title="Opening Range Breakout ETF v1 Validation Report",
        params=params,
        params_dict=params_to_dict(params),
        research=research,
        sweep=sweep_df,
        gauntlet=gauntlet,
        replay_attribution={
            "mode": "vectorized_intraday_cross_sectional_replay",
            "engine_replay_available": False,
            "reason": "engine replay is currently not session-scheduled for multi-ETF 30m intraday flat-by-close strategies",
            "execution_alignment": "breakout signal is held from next 30m bar; zero target before close prevents overnight exposure",
        },
        experiment_uuid=active_experiment.uuid if active_experiment else None,
        intraday=intraday,
    )
    if write_artifacts and artifacts is not None and active_experiment is not None:
        write_opening_range_breakout_validation_artifacts(artifacts, active_experiment.uuid, report)
    return report


def format_opening_range_breakout_gauntlet_report(
    report: OpeningRangeBreakoutValidationReport,
) -> str:
    lines = [format_cross_sectional_gauntlet_report(report)]
    if report.intraday is not None:
        lines.extend([
            "Intraday gates:",
            f"  passed: {report.intraday.passed}",
            f"  metrics: {report.intraday.metrics}",
        ])
        if report.intraday.failures:
            lines.append("  failures:")
            lines.extend(f"    - {failure}" for failure in report.intraday.failures)
    return "\n".join(lines)


def write_opening_range_breakout_validation_artifacts(
    artifacts: ArtifactManager,
    experiment_uuid: str,
    report: OpeningRangeBreakoutValidationReport,
) -> None:
    artifacts.write_json(experiment_uuid, ArtifactKind.VALIDATION_REPORT_JSON, report.to_dict())
    artifacts.write_text(
        experiment_uuid,
        ArtifactKind.VALIDATION_REPORT_MD,
        format_opening_range_breakout_gauntlet_report(report) + "\n",
    )
    artifacts.write_text(
        experiment_uuid,
        ArtifactKind.VALIDATION_VERDICT_TXT,
        "PASS\n" if report.gauntlet.passed else "FAIL\n",
    )
    artifacts.write_json(
        experiment_uuid,
        ArtifactKind.REPLAY_ATTRIBUTION_JSON,
        report.replay_attribution,
    )
    artifacts.write_json(
        experiment_uuid,
        ArtifactKind.DIAGNOSTICS_SIGNALS_JSON,
        {
            "experiment_uuid": report.experiment_uuid,
            "strategy": report.strategy_name,
            "terminal_verdict": "validation_passed" if report.gauntlet.passed else "validation_failed",
            "postmortem": {
                "failure_reasons": list(report.gauntlet.failure_reasons),
                "summary": (
                    "Validation passed; eligible for Paper Ops review only."
                    if report.gauntlet.passed
                    else "Validation failed; archive this Experiment without parameter tuning."
                ),
            },
            "signal_activity": {
                "bar_count": report.research.bar_count,
                "rebalance_count": report.research.rebalance_count,
                "skipped_rebalance_count": report.research.skipped_rebalance_count,
                "trade_count": report.research.trade_count,
            },
            "research_metrics": report.research.metrics,
            "intraday": report.intraday.to_dict() if report.intraday else None,
            "returns": [
                {"timestamp": str(ts), "return": float(value)}
                for ts, value in report.research.returns.items()
            ],
            "replay_attribution": report.replay_attribution,
        },
    )


def _trade_frame_from_weight_deltas(
    executed_trades: pd.DataFrame,
    gross_returns: pd.Series,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for ts, row in executed_trades.iterrows():
        changed = row[row.abs() > 1e-12]
        pnl = float(gross_returns.loc[ts]) if ts in gross_returns.index else 0.0
        pnl_per_trade = pnl / len(changed) if len(changed) else 0.0
        for symbol, delta in changed.items():
            rows.append(
                {
                    "timestamp": ts,
                    "symbol": symbol,
                    "weight_delta": float(delta),
                    "side": "buy" if delta > 0 else "sell",
                    "pnl": pnl_per_trade,
                }
            )
    return pd.DataFrame(rows, columns=["timestamp", "symbol", "weight_delta", "side", "pnl"])
