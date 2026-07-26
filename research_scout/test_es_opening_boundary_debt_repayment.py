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
    no_signal = 0
    bad_geometry = 0
    for day, bars in sessions:
        opening = bars.iloc[0:30]
        rejection = bars.iloc[30:120]
        opening_high = float(opening.high.max())
        opening_low = float(opening.low.min())
        opening_center = center(opening)
        terminal = float(rejection.iloc[-1].close)
        inside = opening_low < terminal < opening_high
        if (
            inside
            and float(rejection.low.min()) < opening_low
            and terminal < opening_center
        ):
            side = 1
        elif (
            inside
            and float(rejection.high.max()) > opening_high
            and terminal > opening_center
        ):
            side = -1
        else:
            no_signal += 1
            continue

        entry_idx = 120
        exit_idx = 240
        entry = float(bars.iloc[entry_idx].open) + side * TICK_SIZE
        target = opening_center - side * TICK_SIZE
        morning_extreme = (
            float(rejection.low.min())
            if side == 1
            else float(rejection.high.max())
        )
        stop = morning_extreme - side * TICK_SIZE
        target_valid = target > entry if side == 1 else target < entry
        stop_valid = stop < entry if side == 1 else stop > entry
        if not target_valid or not stop_valid:
            bad_geometry += 1
            continue

        outcome = None
        for index in range(entry_idx, exit_idx):
            bar = bars.iloc[index]
            stop_hit = float(bar.low) <= stop if side == 1 else float(bar.high) >= stop
            target_hit = (
                float(bar.high) >= target if side == 1 else float(bar.low) <= target
            )
            if stop_hit:
                bar_open = float(bar.open)
                opened_beyond = bar_open < stop if side == 1 else bar_open > stop
                exit_price = (
                    bar_open - side * TICK_SIZE if opened_beyond else stop
                )
                outcome = "stop"
                break
            if target_hit:
                exit_price = target
                outcome = "target"
                break
        if outcome is None:
            exit_price = float(bars.iloc[exit_idx].open) - side * TICK_SIZE
            outcome = "1330"

        pnl = side * (exit_price - entry) * POINT_VALUE - COMMISSION
        records.append(
            {
                "date": day,
                "side": side,
                "pnl": pnl,
                "reason": outcome,
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
        "no_signal": no_signal,
        "bad_geometry": bad_geometry,
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
