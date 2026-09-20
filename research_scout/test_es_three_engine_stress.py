import json
import math
import sys

sys.path.insert(0, ".vendor")
sys.path.insert(0, ".")

import numpy as np
import pandas as pd

from research_scout import test_es_opening_dual_engine_robustness as dual_test

TICK_SIZE = 0.25
POINT_VALUE = 5.0
COMMISSION = 1.24


def build_three_engine_signals(sessions):
    opening_signals, _ = dual_test.build_signals(sessions)
    opening_signals = opening_signals.copy()
    opening_signals["time_exit_idx"] = 360

    reload_signals = []
    for day, bars in sessions:
        cash_open = float(bars.iloc[0].open)
        morning_close = float(bars.iloc[119].close)
        lunch_close = float(bars.iloc[239].close)
        morning_move = morning_close - cash_open
        lunch_move = lunch_close - morning_close
        if (
            morning_move == 0
            or lunch_move * morning_move >= 0
            or (lunch_close - cash_open) * morning_move <= 0
        ):
            continue
        side = 1 if morning_move > 0 else -1
        reload_signals.append(
            {
                "date": day,
                "engine": "reload",
                "side": side,
                "base_entry_idx": 240,
                "stop_reference": cash_open,
                "time_exit_idx": 385,
            }
        )

    return pd.concat(
        [opening_signals, pd.DataFrame(reload_signals)], ignore_index=True
    )


def simulate(
    signals,
    session_map,
    all_engines_gap_through=False,
    extra_stop_fill_ticks=0.0,
    extra_entry_and_exit_ticks=0.0,
    flip_direction=False,
):
    records = []
    skipped_geometry = 0

    for signal in signals.itertuples(index=False):
        bars = session_map[signal.date]
        original_side = int(signal.side)
        entry_idx = int(signal.base_entry_idx)
        time_exit_idx = int(signal.time_exit_idx)
        rule_entry = float(bars.iloc[entry_idx].open) + original_side * TICK_SIZE
        stop_trigger = (
            float(signal.stop_reference)
            if signal.engine == "convexity"
            else float(signal.stop_reference - original_side * TICK_SIZE)
        )
        frozen_stop_fill = float(
            signal.stop_reference - original_side * TICK_SIZE
        )

        if (original_side == 1 and frozen_stop_fill >= rule_entry) or (
            original_side == -1 and frozen_stop_fill <= rule_entry
        ):
            skipped_geometry += 1
            continue

        original_risk_points = abs(rule_entry - frozen_stop_fill)
        side = -original_side if flip_direction else original_side
        entry = (
            float(bars.iloc[entry_idx].open)
            + side * TICK_SIZE
            + side * extra_entry_and_exit_ticks * TICK_SIZE
        )
        stop_fill = (
            entry - side * original_risk_points
            if flip_direction
            else frozen_stop_fill
        )
        active_trigger = stop_fill if flip_direction else stop_trigger

        lows = bars.low.to_numpy(dtype=float)
        highs = bars.high.to_numpy(dtype=float)
        stop_hits = (
            np.flatnonzero(lows[entry_idx:time_exit_idx] <= active_trigger)
            if side == 1
            else np.flatnonzero(highs[entry_idx:time_exit_idx] >= active_trigger)
        )

        if len(stop_hits):
            exit_idx = entry_idx + int(stop_hits[0])
            exit_price = stop_fill
            use_gap_rule = signal.engine == "convexity" or all_engines_gap_through
            if use_gap_rule:
                bar_open = float(bars.iloc[exit_idx].open)
                opened_beyond = (
                    bar_open < active_trigger
                    if side == 1
                    else bar_open > active_trigger
                )
                if opened_beyond:
                    exit_price = bar_open - side * TICK_SIZE
            exit_price -= side * extra_stop_fill_ticks * TICK_SIZE
            reason = "stop"
        else:
            exit_idx = time_exit_idx
            exit_price = (
                float(bars.iloc[time_exit_idx].open)
                - side * TICK_SIZE
                - side * extra_entry_and_exit_ticks * TICK_SIZE
            )
            reason = "time"

        pnl = side * (exit_price - entry) * POINT_VALUE - COMMISSION
        records.append(
            {
                "date": signal.date,
                "engine": signal.engine,
                "side": side,
                "entry_idx": entry_idx,
                "exit_idx": exit_idx,
                "reason": reason,
                "entry": entry,
                "stop": stop_fill,
                "risk_usd": original_risk_points * POINT_VALUE + COMMISSION,
                "pnl": pnl,
                "r_multiple": pnl
                / (original_risk_points * POINT_VALUE + COMMISSION),
            }
        )

    return pd.DataFrame(records), skipped_geometry


