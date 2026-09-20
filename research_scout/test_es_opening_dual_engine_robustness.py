import json
import math
import sys

sys.path.insert(0, ".vendor")

import databento as db
import numpy as np
import pandas as pd

DATA_PATH = (
    "external_artifacts/databento_es_close/GLBX.MDP3/bars/"
    "es_ohlcv_1m_2021-01-01_2026-01-01.dbn.zst"
)
TICK_SIZE = 0.25
POINT_VALUE = 5.0
COMMISSION = 1.24


def load_sessions():
    frame = db.DBNStore.from_file(DATA_PATH).to_df()
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    frame = frame.tz_convert("America/New_York")
    rth = frame.between_time("09:30", "15:59").copy()
    rth["day"] = rth.index.date
    sessions = []
    for day, bars in rth.groupby("day"):
        if len(bars) >= 390:
            sessions.append((pd.Timestamp(day), bars.drop(columns="day").iloc[:390]))
    return sessions


def build_signals(sessions):
    opening_ranges = []
    signals = []
    session_features = []

    for day, bars in sessions:
        opening = bars.iloc[:30]
        opening_high = float(opening.high.max())
        opening_low = float(opening.low.min())
        opening_midpoint = (opening_high + opening_low) / 2
        opening_range = opening_high - opening_low
        prior_range_median = (
            float(np.median(opening_ranges[-60:]))
            if len(opening_ranges) >= 60
            else np.nan
        )
        prior_rth_ranges = [
            float(prior_bars.high.max() - prior_bars.low.min())
            for _, prior_bars in sessions[max(0, len(session_features) - 60) : len(session_features)]
        ]
        prior_rth_median = (
            float(np.median(prior_rth_ranges)) if len(prior_rth_ranges) == 60 else np.nan
        )
        session_features.append(
            {
                "date": day,
                "prior_60_rth_range_fraction": (
                    prior_rth_median / float(opening.iloc[0].open)
                    if not np.isnan(prior_rth_median)
                    else np.nan
                ),
            }
        )

        if not np.isnan(prior_range_median) and opening_range < prior_range_median:
            breakout_side = 0
            signal_end = None
            for start in range(30, 355, 5):
                close = float(bars.iloc[start : start + 5].iloc[-1].close)
                if close > opening_high:
                    breakout_side = 1
                    signal_end = start + 4
                    break
                if close < opening_low:
                    breakout_side = -1
                    signal_end = start + 4
                    break
            if breakout_side and signal_end + 1 < 360:
                signals.append(
                    {
                        "date": day,
                        "engine": "convexity",
                        "side": breakout_side,
                        "base_entry_idx": signal_end + 1,
                        "stop_reference": opening_midpoint,
                    }
                )

        typical = (opening.high + opening.low + opening.close) / 3
        center = float((typical * opening.volume).sum() / opening.volume.sum())
        opening_price = float(opening.iloc[0].open)
        opening_close = float(opening.iloc[-1].close)
        center_side = 0
        if opening_close > opening_price and center > opening_price:
            center_side = 1
        elif opening_close < opening_price and center < opening_price:
            center_side = -1
        if center_side:
            signals.append(
                {
                    "date": day,
                    "engine": "center",
                    "side": center_side,
                    "base_entry_idx": 30,
                    "stop_reference": center,
                }
            )

        opening_ranges.append(opening_range)

    return pd.DataFrame(signals), pd.DataFrame(session_features)


