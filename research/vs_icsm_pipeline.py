"""VS-ICSM research and validation harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from config.schema import CostModelConfig
from experiments.artifacts import ArtifactManager
from experiments.models import Experiment, PromotionStatus
from experiments.registry import ExperimentRegistry
from research.cross_sectional_pipeline import (
    CrossSectionalBacktestResult,
    CrossSectionalValidationReport,
    format_cross_sectional_gauntlet_report,
    write_validation_artifacts,
)
from research.vs_icsm_experiment import (
    STRATEGY_NAME,
    build_vs_icsm_experiment_draft,
    vs_icsm_cost_config,
)
from strategies.vs_icsm.signal import (
    VSICSMParams,
    default_params,
    generate_weight_signals,
    params_to_dict,
)
from validation.gauntlet import GauntletResult, run_gauntlet
from validation.wfa.engine import PRESETS, WFATier

PARAM_COLUMNS = [
    "liquidity_lookback_bars",
    "universe_size",
    "momentum_lookback_bars",
    "volatility_lookback_bars",
    "atr_lookback_bars",
    "k_names",
]


@dataclass(frozen=True)
class StrictGateResult:
    passed: bool
    blockers: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)


def backtest_vs_icsm(
    df: pd.DataFrame,
    params: VSICSMParams | None = None,
    *,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
) -> CrossSectionalBacktestResult:
    params = params or default_params()
    cost_config = cost_config or vs_icsm_cost_config()
    _validate_candidate_panel(df, params)
    desired, _, portfolio = generate_weight_signals(df, params)
    open_px = df.xs("open", axis=1, level=1).astype(float)
    high = df.xs("high", axis=1, level=1).astype(float)
    low = df.xs("low", axis=1, level=1).astype(float)
    volume = df.xs("volume", axis=1, level=1).astype(float)
    actual, trades, fill_rates = _apply_open_limit_execution(desired, open_px, high, low)
    interval_returns = open_px.shift(-1).div(open_px).sub(1.0).fillna(0.0)
    gross_returns = (actual * interval_returns).sum(axis=1)
    costs = _trade_costs_exact(trades, open_px, volume, cost_config)
    returns = gross_returns - costs
    equity = (1.0 + returns).cumprod() * initial_capital
    metrics = _compute_hourly_metrics(returns, equity, initial_capital)
    metrics["fill_rate"] = float(fill_rates.mean()) if not fill_rates.empty else 0.0
    trade_frame = _trade_frame(trades, open_px)
    rebalances = portfolio["is_rebalance"].astype(bool)
    skipped = portfolio["rebalance_skipped"].astype(bool)
    return CrossSectionalBacktestResult(
        strategy_name=STRATEGY_NAME,
        template_version=f"{STRATEGY_NAME}:v1",
        params=params_to_dict(params),
        equity_curve=equity,
        returns=returns,
        weights=actual,
        trades=trade_frame,
        metrics=metrics,
        bar_count=len(df),
        rebalance_count=int(rebalances.sum()),
        skipped_rebalance_count=int(skipped.sum()),
        trade_count=len(trade_frame),
    )


def run_validation_gauntlet(
    df: pd.DataFrame,
    *,
    params: VSICSMParams | None = None,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
    seed: int = 42,
    registry: ExperimentRegistry | None = None,
    experiment: Experiment | None = None,
    experiment_label: str | None = None,
    artifacts: ArtifactManager | None = None,
    write_artifacts: bool = True,
    mc_num_paths: int = 10000,
    mc_block_size: int = 20,
) -> CrossSectionalValidationReport:
    params = params or default_params()
    cost_config = cost_config or vs_icsm_cost_config()
    _validate_candidate_panel(df, params)
    active_experiment = experiment
    if registry is not None:
        if active_experiment is None:
            if experiment_label is None:
                raise ValueError("experiment_label required when registry is provided without experiment")
            active_experiment = registry.create(
                build_vs_icsm_experiment_draft(
                    df,
                    label=experiment_label,
                    params=params,
                    cost_config=cost_config,
                    random_seed=seed,
                )
            )
        registry.transition_promotion_status(active_experiment.uuid, PromotionStatus.VALIDATION_RUNNING)

    research = backtest_vs_icsm(
        df,
        params,
        cost_config=cost_config,
        initial_capital=initial_capital,
    )
    sweep = pd.DataFrame([{**params_to_dict(params), **research.metrics, "trade_count": research.trade_count}])
    train_fn, test_fn = _make_vs_icsm_wfa_fns(
        df,
        params=params,
        cost_config=cost_config,
        initial_capital=initial_capital,
    )
    returns_matrix = research.returns.to_frame("VS-ICSM-Candidate-1").to_numpy()
    gauntlet = run_gauntlet(
        STRATEGY_NAME,
        df,
        train_fn,
        test_fn,
        sweep,
        PARAM_COLUMNS,
        best_sharpe=float(sweep["sharpe"].max()) if not sweep.empty else None,
        returns_matrix=returns_matrix,
        oos_returns=research.returns,
        initial_capital=initial_capital,
        max_dd_limit=-0.15,
        mc_num_paths=mc_num_paths,
        mc_block_size=mc_block_size,
        wfa_config=PRESETS[WFATier.PRIMARY],
        seed=seed,
    )
    strict = evaluate_strict_gates(gauntlet, research.returns)
    if not strict.passed:
        gauntlet.failure_reasons.extend(strict.blockers)
        gauntlet.passed = False
        gauntlet.summary = gauntlet.to_dict()

    if registry is not None and active_experiment is not None:
        registry.transition_promotion_status(
            active_experiment.uuid,
            PromotionStatus.VALIDATION_PASSED if gauntlet.passed else PromotionStatus.VALIDATION_FAILED,
        )

    report = CrossSectionalValidationReport(
        strategy_name=STRATEGY_NAME,
        report_title="VS-ICSM Candidate 1 Validation Report",
        params=params,
        params_dict=params_to_dict(params),
        research=research,
        sweep=sweep,
        gauntlet=gauntlet,
        replay_attribution={
            "mode": "vectorbt_installed_pandas_limit_execution",
            "engine_replay_available": False,
            "reason": "candidate requires multi-asset hourly target weights and open-limit fill simulation",
            "execution_alignment": "close signal, next-hour open limit attempt, open-to-open returns",
        },
        experiment_uuid=active_experiment.uuid if active_experiment else None,
    )
    if write_artifacts and artifacts is not None and active_experiment is not None:
        write_validation_artifacts(artifacts, active_experiment.uuid, report)
    return report


def evaluate_strict_gates(gauntlet: GauntletResult, returns: pd.Series) -> StrictGateResult:
    blockers: list[str] = []
    wfa = gauntlet.wfa_result
    mc = gauntlet.mc_result
    dsr = gauntlet.dsr_result
    if wfa is None or wfa.aggregate_metrics.get("oos_sharpe", 0.0) < 1.0:
        blockers.append("Strict WFA: mean OOS Sharpe < 1.0")
    if wfa is None or wfa.aggregate_metrics.get("oos_max_dd_worst", -1.0) < -0.15:
        blockers.append("Strict WFA: max DD exceeds 15%")
    if wfa is None or (1.0 - wfa.frac_negative_folds) < 0.70:
        blockers.append("Strict WFA: positive windows < 70%")
    if mc is None or mc.pct_5_sharpe <= 0.10:
        blockers.append("Strict MC: 5th percentile Sharpe <= 0.10")
    variance_ratio = _variance_ratio(returns)
    if variance_ratio >= 5.0:
        blockers.append("Strict MC: variance ratio >= 5.0")
    if dsr is None or dsr.dsr_pvalue >= 0.05:
        blockers.append("Strict DSR: p-value >= 0.05")
    rolling = _rolling_12wk_sharpe(returns)
    negative_frac = float((rolling < 0.0).mean()) if not rolling.empty else 1.0
    if rolling.empty or rolling.min() < -0.5:
        blockers.append("Strict Stability: rolling 12wk Sharpe below -0.5")
    if negative_frac >= 0.05:
        blockers.append("Strict Stability: negative rolling 12wk windows >= 5%")
    return StrictGateResult(
        passed=not blockers,
        blockers=blockers,
        metrics={
            "variance_ratio": variance_ratio,
            "rolling_12wk_negative_frac": negative_frac,
        },
    )


def format_vs_icsm_gauntlet_report(report: CrossSectionalValidationReport) -> str:
    return format_cross_sectional_gauntlet_report(report)


def _validate_candidate_panel(df: pd.DataFrame, params: VSICSMParams) -> None:
    symbols = df.columns.get_level_values(0).unique() if isinstance(df.columns, pd.MultiIndex) else []
    if len(symbols) < params.universe_size:
        raise ValueError(
            f"VS-ICSM requires at least {params.universe_size} symbols after ex-ETF/ADR/REIT/SPAC filters; got {len(symbols)}"
        )


def _make_vs_icsm_wfa_fns(
    full_df: pd.DataFrame,
    *,
    params: VSICSMParams,
    cost_config: CostModelConfig,
    initial_capital: float,
):
    def train_fn(train_df: pd.DataFrame, **kwargs: Any) -> dict[str, Any]:
        return params_to_dict(params)

    def test_fn(test_df: pd.DataFrame, fitted_params: dict[str, Any]) -> dict[str, Any]:
        if test_df.empty:
            return {}
        test_start = test_df.index.min()
        test_end = test_df.index.max()
        context = full_df.loc[:test_end]
        result = backtest_vs_icsm(
            context,
            params,
            cost_config=cost_config,
            initial_capital=initial_capital,
        )
        oos_returns = result.returns.loc[test_start:test_end]
        oos_equity = (1.0 + oos_returns).cumprod() * initial_capital
        metrics = _compute_hourly_metrics(oos_returns, oos_equity, initial_capital)
        metrics["returns"] = oos_returns
        return metrics

    return train_fn, test_fn


def _apply_open_limit_execution(
    desired: pd.DataFrame,
    open_px: pd.DataFrame,
    high: pd.DataFrame,
    low: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    actual = pd.DataFrame(0.0, index=desired.index, columns=desired.columns)
    trades = pd.DataFrame(0.0, index=desired.index, columns=desired.columns)
    fill_rates: list[float] = []
    current = pd.Series(0.0, index=desired.columns)
    for i, ts in enumerate(desired.index):
        target = desired.iloc[i - 1] if i > 0 else current
        delta = target - current
        buy = delta > 1e-12
        sell = delta < -1e-12
        buy_fill = low.loc[ts] <= open_px.loc[ts] * 0.9995
        sell_fill = high.loc[ts] >= open_px.loc[ts] * 1.0005
        filled = (buy & buy_fill) | (sell & sell_fill)
        executed = delta.where(filled, 0.0)
        current = current + executed
        actual.loc[ts] = current
        trades.loc[ts] = executed
        attempts = int((buy | sell).sum())
        fill_rates.append(float(filled.sum() / attempts) if attempts else 1.0)
    return actual, trades, pd.Series(fill_rates, index=desired.index)


def _trade_costs_exact(
    trades: pd.DataFrame,
    open_px: pd.DataFrame,
    volume: pd.DataFrame,
    cost_config: CostModelConfig,
) -> pd.Series:
    buy_notional = trades.clip(lower=0.0)
    sell_notional = -trades.clip(upper=0.0)
    median_dv = (open_px * volume).rolling(390, min_periods=1).median()
    large = median_dv >= 1_000_000_000.0
    buy_slip = buy_notional.where(large, 0.0).sum(axis=1) * 0.0003
    buy_slip += buy_notional.where(~large, 0.0).sum(axis=1) * 0.0005
    sell_slip = sell_notional.where(large, 0.0).sum(axis=1) * 0.0003
    sell_slip += sell_notional.where(~large, 0.0).sum(axis=1) * 0.0005
    sec = sell_notional.sum(axis=1) * cost_config.sec_fee_per_dollar_sold
    shares_sold = sell_notional.div(open_px.replace(0.0, np.nan)).fillna(0.0).sum(axis=1)
    taf = shares_sold * cost_config.finra_taf_per_share_sold
    return buy_slip + sell_slip + sec + taf


def _trade_frame(trades: pd.DataFrame, open_px: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for ts, row in trades.iterrows():
        changed = row[row.abs() > 1e-12]
        for symbol, weight_delta in changed.items():
            rows.append(
                {
                    "timestamp": ts,
                    "symbol": symbol,
                    "weight_delta": float(weight_delta),
                    "side": "buy" if weight_delta > 0 else "sell",
                    "reference_open": float(open_px.loc[ts, symbol]),
                }
            )
    return pd.DataFrame(rows, columns=["timestamp", "symbol", "weight_delta", "side", "reference_open"])


def _variance_ratio(returns: pd.Series) -> float:
    clean = returns.dropna()
    if len(clean) < 10:
        return float("inf")
    one = clean.var()
    five = clean.rolling(5).sum().dropna().var()
    return float(five / (5.0 * one)) if one > 0 else float("inf")


def _rolling_12wk_sharpe(returns: pd.Series) -> pd.Series:
    window = 12 * 5 * 7
    rolling_mean = returns.rolling(window).mean()
    rolling_std = returns.rolling(window).std()
    return (rolling_mean / rolling_std * np.sqrt(252 * 6.5)).dropna()


def _compute_hourly_metrics(
    returns: pd.Series,
    equity: pd.Series,
    initial_capital: float,
) -> dict[str, float]:
    if returns.empty:
        return {}
    ann_factor = 252 * 6.5
    total_return = float(equity.iloc[-1] / initial_capital - 1.0)
    years = len(returns) / ann_factor
    cagr = float((equity.iloc[-1] / initial_capital) ** (1.0 / years) - 1.0) if years > 0 else 0.0
    ann_return = float(returns.mean() * ann_factor)
    ann_vol = float(returns.std() * np.sqrt(ann_factor))
    sharpe = ann_return / ann_vol if ann_vol > 0 else 0.0
    downside = returns[returns < 0]
    downside_vol = float(downside.std() * np.sqrt(ann_factor)) if len(downside) else 0.0
    sortino = ann_return / downside_vol if downside_vol > 0 else 0.0
    drawdown = equity / equity.cummax() - 1.0
    nonzero = returns[returns != 0]
    return {
        "total_return": total_return,
        "cagr": cagr,
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "max_drawdown": float(drawdown.min()),
        "ann_volatility": ann_vol,
        "win_rate": float((nonzero > 0).mean()) if len(nonzero) else 0.0,
        "total_bars": float(len(returns)),
        "final_equity": float(equity.iloc[-1]),
    }
