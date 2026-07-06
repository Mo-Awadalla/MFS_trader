"""Scout SPY opening-hour correlation with next and final trading hours."""

from __future__ import annotations

import datetime as dt
import math
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

NY = ZoneInfo("America/New_York")
SYMBOL = "SPY"
OUT = Path("docs/research_scout/SPYOpeningHourCorrelation-v1-results.md")


def fetch_chart(symbol: str) -> pd.DataFrame:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {
        "range": "730d",
        "interval": "60m",
        "includePrePost": "false",
        "events": "history",
    }
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()
    result: dict[str, Any] = response.json()["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    frame = pd.DataFrame(quote)
    frame["timestamp"] = pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(NY)
    frame = frame.set_index("timestamp").sort_index()
    frame = frame.dropna(subset=["open", "close"])
    return frame.between_time("09:30", "16:00", inclusive="left")


def get_bar(group: pd.DataFrame, hour: int, minute: int) -> pd.Series | None:
    rows = group[group.index.time == dt.time(hour, minute)]
    if rows.empty:
        return None
    return rows.iloc[0]


def build_session_returns(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for date, group in frame.groupby(frame.index.date):
        first = get_bar(group, 9, 30)
        next_hour = get_bar(group, 10, 30)
        last = get_bar(group, 15, 30)
        if first is None or next_hour is None or last is None:
            continue
        rows.append(
            {
                "date": pd.Timestamp(date),
                "first_hour_return": float(first["close"] / first["open"] - 1.0),
                "next_hour_return": float(next_hour["close"] / next_hour["open"] - 1.0),
                "last_hour_return": float(last["close"] / last["open"] - 1.0),
            }
        )
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def pct(value: float | None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"{value * 100:.3f}%"


def dec(value: float | None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"{value:.4f}"


def corr_stats(data: pd.DataFrame, target: str) -> tuple[float, float]:
    return (
        float(data["first_hour_return"].corr(data[target], method="pearson")),
        float(data["first_hour_return"].corr(data[target], method="spearman")),
    )


def conditional_rows(data: pd.DataFrame) -> str:
    rows = ""
    buckets = {
        "first hour > 0": data[data["first_hour_return"] > 0],
        "first hour <= 0": data[data["first_hour_return"] <= 0],
    }
    for name, bucket in buckets.items():
        for target in ["next_hour_return", "last_hour_return"]:
            rows += (
                f"| {name} | {target} | {len(bucket)} | "
                f"{pct(float(bucket[target].mean()))} | "
                f"{pct(float(bucket[target].median()))} | "
                f"{pct(float((bucket[target] > 0).mean()))} |\n"
            )
    return rows


def quintile_rows(data: pd.DataFrame) -> str:
    qdata = data.copy()
    qdata["first_hour_quintile"] = pd.qcut(
        qdata["first_hour_return"],
        q=5,
        labels=["Q1 lowest", "Q2", "Q3", "Q4", "Q5 highest"],
        duplicates="drop",
    )
    rows = ""
    for label, group in qdata.groupby("first_hour_quintile", observed=False):
        rows += (
            f"| {label} | {len(group)} | "
            f"{pct(float(group['first_hour_return'].mean()))} | "
            f"{pct(float(group['next_hour_return'].mean()))} | "
            f"{pct(float(group['last_hour_return'].mean()))} |\n"
        )
    return rows


def half_stability(data: pd.DataFrame) -> tuple[str, bool]:
    split = len(data) // 2
    halves = [("first chronological half", data.iloc[:split]), ("second chronological half", data.iloc[split:])]
    rows = ""
    spread_positive = True
    for name, half in halves:
        next_p, _ = corr_stats(half, "next_hour_return")
        last_p, _ = corr_stats(half, "last_hour_return")
        pos = half[half["first_hour_return"] > 0]
        neg = half[half["first_hour_return"] <= 0]
        spread = float(pos["last_hour_return"].mean() - neg["last_hour_return"].mean())
        spread_positive = spread_positive and spread > 0
        rows += f"| {name} | {len(half)} | {dec(next_p)} | {dec(last_p)} | {pct(spread)} |\n"
    return rows, spread_positive


def main() -> None:
    frame = fetch_chart(SYMBOL)
    data = build_session_returns(frame)
    next_pearson, next_spearman = corr_stats(data, "next_hour_return")
    last_pearson, last_spearman = corr_stats(data, "last_hour_return")

    positive = data[data["first_hour_return"] > 0]
    negative = data[data["first_hour_return"] <= 0]
    last_positive_mean = float(positive["last_hour_return"].mean())
    last_negative_mean = float(negative["last_hour_return"].mean())
    last_spread = last_positive_mean - last_negative_mean
    half_rows, half_spread_positive = half_stability(data)

    pass_checks = {
        "at_least_400_valid_sessions": len(data) >= 400,
        "primary_pearson_gt_0_05": last_pearson > 0.05,
        "primary_spearman_gt_0_05": last_spearman > 0.05,
        "positive_bucket_last_hour_mean_gt_negative_bucket": last_spread > 0,
        "positive_vs_negative_last_hour_spread_positive_in_both_halves": half_spread_positive,
    }
    verdict = "SCOUT PASS" if all(pass_checks.values()) else "SCOUT FAIL"
    checks = "".join(
        f"- {'PASS' if value else 'FAIL'}: `{key}`\n" for key, value in pass_checks.items()
    )

    report = f"""# SPYOpeningHourCorrelation-v1 Results

Generated: {dt.datetime.now(tz=NY).isoformat(timespec='seconds')}

## Data source

- Instrument: `{SYMBOL}`.
- Source: Yahoo Chart API `range=730d&interval=60m&includePrePost=false`.
- Data window: {frame.index.min()} to {frame.index.max()}.
- Valid sessions evaluated: {len(data)}.

## Verdict

{verdict}

{checks}

## Primary/secondary correlations

| Relationship | Pearson | Spearman |
|---|---:|---:|
| First hour vs next hour | {dec(next_pearson)} | {dec(next_spearman)} |
| First hour vs last hour | {dec(last_pearson)} | {dec(last_spearman)} |

## Positive vs negative first hour

| Bucket | Target | N | Mean | Median | Win rate |
|---|---|---:|---:|---:|---:|
{conditional_rows(data)}

Last-hour positive-minus-negative mean spread: {pct(last_spread)}.

## First-hour return quintiles

| First-hour quintile | N | Mean first hour | Mean next hour | Mean last hour |
|---|---:|---:|---:|---:|
{quintile_rows(data)}

## Chronological stability

| Half | N | First-vs-next Pearson | First-vs-last Pearson | Last-hour positive-minus-negative spread |
|---|---:|---:|---:|---:|
{half_rows}

## Interpretation guardrail

This is a descriptive scout only. It does not include trading costs, entry/exit mechanics, WFA, DSR, Monte Carlo, or paper execution checks. If this fails, do not rescue it by changing windows or thresholds inside this hypothesis. If it passes, the next step would be a separate frozen trading-rule Experiment.
"""
    OUT.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