def simulate(
    signals,
    session_map,
    adverse_ticks=1,
    delay_minutes=0,
    extra_fill_ticks=0.0,
):
    records = []
    skipped_invalidated = 0
    skipped_bad_geometry = 0
    adverse_points = adverse_ticks * TICK_SIZE

    for signal in signals.itertuples(index=False):
        bars = session_map[signal.date]
        lows = bars.low.to_numpy(dtype=float)
        highs = bars.high.to_numpy(dtype=float)
        side = int(signal.side)
        entry_idx = int(signal.base_entry_idx + delay_minutes)
        if entry_idx >= 360:
            skipped_invalidated += 1
            continue
        stop_trigger = (
            float(signal.stop_reference)
            if signal.engine == "convexity"
            else float(signal.stop_reference - side * adverse_points)
        )
        stop_fill = float(signal.stop_reference - side * adverse_points)

        if delay_minutes:
            invalidated = (
                bool(
                    (
                        lows[int(signal.base_entry_idx) : entry_idx]
                        <= stop_trigger
                    ).any()
                )
                if side == 1
                else bool(
                    (
                        highs[int(signal.base_entry_idx) : entry_idx]
                        >= stop_trigger
                    ).any()
                )
            )
            if invalidated:
                skipped_invalidated += 1
                continue

        rule_entry = float(bars.iloc[entry_idx].open) + side * adverse_points
        if (side == 1 and stop_fill >= rule_entry) or (
            side == -1 and stop_fill <= rule_entry
        ):
            skipped_bad_geometry += 1
            continue
        entry = rule_entry + side * extra_fill_ticks * TICK_SIZE

        exit_price = None
        exit_idx = None
        reason = None
        stop_hits = (
            np.flatnonzero(lows[entry_idx:360] <= stop_trigger)
            if side == 1
            else np.flatnonzero(highs[entry_idx:360] >= stop_trigger)
        )
        if len(stop_hits):
            exit_idx = entry_idx + int(stop_hits[0])
            exit_price = stop_fill
            if signal.engine == "convexity":
                bar_open = float(bars.iloc[exit_idx].open)
                opened_beyond = (
                    bar_open < stop_trigger
                    if side == 1
                    else bar_open > stop_trigger
                )
                if opened_beyond:
                    exit_price = bar_open - side * adverse_points
            exit_price -= side * extra_fill_ticks * TICK_SIZE
            reason = "stop"
        if exit_price is None:
            exit_price = (
                float(bars.iloc[360].open)
                - side * adverse_points
                - side * extra_fill_ticks * TICK_SIZE
            )
            exit_idx = 360
            reason = "1530"

        pnl = side * (exit_price - entry) * POINT_VALUE - COMMISSION
        records.append(
            {
                "date": signal.date,
                "engine": signal.engine,
                "side": side,
                "entry_idx": entry_idx,
                "exit_idx": exit_idx,
                "reason": reason,
                "risk_usd": abs(entry - stop_fill) * POINT_VALUE + COMMISSION,
                "holding_minutes": exit_idx - entry_idx,
                "pnl": pnl,
            }
        )

    return pd.DataFrame(records), {
        "skipped_pre_entry_invalidation": skipped_invalidated,
        "skipped_bad_geometry": skipped_bad_geometry,
    }


def profit_factor(values):
    gains = values[values > 0].sum()
    losses = -values[values < 0].sum()
    return float(gains / losses) if losses else math.inf


def sample_stats(trades, session_dates, lo, hi):
    sample = trades[trades.date.dt.year.between(lo, hi)].copy()
    dates = session_dates[session_dates.dt.year.between(lo, hi)]
    daily = (
        sample.groupby("date").pnl.sum().reindex(dates, fill_value=0.0).astype(float)
    )
    equity = daily.cumsum()
    drawdown = equity - equity.cummax()
    years = hi - lo + 1
    return {
        "trades": int(len(sample)),
        "trades_per_week": round(len(sample) / (years * 52), 3),
        "active_days": int(sample.date.nunique()),
        "active_days_per_week": round(sample.date.nunique() / (years * 52), 3),
        "net_pnl": round(float(sample.pnl.sum()), 2),
        "mean_trade": round(float(sample.pnl.mean()), 3),
        "profit_factor": round(profit_factor(sample.pnl), 3),
        "max_daily_drawdown": round(float(drawdown.min()), 2),
    }


def rolling_diagnostics(trades, session_dates, lo, hi):
    sample = trades[trades.date.dt.year.between(lo, hi)]
    dates = session_dates[session_dates.dt.year.between(lo, hi)]
    daily = sample.groupby("date").pnl.sum().reindex(dates, fill_value=0.0)
    result = {}
    for window, label in [(63, "3m"), (126, "6m"), (252, "12m")]:
        values = daily.rolling(window).sum().dropna()
        if len(values):
            result[label] = {
                "minimum": round(float(values.min()), 2),
                "median": round(float(values.median()), 2),
                "maximum": round(float(values.max()), 2),
                "fraction_positive": round(float((values > 0).mean()), 3),
            }
    return result


def calendar_diagnostics(trades):
    work = trades.copy()
    work["year"] = work.date.dt.year
    work["half"] = work.date.dt.year.astype(str) + "-H" + np.where(
        work.date.dt.month <= 6, "1", "2"
    )
    work["quarter"] = work.date.dt.to_period("Q").astype(str)
    yearly = work.groupby(["engine", "year"]).pnl.agg(["count", "sum"])
    halves = work.groupby("half").pnl.sum()
    quarters = work.groupby("quarter").pnl.sum()
    return {
        "component_years": [
            {
                "engine": engine,
                "year": int(year),
                "trades": int(row["count"]),
                "pnl": round(float(row["sum"]), 2),
            }
            for (engine, year), row in yearly.iterrows()
        ],
        "half_years": {key: round(float(value), 2) for key, value in halves.items()},
        "quarter_summary": {
            "positive": int((quarters > 0).sum()),
            "total": int(len(quarters)),
            "worst": {
                "quarter": str(quarters.idxmin()),
                "pnl": round(float(quarters.min()), 2),
            },
            "best": {
                "quarter": str(quarters.idxmax()),
                "pnl": round(float(quarters.max()), 2),
            },
        },
    }


