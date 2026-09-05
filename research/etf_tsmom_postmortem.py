"""Post-mortem diagnostics for ETFTimeSeriesMomentumVolTarget-v1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.etf_tsmom_pipeline import (
    ARTIFACT_PATH,
    INITIAL_CAPITAL,
    _allocated_costs,
    _daily_metrics,
    _trade_costs,
    backtest_etf_tsmom,
    etf_cost_config,
    load_etf_panel,
)
from strategies.etf_tsmom.signal import generate_weight_signals

POSTMORTEM_PATH = Path("research/artifacts/etf_tsmom_voltarget_v1_postmortem.json")


def build_postmortem() -> dict[str, Any]:
    df = load_etf_panel()
    base = json.loads(ARTIFACT_PATH.read_text()) if ARTIFACT_PATH.exists() else {}
    result = backtest_etf_tsmom(df)
    weights = result["weights"]
    returns = result["returns"]
    gross_returns = result["gross_returns"]
    desired, trades, portfolio = generate_weight_signals(df)
    open_px = df.xs("open", axis=1, level=1).astype(float)
    symbol_returns = open_px.shift(-1).div(open_px).sub(1.0).fillna(0.0)
    costs = _trade_costs(trades, open_px, etf_cost_config())
    symbol_contrib = (weights * symbol_returns).sub(_allocated_costs(costs, weights), axis=0)
    rolling = _rolling_stability(returns)
    return {
        "candidate": "ETFTimeSeriesMomentumVolTarget-v1",
        "status": "validation_failed",
        "verdict": "reject_for_paper_ops_pending_stability_failure",
        "summary_metrics": base.get("net_metrics", result["net_metrics"]),
        "gate_status": {
            "wfa_primary": base.get("wfa_primary", {}).get("strict_wfa_pass"),
            "monte_carlo": base.get("monte_carlo", {}).get("strict_mc_pass"),
            "dsr": base.get("dsr", {}).get("strict_dsr_pass"),
            "stability": base.get("stability", {}).get("strict_stability_pass"),
        },
        "data": base.get("data", {}),
        "gross_vs_net": {
            "gross": result["gross_metrics"],
            "net": result["net_metrics"],
            "cost_drag_total_return": float(gross_returns.sum() - returns.sum()),
            "total_cost_return": float(costs.sum()),
        },
        "regime_split": _regime_split(returns),
        "rolling_stability": rolling,
        "drawdown_autopsy": _drawdown_autopsy(returns),
        "asset_attribution": {
            "pnl_by_symbol": _series_dict(symbol_contrib.sum().sort_values()),
            "worst_symbols": _series_dict(symbol_contrib.sum().sort_values().head(5)),
            "best_symbols": _series_dict(symbol_contrib.sum().sort_values(ascending=False).head(5)),
            "average_weight": _series_dict(weights.mean().sort_values(ascending=False)),
            "max_weight": _series_dict(weights.max().sort_values(ascending=False)),
        },
        "selection_autopsy": _selection_autopsy(weights, portfolio),
        "vol_target_autopsy": _vol_target_autopsy(weights, returns),
        "cost_turnover_autopsy": {
            "trade_count": int((trades.abs() > 1e-12).sum().sum()),
            "turnover_per_year": float(trades.abs().sum(axis=1).resample("YE").sum().mean()),
            "total_cost_return": float(costs.sum()),
            "average_rebalance_turnover": float(trades.abs().sum(axis=1)[trades.abs().sum(axis=1) > 0].mean()),
        },
        "interpretation": _interpret(returns, weights, symbol_contrib, rolling),
        "recommended_next_steps": _recommended_next_steps(rolling),
    }


def write_postmortem(path: str | Path = POSTMORTEM_PATH) -> dict[str, Any]:
    postmortem = build_postmortem()
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(postmortem, indent=2, allow_nan=False))
    return postmortem


def _regime_split(returns: pd.Series) -> dict[str, dict[str, float]]:
    windows = {
        "2021 H2": ("2021-07-01", "2021-12-31"),
        "2022": ("2022-01-01", "2022-12-31"),
        "2023": ("2023-01-01", "2023-12-31"),
        "2024": ("2024-01-01", "2024-12-31"),
        "2025": ("2025-01-01", "2025-12-31"),
        "2026 YTD": ("2026-01-01", None),
    }
    result: dict[str, dict[str, float]] = {}
    for name, (start, end) in windows.items():
        sliced = returns[returns.index >= pd.Timestamp(start, tz="UTC")]
        if end is not None:
            sliced = sliced[sliced.index <= pd.Timestamp(end, tz="UTC")]
        result[name] = _daily_metrics(sliced, INITIAL_CAPITAL) if not sliced.empty else {}
    return result


def _rolling_stability(returns: pd.Series) -> dict[str, Any]:
    rolling = (returns.rolling(60).mean() / returns.rolling(60).std() * np.sqrt(252)).replace(
        [np.inf, -np.inf],
        np.nan,
    ).dropna()
    worst = rolling.sort_values().head(10)
    negative = rolling[rolling < 0.0]
    return {
        "window_days": 60,
        "min_sharpe": float(rolling.min()) if not rolling.empty else 0.0,
        "negative_fraction": float((rolling < 0.0).mean()) if not rolling.empty else 1.0,
        "worst_windows": {str(index): float(value) for index, value in worst.items()},
        "negative_windows_by_year": {str(year): int(count) for year, count in negative.groupby(negative.index.year).size().items()},
    }


def _drawdown_autopsy(returns: pd.Series) -> dict[str, Any]:
    equity = (1.0 + returns).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    trough = drawdown.idxmin()
    peak = equity.loc[:trough].idxmax()
    recovery = drawdown.loc[trough:][drawdown.loc[trough:] >= 0.0]
    return {
        "max_drawdown": float(drawdown.min()),
        "peak": str(peak),
        "trough": str(trough),
        "recovery": str(recovery.index[0]) if not recovery.empty else None,
        "drawdown_days": int((trough - peak).days),
    }


def _selection_autopsy(weights: pd.DataFrame, portfolio: pd.DataFrame) -> dict[str, Any]:
    selected = weights > 1e-12
    top_selection_counts = selected.sum().sort_values(ascending=False)
    shy_only = selected["SHY"] & (selected.sum(axis=1) == 1)
    return {
        "active_days": int((weights.abs().sum(axis=1) > 0.0).sum()),
        "zero_weight_days": int((weights.abs().sum(axis=1) == 0.0).sum()),
        "shy_only_days": int(shy_only.sum()) if "SHY" in selected else 0,
        "skipped_rebalances": int(portfolio["rebalance_skipped"].sum()),
        "selection_counts": _series_dict(top_selection_counts),
    }


def _vol_target_autopsy(weights: pd.DataFrame, returns: pd.Series) -> dict[str, float]:
    gross = weights.abs().sum(axis=1)
    realized_vol = returns.rolling(63).std() * np.sqrt(252)
    return {
        "average_gross": float(gross.mean()),
        "max_gross": float(gross.max()),
        "days_above_1x": float((gross > 1.0).sum()),
        "days_at_or_above_1_49x": float((gross >= 1.49).sum()),
        "realized_vol_mean": float(realized_vol.dropna().mean()),
        "realized_vol_max": float(realized_vol.dropna().max()),
    }


def _interpret(
    returns: pd.Series,
    weights: pd.DataFrame,
    symbol_contrib: pd.DataFrame,
    rolling: dict[str, Any],
) -> list[str]:
    notes: list[str] = []
    if rolling["negative_fraction"] >= 0.05:
        notes.append("stability failure is broad enough to block paper ops")
    if rolling["min_sharpe"] < -0.5:
        notes.append("worst 12-week window is far below the -0.5 stability floor")
    worst_year = returns.groupby(returns.index.year).sum().idxmin()
    notes.append(f"worst calendar-year return contribution is {worst_year}")
    worst_symbol = symbol_contrib.sum().idxmin()
    notes.append(f"largest negative symbol contribution is {worst_symbol}")
    if weights.abs().sum(axis=1).max() > 1.0:
        notes.append("vol target uses leverage above 1x; review whether leverage scalar worsens unstable windows")
    return notes


def _recommended_next_steps(rolling: dict[str, Any]) -> list[str]:
    return [
        "Do not paper trade Candidate 2 while stability gate is false.",
        "Inspect worst 12-week windows against selected assets and gross exposure.",
        "Design Candidate 3 only after deciding whether instability comes from vol-target leverage, asset universe, or absolute trend lag.",
        "Do not tune Candidate 2 parameters in-place; freeze any alternative as a new hypothesis.",
    ]


def _series_dict(series: pd.Series) -> dict[str, float]:
    return {str(index): float(value) for index, value in series.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Write Candidate 2 post-mortem artifact.")
    parser.add_argument("--output", default=str(POSTMORTEM_PATH))
    args = parser.parse_args()
    postmortem = write_postmortem(args.output)
    print(json.dumps({"artifact": args.output, "interpretation": postmortem["interpretation"]}, indent=2))


if __name__ == "__main__":
    main()
