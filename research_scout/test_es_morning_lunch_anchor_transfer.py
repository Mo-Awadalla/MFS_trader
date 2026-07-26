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


def center(bars):
    typical = (bars.high + bars.low + bars.close) / 3.0
    return float((typical * bars.volume).sum() / bars.volume.sum())


def profit_factor(values):
    gains = float(values[values > 0].sum())
    losses = float(-values[values < 0].sum())
    return gains / losses if losses else math.inf


def build_and_simulate(sessions):
    records = []
    no_signal = {}
    bad_geometry = {}
    for day, bars in sessions:
        no_signal.setdefault(day.year, 0)
        bad_geometry.setdefault(day.year, 0)
        morning = bars.iloc[0:120]
        lunch = bars.iloc[120:240]
        morning_center = center(morning)
        lunch_center = center(lunch)
        lunch_close = float(lunch.iloc[-1].close)
        if lunch_center > morning_center and lunch_close > morning_center:
            side = 1
        elif lunch_center < morning_center and lunch_close < morning_center:
            side = -1
        else:
            no_signal[day.year] += 1
            continue

        entry_idx = 240
        exit_idx = 385
        entry = float(bars.iloc[entry_idx].open) + side * TICK_SIZE
        stop = lunch_center - side * TICK_SIZE
        if (side == 1 and stop >= entry) or (side == -1 and stop <= entry):
            bad_geometry[day.year] += 1
            continue

        lows = bars.low.to_numpy(dtype=float)
        highs = bars.high.to_numpy(dtype=float)
        stop_hits = (
            np.flatnonzero(lows[entry_idx:exit_idx] <= stop)
            if side == 1
            else np.flatnonzero(highs[entry_idx:exit_idx] >= stop)
        )
        if len(stop_hits):
            actual_exit_idx = entry_idx + int(stop_hits[0])
            bar_open = float(bars.iloc[actual_exit_idx].open)
            opened_beyond = bar_open < stop if side == 1 else bar_open > stop
            exit_price = (
                bar_open - side * TICK_SIZE if opened_beyond else stop
            )
            reason = "stop"
        else:
            actual_exit_idx = exit_idx
            exit_price = float(bars.iloc[exit_idx].open) - side * TICK_SIZE
            reason = "1555"

        pnl = side * (exit_price - entry) * POINT_VALUE - COMMISSION
        records.append(
            {
                "date": day,
                "side": side,
                "pnl": pnl,
                "reason": reason,
                "risk_usd": abs(entry - stop) * POINT_VALUE + COMMISSION,
            }
        )
    return pd.DataFrame(records), no_signal, bad_geometry


def summarize(trades, session_dates):
    daily = (
        trades.groupby("date").pnl.sum().reindex(session_dates, fill_value=0.0)
    )
    equity = daily.cumsum()
    drawdown = equity - equity.cummax()
    yearly = trades.groupby(trades.date.dt.year).pnl.sum()
    sides = trades.groupby("side").pnl.sum()
    reasons = trades.groupby("reason").pnl.agg(["count", "sum"])
    return {
        "trades": int(len(trades)),
        "trades_per_week": round(len(trades) / (3 * 52), 3),
        "net_pnl_usd": round(float(trades.pnl.sum()), 2),
        "mean_trade_usd": round(float(trades.pnl.mean()), 3),
        "profit_factor": round(profit_factor(trades.pnl), 3),
        "win_rate": round(float((trades.pnl > 0).mean()), 3),
        "max_daily_drawdown_usd": round(float(drawdown.min()), 2),
        "median_initial_risk_usd": round(float(trades.risk_usd.median()), 2),
        "year_pnl_usd": {
            str(int(year)): round(float(value), 2)
            for year, value in yearly.items()
        },
        "side_pnl_usd": {
            "long": round(float(sides.get(1, 0.0)), 2),
            "short": round(float(sides.get(-1, 0.0)), 2),
        },
        "exit_results": {
            str(reason): {
                "trades": int(values["count"]),
                "net_pnl_usd": round(float(values["sum"]), 2),
            }
            for reason, values in reasons.iterrows()
        },
    }