def volatility_regimes(trades, features):
    development = features[
        features.date.dt.year.between(2021, 2023)
        & features.prior_60_rth_range_fraction.notna()
    ]
    low, high = development.prior_60_rth_range_fraction.quantile([1 / 3, 2 / 3])
    labeled = features.copy()
    labeled["regime"] = pd.cut(
        labeled.prior_60_rth_range_fraction,
        [-np.inf, low, high, np.inf],
        labels=["low", "middle", "high"],
    )
    joined = trades.merge(labeled[["date", "regime"]], on="date", how="left")
    output = {
        "development_thresholds": {
            "low_to_middle": float(low),
            "middle_to_high": float(high),
        }
    }
    for name, lo, hi in [("development", 2021, 2023), ("holdout", 2024, 2025)]:
        sample = joined[joined.date.dt.year.between(lo, hi)]
        table = sample.groupby("regime", observed=True).pnl.agg(["count", "mean", "sum"])
        output[name] = {
            str(regime): {
                "trades": int(row["count"]),
                "mean_trade": round(float(row["mean"]), 2),
                "net_pnl": round(float(row["sum"]), 2),
            }
            for regime, row in table.iterrows()
        }
    return output


def capped_portfolio(trades, priority):
    ordered = trades.copy()
    rank = {priority: 0, ("center" if priority == "convexity" else "convexity"): 1}
    ordered["rank"] = ordered.engine.map(rank)
    return (
        ordered.sort_values(["date", "rank", "entry_idx"])
        .drop_duplicates("date", keep="first")
        .drop(columns="rank")
    )


def overlap_diagnostics(trades, lo=2021, hi=2025):
    trades = trades[trades.date.dt.year.between(lo, hi)]
    pivot_side = trades.pivot(index="date", columns="engine", values="side").dropna()
    pivot_pnl = trades.pivot(index="date", columns="engine", values="pnl").dropna()
    categories = pd.DataFrame(index=pivot_side.index)
    categories["same"] = pivot_side.center == pivot_side.convexity
    categories["pnl"] = pivot_pnl.center + pivot_pnl.convexity
    return {
        "overlap_days": int(len(categories)),
        "same_direction": {
            "days": int(categories["same"].sum()),
            "net_pnl": round(float(categories.loc[categories["same"], "pnl"].sum()), 2),
            "mean_daily_pnl": round(
                float(categories.loc[categories["same"], "pnl"].mean()), 2
            ),
        },
        "opposite_direction": {
            "days": int((~categories["same"]).sum()),
            "net_pnl": round(float(categories.loc[~categories["same"], "pnl"].sum()), 2),
            "mean_daily_pnl": round(
                float(categories.loc[~categories["same"], "pnl"].mean()), 2
            ),
        },
        "pnl_correlation_on_overlap": round(
            float(pivot_pnl[["center", "convexity"]].corr().iloc[0, 1]), 3
        ),
    }


def tail_diagnostics(trades, lo, hi):
    sample = trades[trades.date.dt.year.between(lo, hi)].sort_values(
        ["date", "entry_idx"]
    )
    ordered = sample.sort_values("pnl", ascending=False)
    losing = 0
    longest_losing = 0
    for pnl in sample.pnl:
        losing = losing + 1 if pnl < 0 else 0
        longest_losing = max(longest_losing, losing)
    weekly = sample.groupby(sample.date.dt.to_period("W")).pnl.sum()
    return {
        "median_trade": round(float(sample.pnl.median()), 2),
        "pnl_percentiles": {
            str(q): round(float(sample.pnl.quantile(q)), 2)
            for q in [0.01, 0.05, 0.25, 0.75, 0.95, 0.99]
        },
        "largest_winner": round(float(ordered.pnl.iloc[0]), 2),
        "largest_loser": round(float(ordered.pnl.iloc[-1]), 2),
        "net_without_top_5": round(float(ordered.iloc[5:].pnl.sum()), 2),
        "net_without_top_1pct": round(
            float(ordered.iloc[max(1, math.ceil(len(ordered) * 0.01)) :].pnl.sum()), 2
        ),
        "longest_losing_streak": int(longest_losing),
        "positive_week_fraction": round(float((weekly > 0).mean()), 3),
    }


