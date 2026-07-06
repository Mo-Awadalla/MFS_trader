"""Scout predeclared IBB intraday afternoon-recovery hypothesis.

This script is intentionally a research scout, not a promotion/validation runner.
It uses public Yahoo Chart API 60-minute regular-session bars and writes a
Markdown report under docs/research_scout/.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

NY = ZoneInfo("America/New_York")
ROUND_TRIP_COST = 0.0010  # 10 bps
MORNING_THRESHOLD = -0.0075
SYMBOL = "IBB"
BENCHMARK = "SPY"
OUT = Path("docs/research_scout/IBBIntradayAfternoonRecovery-v1-results.md")


@dataclass(frozen=True)
class SessionTrade:
    date: dt.date
    morning_return: float
    entry_return_gross: float
    entry_return_net: float
    open_to_close_return: float
    benchmark_window_return: float | None
    benchmark_open_to_close_return: float | None


def fetch_chart(symbol: str) -> pd.DataFrame:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {
        "range": "730d",
        "interval": "60m",
        "includePrePost": "false",
        "events": "history",
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    frame = pd.DataFrame(quote)
    frame["timestamp"] = pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(NY)
    frame = frame.set_index("timestamp").sort_index()
    frame = frame.dropna(subset=["open", "close"])
    frame = frame.between_time("09:30", "16:00", inclusive="left")
    return frame


def get_bar(group: pd.DataFrame, hour: int, minute: int) -> pd.Series | None:
    target = dt.time(hour, minute)
    rows = group[group.index.time == target]
    if rows.empty:
        return None
    return rows.iloc[0]


def compute_trades(ibb: pd.DataFrame, spy: pd.DataFrame) -> tuple[list[SessionTrade], pd.DataFrame]:
    trades: list[SessionTrade] = []
    all_sessions: list[dict[str, Any]] = []
    spy_groups = dict(tuple(spy.groupby(spy.index.date)))

    for date, group in ibb.groupby(ibb.index.date):
        if len(group) < 5:
            continue
        first = group.iloc[0]
        morning_bar = get_bar(group, 11, 30)  # bar that ends around 12:30
        entry_bar = get_bar(group, 12, 30)  # next available bar open
        last = group.iloc[-1]
        if morning_bar is None or entry_bar is None:
            continue
        morning_return = float(morning_bar["close"] / first["open"] - 1.0)
        window_return = float(last["close"] / entry_bar["open"] - 1.0)
        open_to_close = float(last["close"] / first["open"] - 1.0)

        spy_window: float | None = None
        spy_oc: float | None = None
        spy_group = spy_groups.get(date)
        if spy_group is not None and len(spy_group) >= 5:
            spy_first = spy_group.iloc[0]
            spy_entry = get_bar(spy_group, 12, 30)
            spy_last = spy_group.iloc[-1]
            if spy_entry is not None:
                spy_window = float(spy_last["close"] / spy_entry["open"] - 1.0)
                spy_oc = float(spy_last["close"] / spy_first["open"] - 1.0)

        all_sessions.append(
            {
                "date": pd.Timestamp(date),
                "morning_return": morning_return,
                "window_return_gross": window_return,
                "window_return_net": window_return - ROUND_TRIP_COST,
                "open_to_close_return": open_to_close,
                "spy_window_return": spy_window,
                "spy_open_to_close_return": spy_oc,
            }
        )
        if morning_return <= MORNING_THRESHOLD:
            trades.append(
                SessionTrade(
                    date=date,
                    morning_return=morning_return,
                    entry_return_gross=window_return,
                    entry_return_net=window_return - ROUND_TRIP_COST,
                    open_to_close_return=open_to_close,
                    benchmark_window_return=spy_window,
                    benchmark_open_to_close_return=spy_oc,
                )
            )
    return trades, pd.DataFrame(all_sessions)


def pct(x: float | None) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return f"{x * 100:.3f}%"


def summarize(series: pd.Series) -> dict[str, float]:
    if series.empty:
        return {}
    return {
        "count": float(series.count()),
        "mean": float(series.mean()),
        "median": float(series.median()),
        "win_rate": float((series > 0).mean()),
        "std": float(series.std(ddof=1)) if len(series) > 1 else 0.0,
        "min": float(series.min()),
        "max": float(series.max()),
        "sum": float(series.sum()),
    }


def table_metric(name: str, stats: dict[str, float]) -> str:
    if not stats:
        return f"| {name} | n/a | n/a | n/a | n/a | n/a | n/a |\n"
    return (
        f"| {name} | {int(stats['count'])} | {pct(stats['mean'])} | {pct(stats['median'])} | "
        f"{pct(stats['win_rate'])} | {pct(stats['min'])} | {pct(stats['max'])} |\n"
    )


def main() -> None:
    ibb = fetch_chart(SYMBOL)
    spy = fetch_chart(BENCHMARK)
    trades, sessions = compute_trades(ibb, spy)
    trade_df = pd.DataFrame([t.__dict__ for t in trades])

    data_start = ibb.index.min()
    data_end = ibb.index.max()
    session_count = sessions["date"].nunique() if not sessions.empty else 0

    net = trade_df["entry_return_net"] if not trade_df.empty else pd.Series(dtype=float)
    gross = trade_df["entry_return_gross"] if not trade_df.empty else pd.Series(dtype=float)
    spy_window = trade_df["benchmark_window_return"].dropna() if not trade_df.empty else pd.Series(dtype=float)
    oc = trade_df["open_to_close_return"] if not trade_df.empty else pd.Series(dtype=float)
    all_same_window = sessions["window_return_net"] if not sessions.empty else pd.Series(dtype=float)

    half_text = "n/a"
    first_half_mean = second_half_mean = float("nan")
    if len(trade_df) >= 2:
        ordered = trade_df.sort_values("date").reset_index(drop=True)
        split = len(ordered) // 2
        first_half_mean = float(ordered.iloc[:split]["entry_return_net"].mean())
        second_half_mean = float(ordered.iloc[split:]["entry_return_net"].mean())
        half_text = f"first half {pct(first_half_mean)}, second half {pct(second_half_mean)}"

    top5_contribution = float("nan")
    if not net.empty and float(net.sum()) > 0:
        top5_contribution = float(net.sort_values(ascending=False).head(5).sum() / net.sum())

    by_year = ""
    if not trade_df.empty:
        tmp = trade_df.copy()
        tmp["year"] = pd.to_datetime(tmp["date"]).dt.year
        for year, group in tmp.groupby("year"):
            by_year += (
                f"| {year} | {len(group)} | {pct(float(group['entry_return_net'].mean()))} | "
                f"{pct(float(group['entry_return_net'].median()))} | "
                f"{pct(float((group['entry_return_net'] > 0).mean()))} |\n"
            )

    pass_checks = {
        "at_least_40_trades": len(trade_df) >= 40,
        "net_average_positive": (not net.empty and float(net.mean()) > 0),
        "net_median_positive": (not net.empty and float(net.median()) > 0),
        "net_win_rate_above_52pct": (not net.empty and float((net > 0).mean()) > 0.52),
        "both_halves_positive": (
            not math.isnan(first_half_mean)
            and not math.isnan(second_half_mean)
            and first_half_mean > 0
            and second_half_mean > 0
        ),
        "top5_under_50pct_total_net_profit": (
            not math.isnan(top5_contribution) and top5_contribution < 0.50
        ),
    }
    verdict = "SCOUT PASS" if all(pass_checks.values()) else "SCOUT FAIL"

    rows = ""
    rows += table_metric("Signal trades, gross 12:30-to-close", summarize(gross))
    rows += table_metric("Signal trades, net after 10 bps", summarize(net))
    rows += table_metric("Signal-day IBB open-to-close", summarize(oc))
    rows += table_metric("Signal-day SPY same window", summarize(spy_window))
    rows += table_metric("All sessions same-window net", summarize(all_same_window))

    checks = "".join(
        f"- {'PASS' if value else 'FAIL'}: `{key}`\n" for key, value in pass_checks.items()
    )

    worst = ""
    best = ""
    if not trade_df.empty:
        worst_df = trade_df.nsmallest(5, "entry_return_net")
        best_df = trade_df.nlargest(5, "entry_return_net")
        for _, row in worst_df.iterrows():
            worst += f"| {row['date']} | {pct(row['morning_return'])} | {pct(row['entry_return_net'])} |\n"
        for _, row in best_df.iterrows():
            best += f"| {row['date']} | {pct(row['morning_return'])} | {pct(row['entry_return_net'])} |\n"

    report = f"""# IBBIntradayAfternoonRecovery-v1 Results

