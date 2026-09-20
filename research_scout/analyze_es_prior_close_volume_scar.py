import json
import math
import sys
from pathlib import Path

sys.path.insert(0, ".vendor")
sys.path.insert(0, ".")

import databento as db
import numpy as np
import pandas as pd

from research_scout import test_es_opening_dual_engine_robustness as dual_test
from research_scout import test_es_three_engine_stress as three_test

ROOT = Path("external_artifacts/databento_es_close/GLBX.MDP3")
SESSION_ROOT = ROOT / "sessions"
TICK_SIZE = 0.25
POINT_VALUE = 5.0
COMMISSION = 1.24


def profit_factor(values):
    gains = float(values[values > 0].sum())
    losses = float(-values[values < 0].sum())
    return gains / losses if losses else math.inf


def center(bars):
    typical = (bars.high + bars.low + bars.close) / 3.0
    return float((typical * bars.volume).sum() / bars.volume.sum())


def load_anchor(day):
    path = (
        SESSION_ROOT
        / str(day.year)
        / day.strftime("%Y-%m-%d")
        / "es_trades.dbn.zst"
    )
    if not path.exists():
        return None
    trades = db.DBNStore.from_file(path).to_df()
    if trades.empty or trades.instrument_id.nunique() != 1:
        return None
    trades = trades.sort_values(["ts_event", "sequence"], kind="stable")
    by_price = trades.groupby("price", sort=True)["size"].sum()
    maximum = by_price.max()
    candidates = by_price[by_price == maximum].index.to_numpy(dtype=float)
    vwap = float(np.average(trades.price, weights=trades["size"]))
    distances = np.abs(candidates - vwap)
    scar = float(candidates[distances == distances.min()].min())
    return {
        "scar": scar,
        "vwap": vwap,
        "terminal": float(trades.iloc[-1].price),
        "instrument_id": int(trades.instrument_id.iloc[0]),
    }


def outward_tick_stop(raw_stop, side):
    scaled = raw_stop / TICK_SIZE
    ticks = math.floor(scaled) if side == 1 else math.ceil(scaled)
    return ticks * TICK_SIZE


def simulate(
    sessions,
    anchors,
    anchor_name="scar",
    anchor_lag=1,
    tick_grid_stop=False,
    entry_delay=0,
    exit_idx=360,
    flip_direction=False,
):
    records = []
    exclusions = {
        "missing_anchor": 0,
        "roll_mismatch": 0,
        "no_signal": 0,
        "pre_entry_invalidation": 0,
        "bad_geometry": 0,
    }
    for index in range(anchor_lag, len(sessions)):
        day, bars = sessions[index]
        anchor_day = sessions[index - anchor_lag][0]
        anchor = anchors.get(anchor_day)
        if anchor is None:
            exclusions["missing_anchor"] += 1
            continue
        current_ids = pd.unique(bars.iloc[:30].instrument_id)
        if (
            len(current_ids) != 1
            or int(current_ids[0]) != anchor["instrument_id"]
        ):
            exclusions["roll_mismatch"] += 1
            continue
        opening = bars.iloc[:30]
        opening_center = center(opening)
        opening_close = float(opening.iloc[-1].close)
        anchor_value = float(anchor[anchor_name])
        if opening_center > anchor_value and opening_close > anchor_value:
            original_side = 1
        elif opening_center < anchor_value and opening_close < anchor_value:
            original_side = -1
        else:
            exclusions["no_signal"] += 1
            continue

        base_entry_idx = 30
        active_entry_idx = base_entry_idx + entry_delay
        raw_stop = opening_center - original_side * TICK_SIZE
        original_stop = (
            outward_tick_stop(raw_stop, original_side)
            if tick_grid_stop
            else raw_stop
        )
        original_entry = (
            float(bars.iloc[active_entry_idx].open)
            + original_side * TICK_SIZE
        )
        if entry_delay:
            prior = bars.iloc[base_entry_idx:active_entry_idx]
            invalidated = (
                bool((prior.low <= original_stop).any())
                if original_side == 1
                else bool((prior.high >= original_stop).any())
            )
            if invalidated:
                exclusions["pre_entry_invalidation"] += 1
                continue
        if (
            original_side == 1
            and original_stop >= original_entry
            or original_side == -1
            and original_stop <= original_entry
        ):
            exclusions["bad_geometry"] += 1
            continue

        original_risk_points = abs(original_entry - original_stop)
        side = -original_side if flip_direction else original_side
        entry = float(bars.iloc[active_entry_idx].open) + side * TICK_SIZE
        stop = (
            entry - side * original_risk_points
            if flip_direction
            else original_stop
        )
        lows = bars.low.to_numpy(dtype=float)
        highs = bars.high.to_numpy(dtype=float)
        stop_hits = (
            np.flatnonzero(lows[active_entry_idx:exit_idx] <= stop)
            if side == 1
            else np.flatnonzero(highs[active_entry_idx:exit_idx] >= stop)
        )
        if len(stop_hits):
            actual_exit_idx = active_entry_idx + int(stop_hits[0])
            bar_open = float(bars.iloc[actual_exit_idx].open)
            opened_beyond = bar_open < stop if side == 1 else bar_open > stop
            exit_price = (
                bar_open - side * TICK_SIZE if opened_beyond else stop
            )
            reason = "stop"
        else:
            actual_exit_idx = exit_idx
            exit_price = float(bars.iloc[exit_idx].open) - side * TICK_SIZE
            reason = f"time_{exit_idx}"

        path = bars.iloc[active_entry_idx : actual_exit_idx + 1]
        mfe_points = (
            float(path.high.max()) - entry
            if side == 1
            else entry - float(path.low.min())
        )
        mae_points = (
            entry - float(path.low.min())
            if side == 1
            else float(path.high.max()) - entry
        )
        pnl = side * (exit_price - entry) * POINT_VALUE - COMMISSION
        risk_usd = original_risk_points * POINT_VALUE + COMMISSION
        records.append(
            {
                "date": day,
                "anchor_day": anchor_day,
                "side": side,
                "original_side": original_side,
                "entry_idx": active_entry_idx,
                "exit_idx": actual_exit_idx,
                "reason": reason,
                "entry": entry,
                "stop": stop,
                "risk_usd": risk_usd,
                "pnl": pnl,
                "r_multiple": pnl / risk_usd,
                "mfe_usd": max(0.0, mfe_points * POINT_VALUE),
                "mae_usd": max(0.0, mae_points * POINT_VALUE),
            }
        )
    return pd.DataFrame(records), exclusions


