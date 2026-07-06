"""Validation helpers for swing and intraday strategy candidates.

These checks are intentionally strategy-agnostic. They do not try to prove alpha;
they catch common failure modes that the daily/monthly validation gauntlet does
not see well: unrealistic holding periods, hidden overnight exposure, too few
trades, excessive turnover, day-level profit concentration, and bar-frequency
annualization mistakes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class IntradayValidationConfig:
    """Operational/research gates for swing and day-trading-ish strategies.

    ``max_holding_period_bars`` and ``require_flat_by_session_close`` define
    whether the check is being used for strict day trading or looser swing
    trading. Use strict settings for opening-range / intraday-momentum systems;
    relax them for multi-day swing systems.
    """

    bars_per_session: int
    min_trades: int = 100
    min_trading_sessions: int = 60
    max_holding_period_bars: int | None = None
    require_flat_by_session_close: bool = False
    max_trades_per_session: int = 20
    max_turnover_per_session: float = 8.0
    max_single_session_profit_share: float = 0.20
    min_profit_factor: float = 1.05
    min_expectancy_per_trade: float = 0.0
    max_exposure_fraction: float = 0.80
    allow_short: bool = False


@dataclass
class IntradayValidationResult:
    """Result of intraday/swing-specific validation diagnostics."""

    passed: bool
    failures: list[str] = field(default_factory=list)
    metrics: dict[str, float | int | bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "failures": list(self.failures),
            "metrics": dict(self.metrics),
        }


def estimate_bars_per_session(index: pd.DatetimeIndex) -> int:
    """Estimate bars per trading session from timestamp dates.

    This is a convenience default for regular intraday bars. Production strategy
    validation should pass a frozen ``bars_per_session`` from the Experiment
    snapshot when available.
    """

    if index.empty:
        return 0
    sessions = pd.Series(1, index=index).groupby(index.normalize()).sum()
    return int(sessions.median()) if not sessions.empty else 0


def annualization_factor(index: pd.DatetimeIndex, bars_per_session: int | None = None) -> int:
    """Return a conservative annualization factor for bar returns."""

    if bars_per_session is None:
        bars_per_session = estimate_bars_per_session(index)
    if bars_per_session <= 1:
        return 252
    return int(252 * bars_per_session)


def intraday_performance_metrics(
    returns: pd.Series,
    equity: pd.Series,
    *,
    initial_capital: float,
    bars_per_session: int | None = None,
) -> dict[str, float]:
    """Compute performance metrics with intraday-aware annualization."""

    returns = returns.dropna().astype(float)
    equity = equity.reindex(returns.index).dropna().astype(float)
    if returns.empty or equity.empty:
        return {}
    ann = annualization_factor(pd.DatetimeIndex(returns.index), bars_per_session)
    total_return = float(equity.iloc[-1] / initial_capital - 1.0)
    years = len(returns) / ann if ann > 0 else 0.0
    cagr = float((equity.iloc[-1] / initial_capital) ** (1 / years) - 1) if years > 0 else 0.0
    ann_return = float(returns.mean() * ann)
    ann_vol = float(returns.std(ddof=0) * np.sqrt(ann))
    sharpe = ann_return / ann_vol if ann_vol > 0 else 0.0
    downside = returns[returns < 0]
    downside_vol = float(downside.std(ddof=0) * np.sqrt(ann)) if len(downside) else 0.0
    sortino = ann_return / downside_vol if downside_vol > 0 else 0.0
    drawdown = equity / equity.cummax() - 1.0
    nonzero = returns[returns != 0]
    return {
        "total_return": total_return,
        "cagr": cagr,
        "ann_return": ann_return,
        "ann_volatility": ann_vol,
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "max_drawdown": float(drawdown.min()),
        "win_rate": float((nonzero > 0).mean()) if len(nonzero) else 0.0,
        "annualization_factor": float(ann),
        "total_bars": float(len(returns)),
        "final_equity": float(equity.iloc[-1]),
    }


def evaluate_intraday_constraints(
    *,
    returns: pd.Series,
    trades: pd.DataFrame,
    positions: pd.Series | pd.DataFrame,
    config: IntradayValidationConfig,
) -> IntradayValidationResult:
    """Evaluate non-alpha gates for swing/day-trading strategies.

    Expected inputs:
    - ``returns``: bar-level strategy returns indexed by timestamp.
    - ``trades``: rows with at least a timestamp column or DatetimeIndex; optional
      ``pnl`` and ``weight_delta`` columns improve diagnostics.
    - ``positions``: signed exposure/position weights indexed by timestamp. A
      DataFrame is treated as a cross-sectional book and summed by absolute gross.
    """

    failures: list[str] = []
    returns = returns.dropna().astype(float)
    if returns.empty:
        return IntradayValidationResult(False, ["no_returns"], {})

    idx = pd.DatetimeIndex(returns.index)
    sessions = idx.normalize()
    session_count = int(pd.Index(sessions).nunique())
    trade_times = _trade_timestamps(trades)
    trade_count = int(len(trade_times))
    session_returns = returns.groupby(sessions).sum()
    positive_session_returns = session_returns[session_returns > 0]
    total_positive = float(positive_session_returns.sum())
    max_session_profit_share = (
        float(positive_session_returns.max() / total_positive)
        if total_positive > 0 and not positive_session_returns.empty
        else 0.0
    )

    exposure = _gross_exposure(positions).reindex(returns.index).fillna(0.0).astype(float)
    exposure_fraction = float((exposure.abs() > 1e-12).mean())
    max_abs_exposure = float(exposure.abs().max()) if not exposure.empty else 0.0
    has_short_exposure = bool((exposure < -1e-12).any()) if isinstance(positions, pd.Series) else bool((positions < -1e-12).any().any())

    turnover_by_session = _turnover_by_session(trades, idx)
    max_turnover_per_session = float(turnover_by_session.max()) if not turnover_by_session.empty else 0.0
    trades_per_session = _trades_per_session(trade_times)
    max_trades_per_session = int(trades_per_session.max()) if not trades_per_session.empty else 0

    flat_by_close = _flat_by_session_close(positions)
    max_holding_bars = _max_holding_period_bars(positions)

    pnl = _trade_pnl(trades)
    gross_profit = float(pnl[pnl > 0].sum()) if not pnl.empty else 0.0
    gross_loss = float(-pnl[pnl < 0].sum()) if not pnl.empty else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    expectancy = float(pnl.mean()) if not pnl.empty else 0.0

    if session_count < config.min_trading_sessions:
        failures.append(f"trading_sessions {session_count} < {config.min_trading_sessions}")
    if trade_count < config.min_trades:
        failures.append(f"trade_count {trade_count} < {config.min_trades}")
    if max_session_profit_share > config.max_single_session_profit_share:
        failures.append(
            f"single session contributes {max_session_profit_share:.1%} of positive returns > {config.max_single_session_profit_share:.1%}"
        )
    if max_trades_per_session > config.max_trades_per_session:
        failures.append(
            f"max_trades_per_session {max_trades_per_session} > {config.max_trades_per_session}"
        )
    if max_turnover_per_session > config.max_turnover_per_session:
        failures.append(
            f"max_turnover_per_session {max_turnover_per_session:.2f} > {config.max_turnover_per_session:.2f}"
        )
    if exposure_fraction > config.max_exposure_fraction:
        failures.append(f"exposure_fraction {exposure_fraction:.1%} > {config.max_exposure_fraction:.1%}")
    if has_short_exposure and not config.allow_short:
        failures.append("short_exposure_detected_but_not_allowed")
    if config.require_flat_by_session_close and not flat_by_close:
        failures.append("not_flat_by_session_close")
    if config.max_holding_period_bars is not None and max_holding_bars > config.max_holding_period_bars:
        failures.append(
            f"max_holding_period_bars {max_holding_bars} > {config.max_holding_period_bars}"
        )
    if profit_factor < config.min_profit_factor:
        failures.append(f"profit_factor {profit_factor:.2f} < {config.min_profit_factor:.2f}")
    if expectancy < config.min_expectancy_per_trade:
        failures.append(
            f"expectancy_per_trade {expectancy:.6f} < {config.min_expectancy_per_trade:.6f}"
        )

    metrics: dict[str, float | int | bool] = {
        "trading_sessions": session_count,
        "trade_count": trade_count,
        "max_single_session_profit_share": max_session_profit_share,
        "max_trades_per_session": max_trades_per_session,
        "max_turnover_per_session": max_turnover_per_session,
        "exposure_fraction": exposure_fraction,
        "max_abs_exposure": max_abs_exposure,
        "has_short_exposure": has_short_exposure,
        "flat_by_session_close": flat_by_close,
        "max_holding_period_bars": int(max_holding_bars),
        "profit_factor": float(profit_factor),
        "expectancy_per_trade": expectancy,
    }
    return IntradayValidationResult(not failures, failures, metrics)


def _trade_timestamps(trades: pd.DataFrame) -> pd.DatetimeIndex:
    if trades.empty:
        return pd.DatetimeIndex([])
    if "timestamp" in trades.columns:
        return pd.DatetimeIndex(pd.to_datetime(trades["timestamp"], utc=True))
    if "entry_time" in trades.columns:
        return pd.DatetimeIndex(pd.to_datetime(trades["entry_time"], utc=True))
    return pd.DatetimeIndex(pd.to_datetime(trades.index, utc=True))


def _gross_exposure(positions: pd.Series | pd.DataFrame) -> pd.Series:
    if isinstance(positions, pd.Series):
        return positions.astype(float)
    return positions.astype(float).abs().sum(axis=1)


def _turnover_by_session(trades: pd.DataFrame, returns_index: pd.DatetimeIndex) -> pd.Series:
    if trades.empty:
        return pd.Series(dtype=float)
    times = _trade_timestamps(trades)
    if "weight_delta" in trades.columns:
        turnover = trades["weight_delta"].astype(float).abs().to_numpy()
    elif "quantity" in trades.columns:
        turnover = np.ones(len(trades), dtype=float)
    else:
        turnover = np.ones(len(trades), dtype=float)
    return pd.Series(turnover, index=times).groupby(times.normalize()).sum()


def _trades_per_session(trade_times: pd.DatetimeIndex) -> pd.Series:
    if trade_times.empty:
        return pd.Series(dtype=int)
    return pd.Series(1, index=trade_times).groupby(trade_times.normalize()).sum()


def _flat_by_session_close(positions: pd.Series | pd.DataFrame) -> bool:
    if positions.empty:
        return True
    gross = _gross_exposure(positions)
    last_by_session = gross.groupby(gross.index.normalize()).tail(1)
    return bool((last_by_session.abs() <= 1e-12).all())


def _max_holding_period_bars(positions: pd.Series | pd.DataFrame) -> int:
    if positions.empty:
        return 0
    gross = _gross_exposure(positions).abs() > 1e-12
    max_run = run = 0
    previous_session = None
    for ts, is_exposed in gross.items():
        session = ts.normalize()
        if session != previous_session:
            run = 0
            previous_session = session
        if bool(is_exposed):
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    return int(max_run)


def _trade_pnl(trades: pd.DataFrame) -> pd.Series:
    if trades.empty:
        return pd.Series(dtype=float)
    if "pnl" in trades.columns:
        return trades["pnl"].astype(float)
    return pd.Series(dtype=float)
