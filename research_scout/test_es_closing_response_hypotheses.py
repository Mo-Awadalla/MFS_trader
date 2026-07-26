import json
import math
import sys
from pathlib import Path

sys.path.insert(0, ".vendor")

import databento as db
import numpy as np
import pandas as pd


ROOT = Path("external_artifacts/databento_es_close/GLBX.MDP3")
FEATURE_PATH = ROOT / "es_close_flow_features_2021_2025.parquet"
SESSION_ROOT = ROOT / "sessions"
POINT_VALUE = 5.0
COMMISSION = 1.24
DEVELOPMENT_YEARS = {2021, 2022, 2023}


def profit_factor(values):
    gains = float(values[values > 0].sum())
    losses = float(-values[values < 0].sum())
    return gains / losses if losses else math.inf


def eligible_execution_rows():
    frame = pd.read_parquet(FEATURE_PATH)
    frame["date"] = pd.to_datetime(frame["date"])
    mask = (
        frame.date.dt.year.isin(DEVELOPMENT_YEARS)
        & (frame.rth_bar_count == 390)
        & ~frame.short_session
        & ~frame.degraded
        & frame.mechanically_eligible
        & frame.es_roll_match
        & frame.mes_roll_match
        & frame.quote_valid
        & frame.entry_bid.notna()
        & frame.entry_ask.notna()
        & frame.exit_bid.notna()
        & frame.exit_ask.notna()
        & (frame.entry_bid > 0)
        & (frame.entry_ask >= frame.entry_bid)
        & (frame.exit_bid > 0)
        & (frame.exit_ask >= frame.exit_bid)
    )
    return frame.loc[mask].set_index("date").sort_index()


def load_trades(day):
    path = (
        SESSION_ROOT
        / str(day.year)
        / day.strftime("%Y-%m-%d")
        / "es_trades.dbn.zst"
    )
    if not path.exists():
        return None
    trades = db.DBNStore.from_file(path).to_df()
    if len(trades) == 0:
        return None
    trades = trades.sort_values(["ts_event", "sequence"], kind="stable")
    return trades[["ts_event", "price", "size"]].copy()


def impact_half_life(trades):
    event = trades[trades.ts_event.dt.minute < 20].copy()
    if event.empty:
        return None
    event["minute"] = event.ts_event.dt.floor("min")
    minute = event.groupby("minute", sort=True).price.agg(["first", "last"])
    minute["displacement"] = minute["last"] - minute["first"]
    minute = minute[minute.displacement != 0]
    if minute.empty:
        return None
    selected_time = minute.displacement.abs().idxmax()
    selected = minute.loc[selected_time]
    event_side = 1 if selected.displacement > 0 else -1
    midpoint = (float(selected["first"]) + float(selected["last"])) / 2.0
    terminal = float(trades.iloc[-1].price)
    retained = event_side * (terminal - midpoint) >= 0
    side = event_side if retained else -event_side
    return side, "retained" if retained else "repaired"


def volume_scar_escape(trades):
    by_price = trades.groupby("price", sort=True)["size"].sum()
    max_volume = by_price.max()
    candidates = by_price[by_price == max_volume].index.to_numpy(dtype=float)
    full_vwap = float(np.average(trades.price, weights=trades["size"]))
    distances = np.abs(candidates - full_vwap)
    scar = float(candidates[distances == distances.min()].min())
    confirmation = trades[trades.ts_event.dt.minute >= 25]
    if confirmation.empty:
        return None
    center = float(np.average(confirmation.price, weights=confirmation["size"]))
    terminal = float(trades.iloc[-1].price)
    if center > scar and terminal > scar:
        return 1, "above_scar"
    if center < scar and terminal < scar:
        return -1, "below_scar"
    return None


def auction_density_switch(trades):
    first = trades[trades.ts_event.dt.minute < 15]
    second = trades[trades.ts_event.dt.minute >= 15]
    if first.empty or second.empty:
        return None
    first_density = float(first["size"].sum()) / float(first.price.nunique())
    second_density = float(second["size"].sum()) / float(second.price.nunique())
    displacement = float(second.iloc[-1].price - second.iloc[0].price)
    if displacement == 0:
        return None
    move_side = 1 if displacement > 0 else -1
    dense = second_density >= first_density
    side = move_side if dense else -move_side
    return side, "dense" if dense else "vacuum"


def simulate_signal(row, side):
    entry = float(row.entry_ask if side == 1 else row.entry_bid)
    exit_price = float(row.exit_bid if side == 1 else row.exit_ask)
    return side * (exit_price - entry) * POINT_VALUE - COMMISSION


def summarize(trades, eligible_dates):
    if trades.empty:
        return {}
    daily = (
        trades.groupby("date").pnl.sum().reindex(eligible_dates, fill_value=0.0)
    )
    equity = daily.cumsum()
    drawdown = equity - equity.cummax()
    yearly = trades.groupby(trades.date.dt.year).pnl.sum()
    sides = trades.groupby("side").pnl.sum()
    states = trades.groupby("state").pnl.agg(["count", "sum"])
    return {
        "trades": int(len(trades)),
        "trades_per_week": round(len(trades) / (3 * 52), 3),
        "net_pnl_usd": round(float(trades.pnl.sum()), 2),
        "mean_trade_usd": round(float(trades.pnl.mean()), 3),
        "profit_factor": round(profit_factor(trades.pnl), 3),
        "win_rate": round(float((trades.pnl > 0).mean()), 3),
        "max_daily_drawdown_usd": round(float(drawdown.min()), 2),
        "year_pnl_usd": {
            str(int(year)): round(float(value), 2)
            for year, value in yearly.items()
        },
        "side_pnl_usd": {
            "long": round(float(sides.get(1, 0.0)), 2),
            "short": round(float(sides.get(-1, 0.0)), 2),
        },
        "state_results": {
            str(state): {
                "trades": int(values["count"]),
                "net_pnl_usd": round(float(values["sum"]), 2),
            }
            for state, values in states.iterrows()
        },
        "median_entry_spread_ticks": round(
            float(trades.entry_spread.median() / 0.25), 3
        ),
        "median_exit_spread_ticks": round(
            float(trades.exit_spread.median() / 0.25), 3
        ),
    }


def main():
    executions = eligible_execution_rows()
    engines = {
        "impact_half_life": impact_half_life,
        "volume_scar_escape": volume_scar_escape,
        "auction_density_switch": auction_density_switch,
    }
    records = {name: [] for name in engines}
    missing_trade_files = 0

    for day, row in executions.iterrows():
        trades = load_trades(day)
        if trades is None:
            missing_trade_files += 1
            continue
        for name, function in engines.items():
            signal = function(trades)
            if signal is None:
                continue
            side, state = signal
            records[name].append(
                {
                    "date": day,
                    "side": side,
                    "state": state,
                    "pnl": simulate_signal(row, side),
                    "entry_spread": float(row.entry_spread),
                    "exit_spread": float(row.exit_spread),
                }
            )

    output = {
        "development_period": "2021-2023",
        "eligible_execution_sessions": int(len(executions)),
        "missing_trade_files": missing_trade_files,
        "results": {},
    }
    for name, rows in records.items():
        frame = pd.DataFrame(rows)
        output["results"][name] = summarize(frame, executions.index)

    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