def sample(trades, lo, hi):
    return trades[trades.date.dt.year.between(lo, hi)].copy()


def basic_stats(trades, dates):
    daily = trades.groupby("date").pnl.sum().reindex(dates, fill_value=0.0)
    equity = daily.cumsum()
    drawdown = equity - equity.cummax()
    return {
        "trades": int(len(trades)),
        "trades_per_week": round(
            len(trades) / (len(pd.unique(dates.year)) * 52), 3
        ),
        "net_pnl_usd": round(float(trades.pnl.sum()), 2),
        "mean_trade_usd": round(float(trades.pnl.mean()), 3),
        "median_trade_usd": round(float(trades.pnl.median()), 3),
        "profit_factor": round(profit_factor(trades.pnl), 3),
        "win_rate": round(float((trades.pnl > 0).mean()), 3),
        "max_daily_drawdown_usd": round(float(drawdown.min()), 2),
        "mean_r": round(float(trades.r_multiple.mean()), 3),
        "median_r": round(float(trades.r_multiple.median()), 3),
        "median_risk_usd": round(float(trades.risk_usd.median()), 2),
        "median_mfe_usd": round(float(trades.mfe_usd.median()), 2),
        "median_mae_usd": round(float(trades.mae_usd.median()), 2),
    }


def period_stats(trades, all_dates, lo, hi):
    dates = all_dates[all_dates.year.to_series(index=all_dates).between(lo, hi)]
    return basic_stats(sample(trades, lo, hi), dates)


def moving_block_bootstrap(trades, dates, block, extra_cost, seed):
    frame = pd.DataFrame(index=dates)
    frame["pnl"] = trades.groupby("date").pnl.sum()
    frame["count"] = trades.groupby("date").size()
    frame = frame.fillna(0.0)
    daily = (frame.pnl - extra_cost * frame["count"]).to_numpy(dtype=float)
    blocks = np.array(
        [daily[start : start + block] for start in range(len(daily) - block + 1)]
    )
    rng = np.random.default_rng(seed)
    draws = 20000
    block_count = math.ceil(len(daily) / block)
    totals = np.empty(draws)
    for draw in range(draws):
        chosen = blocks[rng.integers(0, len(blocks), size=block_count)].ravel()
        totals[draw] = chosen[: len(daily)].sum()
    return {
        "block_sessions": block,
        "extra_cost_per_trade_usd": extra_cost,
        "draws": draws,
        "probability_total_pnl_le_zero": round(float((totals <= 0).mean()), 4),
        "p05_total_pnl_usd": round(float(np.quantile(totals, 0.05)), 2),
        "median_total_pnl_usd": round(float(np.median(totals)), 2),
    }


