"""Standardized candidate metrics and validation checks.

Shared by candidate research modules so every candidate reports the same
metric set: Sharpe, Sortino, CAGR, max drawdown, Calmar, turnover, trade
count, exposure, stability score, WFA/MC pass-fail, and DSR p-value.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from validation.dsr.engine import compute_dsr
from validation.mc.engine import run_monte_carlo
from validation.wfa.engine import PRESETS, WFATier, generate_folds

TRADING_DAYS = 252

STRESS_WINDOWS = {
    "2022": ("2022-01-01", "2022-12-31"),
    "2023": ("2023-01-01", "2023-12-31"),
    "2025": ("2025-01-01", "2025-12-31"),
}


def standard_metrics(
    returns: pd.Series,
    *,
    weights: pd.DataFrame | None = None,
    trades: pd.DataFrame | None = None,
    initial_capital: float = 10_000.0,
) -> dict[str, float]:
    """Standardized daily-bar performance metrics for a candidate."""
    if returns.empty:
        return {"total_bars": 0}
    equity = (1.0 + returns).cumprod() * initial_capital
    years = len(returns) / TRADING_DAYS
    ann_return = float(returns.mean() * TRADING_DAYS)
    ann_vol = float(returns.std() * np.sqrt(TRADING_DAYS))
    downside = returns[returns < 0.0]
    downside_vol = float(downside.std() * np.sqrt(TRADING_DAYS)) if len(downside) > 1 else 0.0
    cummax = equity.cummax()
    max_dd = float(((equity - cummax) / cummax).min())
    cagr = float((equity.iloc[-1] / initial_capital) ** (1.0 / years) - 1.0) if years > 0 else 0.0
    metrics: dict[str, float] = {
        "total_bars": int(len(returns)),
        "total_return": float(equity.iloc[-1] / initial_capital - 1.0),
        "final_equity": float(equity.iloc[-1]),
        "cagr": cagr,
        "ann_volatility": ann_vol,
        "sharpe": ann_return / ann_vol if ann_vol > 0.0 else 0.0,
        "sortino": ann_return / downside_vol if downside_vol > 0.0 else 0.0,
        "max_drawdown": max_dd,
        "calmar": cagr / abs(max_dd) if max_dd < 0.0 else 0.0,
        **stability_score(returns),
    }
    if weights is not None:
        gross = weights.abs().sum(axis=1)
        metrics["average_gross_exposure"] = float(gross.mean())
        metrics["max_gross_exposure"] = float(gross.max())
        metrics["exposure_pct"] = float((gross > 1e-12).mean())
    if trades is not None:
        metrics["num_trades"] = int((trades.abs() > 1e-12).sum().sum())
        metrics["turnover_per_year"] = float(trades.abs().sum(axis=1).resample("YE").sum().mean())
    return metrics


def stability_score(returns: pd.Series, window: int = 60) -> dict[str, float]:
    """Rolling 12-week (60 trading day) Sharpe stability, house convention."""
    rolling = (
        (returns.rolling(window).mean() / returns.rolling(window).std() * np.sqrt(TRADING_DAYS))
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    negative_fraction = float((rolling < 0.0).mean()) if not rolling.empty else 1.0
    return {
        "stability_score": 1.0 - negative_fraction,
        "rolling_12wk_negative_fraction": negative_fraction,
        "rolling_12wk_min_sharpe": float(rolling.min()) if not rolling.empty else 0.0,
    }


def stress_window_report(
    returns: pd.Series,
    *,
    windows: dict[str, tuple[str, str]] | None = None,
    initial_capital: float = 10_000.0,
) -> dict[str, dict[str, float]]:
    """Per-window performance for the declared stress periods."""
    report: dict[str, dict[str, float]] = {}
    for name, (start, end) in (windows or STRESS_WINDOWS).items():
        window_returns = returns.loc[start:end]
        if window_returns.empty:
            report[name] = {"total_bars": 0}
            continue
        equity = (1.0 + window_returns).cumprod() * initial_capital
        cummax = equity.cummax()
        vol = float(window_returns.std() * np.sqrt(TRADING_DAYS))
        report[name] = {
            "total_bars": int(len(window_returns)),
            "total_return": float((1.0 + window_returns).prod() - 1.0),
            "sharpe": float(window_returns.mean() * TRADING_DAYS) / vol if vol > 0.0 else 0.0,
            "max_drawdown": float(((equity - cummax) / cummax).min()),
        }
    return report


def wfa_check(
    panel: pd.DataFrame,
    backtest_returns_fn: Callable[[pd.DataFrame], pd.Series],
    *,
    initial_capital: float = 10_000.0,
) -> dict[str, Any]:
    """Walk-forward check on the PRIMARY preset.

    ``backtest_returns_fn`` receives the panel truncated at the fold's test
    end and must return daily net returns for the full truncated history.
    """
    folds = []
    for i, (train_start, train_end, test_start, test_end) in enumerate(
        generate_folds(panel, PRESETS[WFATier.PRIMARY])
    ):
        returns = backtest_returns_fn(panel.loc[:test_end])
        oos = returns.loc[test_start:test_end]
        folds.append(
            {
                "fold": i,
                "train_start": str(train_start),
                "train_end": str(train_end),
                "test_start": str(test_start),
                "test_end": str(test_end),
                "bars": int(len(oos)),
                **standard_metrics(oos, initial_capital=initial_capital),
            }
        )
    positive = sum(1 for fold in folds if fold.get("total_return", 0.0) > 0.0)
    mean_sharpe = float(np.mean([fold["sharpe"] for fold in folds])) if folds else 0.0
    worst_dd = min((fold["max_drawdown"] for fold in folds), default=0.0)
    positive_fraction = positive / len(folds) if folds else 0.0
    return {
        "num_folds": len(folds),
        "mean_fold_sharpe": mean_sharpe,
        "worst_fold_max_drawdown": worst_dd,
        "positive_folds": positive,
        "positive_fold_fraction": positive_fraction,
        "strict_wfa_pass": bool(mean_sharpe >= 1.0 and worst_dd >= -0.15 and positive_fraction >= 0.70),
        "folds": folds,
    }


def mc_check(returns: pd.Series, *, initial_capital: float = 10_000.0) -> dict[str, Any]:
    """Monte Carlo block-bootstrap check, house convention."""
    result = run_monte_carlo(
        returns,
        num_paths=10000,
        block_size=20,
        initial_capital=initial_capital,
        ruin_threshold=-0.50,
        seed=42,
    )
    summary = result.summarize(initial_capital=initial_capital, ruin_threshold=-0.50)
    return {**summary, "strict_mc_pass": bool(summary.get("pct_5_sharpe", -999.0) > 0.10)}


def dsr_check(returns: pd.Series, observed_sharpe: float, *, candidate: str) -> dict[str, Any]:
    """Deflated Sharpe Ratio p-value, house convention."""
    result = compute_dsr(
        observed_sharpe=observed_sharpe,
        returns_matrix=returns.to_frame(candidate).to_numpy(),
        num_trials_raw=1,
        track_record_length=len(returns),
    )
    return {
        "observed_sharpe": observed_sharpe,
        "num_trials_raw": result.num_trials_raw,
        "num_trials_eff": result.num_trials_eff,
        "track_record_length": result.track_record_length,
        "pvalue": result.dsr_pvalue,
        "strict_dsr_pass": bool(result.dsr_pvalue < 0.05),
    }
