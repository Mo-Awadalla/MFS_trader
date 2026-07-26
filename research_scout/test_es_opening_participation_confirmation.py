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


def load_development_sessions():
    frame = db.DBNStore.from_file(DATA_PATH).to_df()
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    frame = frame.tz_convert("America/New_York")
    frame = frame[frame.index.year.isin({2021, 2022, 2023})]
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


def main():
    sessions = load_development_sessions()
    records = []
    no_participation = 0
    no_migration = 0
    bad_geometry = 0
    for day, bars in sessions:
        first = bars.iloc[0:15]
        second = bars.iloc[15:30]
        if float(second.volume.sum()) <= float(first.volume.sum()):
            no_participation += 1
            continue
        first_center = center(first)
        second_center = center(second)
        second_close = float(second.iloc[-1].close)
        if second_center > first_center and second_close > first_center:
            side = 1
        elif second_center < first_center and second_close < first_center:
            side = -1
        else:
            no_migration += 1
            continue

        entry_idx = 30
        exit_idx = 360
        entry = float(bars.iloc[entry_idx].open) + side * TICK_SIZE
        stop = first_center - side * TICK_SIZE
        if (side == 1 and stop >= entry) or (side == -1 and stop <= entry):
            bad_geometry += 1
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
            exit_price = float(bars.iloc[exit_idx].open) - side * TICK_SIZE
            reason = "1530"

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

    trades = pd.DataFrame(records)
    dates = pd.DatetimeIndex([day for day, _ in sessions])
    daily = trades.groupby("date").pnl.sum().reindex(dates, fill_value=0.0)
    drawdown = daily.cumsum() - daily.cumsum().cummax()
    yearly = trades.groupby(trades.date.dt.year).pnl.sum()
    sides = trades.groupby("side").pnl.sum()
    reasons = trades.groupby("reason").pnl.agg(["count", "sum"])
    output = {
        "development_period": "2021-2023",
        "sessions": int(len(sessions)),
        "no_participation_confirmation": no_participation,
        "no_migration_confirmation": no_migration,
        "bad_stop_geometry": bad_geometry,
        "result": {
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
        },
    }
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
