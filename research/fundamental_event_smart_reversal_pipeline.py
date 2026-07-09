"""Research scout for FundamentalEventSmartReversal v1.

This module deliberately stops before the repository Validation Gauntlet. The
current gauntlet has known overlapping-OOS and Monte Carlo drawdown-tail defects;
scout evidence cannot authorize paper or live trading.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from config.schema import CostModelConfig
from research.bb_defaults import default_cost_config
from research.runner import compute_metrics
from strategies.fundamental_event_smart_reversal.signal import (
    EVENT_FIELD,
    FundamentalEventSmartReversalParams,
    default_params,
    generate_signals,
    params_to_dict,
)

STRATEGY_NAME = "fundamental_event_smart_reversal"
COST_SENSITIVITY_BPS = (0.0, 0.5, 1.0, 2.0, 5.0, 10.0)
OVERLAY_GROSS_EXPOSURE = 0.20


@dataclass
class FundamentalEventSmartReversalScoutReport:
    strategy_name: str
    params: dict[str, Any]
    analysis_start: str | None
    analysis_end: str | None
    gross_metrics: dict[str, float]
    default_net_metrics: dict[str, float]
    spy_metrics: dict[str, float]
    spy_plus_20pct_overlay_metrics: dict[str, float]
    overlay_diagnostics: dict[str, float]
    factor_diagnostics: dict[str, float]
    turnover: dict[str, float]
    cost_drag: dict[str, float]
    cost_sensitivity_bps: dict[str, dict[str, float]]
    rank_ic: dict[str, float]
    event_diagnostics: dict[str, int]
    no_event_comparator: dict[str, Any]
    scout_gates: dict[str, bool]
    scout_passed: bool
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_scout(
    df: pd.DataFrame,
    *,
    params: FundamentalEventSmartReversalParams | None = None,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10_000.0,
) -> FundamentalEventSmartReversalScoutReport:
    """Run the single frozen event-veto strategy and predeclared diagnostics."""
    params = params or default_params()
    cost_config = cost_config or default_cost_config()
    signals = generate_signals(df, params)
    components = _return_components(df, signals, cost_config, initial_capital)

    active = components["held_weights"].abs().sum(axis=1) > 0.0
    analysis_index = active.index[active]
    if len(analysis_index):
        start = analysis_index[0]
        end = df.index[-1]
    else:
        start = df.index[0] if len(df) else None
        end = df.index[-1] if len(df) else None

    gross = _slice(components["gross_returns"], start)
    net = _slice(components["net_returns"], start)
    trading_cost = _slice(components["trading_cost"], start)
    borrow_cost = _slice(components["borrow_cost"], start)
    daily_turnover = _slice(components["daily_turnover"], start)

    spy_returns = df.xs("close", axis=1, level=1)[params.benchmark_symbol].astype(float)
    spy_returns = _slice(spy_returns.pct_change(fill_method=None).fillna(0.0), start)
    gross_metrics = _metrics(gross, initial_capital)
    default_net_metrics = _metrics(net, initial_capital)
    spy_metrics = _metrics(spy_returns, initial_capital)
    base_strategy_gross = params.long_gross + params.short_gross
    overlay_scale = OVERLAY_GROSS_EXPOSURE / base_strategy_gross
    overlay_returns = spy_returns.add(net.reindex(spy_returns.index).fillna(0.0) * overlay_scale)
    overlay_metrics = _metrics(overlay_returns, initial_capital)

    cost_sensitivity: dict[str, dict[str, float]] = {}
    for bps in COST_SENSITIVITY_BPS:
        stressed = gross - daily_turnover * (bps / 10_000.0) - borrow_cost
        cost_sensitivity[f"{bps:.1f}"] = _metrics(stressed, initial_capital)

    no_event = df.copy()
    event_columns = pd.IndexSlice[:, EVENT_FIELD]
    no_event.loc[:, event_columns] = 0.0
    no_event_signals = generate_signals(no_event, params)
    no_event_components = _return_components(
        no_event,
        no_event_signals,
        cost_config,
        initial_capital,
    )
    no_event_net = _slice(no_event_components["net_returns"], start)

    rank_ic = _rank_ic(df, signals, params.benchmark_symbol)
    event_flags = df.xs(EVENT_FIELD, axis=1, level=1).fillna(0.0).astype(bool)
    event_vetoed = signals[("portfolio", "event_vetoed_count")].astype(int)
    event_forced = signals[("portfolio", "event_forced_exit_count")].astype(int)
    factor_diagnostics = _factor_diagnostics(net, spy_returns)

    mean_turnover = float(daily_turnover.mean()) if len(daily_turnover) else 0.0
    gates = {
        "gross_total_return_positive": gross_metrics.get("total_return", 0.0) > 0.0,
        "gross_sharpe_positive": gross_metrics.get("sharpe", 0.0) > 0.0,
        "mean_rank_ic_negative": rank_ic["mean"] < 0.0,
        "default_net_total_return_positive": default_net_metrics.get("total_return", 0.0) > 0.0,
        "mean_daily_gross_turnover_at_most_1x": mean_turnover <= 1.0,
    }

    return FundamentalEventSmartReversalScoutReport(
        strategy_name=STRATEGY_NAME,
        params=params_to_dict(params),
        analysis_start=str(start) if start is not None else None,
        analysis_end=str(end) if end is not None else None,
        gross_metrics=gross_metrics,
        default_net_metrics=default_net_metrics,
        spy_metrics=spy_metrics,
        spy_plus_20pct_overlay_metrics=overlay_metrics,
        overlay_diagnostics={
            "strategy_return_scale": overlay_scale,
            "strategy_overlay_gross": OVERLAY_GROSS_EXPOSURE,
            "total_portfolio_gross": 1.0 + OVERLAY_GROSS_EXPOSURE,
            "total_portfolio_net": 1.0
            + overlay_scale * (params.long_gross - params.short_gross),
        },
        factor_diagnostics=factor_diagnostics,
        turnover={
            "mean_daily_gross": mean_turnover,
            "median_daily_gross": float(daily_turnover.median()) if len(daily_turnover) else 0.0,
            "p95_daily_gross": float(daily_turnover.quantile(0.95)) if len(daily_turnover) else 0.0,
            "max_daily_gross": float(daily_turnover.max()) if len(daily_turnover) else 0.0,
        },
        cost_drag={
            "mean_daily_trading_cost_bps": float(trading_cost.mean() * 10_000.0),
            "mean_daily_borrow_cost_bps": float(borrow_cost.mean() * 10_000.0),
            "mean_daily_total_cost_bps": float((trading_cost + borrow_cost).mean() * 10_000.0),
        },
        cost_sensitivity_bps=cost_sensitivity,
        rank_ic=rank_ic,
        event_diagnostics={
            "filing_flagged_symbol_sessions": int(event_flags.sum().sum()),
            "event_vetoed_symbol_days": int(event_vetoed.sum()),
            "event_forced_exits": int(event_forced.sum()),
        },
        no_event_comparator={
            "label": "diagnostic_only",
            "promotion_eligible": False,
            "default_net_metrics": _metrics(no_event_net, initial_capital),
            "mean_daily_gross_turnover": float(
                _slice(no_event_components["daily_turnover"], start).mean()
            ),
        },
        scout_gates=gates,
        scout_passed=all(gates.values()),
        limitations=[
            "Static current-active stock universe has survivorship bias.",
            "SEC filing presence is a public-information proxy, not directional fundamental sentiment.",
            "Shared daily backtester credits close-to-close returns after a one-bar target lag; broker next-open fills require separate reconciliation.",
            "Known Validation Gauntlet defects block promotion even if scout gates pass.",
        ],
    )


def _return_components(
    df: pd.DataFrame,
    signals: pd.DataFrame,
    cost_config: CostModelConfig,
    initial_capital: float,
) -> dict[str, Any]:
    target_weights = signals.xs("weight", axis=1, level="field").astype(float)
    close = df.xs("close", axis=1, level=1).astype(float)
    volume = df.xs("volume", axis=1, level=1).astype(float)
    asset_returns = close.pct_change(fill_method=None).fillna(0.0)
    held_weights = target_weights.shift(1).fillna(0.0)
    execution_price = close.shift(1)
    median_dollar_volume = (close * volume).rolling(20, min_periods=1).median().shift(1)

    executed_trades = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    gross_returns = pd.Series(0.0, index=close.index)
    trading_cost = pd.Series(0.0, index=close.index)
    borrow_cost = pd.Series(0.0, index=close.index)
    net_returns = pd.Series(0.0, index=close.index)
    pretrade_weights = pd.Series(0.0, index=close.columns)
    equity = float(initial_capital)

    for ts in close.index:
        desired = held_weights.loc[ts]
        trades = desired - pretrade_weights
        executed_trades.loc[ts] = trades
        trading_cost.loc[ts] = _trade_cost_fraction(
            trades,
            execution_price.loc[ts],
            median_dollar_volume.loc[ts],
            equity,
            cost_config,
        )
        borrow_cost.loc[ts] = float(
            (-desired.clip(upper=0.0)).sum()
            * (cost_config.borrow_cost_annual_pct / 252.0)
        )
        gross_returns.loc[ts] = float((desired * asset_returns.loc[ts]).sum())
        net_returns.loc[ts] = (
            gross_returns.loc[ts] - trading_cost.loc[ts] - borrow_cost.loc[ts]
        )
        equity_multiplier = 1.0 + net_returns.loc[ts]
        if equity_multiplier <= 0.0:
            raise ValueError("Strategy equity became non-positive during cost simulation")
        pretrade_weights = desired * (1.0 + asset_returns.loc[ts]) / equity_multiplier
        equity *= equity_multiplier

    return {
        "held_weights": held_weights,
        "executed_trades": executed_trades,
        "daily_turnover": executed_trades.abs().sum(axis=1),
        "gross_returns": gross_returns,
        "trading_cost": trading_cost,
        "borrow_cost": borrow_cost,
        "net_returns": net_returns,
    }


def _trade_cost_fraction(
    trades: pd.Series,
    prices: pd.Series,
    median_dollar_volume: pd.Series,
    equity: float,
    cost_config: CostModelConfig,
) -> float:
    """Return one-side equity trading costs including ADV impact and regulatory fees."""
    absolute = trades.abs()
    sells = (-trades.clip(upper=0.0))
    cost = absolute * (cost_config.slippage_fixed_pct + cost_config.commission_pct)
    cost += sells * cost_config.sec_fee_per_dollar_sold

    valid_price = prices.where(prices > 0.0)
    cost += (sells * cost_config.finra_taf_per_share_sold / valid_price).fillna(0.0)

    valid_adv = median_dollar_volume.where(median_dollar_volume > 0.0)
    participation = (absolute * equity / valid_adv).fillna(0.0)
    cost += absolute * cost_config.slippage_variable_coeff * participation
    return float(cost.sum())


def _rank_ic(
    df: pd.DataFrame,
    signals: pd.DataFrame,
    benchmark_symbol: str,
) -> dict[str, float]:
    scores = signals.xs("signal_return", axis=1, level="field").astype(float)
    eligible = signals.xs("eligible", axis=1, level="field").fillna(False).astype(bool)
    close = df.xs("close", axis=1, level=1).astype(float)
    next_returns = close.pct_change(fill_method=None).shift(-1)
    values: list[float] = []
    for ts in scores.index:
        mask = eligible.loc[ts] & scores.loc[ts].notna() & next_returns.loc[ts].notna()
        if benchmark_symbol in mask.index:
            mask.loc[benchmark_symbol] = False
        if int(mask.sum()) < 5:
            continue
        ic = scores.loc[ts, mask].corr(next_returns.loc[ts, mask], method="spearman")
        if pd.notna(ic):
            values.append(float(ic))
    series = pd.Series(values, dtype=float)
    return {
        "mean": float(series.mean()) if len(series) else 0.0,
        "median": float(series.median()) if len(series) else 0.0,
        "positive_fraction": float((series > 0.0).mean()) if len(series) else 0.0,
        "observations": float(len(series)),
    }


def _factor_diagnostics(strategy: pd.Series, spy: pd.Series) -> dict[str, float]:
    aligned = pd.concat([strategy.rename("strategy"), spy.rename("spy")], axis=1).dropna()
    if len(aligned) < 2 or float(aligned["spy"].var()) <= 0.0:
        return {"beta_to_spy": 0.0, "annualized_alpha": 0.0, "correlation_to_spy": 0.0}
    beta = float(aligned["strategy"].cov(aligned["spy"]) / aligned["spy"].var())
    alpha = float((aligned["strategy"] - beta * aligned["spy"]).mean() * 252.0)
    correlation = float(aligned["strategy"].corr(aligned["spy"]))
    return {
        "beta_to_spy": beta,
        "annualized_alpha": alpha,
        "correlation_to_spy": correlation,
    }


def _slice(series: pd.Series, start: pd.Timestamp | None) -> pd.Series:
    return series.loc[start:] if start is not None else series


def _metrics(returns: pd.Series, initial_capital: float) -> dict[str, float]:
    returns = returns.fillna(0.0).astype(float)
    equity = (1.0 + returns).cumprod() * initial_capital
    return compute_metrics(returns, equity, initial_capital)