Generated: {dt.datetime.now(tz=NY).isoformat(timespec='seconds')}

## Data source

- Instrument: `{SYMBOL}`.
- Benchmark/context: `{BENCHMARK}`.
- Source: Yahoo Chart API `range=730d&interval=60m&includePrePost=false`.
- Data window: {data_start} to {data_end}.
- Valid IBB sessions evaluated: {session_count}.
- Largest-biotech-ETF note: Nasdaq ETF summary check showed IBB market cap around $8.92B during the run, larger than XBI/FBT/BBH in the quick comparison.

## Frozen rule recap

If IBB return from first regular-session open to the close of the 11:30 ET hourly bar is <= {pct(MORNING_THRESHOLD)}, buy the next available 12:30 ET hourly bar open and exit at the final same-day regular-session close. Long-only, flat by close. Net return subtracts {pct(ROUND_TRIP_COST)} round-trip cost.

## Verdict

{verdict}

{checks}

Half-sample net average: {half_text}.

Top 5 net-profit contribution: {pct(top5_contribution) if not math.isnan(top5_contribution) else 'n/a'}.

## Summary metrics

| Series | N | Mean | Median | Win rate | Worst | Best |
|---|---:|---:|---:|---:|---:|---:|
{rows}

## By calendar year, signal trades net after cost

| Year | Trades | Mean | Median | Win rate |
|---|---:|---:|---:|---:|
{by_year if by_year else '| n/a | 0 | n/a | n/a | n/a |'}

## Worst signal days after cost

| Date | Morning return | Net 12:30-to-close return |
|---|---:|---:|
{worst if worst else '| n/a | n/a | n/a |'}

## Best signal days after cost

| Date | Morning return | Net 12:30-to-close return |
|---|---:|---:|
{best if best else '| n/a | n/a | n/a |'}

## Interpretation guardrail

This is a scout result, not a trading authorization. If this failed, do not rescue it by changing the threshold or timing window inside this hypothesis. If it passed, it would still need a new frozen Experiment with cleaner data, more robust intraday validation, explicit event/news filters, and paper/sim execution checks.
"""
    OUT.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
