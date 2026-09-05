"""Post-mortem diagnostics for VS-ICSM Candidate 1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.vs_icsm_data import load_universe_symbols, load_vs_icsm_mixed_panel
from research.vs_icsm_experiment import vs_icsm_cost_config
from research.vs_icsm_pipeline import (
    _apply_open_limit_execution,
    _compute_hourly_metrics,
    _trade_costs_exact,
    backtest_vs_icsm,
)
from strategies.vs_icsm.signal import default_params, generate_weight_signals

ARTIFACT_PATH = Path("research/artifacts/vs_icsm_candidate_1_postmortem.json")
INITIAL_CAPITAL = 10_000.0
ANN_FACTOR = 252 * 6.5


def build_postmortem(df: pd.DataFrame) -> dict[str, Any]:
    params = default_params()
    cost_config = vs_icsm_cost_config()
    full = backtest_vs_icsm(df, params, cost_config=cost_config, initial_capital=INITIAL_CAPITAL)

    desired, _, portfolio = generate_weight_signals(df, params)
    open_px = df.xs("open", axis=1, level=1).astype(float)
    high = df.xs("high", axis=1, level=1).astype(float)
    low = df.xs("low", axis=1, level=1).astype(float)
    volume = df.xs("volume", axis=1, level=1).astype(float)
    close = df.xs("close", axis=1, level=1).astype(float)
    actual, trades, fill_rates = _apply_open_limit_execution(desired, open_px, high, low)
    interval_returns = open_px.shift(-1).div(open_px).sub(1.0).fillna(0.0)
    gross_returns = (actual * interval_returns).sum(axis=1)
    costs = _cost_components(trades, open_px, volume, cost_config)

    gross_vs_net = {
        "no_fees_no_slippage": _metrics_for_returns(gross_returns),
        "fees_only": _metrics_for_returns(gross_returns - costs["fees"]),
        "slippage_only": _metrics_for_returns(gross_returns - costs["slippage"]),
        "full_costs": _metrics_for_returns(gross_returns - costs["total"]),
    }
    signal = _score(close, params.momentum_lookback_bars, params.volatility_lookback_bars)
    regimes = _regime_split(gross_returns - costs["total"])
    attribution = _long_short_attribution(actual, interval_returns, gross_returns, costs["total"])
    trade_autopsy = _trade_level_autopsy(actual, trades, interval_returns, open_px, costs["total"])
    ic = _ic_diagnostics(signal, interval_returns, periods=(1, 3, 6, 12, 24))
    eligibility = _eligibility_diagnostics(portfolio)

    return {
        "candidate": "VS-ICSM Candidate 1",
        "status": "validation_failed",
        "verdict": "reject_for_paper_ops",
        "reason": "negative Sharpe, catastrophic drawdown, large negative total return, high active trade count",
        "pipeline_status": "passed",
        "economic_status": "failed",
        "summary_metrics": {
            "sharpe": full.metrics["sharpe"],
            "max_drawdown": full.metrics["max_drawdown"],
            "total_return": full.metrics["total_return"],
            "final_equity": full.metrics["final_equity"],
            "trades": full.trade_count,
            "fill_rate": float(fill_rates.mean()),
        },
        "data": {
            "symbols": int(len(actual.columns)),
            "rows": int(len(df)),
            "start": str(df.index.min()),
            "end": str(df.index.max()),
            "sources": "Alpaca before 2021-07-01; Massive flatfiles from 2021-07-01 onward",
        },
        "gross_vs_net": gross_vs_net,
        "eligibility_diagnostics": eligibility,
        "long_short_attribution": attribution,
        "regime_split": regimes,
        "trade_level_autopsy": trade_autopsy,
        "signal_ic_analysis": ic,
        "interpretation": _interpret(gross_vs_net, attribution, ic, eligibility),
        "required_followup": [
            "gross_vs_net",
            "long_short_attribution",
            "regime_split",
            "trade_level_autopsy",
            "signal_ic_analysis",
        ],
    }


def write_postmortem(path: str | Path = ARTIFACT_PATH) -> dict[str, Any]:
    symbols = load_universe_symbols()
    df = load_vs_icsm_mixed_panel(symbols)
    postmortem = build_postmortem(df)
    artifact_path = Path(path)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(postmortem, indent=2, allow_nan=False))
    return postmortem


def _cost_components(trades: pd.DataFrame, open_px: pd.DataFrame, volume: pd.DataFrame, cost_config: Any) -> dict[str, pd.Series]:
    total = _trade_costs_exact(trades, open_px, volume, cost_config)
    sell_notional = -trades.clip(upper=0.0)
    fees = sell_notional.sum(axis=1) * cost_config.sec_fee_per_dollar_sold
    shares_sold = sell_notional.div(open_px.replace(0.0, np.nan)).fillna(0.0).sum(axis=1)
    fees = fees + shares_sold * cost_config.finra_taf_per_share_sold
    slippage = total - fees
    return {"fees": fees, "slippage": slippage, "total": total}


def _metrics_for_returns(returns: pd.Series) -> dict[str, float]:
    equity = (1.0 + returns).cumprod() * INITIAL_CAPITAL
    return _compute_hourly_metrics(returns, equity, INITIAL_CAPITAL)


def _score(close: pd.DataFrame, momentum_lookback: int, volatility_lookback: int) -> pd.DataFrame:
    returns = close.pct_change(fill_method=None)
    return returns.rolling(momentum_lookback).sum() / returns.rolling(volatility_lookback).std()


def _long_short_attribution(
    actual: pd.DataFrame,
    interval_returns: pd.DataFrame,
    gross_returns: pd.Series,
    costs: pd.Series,
) -> dict[str, Any]:
    long_book = (actual.clip(lower=0.0) * interval_returns).sum(axis=1)
    short_book = (actual.clip(upper=0.0) * interval_returns).sum(axis=1)
    cash = 1.0 - actual.abs().sum(axis=1)
    return {
        "note": "VS-ICSM Candidate 1 is long-only; short_book is structurally zero. long_short_spread is reported for schema compatibility.",
        "long_book_return": float(long_book.sum()),
        "short_book_return": float(short_book.sum()),
        "long_short_spread_return": float((long_book - short_book).sum()),
        "cash_idle_average_weight": float(cash.mean()),
        "cash_idle_min_weight": float(cash.min()),
        "rebalance_cost_drag": float(costs.sum()),
        "net_return_sum": float((gross_returns - costs).sum()),
    }


def _regime_split(returns: pd.Series) -> dict[str, dict[str, float]]:
    windows = {
        "Alpaca pre-2021-07-01": (None, "2021-06-30 23:59:59+00:00"),
        "Massive 2021-07-01 onward": ("2021-07-01 00:00:00+00:00", None),
        "2021-07 to 2021-12": ("2021-07-01 00:00:00+00:00", "2021-12-31 23:59:59+00:00"),
        "2022": ("2022-01-01 00:00:00+00:00", "2022-12-31 23:59:59+00:00"),
        "2023": ("2023-01-01 00:00:00+00:00", "2023-12-31 23:59:59+00:00"),
        "2024": ("2024-01-01 00:00:00+00:00", "2024-12-31 23:59:59+00:00"),
        "2025": ("2025-01-01 00:00:00+00:00", "2025-12-31 23:59:59+00:00"),
        "2026 YTD": ("2026-01-01 00:00:00+00:00", None),
    }
    result: dict[str, dict[str, float]] = {}
    for name, (start, end) in windows.items():
        sliced = returns
        if start is not None:
            sliced = sliced[sliced.index >= pd.Timestamp(start)]
        if end is not None:
            sliced = sliced[sliced.index <= pd.Timestamp(end)]
        result[name] = _metrics_for_returns(sliced) if not sliced.empty else {}
    return result


def _trade_level_autopsy(
    actual: pd.DataFrame,
    trades: pd.DataFrame,
    interval_returns: pd.DataFrame,
    open_px: pd.DataFrame,
    costs: pd.Series,
) -> dict[str, Any]:
    trade_mask = trades.abs() > 1e-12
    signed_trade_pnl = (trades * interval_returns).where(trade_mask).stack()
    symbol_contrib = (actual * interval_returns).sub(_allocated_costs(costs, actual), axis=0)
    per_symbol = symbol_contrib.sum().sort_values()
    hold_lengths = _hold_lengths(actual)
    trades_per_symbol = trade_mask.sum().sort_values(ascending=False)
    wins = signed_trade_pnl[signed_trade_pnl > 0].sum()
    losses = -signed_trade_pnl[signed_trade_pnl < 0].sum()
    return {
        "method": "Trade PnL is signed next-bar return contribution on executed weight deltas; per-symbol PnL is held-weight bar contribution after proportional cost allocation.",
        "average_trade_pnl": float(signed_trade_pnl.mean()) if len(signed_trade_pnl) else 0.0,
        "median_trade_pnl": float(signed_trade_pnl.median()) if len(signed_trade_pnl) else 0.0,
        "win_rate": float((signed_trade_pnl > 0).mean()) if len(signed_trade_pnl) else 0.0,
        "profit_factor": float(wins / losses) if losses > 0 else float("inf"),
        "average_hold_time_bars": float(np.mean(hold_lengths)) if hold_lengths else 0.0,
        "turnover_per_day": float(trades.abs().sum(axis=1).resample("1D").sum().mean()),
        "trade_count": int(trade_mask.sum().sum()),
        "trades_per_symbol_top20": _series_to_float_dict(trades_per_symbol.head(20)),
        "pnl_by_symbol": _series_to_float_dict(per_symbol),
        "worst_20_symbols": _series_to_float_dict(per_symbol.head(20)),
        "best_20_symbols": _series_to_float_dict(per_symbol.tail(20).sort_values(ascending=False)),
        "average_reference_open": float(open_px.where(trade_mask).stack().mean()),
    }


def _allocated_costs(costs: pd.Series, actual: pd.DataFrame) -> pd.DataFrame:
    gross = actual.abs().sum(axis=1).replace(0.0, np.nan)
    weights = actual.abs().div(gross, axis=0).fillna(0.0)
    return weights.mul(costs, axis=0)


def _hold_lengths(actual: pd.DataFrame) -> list[int]:
    lengths: list[int] = []
    held = actual.abs() > 1e-12
    for symbol in held.columns:
        run = 0
        for is_held in held[symbol].to_numpy(dtype=bool):
            if is_held:
                run += 1
            elif run:
                lengths.append(run)
                run = 0
        if run:
            lengths.append(run)
    return lengths


def _ic_diagnostics(signal: pd.DataFrame, interval_returns: pd.DataFrame, periods: tuple[int, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for period in periods:
        forward = interval_returns.shift(-1).rolling(period).sum().shift(-(period - 1))
        pearson = signal.corrwith(forward, axis=1, method="pearson").replace([np.inf, -np.inf], np.nan).dropna()
        spearman = signal.corrwith(forward, axis=1, method="spearman").replace([np.inf, -np.inf], np.nan).dropna()
        result[f"{period}h"] = {
            "pearson": _ic_summary(pearson),
            "spearman": _ic_summary(spearman),
            "by_year_spearman": {
                str(year): _ic_summary(group)
                for year, group in spearman.groupby(spearman.index.year)
            },
            "by_sector": "not_available",
        }
    return result


def _ic_summary(values: pd.Series) -> dict[str, float]:
    if values.empty:
        return {"mean": 0.0, "std": 0.0, "t_stat": 0.0, "hit_rate": 0.0, "observations": 0.0}
    std = float(values.std())
    mean = float(values.mean())
    return {
        "mean": mean,
        "std": std,
        "t_stat": float(mean / (std / np.sqrt(len(values)))) if std > 0 else 0.0,
        "hit_rate": float((values > 0.0).mean()),
        "observations": float(len(values)),
    }


def _eligibility_diagnostics(portfolio: pd.DataFrame) -> dict[str, Any]:
    active = ~portfolio["rebalance_skipped"].astype(bool)
    first_active = portfolio.index[active.argmax()] if bool(active.any()) else None
    by_year = portfolio.groupby(portfolio.index.year)["eligible_count"].agg(["min", "max", "mean"])
    active_by_year = active.groupby(portfolio.index.year).sum()
    return {
        "first_non_skipped_rebalance": str(first_active) if first_active is not None else None,
        "active_rebalances": int(active.sum()),
        "skipped_rebalances": int((~active).sum()),
        "eligible_count_by_year": {
            str(year): {column: float(value) for column, value in row.items()}
            for year, row in by_year.iterrows()
        },
        "active_rebalances_by_year": {
            str(year): int(value) for year, value in active_by_year.items()
        },
    }


def _interpret(
    gross_vs_net: dict[str, dict[str, float]],
    attribution: dict[str, Any],
    ic: dict[str, Any],
    eligibility: dict[str, Any],
) -> list[str]:
    notes: list[str] = []
    gross = gross_vs_net["no_fees_no_slippage"]
    full = gross_vs_net["full_costs"]
    if gross.get("sharpe", 0.0) < 0.0:
        notes.append("gross negative: signal/portfolio loses before fees and slippage")
    if gross.get("sharpe", 0.0) > 0.0 and full.get("sharpe", 0.0) < 0.0:
        notes.append("gross positive but net negative: turnover/cost problem")
    if full.get("max_drawdown", 0.0) < -0.15:
        notes.append("drawdown violates strict 15% limit")
    if attribution["short_book_return"] == 0.0:
        notes.append("short attribution not applicable: candidate is long-only")
    first_active = eligibility.get("first_non_skipped_rebalance")
    if first_active:
        notes.append(f"strategy did not place active weights until {first_active}; early regimes are mostly warm-up/universe-ineligible")
    one_hour_ic = ic.get("1h", {}).get("spearman", {}).get("mean", 0.0)
    if one_hour_ic < 0.0:
        notes.append("1h Spearman IC is negative; rank direction may be wrong at the execution horizon")
    elif abs(one_hour_ic) < 0.01:
        notes.append("1h Spearman IC is near zero; signal family likely weak at the execution horizon")
    return notes


def _series_to_float_dict(series: pd.Series) -> dict[str, float]:
    return {str(index): float(value) for index, value in series.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Write VS-ICSM Candidate 1 post-mortem artifact.")
    parser.add_argument("--output", default=str(ARTIFACT_PATH))
    args = parser.parse_args()
    postmortem = write_postmortem(args.output)
    print(json.dumps(postmortem["summary_metrics"], indent=2))
    print(args.output)


if __name__ == "__main__":
    main()