def rolling_diagnostics(trades, session_dates):
    daily = (
        trades.groupby("date").pnl.sum().reindex(session_dates, fill_value=0.0)
    )
    result = {}
    for window, label in [(63, "3m"), (126, "6m"), (252, "12m")]:
        values = daily.rolling(window).sum().dropna()
        if len(values):
            result[label] = {
                "minimum_usd": round(float(values.min()), 2),
                "median_usd": round(float(values.median()), 2),
                "maximum_usd": round(float(values.max()), 2),
                "fraction_positive": round(float((values > 0).mean()), 3),
            }
    return result


def block_bootstrap_loss_probability(trades, session_dates, seed=20260726):
    daily = (
        trades.groupby("date").pnl.sum().reindex(session_dates, fill_value=0.0)
    ).to_numpy(dtype=float)
    block = 5
    blocks = np.array(
        [
            daily[start : start + block]
            for start in range(0, len(daily) - block + 1)
        ]
    )
    rng = np.random.default_rng(seed)
    draws = 10000
    block_count = math.ceil(len(daily) / block)
    totals = np.empty(draws)
    for draw in range(draws):
        chosen = blocks[rng.integers(0, len(blocks), size=block_count)].ravel()
        totals[draw] = chosen[: len(daily)].sum()
    return {
        "method": "10000 stationary-length five-session block resamples",
        "seed": seed,
        "probability_total_pnl_le_zero": round(float((totals <= 0).mean()), 4),
        "p05_total_pnl_usd": round(float(np.quantile(totals, 0.05)), 2),
        "median_total_pnl_usd": round(float(np.median(totals)), 2),
    }


def stress_diagnostics(trades, session_dates):
    ordered = trades.sort_values("pnl", ascending=False)
    work = trades.copy()
    work["month"] = work.date.dt.to_period("M")
    work["year"] = work.date.dt.year
    best_months = (
        work.groupby(["year", "month"]).pnl.sum().groupby(level=0).idxmax()
    )
    best_month_values = [
        float(work[(work.year == year) & (work.month == month)].pnl.sum())
        for year, month in best_months
    ]
    return {
        "additional_1_25_usd_per_trade": round(
            float(trades.pnl.sum() - 1.25 * len(trades)), 2
        ),
        "remove_five_best_trades": round(float(ordered.iloc[5:].pnl.sum()), 2),
        "remove_ten_best_trades": round(float(ordered.iloc[10:].pnl.sum()), 2),
        "five_best_trade_pnl_usd": [
            round(float(value), 2) for value in ordered.head(5).pnl
        ],
        "remove_each_year_best_month": round(
            float(trades.pnl.sum() - sum(best_month_values)), 2
        ),
        "best_month_pnl_by_year_usd": {
            str(year): round(value, 2)
            for (year, _), value in zip(best_months, best_month_values)
        },
        "rolling": rolling_diagnostics(trades, session_dates),
        "five_day_block_bootstrap": block_bootstrap_loss_probability(
            trades, session_dates
        ),
    }


def main():
    sessions = load_sessions()
    all_dates = pd.DatetimeIndex([day for day, _ in sessions])
    trades, no_signal, bad_geometry = build_and_simulate(sessions)
    development = trades[trades.date.dt.year.isin({2021, 2022, 2023})].copy()
    holdout = trades[trades.date.dt.year.isin({2024, 2025})].copy()
    development_dates = all_dates[all_dates.year.isin({2021, 2022, 2023})]
    holdout_dates = all_dates[all_dates.year.isin({2024, 2025})]
    output = {
        "development": {
            "period": "2021-2023",
            "sessions": int(len(development_dates)),
            "no_signal_sessions": int(
                sum(no_signal.get(year, 0) for year in {2021, 2022, 2023})
            ),
            "bad_stop_geometry": int(
                sum(bad_geometry.get(year, 0) for year in {2021, 2022, 2023})
            ),
            "result": summarize(development, development_dates),
            "stress": stress_diagnostics(development, development_dates),
        },
        "secondary_holdout": {
            "period": "2024-2025",
            "sessions": int(len(holdout_dates)),
            "no_signal_sessions": int(
                sum(no_signal.get(year, 0) for year in {2024, 2025})
            ),
            "bad_stop_geometry": int(
                sum(bad_geometry.get(year, 0) for year in {2024, 2025})
            ),
            "result": summarize(holdout, holdout_dates),
            "stress": stress_diagnostics(holdout, holdout_dates),
        },
    }
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
