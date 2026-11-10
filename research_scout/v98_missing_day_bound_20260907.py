"""Conservative rejection bound; never impute missing prices or actual returns."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from decimal import Decimal, localcontext

import numpy as np
import pandas as pd

from research.intraday_contract import Leg
from research_scout.v98_backtest_20260907 import independent_cash
from research_scout.v98_earnings_answers_20260907 import NY, OUT, ROOT, read, save, sha


def optimistic_day_factor(extrema):
    """A funded long basket is a convex combination of cash/stock factors."""
    if not extrema:
        raise ValueError("No eligible price bounds")
    values = []
    for row in extrema:
        low, high = float(row["low"]), float(row["high"])
        if not np.isfinite([low, high]).all() or not 0 < low <= high:
            raise ValueError("Invalid price extrema")
        values.append(high / low)
    return max(1.0, *values)


def prepare():
    protocol = read("missing_day_bound_protocol.json")
    bars = pd.read_parquet(OUT / "event_bars.parquet")
    bars["day"] = bars.timestamp.dt.tz_convert(NY).dt.strftime("%Y-%m-%d")
    bound_rows = {}
    for day, symbols in protocol["possible_gap_day_universes"].items():
        rows = []
        for symbol in symbols:
            source = protocol["daily_source_files"][symbol]
            path = ROOT / source["path"]
            if not source["exists"] or sha(path.read_bytes()) != source["sha256"]:
                raise ValueError("Missing or changed daily bound source")
            opening = pd.Timestamp(day, tz=NY).tz_convert("UTC")
            closing = (pd.Timestamp(day, tz=NY) + pd.DateOffset(days=1)).tz_convert("UTC")
            daily = pd.read_parquet(
                path, filters=[("timestamp", ">=", opening), ("timestamp", "<", closing)]
            )
            if len(daily) != 1:
                raise ValueError(f"Daily bound not unique: {symbol} {day}")
            r = daily.iloc[0]
            if not r.low <= min(r.open, r.close) <= max(r.open, r.close) <= r.high:
                raise ValueError("Invalid daily OHLC ordering")
            part = bars.loc[(bars.symbol == symbol) & (bars.day == day)]
            if not len(part):
                raise ValueError("Cannot cross-check any intraday records")
            # Uniform split/dividend scaling cancels in both ratios. This is a
            # necessary range-consistency check, not proof of daily-feed accuracy.
            intraday_range = float(part.high.max() / part.low.min())
            daily_range = float(r.high / r.low)
            if intraday_range > daily_range * (1 + 1e-5):
                raise ValueError(f"Daily range contradicts observed intraday range: {symbol} {day}")
            rows.append(
                {
                    "symbol": symbol,
                    "low": float(r.low),
                    "high": float(r.high),
                    "range_factor": daily_range,
                    "observed_intraday_range_factor": intraday_range,
                    "observed_intraday_bars": len(part),
                    "daily_source": source["path"],
                    "daily_source_sha256": source["sha256"],
                }
            )
        bound_rows[day] = {"stocks": rows, "optimistic_factor": optimistic_day_factor(rows)}
    save(
        "missing_day_bound_inputs.json",
        {
            "prepared_utc": datetime.now(UTC).isoformat(),
            "days": bound_rows,
            "qualification": "Daily high/low ratios checked against the observed intraday range. Shared-provider daily caches are not independently certified; the bound is conditional on their extrema covering the missing fills.",
        },
    )
    print(f"Prepared upper-bound inputs for {len(bound_rows)} possible missing dates", flush=True)


def finish():
    inputs = read("missing_day_bound_inputs.json")
    protocol = read("missing_day_bound_protocol.json")
    reports = {}
    for name in ["primary", "baseline", "all_events"]:
        result = read(f"{name}_evaluation.json")
        legs = [Leg(**row) for row in read(f"{name}_legs.json")]
        known_decisions = {
            d: state for d, state in result["decisions"].items() if state != "missing"
        }
        reconciled = {}
        for label, bps in [("reference", 0), ("net", 5), ("cost_stress", 10)]:
            value = independent_cash(legs, known_decisions, bps)
            expected = result["available_case_metrics"][label]["ending_cash"]
            difference = abs(value - expected)
            if difference > 1e-8:
                raise ValueError("Known-day independent cash reconciliation failed")
            reconciled[label] = {
                "known_day_product_value": value,
                "absolute_difference": difference,
                "not_full_calendar_actual_equity": True,
            }
        missing_days = result["missing_dates"]
        if not set(missing_days) <= set(inputs["days"]):
            raise ValueError("Unexpected missing day outside prior bound protocol")
        with localcontext() as ctx:
            ctx.prec = 40
            multiplier = Decimal(1)
            for day in missing_days:
                factors = [
                    Decimal(str(r["high"])) / Decimal(str(r["low"]))
                    for r in inputs["days"][day]["stocks"]
                ]
                multiplier *= max(Decimal(1), *factors)
            bounds = {
                label: float(Decimal(str(r["known_day_product_value"])) * multiplier)
                for label, r in reconciled.items()
            }
        spy = result["SPY"]["ending_cash"]
        reports[name] = {
            "missing_dates": missing_days,
            "known_calendar_sessions": result["known_sessions"],
            "unknown_day_factors": {
                d: inputs["days"][d]["optimistic_factor"] for d in missing_days
            },
            "unknown_day_multiplier": float(multiplier),
            "independent_known_day_reconciliation": reconciled,
            "optimistic_full_calendar_upper_bounds": bounds,
            "SPY_ending_cash": spy,
            "net_known_day_upper_bound_below_SPY": bounds["net"] < spy,
            "all_frictionless_upper_bound_below_SPY": bounds["reference"] < spy,
            "actual_full_calendar_ending_equity": result["ending_cash"],
            "actual_full_calendar_equity_complete": result["complete_equity"],
        }
    if not all(
        sha((ROOT / r["path"]).read_bytes()) == r["sha256"]
        for r in protocol["daily_source_files"].values()
    ):
        raise ValueError("Daily bound source mutated")
    failed = reports["primary"]["net_known_day_upper_bound_below_SPY"]
    final = {
        "experiment": "V98",
        "completed_utc": datetime.now(UTC).isoformat(),
        "status": "aborted_conditional_upper_bound_failure"
        if failed
        else "inconclusive_missing_prices",
        "primary_accounting_status": read("verdict.json")["status"],
        "economic_interpretation": "Even perfect, costless trading within the cached daily ranges on every unknown day cannot make the fixed available-data run beat SPY."
        if failed
        else "Available inputs do not establish the full-calendar outcome; this is not a pass.",
        "limits": protocol["bound_scope"],
        "bounds_are_not_actual_returns": True,
        "historical_text_vintage_and_survivor_universe_unresolved": True,
        "edge_validated": False,
        "further_parameter_or_2024_plus_tests_run": False,
        "portfolios": reports,
    }
    save("bounded_economic_verdict.json", final)
    print(final["status"], flush=True)
    for name, report in reports.items():
        print(
            name,
            {
                "known_day_net_product": report["independent_known_day_reconciliation"]["net"][
                    "known_day_product_value"
                ],
                "net_upper_bound": report["optimistic_full_calendar_upper_bounds"]["net"],
                "frictionless_upper_bound": report["optimistic_full_calendar_upper_bounds"][
                    "reference"
                ],
                "SPY": report["SPY_ending_cash"],
                "missing_days": len(report["missing_dates"]),
            },
            flush=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["prepare", "finish"])
    args = parser.parse_args()
    {"prepare": prepare, "finish": finish}[args.stage]()