def longest_losing_streak(values):
    run = 0
    longest = 0
    for value in values:
        run = run + 1 if value < 0 else 0
        longest = max(longest, run)
    return longest


def concentration(trades, dates):
    ordered = trades.sort_values("pnl", ascending=False)
    work = trades.copy()
    work["week"] = work.date.dt.to_period("W")
    work["month"] = work.date.dt.to_period("M")
    work["quarter"] = work.date.dt.to_period("Q")
    work["year"] = work.date.dt.year
    full_daily = trades.groupby("date").pnl.sum().reindex(dates, fill_value=0.0)
    weekly = full_daily.groupby(full_daily.index.to_period("W")).sum()
    monthly = full_daily.groupby(full_daily.index.to_period("M")).sum()
    quarterly = full_daily.groupby(full_daily.index.to_period("Q")).sum()
    top = ordered.head(10)[["date", "side", "pnl", "risk_usd", "r_multiple"]]
    bottom = trades.sort_values("pnl").head(10)[
        ["date", "side", "pnl", "risk_usd", "r_multiple"]
    ]

    def rows(frame):
        return [
            {
                "date": row.date.strftime("%Y-%m-%d"),
                "side": "long" if row.side == 1 else "short",
                "pnl_usd": round(float(row.pnl), 2),
                "risk_usd": round(float(row.risk_usd), 2),
                "r_multiple": round(float(row.r_multiple), 3),
            }
            for row in frame.itertuples(index=False)
        ]

    return {
        "net_without_top_1_usd": round(float(ordered.iloc[1:].pnl.sum()), 2),
        "net_without_top_5_usd": round(float(ordered.iloc[5:].pnl.sum()), 2),
        "net_without_top_10_usd": round(float(ordered.iloc[10:].pnl.sum()), 2),
        "longest_losing_trade_streak": longest_losing_streak(trades.pnl),
        "positive_week_fraction": round(float((weekly > 0).mean()), 3),
        "positive_month_fraction": round(float((monthly > 0).mean()), 3),
        "positive_quarter_fraction": round(float((quarterly > 0).mean()), 3),
        "year_pnl_usd": {
            str(year): round(float(value), 2)
            for year, value in work.groupby("year").pnl.sum().items()
        },
        "quarter_pnl_usd": {
            str(period): round(float(value), 2)
            for period, value in quarterly.items()
        },
        "top_ten": rows(top),
        "bottom_ten": rows(bottom),
    }


def summarize_variant(trades, all_dates):
    return {
        "development": period_stats(trades, all_dates, 2021, 2023),
        "secondary_holdout": period_stats(trades, all_dates, 2024, 2025),
    }


def extra_cost_table(trades, lo, hi):
    subset = sample(trades, lo, hi)
    return {
        f"{cost:.2f}": round(
            float(subset.pnl.sum() - cost * len(subset)), 2
        )
        for cost in [0.0, 1.25, 2.5, 5.0]
    }


def daily_series(trades, dates):
    return trades.groupby("date").pnl.sum().reindex(dates, fill_value=0.0)


def portfolio_diagnostics(candidate, benchmark, all_dates):
    result = {}
    for lo, hi, label in [(2021, 2023, "development"), (2024, 2025, "holdout")]:
        dates = all_dates[all_dates.year.to_series(index=all_dates).between(lo, hi)]
        cand = sample(candidate, lo, hi)
        bench = benchmark[benchmark.date.dt.year.between(lo, hi)]
        c_daily = daily_series(cand, dates)
        b_daily = daily_series(bench, dates)
        union = (c_daily != 0) | (b_daily != 0)
        overlap = (c_daily != 0) & (b_daily != 0)
        combined_trades = pd.concat(
            [
                cand[["date", "pnl"]],
                bench[["date", "pnl"]],
            ],
            ignore_index=True,
        )
        combined_daily = daily_series(combined_trades, dates)
        combined_dd = combined_daily.cumsum()
        combined_dd = combined_dd - combined_dd.cummax()
        result[label] = {
            "candidate_active_days": int(cand.date.nunique()),
            "benchmark_active_days": int(bench.date.nunique()),
            "overlap_days": int(overlap.sum()),
            "fraction_candidate_days_overlapping": round(
                float(overlap.sum() / cand.date.nunique()), 3
            ),
            "daily_correlation_all_days": round(float(c_daily.corr(b_daily)), 3),
            "daily_correlation_union_active_days": round(
                float(c_daily[union].corr(b_daily[union])), 3
            ),
            "daily_correlation_overlap_days": round(
                float(c_daily[overlap].corr(b_daily[overlap])), 3
            ),
            "descriptive_unweighted_combination": {
                "trades": int(len(combined_trades)),
                "net_pnl_usd": round(float(combined_trades.pnl.sum()), 2),
                "profit_factor": round(
                    profit_factor(combined_trades.pnl), 3
                ),
                "max_daily_drawdown_usd": round(float(combined_dd.min()), 2),
                "net_after_extra_2_50_per_trade_usd": round(
                    float(
                        combined_trades.pnl.sum()
                        - 2.5 * len(combined_trades)
                    ),
                    2,
                ),
            },
        }
        engine_corr = {}
        for engine, group in bench.groupby("engine"):
            engine_daily = daily_series(group, dates)
            engine_corr[str(engine)] = round(
                float(c_daily.corr(engine_daily)), 3
            )
        result[label]["candidate_daily_correlation_by_engine"] = engine_corr
    return result