def moving_block_bootstrap(daily_values, seed, repetitions=5000, block=5):
    values = np.asarray(daily_values, dtype=float)
    size = len(values)
    rng = np.random.default_rng(seed)
    totals = np.empty(repetitions)
    drawdowns = np.empty(repetitions)
    blocks_needed = math.ceil(size / block)
    for rep in range(repetitions):
        starts = rng.integers(0, size, blocks_needed)
        sample = np.concatenate(
            [values[(start + np.arange(block)) % size] for start in starts]
        )[:size]
        equity = np.cumsum(sample)
        drawdown = equity - np.maximum.accumulate(equity)
        totals[rep] = sample.sum()
        drawdowns[rep] = drawdown.min()
    return {
        "total_pnl_95pct_ci": np.quantile(totals, [0.025, 0.975]).round(2).tolist(),
        "probability_total_not_positive": round(float((totals <= 0).mean()), 3),
        "max_drawdown_percentiles": {
            "5pct_worst_tail": round(float(np.quantile(drawdowns, 0.05)), 2),
            "median": round(float(np.quantile(drawdowns, 0.5)), 2),
            "95pct": round(float(np.quantile(drawdowns, 0.95)), 2),
        },
    }


def bootstrap_diagnostics(trades, session_dates):
    output = {}
    for name, lo, hi, seed in [
        ("development", 2021, 2023, 20260725),
        ("holdout", 2024, 2025, 20260726),
    ]:
        sample = trades[trades.date.dt.year.between(lo, hi)]
        dates = session_dates[session_dates.dt.year.between(lo, hi)]
        daily = sample.groupby("date").pnl.sum().reindex(dates, fill_value=0.0)
        output[name] = moving_block_bootstrap(daily.values, seed)
    return output


def main():
    sessions = load_sessions()
    session_map = dict(sessions)
    session_dates = pd.Series([day for day, _ in sessions])
    signals, features = build_signals(sessions)
    baseline, baseline_skips = simulate(signals, session_map)

    result = {
        "baseline": {
            "development": sample_stats(baseline, session_dates, 2021, 2023),
            "holdout": sample_stats(baseline, session_dates, 2024, 2025),
            "full": sample_stats(baseline, session_dates, 2021, 2025),
            "skips": baseline_skips,
        },
        "calendar": calendar_diagnostics(baseline),
        "rolling": {
            "development": rolling_diagnostics(
                baseline, session_dates, 2021, 2023
            ),
            "holdout": rolling_diagnostics(baseline, session_dates, 2024, 2025),
            "full": rolling_diagnostics(baseline, session_dates, 2021, 2025),
        },
        "volatility_regimes": volatility_regimes(baseline, features),
        "overlap": {
            "development": overlap_diagnostics(baseline, 2021, 2023),
            "holdout": overlap_diagnostics(baseline, 2024, 2025),
            "full": overlap_diagnostics(baseline, 2021, 2025),
        },
        "execution": {
            "execution_buffer_ticks": {},
            "extra_fill_ticks": {},
            "delay_minutes_with_stale_signal_cancellation": {},
        },
        "single_position_diagnostics": {},
        "tails": {
            "development": tail_diagnostics(baseline, 2021, 2023),
            "holdout": tail_diagnostics(baseline, 2024, 2025),
        },
        "bootstrap": bootstrap_diagnostics(baseline, session_dates),
    }

    for ticks in [1, 2, 3, 5]:
        tested, skips = simulate(signals, session_map, adverse_ticks=ticks)
        result["execution"]["execution_buffer_ticks"][str(ticks)] = {
            "development": sample_stats(tested, session_dates, 2021, 2023),
            "holdout": sample_stats(tested, session_dates, 2024, 2025),
            "skips": skips,
        }

    for extra_ticks in [0, 0.5, 1, 2]:
        tested, skips = simulate(
            signals, session_map, extra_fill_ticks=extra_ticks
        )
        result["execution"]["extra_fill_ticks"][str(extra_ticks)] = {
            "development": sample_stats(tested, session_dates, 2021, 2023),
            "holdout": sample_stats(tested, session_dates, 2024, 2025),
            "skips": skips,
        }

    for delay in [0, 1, 2, 5]:
        tested, skips = simulate(signals, session_map, delay_minutes=delay)
        result["execution"]["delay_minutes_with_stale_signal_cancellation"][
            str(delay)
        ] = {
            "development": sample_stats(tested, session_dates, 2021, 2023),
            "holdout": sample_stats(tested, session_dates, 2024, 2025),
            "skips": skips,
        }

    for priority in ["convexity", "center"]:
        capped = capped_portfolio(baseline, priority)
        result["single_position_diagnostics"][f"{priority}_priority"] = {
            "development": sample_stats(capped, session_dates, 2021, 2023),
            "holdout": sample_stats(capped, session_dates, 2024, 2025),
        }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
