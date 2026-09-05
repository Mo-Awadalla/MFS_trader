"""BayesianDMAWeeklyETF-v1 research implementation."""

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

CANDIDATE = "BayesianDMAWeeklyETF-v1"
ARTIFACT_PATH = Path("research/artifacts/bayesian_dma_weekly_etf_v1_backtest.json")
COMPARISON_PATH = Path("research/artifacts/bayesian_dma_weekly_etf_v1_vs_candidate2.json")
RETURNS_DIR = Path("research/artifacts/bayesian_dma_weekly_etf_v1")
CANDIDATE2_ARTIFACT = Path("research/artifacts/etf_tsmom_voltarget_v1_backtest.json")
RISK_ASSETS = tuple(symbol for symbol in DEFAULT_UNIVERSE if symbol != "SHY")


def dma_tsmom_signal(
    prices: pd.DataFrame,
    lookbacks: list[int] | tuple[int, ...] = (21, 63, 126),
    lambda_t: float = 0.99,
    rebalance_freq: str = "W-FRI",
    long_only: bool = True,
) -> tuple[pd.DataFrame, np.ndarray]:
    """Return weekly DMA positions and per-asset model weights.

    This v1 uses a continuous Bernoulli hit-rate likelihood. It tests the DMA
    lookback-weighting mechanism, not the paper's TVP logistic regression.
    """
    if prices.empty:
        empty = pd.DataFrame(index=pd.DatetimeIndex([], name=prices.index.name), columns=prices.columns)
        return empty, np.empty((0, len(prices.columns), len(lookbacks)))
    prices = prices.sort_index().astype(float)
    weekly = prices.resample(rebalance_freq).last().dropna(how="all")
    positions = pd.DataFrame(0, index=weekly.index, columns=weekly.columns, dtype=int)
    model_weights = np.full((len(weekly), len(weekly.columns), len(lookbacks)), 1.0 / len(lookbacks))
    weekly_returns = weekly.pct_change(fill_method=None)
    realized_direction = np.sign(weekly_returns).replace(0.0, np.nan)
    signals = {
        lookback: np.sign(weekly.div(weekly.shift(max(1, lookback // 5))).sub(1.0))
        for lookback in lookbacks
    }
    correct_counts = pd.DataFrame(1.0, index=weekly.columns, columns=list(lookbacks))
    total_counts = pd.DataFrame(2.0, index=weekly.columns, columns=list(lookbacks))

    for t, ts in enumerate(weekly.index):
        if t > 0:
            prev_ts = weekly.index[t - 1]
            actual = realized_direction.loc[prev_ts]
            for _k, lookback in enumerate(lookbacks):
                pred = signals[lookback].loc[prev_ts]
                valid = actual.notna() & pred.notna()
                correct_counts.loc[valid, lookback] += (pred.loc[valid] == actual.loc[valid]).astype(float)
                total_counts.loc[valid, lookback] += 1.0
            hit_rates = (correct_counts / total_counts).clip(1e-6, 1.0 - 1e-6)
            previous = pd.DataFrame(
                model_weights[t - 1],
                index=weekly.columns,
                columns=list(lookbacks),
            )
            prior = previous.pow(lambda_t)
            likelihood = pd.DataFrame(1.0, index=weekly.columns, columns=list(lookbacks))
            for lookback in lookbacks:
                pred = signals[lookback].loc[prev_ts]
                actual_valid = actual.notna() & pred.notna()
                correct = pred.loc[actual_valid] == actual.loc[actual_valid]
                likelihood.loc[actual_valid, lookback] = np.where(
                    correct,
                    hit_rates.loc[actual_valid, lookback],
                    1.0 - hit_rates.loc[actual_valid, lookback],
                )
            posterior = prior * likelihood
            model_weights[t] = posterior.div(posterior.sum(axis=1), axis=0).to_numpy()

        integrated = pd.Series(0.0, index=weekly.columns)
        for k, lookback in enumerate(lookbacks):
            integrated += model_weights[t, :, k] * signals[lookback].loc[ts].reindex(weekly.columns).fillna(0.0)
        position = np.sign(integrated).astype(int)
        if long_only:
            position = position.clip(lower=0)
        positions.loc[ts] = position
    return positions, model_weights


def dma_daily_weights(
    prices: pd.DataFrame,
    *,
    lookbacks: list[int] | tuple[int, ...] = (21, 63, 126),
    lambda_t: float = 0.99,
    long_only: bool = True,
    max_weight: float = 0.50,
    max_gross_exposure: float = 1.0,
    vol_window: int = 20,
    vol_target: float = 0.10,
    cash_proxy: str = "SHY",
) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    risky = prices.loc[:, [symbol for symbol in prices.columns if symbol != cash_proxy]]
    weekly_positions, model_weights = dma_tsmom_signal(
        risky,
        lookbacks=lookbacks,
        lambda_t=lambda_t,
        rebalance_freq="W-FRI",
        long_only=long_only,
    )
    daily_returns = prices.pct_change(fill_method=None)
    realized_vol = daily_returns.rolling(vol_window).std() * np.sqrt(252)
    weights = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    current = pd.Series(0.0, index=prices.columns)
    weekly_idx = 0
    for i, ts in enumerate(prices.index):
        while (
            weekly_idx < len(weekly_positions.index)
            and weekly_positions.index[weekly_idx].normalize() < ts.normalize()
        ):
            signal_ts = weekly_positions.index[weekly_idx]
            signal_loc = _last_daily_loc_on_or_before(prices.index, signal_ts)
            if signal_loc is not None and i > max(lookbacks):
                active = weekly_positions.iloc[weekly_idx]
                selected = list(active[active > 0].index)
                if selected:
                    target = _inverse_vol_weights(realized_vol.iloc[signal_loc].reindex(selected), prices.columns)
                    target = _cap_and_redistribute(target, max_weight)
                    target = _apply_vol_target(
                        target,
                        realized_vol.iloc[signal_loc],
                        vol_target,
                        max_gross_exposure,
                    )
                else:
                    target = pd.Series(0.0, index=prices.columns)
                    target.loc[cash_proxy] = 1.0
                current = target
            weekly_idx += 1
        weights.loc[ts] = current
    trades = weights.diff().fillna(weights)
    return weights, trades, model_weights


def run_candidate() -> dict[str, Any]:
    panel = load_etf_panel()
    open_px = panel.xs("open", axis=1, level=1).astype(float)
    close = panel.xs("close", axis=1, level=1).astype(float)
    weights, trades, model_weights = dma_daily_weights(close)
    symbol_returns = open_px.shift(-1).div(open_px).sub(1.0).fillna(0.0)
    gross_returns = (weights * symbol_returns).sum(axis=1)
    costs = _trade_costs(trades, open_px, etf_cost_config())
    returns = gross_returns - costs
    artifact = {
        "candidate": CANDIDATE,
        "status": "research_backtest_complete",
        "promotion_status": "validation_failed",
        "verdict": "pending_gate_results",
        "v1_caveat": "Tests DMA lookback-weighting with continuous Bernoulli hit-rate likelihood; does not test Levy-Lopes TVP logistic regression.",
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
            "lookbacks": [21, 63, 126],
            "lambda_t": 0.99,
            "rebalance_freq": "W-FRI",
            "long_only": True,
            "cash_proxy": "SHY",
            "vol_window": 20,
            "vol_target": 0.10,
            "max_weight": 0.50,
            "max_gross_exposure": 1.0,
        },
        "gross_metrics": _daily_metrics(gross_returns, INITIAL_CAPITAL),
        "net_metrics": _daily_metrics(returns, INITIAL_CAPITAL),
        "trade_count": int((trades.abs() > 1e-12).sum().sum()),
        "average_gross_exposure": float(weights.abs().sum(axis=1).mean()),
        "max_gross_exposure": float(weights.abs().sum(axis=1).max()),
        "turnover_per_year": float(trades.abs().sum(axis=1).resample("YE").sum().mean()),
        "pnl_by_symbol": _series_dict((weights * symbol_returns).sub(_allocated_costs(costs, weights), axis=0).sum().sort_values()),
    }
    artifact["wfa_primary"] = _wfa_check(panel)
    artifact["monte_carlo"] = _monte_carlo_check(returns)
    artifact["dsr"] = _dsr_check(returns, artifact["net_metrics"]["sharpe"])
    artifact["stability"] = _stability_check(returns)
    artifact["verdict"] = _verdict(artifact)
    artifact["promotion_status"] = "validation_failed" if "reject" in artifact["verdict"] else "validation_partial_pass"
    _write_outputs(artifact, returns, gross_returns, weights, model_weights)
    _write_comparison(artifact)
    return artifact


def _wfa_check(panel: pd.DataFrame) -> dict[str, Any]:
    folds = []
    for i, (_train_start, _train_end, test_start, test_end) in enumerate(
        generate_folds(panel, PRESETS[WFATier.PRIMARY])
    ):
        context = panel.loc[:test_end]
        open_px = context.xs("open", axis=1, level=1).astype(float)
        close = context.xs("close", axis=1, level=1).astype(float)
        weights, trades, _ = dma_daily_weights(close)
        returns = (weights * open_px.shift(-1).div(open_px).sub(1.0).fillna(0.0)).sum(axis=1)
        returns = returns - _trade_costs(trades, open_px, etf_cost_config())
        oos = returns.loc[test_start:test_end]
        folds.append({"fold": i, "bars": int(len(oos)), **_daily_metrics(oos, INITIAL_CAPITAL)})
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
    result = run_monte_carlo(returns, num_paths=10000, block_size=20, initial_capital=INITIAL_CAPITAL, seed=42)
    summary = result.summarize(initial_capital=INITIAL_CAPITAL)
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
        "pvalue": result.dsr_pvalue,
        "strict_dsr_pass": bool(result.dsr_pvalue < 0.05),
        "num_trials_raw": result.num_trials_raw,
        "num_trials_eff": result.num_trials_eff,
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
        "c5_success_bucket": "<20%" if negative_fraction < 0.20 else "20-27%" if negative_fraction <= 0.27 else ">27%",
        "strict_stability_pass": bool((not rolling.empty) and min_sharpe >= -0.5 and negative_fraction < 0.05),
        "c5_priority_pass": bool(negative_fraction < 0.20),
        "worst_windows": {str(index): float(value) for index, value in rolling.sort_values().head(10).items()},
    }


def _verdict(artifact: dict[str, Any]) -> str:
    if artifact["stability"]["c5_priority_pass"]:
        return "prioritize_for_v2_paper_faithful_logistic_review"
    if artifact["stability"]["c5_success_bucket"] == "20-27%":
        return "comparable_to_baseline_not_priority"
    return "reject_dma_weighting_class"


def _write_outputs(
    artifact: dict[str, Any],
    returns: pd.Series,
    gross_returns: pd.Series,
    weights: pd.DataFrame,
    model_weights: np.ndarray,
) -> None:
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(artifact, indent=2, allow_nan=False))
    RETURNS_DIR.mkdir(parents=True, exist_ok=True)
    returns.to_frame("returns").to_parquet(RETURNS_DIR / "returns.parquet")
    gross_returns.to_frame("gross_returns").to_parquet(RETURNS_DIR / "gross_returns.parquet")
    weights.to_parquet(RETURNS_DIR / "weights.parquet")
    np.save(RETURNS_DIR / "model_weights.npy", model_weights)


def _write_comparison(artifact: dict[str, Any]) -> None:
    if not CANDIDATE2_ARTIFACT.exists():
        return
    candidate2 = json.loads(CANDIDATE2_ARTIFACT.read_text())
    comparison = {
        "candidate2": _comparison_row(candidate2),
        "c5": _comparison_row(artifact),
    }
    comparison["delta_c5_minus_candidate2"] = {
        key: comparison["c5"][key] - comparison["candidate2"][key]
        for key in comparison["c5"]
        if isinstance(comparison["c5"][key], int | float)
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


def _last_daily_loc_on_or_before(index: pd.DatetimeIndex, signal_ts: pd.Timestamp) -> int | None:
    eligible = np.flatnonzero(index.normalize() <= signal_ts.normalize())
    if len(eligible) == 0:
        return None
    return int(eligible[-1])


def _inverse_vol_weights(vol: pd.Series, symbols: pd.Index) -> pd.Series:
    weights = pd.Series(0.0, index=symbols)
    inv = 1.0 / vol.replace(0.0, np.nan).dropna()
    if inv.empty:
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
    return capped


def _apply_vol_target(weights: pd.Series, vol: pd.Series, target_vol: float, max_gross: float) -> pd.Series:
    selected = weights[weights > 0.0]
    if selected.empty:
        return weights
    selected_vol = vol.reindex(selected.index).dropna()
    if selected_vol.empty:
        return weights
    portfolio_vol = float(np.sqrt((selected.pow(2) * selected_vol.pow(2)).sum()))
    if portfolio_vol <= 0.0:
        return weights
    return weights * min(max_gross, target_vol / portfolio_vol)


def _series_dict(series: pd.Series) -> dict[str, float]:
    return {str(index): float(value) for index, value in series.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BayesianDMAWeeklyETF-v1.")
    parser.parse_args()
    artifact = run_candidate()
    print(
        json.dumps(
            {
                "candidate": artifact["candidate"],
                "verdict": artifact["verdict"],
                "net_metrics": artifact["net_metrics"],
                "stability": artifact["stability"],
                "artifact": str(ARTIFACT_PATH),
                "comparison": str(COMPARISON_PATH),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
