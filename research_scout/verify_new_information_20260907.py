"""Independent source and share/cash audit of frozen new-test executions."""

import hashlib
import json
from collections import defaultdict
from decimal import Decimal, getcontext
from pathlib import Path

import exchange_calendars as xc
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/new_information_tests_20260907"


def audit_accounting(name):
    getcontext().prec = 40
    result = json.loads((OUT / f"{name}_evaluation.json").read_text())
    baskets = defaultdict(list)
    for leg in result["accounting"]:
        baskets[leg["day"]].append(leg)
    symbols = {r["symbol"] for r in result["accounting"]}
    prices = {}
    for symbol in symbols:
        frame = pd.read_parquet(
            ROOT / f"data/parquet/equity/alpaca_sip/{symbol}_1d.parquet",
            filters=[("timestamp", "<", pd.Timestamp("2024-01-01", tz="UTC"))],
        )
        frame.index = (
            pd.to_datetime(frame.timestamp, utc=True)
            .dt.tz_convert("America/New_York")
            .dt.strftime("%Y-%m-%d")
        )
        prices[symbol] = frame
    ending = {}
    for label, cost in [("reference", Decimal(0)), ("net", Decimal("0.0005"))]:
        cash = Decimal(100)
        for day, basket in sorted(baskets.items()):
            start = cash
            cash = Decimal(0)
            for leg in basket:
                row = prices[leg["symbol"]].loc[day]
                assert float(row.open) == leg["entry_ask"] == leg["entry_bid"]
                assert float(row.close) == leg["exit_bid"] == leg["exit_ask"]
                assert abs(leg["weight"] - 1 / len(basket)) < 1e-12
                assert (
                    pd.Timestamp(leg["signal_available"])
                    < pd.Timestamp(leg["entry_time"])
                    < pd.Timestamp(leg["exit_time"])
                )
                assert (
                    pd.Timestamp(leg["entry_time"])
                    .tz_convert("America/New_York")
                    .strftime("%Y-%m-%d %H:%M")
                    == day + " 09:30"
                )
                assert (
                    pd.Timestamp(leg["exit_time"])
                    .tz_convert("America/New_York")
                    .strftime("%Y-%m-%d %H:%M")
                    == day + " 16:00"
                )
                allocation = start / Decimal(len(basket))
                shares = allocation / (Decimal(str(row.open)) * (1 + cost))
                cash += shares * Decimal(str(row.close)) * (1 - cost)
        observed = result["available_case_metrics"][label]["ending_cash"]
        assert abs(float(cash) - observed) < 1e-9
        ending[label] = {
            "independent_decimal_cash": str(cash),
            "absolute_error": abs(float(cash) - observed),
        }
    return {
        "accounting_legs_checked": len(result["accounting"]),
        "trade_days_checked": len(baskets),
        "ending": ending,
    }


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    assert all(
        hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == expected
        for p, expected in spec["source_hashes"].items()
    )
    signals = json.loads((OUT / "V96_signals.json").read_text())
    records = {}
    for path in (ROOT / "data/parquet/sec_filings/raw").glob("CIK*.json"):
        blob = json.loads(path.read_text(encoding="utf-8"))
        columns = blob.get("filings", {}).get("recent", blob)
        for i, accession in enumerate(columns.get("accessionNumber", [])):
            if columns["form"][i] in {"10-Q", "10-K"}:
                records[accession] = {
                    k: columns[k][i] for k in ["form", "reportDate", "acceptanceDateTime"]
                }
    schedule = xc.get_calendar("XNYS", start="2020-12-01", end="2023-12-31").schedule
    schedule = schedule[schedule.close.dt.tz_convert("America/New_York").dt.hour == 16]
    for event in signals["events"]:
        row, prior = records[event["accession"]], records[event["prior_accession"]]
        current, previous = (
            pd.Timestamp(row["acceptanceDateTime"]),
            pd.Timestamp(prior["acceptanceDateTime"]),
        )
        assert current == pd.Timestamp(event["acceptance"]) and previous == pd.Timestamp(
            event["prior_acceptance"]
        )
        assert row["form"] == prior["form"] == event["form"] and previous < current
        assert (
            350 <= (pd.Timestamp(row["reportDate"]) - pd.Timestamp(prior["reportDate"])).days <= 380
        )
        lag = (
            pd.Timestamp(current.tz_convert("America/New_York").date())
            - pd.Timestamp(row["reportDate"])
        ).days
        prior_lag = (
            pd.Timestamp(previous.tz_convert("America/New_York").date())
            - pd.Timestamp(prior["reportDate"])
        ).days
        assert lag == event["reporting_lag_days"] and prior_lag == event["prior_reporting_lag_days"]
        assert event["selected"] == (prior_lag - lag >= 5)
        first = (
            schedule[schedule.open > current + pd.Timedelta(minutes=30)]
            .index[0]
            .strftime("%Y-%m-%d")
        )
        assert first == event["trade_day"]
    assert signals["selected"] == [r for r in signals["events"] if r["selected"]]
    audit = {
        "V96": {
            **audit_accounting("V96"),
            "raw_filing_comparisons_checked": len(signals["events"]),
        },
        "original_source_hashes_unchanged": True,
        "later_prices_read": False,
    }
    if (OUT / "V97_evaluation.json").exists():
        audit["V97"] = audit_accounting("V97")
    (OUT / "independent_verification.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