def profit_factor(values):
    gains = values[values > 0].sum()
    losses = -values[values < 0].sum()
    return float(gains / losses) if losses else math.inf


def stats(trades, session_dates, lo, hi):
    sample = trades[trades.date.dt.year.between(lo, hi)]
    dates = session_dates[session_dates.dt.year.between(lo, hi)]
    daily = sample.groupby("date").pnl.sum().reindex(dates, fill_value=0.0)
    equity = daily.cumsum()
    drawdown = equity - equity.cummax()
    return {
        "trades": int(len(sample)),
        "trades_per_week": round(len(sample) / ((hi - lo + 1) * 52), 3),
        "active_days_per_week": round(
            sample.date.nunique() / ((hi - lo + 1) * 52), 3
        ),
        "net_pnl": round(float(sample.pnl.sum()), 2),
        "mean_trade": round(float(sample.pnl.mean()), 3),
        "profit_factor": round(profit_factor(sample.pnl), 3),
        "max_drawdown": round(float(drawdown.min()), 2),
    }


def component_stats(trades, lo, hi):
    sample = trades[trades.date.dt.year.between(lo, hi)]
    table = sample.groupby("engine").agg(
        trades=("pnl", "size"),
        mean_pnl=("pnl", "mean"),
        net_pnl=("pnl", "sum"),
        mean_r=("r_multiple", "mean"),
        median_r=("r_multiple", "median"),
    )
    return {
        engine: {
            key: round(float(value), 3)
            for key, value in row.items()
        }
        for engine, row in table.iterrows()
    }


def daily_tail(trades, session_dates, lo, hi):
    sample = trades[trades.date.dt.year.between(lo, hi)]
    dates = session_dates[session_dates.dt.year.between(lo, hi)]
    daily = sample.groupby("date").pnl.sum().reindex(dates, fill_value=0.0)
    losing_run = 0
    longest_losing_run = 0
    for value in daily:
        losing_run = losing_run + 1 if value < 0 else 0
        longest_losing_run = max(longest_losing_run, losing_run)
    negative_tail = daily[daily <= daily.quantile(0.05)]
    return {
        "worst_day": round(float(daily.min()), 2),
        "one_percentile": round(float(daily.quantile(0.01)), 2),
        "five_percentile": round(float(daily.quantile(0.05)), 2),
        "five_percent_expected_shortfall": round(float(negative_tail.mean()), 2),
        "longest_losing_day_streak": int(longest_losing_run),
        "positive_day_fraction": round(float((daily > 0).mean()), 3),
    }


def concurrency(trades, lo, hi):
    sample = trades[trades.date.dt.year.between(lo, hi)]
    daily_max = {}
    daily_gross_minutes = {}
    daily_signal_risk = sample.groupby("date").risk_usd.sum()

    for day, group in sample.groupby("date"):
        counts = np.zeros(390, dtype=int)
        for trade in group.itertuples(index=False):
            end = max(int(trade.entry_idx) + 1, int(trade.exit_idx) + 1)
            counts[int(trade.entry_idx) : min(end, 390)] += 1
        daily_max[day] = int(counts.max())
        daily_gross_minutes[day] = int(counts.sum())

    max_series = pd.Series(daily_max, dtype=int)
    gross_series = pd.Series(daily_gross_minutes, dtype=float)
    return {
        "days_by_max_concurrent_positions": {
            str(level): int((max_series == level).sum())
            for level in sorted(max_series.unique())
        },
        "fraction_active_days_with_two_or_more_concurrent": round(
            float((max_series >= 2).mean()), 3
        ),
        "fraction_active_days_with_three_concurrent": round(
            float((max_series >= 3).mean()), 3
        ),
        "median_gross_position_minutes_per_active_day": round(
            float(gross_series.median()), 1
        ),
        "initial_signal_risk_usd": {
            "median_active_day": round(float(daily_signal_risk.median()), 2),
            "95pct_active_day": round(float(daily_signal_risk.quantile(0.95)), 2),
            "maximum_active_day": round(float(daily_signal_risk.max()), 2),
        },
    }


