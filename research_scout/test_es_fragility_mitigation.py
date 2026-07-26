import json
import math
import sys

sys.path.insert(0, ".vendor")
sys.path.insert(0, ".")

import numpy as np
import pandas as pd

from research_scout import test_es_opening_dual_engine_robustness as dual_test
from research_scout import test_es_three_engine_stress as triple_test


EXTRA_COSTS = [0.0, 1.25, 2.5]


def profit_factor(values):
    gains = float(values[values > 0].sum())
    losses = float(-values[values < 0].sum())
    return gains / losses if losses else math.inf


def select_first_signal_daily(trades):
    selected = []
    for _, group in trades.groupby("date", sort=True):
        first_idx = int(group.entry_idx.min())
        same_minute = group[group.entry_idx == first_idx].copy()
        same_minute = same_minute.sort_values(
            ["risk_usd", "engine"], ascending=[True, True]
        )
        selected.append(same_minute.iloc[0])
    return pd.DataFrame(selected).reset_index(drop=True)


def sample(trades, lo, hi, extra_cost=0.0):
    work = trades[trades.date.dt.year.between(lo, hi)].copy()
    work["adjusted_pnl"] = work.pnl - extra_cost
    return work


def statistics(trades, session_dates, lo, hi, extra_cost=0.0):
    work = sample(trades, lo, hi, extra_cost)
    dates = session_dates[session_dates.dt.year.between(lo, hi)]
    daily = (
        work.groupby("date").adjusted_pnl.sum().reindex(dates, fill_value=0.0)
    )
    equity = daily.cumsum()
    drawdown = equity - equity.cummax()
    values = work.adjusted_pnl
    return {
        "trades": int(len(work)),
        "trades_per_week": round(len(work) / ((hi - lo + 1) * 52), 3),
        "active_days_per_week": round(
            work.date.nunique() / ((hi - lo + 1) * 52), 3
        ),
        "net_pnl": round(float(values.sum()), 2),
        "mean_trade": round(float(values.mean()), 3),
        "profit_factor": round(profit_factor(values), 3),
        "win_rate": round(float((values > 0).mean()), 3),
        "max_drawdown": round(float(drawdown.min()), 2),
    }


def yearly(trades, extra_cost=0.0):
    work = trades.copy()
    work["adjusted_pnl"] = work.pnl - extra_cost
    return {
        str(int(year)): round(float(group.adjusted_pnl.sum()), 2)
        for year, group in work.groupby(work.date.dt.year)
    }


def tail_diagnostics(trades, lo, hi, extra_cost=0.0):
    work = sample(trades, lo, hi, extra_cost).sort_values(
        ["date", "entry_idx"]
    )
    ordered = work.sort_values("adjusted_pnl", ascending=False)
    weekly = work.groupby(work.date.dt.to_period("W")).adjusted_pnl.sum()
    monthly = work.groupby(work.date.dt.to_period("M")).adjusted_pnl.sum()
    best_month = float(monthly.max())
    total = float(work.adjusted_pnl.sum())
    return {
        "median_trade": round(float(work.adjusted_pnl.median()), 2),
        "largest_winner": round(float(ordered.adjusted_pnl.iloc[0]), 2),
        "largest_loser": round(float(ordered.adjusted_pnl.iloc[-1]), 2),
        "net_without_top_5": round(
            float(ordered.iloc[5:].adjusted_pnl.sum()), 2
        ),
        "net_without_top_1pct": round(
            float(
                ordered.iloc[
                    max(1, math.ceil(len(ordered) * 0.01)) :
                ].adjusted_pnl.sum()
            ),
            2,
        ),
        "positive_week_fraction": round(float((weekly > 0).mean()), 3),
        "best_month": str(monthly.idxmax()),
        "best_month_pnl": round(best_month, 2),
        "best_month_fraction_of_total": (
            round(best_month / total, 3) if total > 0 else None
        ),
    }


def remove_best_month_each_year(trades, lo, hi, extra_cost=0.0):
    work = sample(trades, lo, hi, extra_cost)
    work["month"] = work.date.dt.to_period("M")
    monthly = work.groupby("month").adjusted_pnl.sum()
    removed = []
    for year in range(lo, hi + 1):
        year_months = monthly[monthly.index.year == year]
        if len(year_months):
            removed.append(str(year_months.idxmax()))
    retained = work[~work.month.astype(str).isin(removed)]
    return {
        "removed_months": removed,
        "retained_net_pnl": round(float(retained.adjusted_pnl.sum()), 2),
        "retained_profit_factor": round(
            profit_factor(retained.adjusted_pnl), 3
        ),
    }


