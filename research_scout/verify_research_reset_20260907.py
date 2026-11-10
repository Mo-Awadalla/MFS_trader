"""Independent Decimal share/cash reconstruction of the shared-contract exports.

Does not import the evaluator or use its per-leg return calculations.
"""

import hashlib
import json
from collections import defaultdict
from decimal import Decimal, getcontext
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/research_reset_20260907"
getcontext().prec = 40


def dec(value):
    return Decimal(str(value))


def main():
    checked = {}
    for path in sorted(OUT.glob("*_evaluation.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload["accounting"]
        baskets = defaultdict(list)
        missing = set(payload["missing_dates"])
        for row in rows:
            assert row["day"] not in missing
            times = [pd.Timestamp(row[k]) for k in ("signal_available", "entry_time", "exit_time")]
            assert times[0] < times[1] < times[2]
            assert all(
                t.tz_convert("America/New_York").strftime("%Y-%m-%d") == row["day"]
                for t in times[1:]
            )
            baskets[(row["day"], row["entry_time"], row["exit_time"])].append(row)
        assert len(rows) == payload["legs"]
        assert len({r["day"] for r in rows}) == payload["trade_days"]
        assert payload["known_sessions"] + len(missing) == payload["calendar_sessions"]
        if missing:
            assert (
                payload["ending_cash"] is None and payload["excess_mean_daily_95_interval"] is None
            )
            assert not payload["preliminary_economic_pass"]
        differences = {}
        for mode in ("reference", "crossed", "net", "cost_stress"):
            reported = payload["available_case_metrics"][mode]
            if reported is None:
                continue
            cash = Decimal(100)
            for _, basket in sorted(baskets.items()):
                allocation = sum(dec(r["weight"]) for r in basket)
                assert allocation <= Decimal("1.000000000001")
                released = cash * (1 - allocation)
                for row in basket:
                    if mode == "reference":
                        buy = (dec(row["entry_bid"]) + dec(row["entry_ask"])) / 2
                        sell = (dec(row["exit_bid"]) + dec(row["exit_ask"])) / 2
                    else:
                        buy, sell = dec(row["entry_ask"]), dec(row["exit_bid"])
                    fee_rate = fee_per_share = Decimal(0)
                    if mode in {"net", "cost_stress"}:
                        costs = payload["costs"]
                        slippage = dec(costs["extra_bps_each_side"]) / 10000
                        if mode == "cost_stress":
                            slippage *= 2
                        buy *= 1 + slippage
                        sell *= 1 - slippage
                        fee_rate = dec(costs["sell_notional_rate"])
                        fee_per_share = dec(costs["sell_per_share"])
                    shares = cash * dec(row["weight"]) / buy
                    released += shares * (sell * (1 - fee_rate) - fee_per_share)
                cash = released
            difference = abs(float(cash) - reported["ending_cash"])
            assert difference < 1e-8, (path.name, mode, difference)
            differences[mode] = difference
        checked[path.stem] = {
            "legs": len(rows),
            "trade_days": payload["trade_days"],
            "missing_days": len(missing),
            "max_cash_difference": max(differences.values()),
        }
    original = json.loads((OUT / "specification.json").read_text(encoding="utf-8"))
    hashes_match = all(
        hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
        for path, digest in original["source_hashes"].items()
    )
    assert hashes_match
    reproduction = json.loads((OUT / "reproduction.json").read_text(encoding="utf-8"))
    assert reproduction["V83"]["max_daily_net_difference"] < 1e-12
    for case in ("V56", "V76", "V45"):
        row = reproduction[case]
        assert (
            abs(row["original_observed_quote_cash"] - row["new_crossed_available_case_cash"]) < 1e-8
        )
    payload = {
        "passed": True,
        "method": "Decimal fractional-share purchases, sale proceeds and residual cash; sequential capital release; no evaluator imports",
        "evaluations": checked,
        "all_selected_original_hashes_unchanged": hashes_match,
        "limitation": "Reconciles exported prices and accounting. It does not independently establish quote freshness, fill capacity or alpha.",
    }
    (OUT / "verification.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