def main():
    sessions = dual_test.load_sessions()
    all_dates = pd.DatetimeIndex([day for day, _ in sessions])
    anchors = {day: load_anchor(day) for day, _ in sessions}

    baseline, baseline_exclusions = simulate(sessions, anchors)
    controls = {}
    for name, anchor_name, lag in [
        ("prior_volume_scar", "scar", 1),
        ("prior_transaction_vwap", "vwap", 1),
        ("prior_terminal_price", "terminal", 1),
        ("two_session_stale_volume_scar", "scar", 2),
    ]:
        trades, exclusions = simulate(
            sessions, anchors, anchor_name=anchor_name, anchor_lag=lag
        )
        controls[name] = {
            "results": summarize_variant(trades, all_dates),
            "exclusions": exclusions,
        }

    tick_grid, _ = simulate(sessions, anchors, tick_grid_stop=True)
    flipped, _ = simulate(sessions, anchors, flip_direction=True)
    delays = {}
    for delay in [1, 5, 15]:
        trades, exclusions = simulate(
            sessions, anchors, entry_delay=delay
        )
        delays[str(delay)] = {
            "results": summarize_variant(trades, all_dates),
            "exclusions": exclusions,
        }
    exits = {}
    for label, index in [("1430", 300), ("1500", 330), ("1555", 385)]:
        trades, exclusions = simulate(sessions, anchors, exit_idx=index)
        exits[label] = {
            "results": summarize_variant(trades, all_dates),
            "exclusions": exclusions,
        }

    development = sample(baseline, 2021, 2023)
    holdout = sample(baseline, 2024, 2025)
    development_dates = all_dates[
        all_dates.year.to_series(index=all_dates).between(2021, 2023)
    ]
    holdout_dates = all_dates[
        all_dates.year.to_series(index=all_dates).between(2024, 2025)
    ]

    session_map = dict(sessions)
    benchmark_signals = three_test.build_three_engine_signals(sessions)
    benchmark, benchmark_skipped = three_test.simulate(
        benchmark_signals, session_map
    )

    output = {
        "candidate": {
            "results": summarize_variant(baseline, all_dates),
            "exclusions": baseline_exclusions,
            "extra_cost_pnl_usd": {
                "development": extra_cost_table(baseline, 2021, 2023),
                "holdout": extra_cost_table(baseline, 2024, 2025),
            },
            "concentration": {
                "development": concentration(
                    development, development_dates
                ),
                "holdout": concentration(holdout, holdout_dates),
            },
            "bootstrap": {
                "development": [
                    moving_block_bootstrap(
                        development, development_dates, block, cost, 20260726
                    )
                    for block in [5, 20]
                    for cost in [0.0, 2.5]
                ],
                "holdout": [
                    moving_block_bootstrap(
                        holdout, holdout_dates, block, cost, 20260726
                    )
                    for block in [5, 20]
                    for cost in [0.0, 2.5]
                ],
            },
        },
        "anchor_falsification_controls": controls,
        "execution_diagnostics": {
            "adverse_tick_grid_stop": summarize_variant(
                tick_grid, all_dates
            ),
            "entry_delays_minutes": delays,
            "time_exit_controls": exits,
        },
        "paired_direction_placebo": {
            "actual": summarize_variant(baseline, all_dates),
            "flipped_same_time_same_initial_risk": summarize_variant(
                flipped, all_dates
            ),
        },
        "three_engine_relationship": {
            "benchmark_skipped_bad_geometry": benchmark_skipped,
            "diagnostics": portfolio_diagnostics(
                baseline, benchmark, all_dates
            ),
        },
    }
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
