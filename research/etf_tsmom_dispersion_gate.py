"""CrossSectionalDispersionGateWeeklyETF-v1 research implementation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.etf_tsmom_pipeline import (
    INITIAL_CAPITAL,
    _allocated_costs,
    _daily_metrics,
    _trade_costs,
    etf_cost_config,
    load_etf_panel,
)
from strategies.etf_tsmom.signal import DEFAULT_UNIVERSE
from validation.dsr.engine import compute_dsr
from validation.mc.engine import run_monte_carlo
from validation.wfa.engine import PRESETS, WFATier, generate_folds

CANDIDATE = "CrossSectionalDispersionGateWeeklyETF-v1"
ARTIFACT_PATH = Path("research/artifacts/dispersion_gate_v1_backtest.json")
COMPARISON_PATH = Path("research/artifacts/dispersion_gate_v1_vs_candidate2.json")
RETURNS_DIR = Path("research/artifacts/dispersion_gate_v1")
CANDIDATE2_ARTIFACT = Path("research/artifacts/etf_tsmom_voltarget_v1_backtest.json")
RISK_ASSETS = ("SPY", "QQQ", "IWM", "IEF", "GLD", "DBC", "EFA", "EEM", "VNQ", "TLT")
CASH_PROXY = "SHY"


def dispersion_metric(
    prices: pd.DataFrame,
    *,
    risky_assets: tuple[str, ...] = RISK_ASSETS,
    dispersion_window: int = 21,
) -> pd.Series:
    returns = prices.loc[:, list(risky_assets)].pct_change(fill_method=None)
    cross_sectional_std = returns.std(axis=1)
    return cross_sectional_std.rolling(dispersion_window).mean()


def dispersion_gate_tsmom_signal(
    prices: pd.DataFrame,
    rebalance_freq: str = "W-FRI",
    dispersion_window: int = 21,
    threshold_lookback: int = 252,
    threshold_percentile: float = 0.80,
    long_only: bool = True,
) -> tuple[pd.DataFrame, pd.Series]:
    """Return weekly C12 weights and gate state.

    Weekly rows are signal dates. Signals use only daily closes strictly before
    the weekly label, then execute in the daily backtest on the next session.
    """
    if not long_only:
        raise ValueError("C12 v1 is frozen as long-only")
    prices = prices.sort_index().astype(float)
    symbols = list(prices.columns)
    _validate_columns(symbols)
    weekly_index = prices.resample(rebalance_freq).last().index
    positions = pd.DataFrame(0.0, index=weekly_index, columns=symbols)
    gate_state = pd.Series(False, index=weekly_index, dtype=bool)
    momentum = prices.loc[:, list(RISK_ASSETS)].div(prices.loc[:, list(RISK_ASSETS)].shift(63)).sub(1.0)
    realized_vol = prices.pct_change(fill_method=None).rolling(20).std() * np.sqrt(252)
    dispersion = dispersion_metric(prices, dispersion_window=dispersion_window)
    threshold = dispersion.rolling(threshold_lookback).quantile(threshold_percentile)

    for ts in weekly_index:
        signal_loc = _last_daily_loc_before(prices.index, ts)
        if signal_loc is None or signal_loc <= max(63, 20, dispersion_window + threshold_lookback):
            positions.loc[ts, CASH_PROXY] = 1.0
            continue
        signal_ts = prices.index[signal_loc]
        gate_on = bool(dispersion.loc[signal_ts] <= threshold.loc[signal_ts])
        gate_state.loc[ts] = gate_on
        if not gate_on:
            positions.loc[ts, CASH_PROXY] = 1.0
            continue
        signal = momentum.loc[signal_ts].replace([np.inf, -np.inf], np.nan).dropna()
        selected = list(signal[signal > 0.0].index)
        if not selected:
            positions.loc[ts, CASH_PROXY] = 1.0
            continue
        target = _inverse_vol_weights(realized_vol.loc[signal_ts].reindex(selected), symbols)
        target = _cap_and_redistribute(target, 0.50)
        gross = float(target.abs().sum())
        if gross > 1.0:
            target = target / gross
        positions.loc[ts] = target
    return positions, gate_state


def dispersion_gate_daily_weights(
    prices: pd.DataFrame,
    *,
    rebalance_freq: str = "W-FRI",
    dispersion_window: int = 21,
    threshold_lookback: int = 252,
    threshold_percentile: float = 0.80,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    weekly_positions, gate_state = dispersion_gate_tsmom_signal(
        prices,
        rebalance_freq=rebalance_freq,
        dispersion_window=dispersion_window,
        threshold_lookback=threshold_lookback,
        threshold_percentile=threshold_percentile,
    )
    weights = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    current = pd.Series(0.0, index=prices.columns)
    weekly_idx = 0
    for ts in prices.index:
        while (
            weekly_idx < len(weekly_positions.index)
            and weekly_positions.index[weekly_idx].normalize() < ts.normalize()
        ):
            current = weekly_positions.iloc[weekly_idx]
            weekly_idx += 1
        weights.loc[ts] = current
    trades = weights.diff().fillna(weights)
    return weights, trades, gate_state


def run_candidate() -> dict[str, Any]:
    panel = load_etf_panel()
    result = _backtest(panel)
    returns = result["returns"]
    artifact = {
        "candidate": CANDIDATE,
        "status": "research_backtest_complete",
        "promotion_status": "validation_failed",
        "verdict": "pending_gate_results",
        "citation_caveat": "Conceptual transfer from FX dispersion literature; not a published ETF strategy replication.",
        "data": {
            "source": "Massive adjusted daily flatfiles",
            "symbols": list(DEFAULT_UNIVERSE),
            "risk_assets": list(RISK_ASSETS),
            "rows": int(len(panel)),
            "start": str(panel.index.min()),
            "end": str(panel.index.max()),
            "limitation": "Massive flatfile access denied before 2021-06-30 under current credentials",
        },
        "params": {
            "rebalance_freq": "W-FRI",
            "lookback_days": 63,
            "dispersion_window": 21,
            "threshold_lookback": 252,
            "threshold_percentile": 0.80,
            "realized_vol_days": 20,
            "max_weight": 0.50,
            "max_gross_exposure": 1.0,
            "cash_proxy": CASH_PROXY,
        },
        "gross_metrics": result["gross_metrics"],
        "net_metrics": result["net_metrics"],
        "trade_count": result["trade_count"],
        "average_gross_exposure": result["average_gross_exposure"],
        "max_gross_exposure": result["max_gross_exposure"],
        "turnover_per_year": result["turnover_per_year"],
        "gate_off_fraction": result["gate_off_fraction"],
        "gate_off_weeks": result["gate_off_weeks"],
        "total_weeks": result["total_weeks"],
        "pnl_by_symbol": result["pnl_by_symbol"],
    }
    artifact["wfa_primary"] = _wfa_check(panel)
    artifact["monte_carlo"] = _monte_carlo_check(returns)
    artifact["dsr"] = _dsr_check(returns, artifact["net_metrics"]["sharpe"])
    artifact["stability"] = _stability_check(returns)
    artifact["stress_windows"] = _stress_windows(result["gate_state"], returns)
    artifact["verdict"] = _verdict(artifact)
    artifact["promotion_status"] = "validation_partial_pass" if artifact["stability"]["c12_priority_pass"] else "validation_failed"
    _write_outputs(artifact, result)
    _write_comparison(artifact)
    return artifact


def _backtest(panel: pd.DataFrame) -> dict[str, Any]:
    open_px = panel.xs("open", axis=1, level=1).astype(float)
    close = panel.xs("close", axis=1, level=1).astype(float)
    close = close.loc[:, list(RISK_ASSETS) + [CASH_PROXY]]
    open_px = open_px.loc[:, close.columns]
    weights, trades, gate_state = dispersion_gate_daily_weights(close)
    symbol_returns = open_px.shift(-1).div(open_px).sub(1.0).fillna(0.0)
    gross_returns = (weights * symbol_returns).sum(axis=1)
    costs = _trade_costs(trades, open_px, etf_cost_config())
    returns = gross_returns - costs
    symbol_pnl = (weights * symbol_returns).sub(_allocated_costs(costs, weights), axis=0).sum().sort_values()
    gate_ready = gate_state.iloc[gate_state.index.searchsorted(close.index[min(len(close) - 1, 336)]) :]
    return {
        "gross_metrics": _daily_metrics(gross_returns, INITIAL_CAPITAL),
        "net_metrics": _daily_metrics(returns, INITIAL_CAPITAL),
        "trade_count": int((trades.abs() > 1e-12).sum().sum()),
        "average_gross_exposure": float(weights.abs().sum(axis=1).mean()),
        "max_gross_exposure": float(weights.abs().sum(axis=1).max()),
        "turnover_per_year": float(trades.abs().sum(axis=1).resample("YE").sum().mean()),
        "gate_off_fraction": float((~gate_ready).mean()) if not gate_ready.empty else 0.0,
        "gate_off_weeks": int((~gate_ready).sum()),
        "total_weeks": int(len(gate_ready)),
        "pnl_by_symbol": {str(index): float(value) for index, value in symbol_pnl.items()},
        "weights": weights,
        "trades": trades,
        "returns": returns,
        "gross_returns": gross_returns,
        "gate_state": gate_state,
    }


def _wfa_check(panel: pd.DataFrame) -> dict[str, Any]:
    folds = []
    for i, (train_start, train_end, test_start, test_end) in enumerate(
        generate_folds(panel, PRESETS[WFATier.PRIMARY])
    ):
        result = _backtest(panel.loc[:test_end])
        oos = result["returns"].loc[test_start:test_end]
        folds.append(
            {
                "fold": i,
                "train_start": str(train_start),
                "train_end": str(train_end),
                "test_start": str(test_start),
                "test_end": str(test_end),
                "bars": int(len(oos)),
                **_daily_metrics(oos, INITIAL_CAPITAL),
            }
        )
    positive = sum(1 for fold in folds if fold["total_return"] > 0.0)
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


def _monte_carlo_check(returns: pd.Series) -> dict[str, Any]:
    result = run_monte_carlo(
        returns,
        num_paths=10000,
        block_size=20,
        initial_capital=INITIAL_CAPITAL,
        ruin_threshold=-0.50,
        seed=42,
    )
    summary = result.summarize(initial_capital=INITIAL_CAPITAL, ruin_threshold=-0.50)
    return {**summary, "strict_mc_pass": bool(summary.get("pct_5_sharpe", -999.0) > 0.10)}


def _dsr_check(returns: pd.Series, observed_sharpe: float) -> dict[str, Any]:
    result = compute_dsr(
        observed_sharpe=observed_sharpe,
        returns_matrix=returns.to_frame(CANDIDATE).to_numpy(),
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


def _stability_check(returns: pd.Series) -> dict[str, Any]:
    rolling = (returns.rolling(60).mean() / returns.rolling(60).std() * np.sqrt(252)).replace(
        [np.inf, -np.inf],
        np.nan,
    ).dropna()
    negative_fraction = float((rolling < 0.0).mean()) if not rolling.empty else 1.0
    min_sharpe = float(rolling.min()) if not rolling.empty else 0.0
    return {
        "rolling_12wk_min_sharpe": min_sharpe,
        "rolling_12wk_negative_fraction": negative_fraction,
        "c12_success_bucket": "<20%" if negative_fraction < 0.20 else "20-27%" if negative_fraction <= 0.27 else ">27%",
        "strict_stability_pass": bool((not rolling.empty) and min_sharpe >= -0.5 and negative_fraction < 0.05),
        "c12_priority_pass": bool(negative_fraction < 0.20),
        "worst_windows": {str(index): float(value) for index, value in rolling.sort_values().head(10).items()},
    }


def _stress_windows(gate_state: pd.Series, returns: pd.Series) -> dict[str, dict[str, float]]:
    windows = {
        "2022_h1": ("2022-01-01", "2022-06-30"),
        "2023_h2": ("2023-07-01", "2023-12-31"),
        "2025_h1": ("2025-01-01", "2025-06-30"),
    }
    result = {}
    for name, (start, end) in windows.items():
        gates = gate_state.loc[start:end]
        period_returns = returns.loc[start:end]
        result[name] = {
            "gate_off_fraction": float((~gates).mean()) if not gates.empty else 0.0,
            "total_return": float((1.0 + period_returns).prod() - 1.0) if not period_returns.empty else 0.0,
        }
    return result


def _verdict(artifact: dict[str, Any]) -> str:
    stability = artifact["stability"]
    if stability["c12_priority_pass"]:
        return "prioritize_dispersion_gate_for_review"
    if stability["c12_success_bucket"] == "20-27%":
        return "comparable_to_baseline_not_priority"
    return "reject_dispersion_gate_v1"


def _write_outputs(artifact: dict[str, Any], result: dict[str, Any]) -> None:
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(artifact, indent=2, allow_nan=False))
    RETURNS_DIR.mkdir(parents=True, exist_ok=True)
    result["returns"].to_frame("returns").to_parquet(RETURNS_DIR / "returns.parquet")
    result["gross_returns"].to_frame("gross_returns").to_parquet(RETURNS_DIR / "gross_returns.parquet")
    result["weights"].to_parquet(RETURNS_DIR / "weights.parquet")
    result["gate_state"].to_frame("gate_on").to_parquet(RETURNS_DIR / "gate_state.parquet")


def _write_comparison(artifact: dict[str, Any]) -> None:
    if not CANDIDATE2_ARTIFACT.exists():
        return
    candidate2 = json.loads(CANDIDATE2_ARTIFACT.read_text())
    comparison = {
        "candidate2": _comparison_row(candidate2),
        "c12": _comparison_row(artifact),
    }
    comparison["delta_c12_minus_candidate2"] = {
        key: comparison["c12"][key] - comparison["candidate2"][key]
        for key in comparison["c12"]
        if isinstance(comparison["c12"][key], int | float)
        and isinstance(comparison["candidate2"].get(key), int | float)
    }
    COMPARISON_PATH.write_text(json.dumps(comparison, indent=2, allow_nan=False))


def _comparison_row(artifact: dict[str, Any]) -> dict[str, Any]:
    metrics = artifact["net_metrics"]
    stability = artifact["stability"]
    return {
        "candidate": artifact["candidate"],
        "verdict": artifact["verdict"],
        "sharpe": metrics["sharpe"],
        "cagr": metrics["cagr"],
        "total_return": metrics["total_return"],
        "max_drawdown": metrics["max_drawdown"],
        "ann_volatility": metrics["ann_volatility"],
        "trade_count": artifact["trade_count"],
        "average_gross_exposure": artifact["average_gross_exposure"],
        "max_gross_exposure": artifact["max_gross_exposure"],
        "wfa_pass": artifact["wfa_primary"]["strict_wfa_pass"],
        "mc_pass": artifact["monte_carlo"]["strict_mc_pass"],
        "dsr_pass": artifact["dsr"]["strict_dsr_pass"],
        "stability_pass": stability["strict_stability_pass"],
        "rolling_12wk_min_sharpe": stability["rolling_12wk_min_sharpe"],
        "rolling_12wk_negative_fraction": stability["rolling_12wk_negative_fraction"],
    }


def _validate_columns(symbols: list[str]) -> None:
    missing = [symbol for symbol in (*RISK_ASSETS, CASH_PROXY) if symbol not in symbols]
    if missing:
        raise ValueError(f"missing required C12 symbols: {missing}")


def _last_daily_loc_before(index: pd.DatetimeIndex, signal_ts: pd.Timestamp) -> int | None:
    eligible = np.flatnonzero(index.normalize() < signal_ts.normalize())
    if len(eligible) == 0:
        return None
    return int(eligible[-1])


def _inverse_vol_weights(vol: pd.Series, symbols: list[str]) -> pd.Series:
    weights = pd.Series(0.0, index=symbols)
    inv = 1.0 / vol.replace(0.0, np.nan).dropna()
    if inv.empty:
        weights.loc[CASH_PROXY] = 1.0
        return weights
    weights.loc[list(inv.index)] = inv / inv.sum()
    return weights


def _cap_and_redistribute(weights: pd.Series, cap: float) -> pd.Series:
    capped = weights.copy()
    for _ in range(len(capped)):
        over = capped > cap
        if not bool(over.any()):
            break
        excess = float((capped[over] - cap).sum())
        capped[over] = cap
        under = (capped > 0.0) & (capped < cap)
        if not bool(under.any()) or excess <= 0.0:
            break
        capped.loc[under] += excess * capped.loc[under] / capped.loc[under].sum()
    gross = float(capped.sum())
    if 0.0 < gross < 1.0 and bool((capped > 0.0).any()):
        capped.loc[capped > 0.0] /= gross
    return capped


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CrossSectionalDispersionGateWeeklyETF-v1.")
    parser.parse_args()
    artifact = run_candidate()
    print(
        json.dumps(
            {
                "candidate": artifact["candidate"],
                "verdict": artifact["verdict"],
                "net_metrics": artifact["net_metrics"],
                "gate_off_fraction": artifact["gate_off_fraction"],
                "stability": artifact["stability"],
                "artifact": str(ARTIFACT_PATH),
                "comparison": str(COMPARISON_PATH),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
