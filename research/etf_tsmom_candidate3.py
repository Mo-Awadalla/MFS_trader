"""Candidate 3: ETF TSMOM with no leverage above 1x."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.etf_tsmom_pipeline import (
    INITIAL_CAPITAL,
    _daily_metrics,
    backtest_etf_tsmom,
    load_etf_panel,
)
from strategies.etf_tsmom.signal import DEFAULT_UNIVERSE, ETFTSMOMParams
from validation.dsr.engine import compute_dsr
from validation.mc.engine import run_monte_carlo
from validation.wfa.engine import PRESETS, WFATier, generate_folds

CANDIDATE = "ETFTimeSeriesMomentumNoLeverage-v1"
ARTIFACT_PATH = Path("research/artifacts/etf_tsmom_noleverage_v1_backtest.json")
COMPARISON_PATH = Path("research/artifacts/etf_tsmom_candidate2_vs_candidate3.json")
RETURNS_DIR = Path("research/artifacts/etf_tsmom_noleverage_v1")
CANDIDATE2_ARTIFACT = Path("research/artifacts/etf_tsmom_voltarget_v1_backtest.json")


def candidate3_params() -> ETFTSMOMParams:
    return ETFTSMOMParams(
        lookback_days=252,
        realized_vol_days=63,
        top_k=3,
        max_weight=0.50,
        annual_vol_target=0.10,
        max_gross_exposure=1.0,
        cash_proxy="SHY",
    )


def run_candidate3() -> dict[str, Any]:
    df = load_etf_panel()
    params = candidate3_params()
    result = backtest_etf_tsmom(df, params=params)
    returns = result["returns"]
    wfa = _wfa_check(df, params)
    mc = _monte_carlo_check(returns)
    dsr = _dsr_check(returns, result["net_metrics"]["sharpe"])
    stability = _stability_check(returns)
    artifact = {
        "candidate": CANDIDATE,
        "status": "research_backtest_complete",
        "promotion_status": "validation_failed" if not stability["strict_stability_pass"] else "validation_partial_pass",
        "verdict": "reject_for_paper_ops_pending_stability_failure"
        if not stability["strict_stability_pass"]
        else "not_promoted_full_gauntlet_required",
        "frozen_spec": {
            "universe": list(DEFAULT_UNIVERSE),
            "rebalance": "monthly",
            "signal": "12-month absolute total return per ETF using data before rebalance date",
            "selection": "top 3 eligible ETFs by 12-month return; if none eligible, 100% SHY",
            "sizing": "inverse trailing 63-day realized volatility",
            "cap": "50% per ETF before gross scalar",
            "gross_exposure": "final gross exposure clamped to <= 1.0; no leverage",
            "execution": "next trading day open",
            "tuning": "none",
        },
        "data": {
            "source": "Massive adjusted daily flatfiles",
            "symbols": list(DEFAULT_UNIVERSE),
            "rows": int(len(df)),
            "start": str(df.index.min()),
            "end": str(df.index.max()),
            "limitation": "Massive flatfile access denied before 2021-06-30 under current credentials",
        },
        "params": result["params"],
        "gross_metrics": result["gross_metrics"],
        "net_metrics": result["net_metrics"],
        "trade_count": result["trade_count"],
        "rebalance_count": result["rebalance_count"],
        "skipped_rebalance_count": result["skipped_rebalance_count"],
        "average_gross_exposure": result["average_gross_exposure"],
        "max_gross_exposure": result["max_gross_exposure"],
        "turnover_per_year": result["turnover_per_year"],
        "pnl_by_symbol": result["pnl_by_symbol"],
        "wfa_primary": wfa,
        "monte_carlo": mc,
        "dsr": dsr,
        "stability": stability,
    }
    _write_outputs(artifact, result)
    comparison = _compare_to_candidate2(artifact)
    COMPARISON_PATH.write_text(json.dumps(comparison, indent=2, allow_nan=False))
    return artifact


def _write_outputs(artifact: dict[str, Any], result: dict[str, Any]) -> None:
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(artifact, indent=2, allow_nan=False))
    RETURNS_DIR.mkdir(parents=True, exist_ok=True)
    result["returns"].to_frame("returns").to_parquet(RETURNS_DIR / "returns.parquet")
    result["gross_returns"].to_frame("gross_returns").to_parquet(RETURNS_DIR / "gross_returns.parquet")
    result["weights"].to_parquet(RETURNS_DIR / "weights.parquet")


def _wfa_check(df: pd.DataFrame, params: ETFTSMOMParams) -> dict[str, Any]:
    folds = []
    for i, (train_start, train_end, test_start, test_end) in enumerate(
        generate_folds(df, PRESETS[WFATier.PRIMARY])
    ):
        result = backtest_etf_tsmom(df.loc[:test_end], params=params)
        returns = result["returns"].loc[test_start:test_end]
        folds.append(
            {
                "fold": i,
                "train_start": str(train_start),
                "train_end": str(train_end),
                "test_start": str(test_start),
                "test_end": str(test_end),
                "bars": int(len(returns)),
                **_daily_metrics(returns, INITIAL_CAPITAL),
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
        "worst_windows": {str(index): float(value) for index, value in rolling.sort_values().head(10).items()},
        "strict_stability_pass": bool((not rolling.empty) and min_sharpe >= -0.5 and negative_fraction < 0.05),
    }


def _compare_to_candidate2(candidate3: dict[str, Any]) -> dict[str, Any]:
    candidate2 = json.loads(CANDIDATE2_ARTIFACT.read_text())
    c2 = _comparison_row(candidate2)
    c3 = _comparison_row(candidate3)
    deltas = {
        key: c3[key] - c2[key]
        for key in c3
        if isinstance(c3[key], int | float) and isinstance(c2.get(key), int | float)
    }
    return {
        "candidate2": c2,
        "candidate3": c3,
        "delta_candidate3_minus_candidate2": deltas,
        "verdict": _comparison_verdict(candidate2, candidate3),
    }


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
        "final_equity": metrics["final_equity"],
        "ann_volatility": metrics["ann_volatility"],
        "average_gross_exposure": artifact["average_gross_exposure"],
        "max_gross_exposure": artifact["max_gross_exposure"],
        "trade_count": artifact["trade_count"],
        "wfa_pass": artifact["wfa_primary"]["strict_wfa_pass"],
        "mc_pass": artifact["monte_carlo"]["strict_mc_pass"],
        "dsr_pass": artifact["dsr"]["strict_dsr_pass"],
        "stability_pass": stability["strict_stability_pass"],
        "rolling_12wk_min_sharpe": stability["rolling_12wk_min_sharpe"],
        "rolling_12wk_negative_fraction": stability["rolling_12wk_negative_fraction"],
    }


def _comparison_verdict(candidate2: dict[str, Any], candidate3: dict[str, Any]) -> str:
    if candidate3["stability"]["strict_stability_pass"]:
        return "candidate3_improves_stability_and_can_continue_validation_review"
    if (
        candidate3["stability"]["rolling_12wk_negative_fraction"]
        < candidate2["stability"]["rolling_12wk_negative_fraction"]
    ):
        return "candidate3_improves_but_does_not_fix_stability"
    return "candidate3_does_not_fix_stability"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Candidate 3 no-leverage ETF TSMOM checks.")
    parser.parse_args()
    artifact = run_candidate3()
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