def leave_one_engine_out(trades, session_dates):
    result = {}
    for engine in sorted(trades.engine.unique()):
        reduced = trades[trades.engine != engine]
        result[f"without_{engine}"] = {
            "development": stats(reduced, session_dates, 2021, 2023),
            "holdout": stats(reduced, session_dates, 2024, 2025),
        }
    return result


def remove_best_month_each_year(trades, lo, hi):
    sample = trades[trades.date.dt.year.between(lo, hi)].copy()
    sample["month"] = sample.date.dt.to_period("M")
    monthly = sample.groupby("month").pnl.sum()
    removed = []
    for year in range(lo, hi + 1):
        year_months = monthly[monthly.index.year == year]
        if len(year_months):
            removed.append(str(year_months.idxmax()))
    retained = sample[~sample.month.astype(str).isin(removed)]
    return {
        "removed_months": removed,
        "retained_net_pnl": round(float(retained.pnl.sum()), 2),
        "retained_profit_factor": round(profit_factor(retained.pnl), 3),
    }


def clustered_execution_stress(trades, session_dates, lo, hi):
    sample = trades[trades.date.dt.year.between(lo, hi)].copy()
    daily_count = sample.groupby("date").size()
    stacked_days = daily_count[daily_count >= 2].index
    stressed = sample.pnl.copy()
    stressed.loc[sample.date.isin(stacked_days)] -= 2.50
    stressed_sample = sample.copy()
    stressed_sample["pnl"] = stressed
    return {
        "stacked_days": int(len(stacked_days)),
        "stressed_net_pnl": round(float(stressed.sum()), 2),
        "stressed_profit_factor": round(profit_factor(stressed), 3),
        "stressed_stats": stats(stressed_sample, session_dates, lo, hi),
    }


def main():
    sessions = dual_test.load_sessions()
    session_map = dict(sessions)
    session_dates = pd.Series([day for day, _ in sessions])
    signals = build_three_engine_signals(sessions)

    baseline, skipped = simulate(signals, session_map)
    gap_fill, _ = simulate(
        signals, session_map, all_engines_gap_through=True
    )
    gap_plus_tick, _ = simulate(
        signals,
        session_map,
        all_engines_gap_through=True,
        extra_stop_fill_ticks=1,
    )
    flipped, _ = simulate(signals, session_map, flip_direction=True)

    output = {
        "baseline": {
            "skipped_bad_geometry": skipped,
            "development": stats(baseline, session_dates, 2021, 2023),
            "holdout": stats(baseline, session_dates, 2024, 2025),
            "full": stats(baseline, session_dates, 2021, 2025),
        },
        "component_risk_normalized": {
            "development": component_stats(baseline, 2021, 2023),
            "holdout": component_stats(baseline, 2024, 2025),
        },
        "daily_tail": {
            "development": daily_tail(baseline, session_dates, 2021, 2023),
            "holdout": daily_tail(baseline, session_dates, 2024, 2025),
        },
        "concurrency": {
            "development": concurrency(baseline, 2021, 2023),
            "holdout": concurrency(baseline, 2024, 2025),
        },
        "stop_fill_stress": {
            "gap_through_bar_open": {
                "development": stats(gap_fill, session_dates, 2021, 2023),
                "holdout": stats(gap_fill, session_dates, 2024, 2025),
            },
            "gap_through_plus_one_tick": {
                "development": stats(
                    gap_plus_tick, session_dates, 2021, 2023
                ),
                "holdout": stats(gap_plus_tick, session_dates, 2024, 2025),
            },
        },
        "paired_direction_placebo": {
            "actual": {
                "development": stats(baseline, session_dates, 2021, 2023),
                "holdout": stats(baseline, session_dates, 2024, 2025),
            },
            "flipped_same_time_same_initial_risk": {
                "development": stats(flipped, session_dates, 2021, 2023),
                "holdout": stats(flipped, session_dates, 2024, 2025),
            },
            "flipped_components_development": component_stats(
                flipped, 2021, 2023
            ),
            "flipped_components_holdout": component_stats(flipped, 2024, 2025),
        },
        "leave_one_engine_out": leave_one_engine_out(
            baseline, session_dates
        ),
        "remove_best_month_each_year": {
            "development": remove_best_month_each_year(
                baseline, 2021, 2023
            ),
            "holdout": remove_best_month_each_year(baseline, 2024, 2025),
        },
        "clustered_execution_stress": {
            "development": clustered_execution_stress(
                baseline, session_dates, 2021, 2023
            ),
            "holdout": clustered_execution_stress(
                baseline, session_dates, 2024, 2025
            ),
        },
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