def rolling(trades, session_dates, lo, hi, extra_cost=0.0):
    work = sample(trades, lo, hi, extra_cost)
    dates = session_dates[session_dates.dt.year.between(lo, hi)]
    daily = (
        work.groupby("date").adjusted_pnl.sum().reindex(dates, fill_value=0.0)
    )
    output = {}
    for window, label in [(63, "3m"), (126, "6m"), (252, "12m")]:
        values = daily.rolling(window).sum().dropna()
        if len(values):
            output[label] = {
                "minimum": round(float(values.min()), 2),
                "median": round(float(values.median()), 2),
                "fraction_positive": round(float((values > 0).mean()), 3),
            }
    return output


def bootstrap(trades, session_dates, lo, hi, extra_cost, seed):
    work = sample(trades, lo, hi, extra_cost)
    dates = session_dates[session_dates.dt.year.between(lo, hi)]
    daily = (
        work.groupby("date").adjusted_pnl.sum().reindex(dates, fill_value=0.0)
    )
    return dual_test.moving_block_bootstrap(daily.values, seed)


def risk_summary(trades, lo, hi):
    work = trades[trades.date.dt.year.between(lo, hi)]
    daily_risk = work.groupby("date").risk_usd.sum()
    return {
        "median_active_day": round(float(daily_risk.median()), 2),
        "95pct_active_day": round(float(daily_risk.quantile(0.95)), 2),
        "maximum_active_day": round(float(daily_risk.max()), 2),
    }


def skipped_summary(baseline, challenger):
    work = baseline.copy()
    work["selection_key"] = list(
        zip(work.date.astype(str), work.engine, work.entry_idx)
    )
    chosen_keys = set(
        zip(
            challenger.date.astype(str),
            challenger.engine,
            challenger.entry_idx,
        )
    )
    skipped = work[~work.selection_key.isin(chosen_keys)]
    return {
        "trades_removed": int(len(skipped)),
        "removed_by_engine": {
            str(engine): int(count)
            for engine, count in skipped.engine.value_counts().items()
        },
    }


def evaluate(name, trades, session_dates, seed_offset):
    output = {
        "name": name,
        "baseline_cost": {
            "development": statistics(trades, session_dates, 2021, 2023),
            "holdout": statistics(trades, session_dates, 2024, 2025),
            "full": statistics(trades, session_dates, 2021, 2025),
            "year_pnl": yearly(trades),
        },
        "cost_reserves": {},
        "holdout_tail": tail_diagnostics(trades, 2024, 2025),
        "holdout_remove_best_month_each_year": remove_best_month_each_year(
            trades, 2024, 2025
        ),
        "holdout_rolling": rolling(trades, session_dates, 2024, 2025),
        "holdout_bootstrap": bootstrap(
            trades, session_dates, 2024, 2025, 0.0, 20260810 + seed_offset
        ),
        "holdout_initial_signal_risk": risk_summary(trades, 2024, 2025),
    }
    for cost in EXTRA_COSTS:
        output["cost_reserves"][f"{cost:.2f}"] = {
            "development": statistics(
                trades, session_dates, 2021, 2023, cost
            ),
            "holdout": statistics(
                trades, session_dates, 2024, 2025, cost
            ),
        }
    return output


def main():
    sessions = dual_test.load_sessions()
    session_map = {day: bars for day, bars in sessions}
    session_dates = pd.Series([day for day, _ in sessions])
    signals = triple_test.build_three_engine_signals(sessions)
    baseline, skipped_geometry = triple_test.simulate(signals, session_map)
    challenger = select_first_signal_daily(baseline)
    if not challenger.date.is_unique:
        raise AssertionError("challenger must contain at most one trade per date")
    if len(challenger) != baseline.date.nunique():
        raise AssertionError("challenger must select one trade on every active date")
    reproduced_holdout = statistics(
        baseline, session_dates, 2024, 2025
    )["net_pnl"]
    if reproduced_holdout != 1605.49:
        raise AssertionError(
            f"baseline audit mismatch: expected 1605.49, got {reproduced_holdout}"
        )

    result = {
        "research_status": (
            "historical diagnostic only; challenger was created after "
            "2024-2025 had already informed the research program"
        ),
        "baseline_skipped_bad_geometry": int(skipped_geometry),
        "benchmark": evaluate(
            "unchanged_three_engine_portfolio", baseline, session_dates, 0
        ),
        "challenger": evaluate(
            "one_position_first_signal_minimum_risk_tie_breaker",
            challenger,
            session_dates,
            1,
        ),
        "selection_effect": skipped_summary(baseline, challenger),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
