"""Document eligibility mismatches and a fixed one-minute execution stress.

This is a diagnostic supplement on exposed history, not new confirmation.
"""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import exchange_calendars as xc
import pandas as pd

from research.intraday_contract import Leg, benchmark_returns, evaluate

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/research_reset_20260907"
CASES = ("V83", "V56", "V76", "V45")


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    spec_path = OUT / "diagnostic_supplement_specification.json"
    if not spec_path.exists():
        spec = {
            "created_utc": datetime.now(UTC).isoformat(),
            "status": "Post-replay diagnostic, fixed before reading the additional outcomes",
            "entry_delay": "Exactly one minute later, unchanged symbol, sizing and exit. No delay search.",
            "eligibility": "Reconcile V56 feasibility signal-date exclusions with the economic ledger. Report an audit-aligned scenario separately; preserve both original artifacts.",
            "other_cases": "V49 remains gated without P&L. V94 lacks minute execution quotes and is not assigned a fabricated one-minute fill.",
            "input_hashes": {
                case: hashlib.sha256((OUT / f"{case}_evaluation.json").read_bytes()).hexdigest()
                for case in CASES
            },
        }
        with spec_path.open("x", encoding="utf-8") as handle:
            json.dump(spec, handle, indent=2)
    cal = xc.get_calendar("XNYS", start="2020-01-01", end="2023-12-31")
    calendar_days = cal.sessions.strftime("%Y-%m-%d").tolist()
    previous = dict(zip(calendar_days[1:], calendar_days, strict=False))
    days = [d for d in calendar_days if "2021-01-04" <= d <= "2023-12-29"]
    prices = pd.read_parquet(ROOT / "data/parquet/equity/yahoo_chart/SPY_1d.parquet")
    prices.index = (
        pd.to_datetime(prices.timestamp, utc=True)
        .dt.tz_convert("America/New_York")
        .dt.strftime("%Y-%m-%d")
    )
    benchmark = benchmark_returns(prices, days, basis="legacy_adjusted_proxy")
    base56 = read("V56_evaluation.json")
    excluded = set(base56["original_excluded_dates_in_calendar"])
    legs56 = [Leg(**row) for row in read("V56_legs.json")]
    mismatch = [
        {"trade_day": leg.day, "signal_day": previous[leg.day]}
        for leg in legs56
        if previous[leg.day] in excluded or previous[leg.day] < "2021-01-01"
    ]
    assert len(mismatch) == 5
    removed = {row["trade_day"] for row in mismatch}
    aligned = [leg for leg in legs56 if leg.day not in removed]
    decisions = dict.fromkeys(days, "cash")
    decisions.update({leg.day: "trade" for leg in aligned})
    evaluated = evaluate(aligned, decisions, benchmark)
    assert evaluated["legs"] == 377
    save("V56_audit_aligned_evaluation.json", evaluated)
    reconciliation = {
        "V56": {
            "cause": "Feasibility excludes degraded ARCA signal dates as well as execution dates; the economic path excludes execution dates only, although its actual signals use Yahoo daily prices.",
            "extra_economic_trades": mismatch,
            "original_economic_trades": 382,
            "audit_aligned_trades": 377,
            "audit_aligned_ending_cash": evaluated["ending_cash"],
            "audit_aligned_preliminary_pass": evaluated["preliminary_economic_pass"],
            "interpretation": "Protocol mismatch, not established bad Yahoo signal values. Neither eligibility policy establishes SPY outperformance.",
        },
        "V45": {
            "event_trades": 378,
            "distinct_trade_days": 306,
            "correction": "Original sessions field counts event trades, including sequential trades on one date.",
        },
        "V76": {
            "missing_day": "2021-11-26",
            "exchange_close": cal.session_close("2021-11-26")
            .tz_convert("America/New_York")
            .isoformat(),
            "original_exit": "15:55:00 America/New_York",
            "interpretation": "Original exit falls after the 13:00 regular-session close and no qualifying exit was retained. An early-close policy must be declared; do not insert zero return or invent a 12:55 fill after seeing outcomes.",
        },
    }
    save("protocol_reconciliation.json", reconciliation)
    from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay
    from research_scout import test_upro_spxu_creative_hypotheses as source

    print("Loading existing minute quotes for the fixed entry-delay stress", flush=True)
    sessions = relay.sessions(relay.ARCA_PATH)
    summary = {}
    for case in CASES:
        old = read(f"{case}_evaluation.json")
        decisions = dict.fromkeys(days, "cash")
        decisions.update(dict.fromkeys(old["missing_dates"], "missing"))
        delayed = []
        for row in read(f"{case}_legs.json"):
            leg = Leg(**row)
            target = pd.Timestamp(leg.entry_time) + pd.Timedelta(minutes=1)
            frame = sessions[pd.Timestamp(leg.day)][leg.symbol]
            quote = source.quote_at(frame, target)
            if not source.valid_quote(quote):
                decisions[leg.day] = "missing"
                continue
            delayed.append(
                replace(
                    leg,
                    entry_time=target.isoformat(),
                    entry_bid=float(quote.bid_px_00),
                    entry_ask=float(quote.ask_px_00),
                )
            )
            if decisions[leg.day] != "missing":
                decisions[leg.day] = "trade"
        delayed = [leg for leg in delayed if decisions[leg.day] != "missing"]
        evaluation = evaluate(delayed, decisions, benchmark)
        evaluation["stress"] = (
            "One-minute entry delay; original exit and direction; common base costs"
        )
        save(f"{case}_one_minute_delay_evaluation.json", evaluation)
        summary[case] = {
            key: value
            for key, value in evaluation.items()
            if key not in {"daily_returns", "accounting"}
        }
        print(case, evaluation["ending_cash"], evaluation["missing_dates"], flush=True)
    save("latency_stress_summary.json", summary)
    spec = read("diagnostic_supplement_specification.json")
    assert all(
        hashlib.sha256((OUT / f"{case}_evaluation.json").read_bytes()).hexdigest() == digest
        for case, digest in spec["input_hashes"].items()
    )


if __name__ == "__main__":
    main()
