"""Independent native DEEP source, venue-clock book and conditional cash verification."""

import gzip
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from research_scout.audit_iex_deep_20261002 import native, sha
from research_scout.audit_iex_spread_probe_20261002 import verify_case

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/iex_deep_hft_20261002/price_probe_v1"


def read_records(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def venue_quotes(rows):
    updates = sorted([r for r in rows if r["type"] in ("8", "5")],
                     key=lambda r: (r["event_ns"], r["sequence"]))
    sides, quotes, pending = {"8": {}, "5": {}}, [], None
    for update in updates:
        assert pending is None or pending == update["event_ns"]
        pending = update["event_ns"]
        prices = sides[update["type"]]
        p, q = update["price"], update["size"]
        assert p > 0 and q >= 0
        if q == 0:
            assert p in prices
            del prices[p]
        else:
            prices[p] = q
        if update["flags"] == 0:
            continue
        assert update["flags"] == 1
        pending = None
        bid, ask = max(sides["8"], default=0), min(sides["5"], default=0)
        state = {"type": "Q", "flags": 0, "symbol": update["symbol"],
                 "bid_price": bid, "ask_price": ask,
                 "bid_size": sides["8"].get(bid, 0), "ask_size": sides["5"].get(ask, 0),
                 "event_ns": update["event_ns"], "capture_ns": update["capture_ns"],
                 "send_ns": update["send_ns"], "sequence": update["sequence"],
                 "native_final_update": update,
                 "derived_from": "DEEP displayed levels after atomic completion",
                 "bid_levels": [list(r) for r in sorted(sides["8"].items(), reverse=True)],
                 "ask_levels": [list(r) for r in sorted(sides["5"].items())]}
        if quotes and quotes[-1]["event_ns"] == state["event_ns"]:
            quotes.pop()
        quotes.append(state)
    assert pending is None
    return [r for r in rows if r["type"] not in ("8", "5")] + quotes


def one_day(day, expected_hash):
    path = OUT / "sessions" / (day + ".json")
    assert sha(path) == expected_hash
    result = json.loads(path.read_text())
    source = Path(result["prefix_path"])
    assert sha(source) == result["prefix_sha256"]
    assert result["coverage"]["covered"]
    symbol = result["event"]["symbol"]
    selected, messages = [], 0
    for row in native(source, result["coverage"]["endpoint_ns"]):
        messages += 1
        if row.get("symbol") == symbol:
            selected.append(row)
    assert messages == result["source_messages_checked"]
    assert len(selected) == result["native_symbol_messages"]
    original, derived = Path(result["native_path"]), Path(result["venue_path"])
    assert sha(original) == result["native_sha256"] and sha(derived) == result["venue_sha256"]
    assert selected == read_records(original)
    tape = venue_quotes(selected)
    assert tape == read_records(derived)
    assert sum(r["type"] == "Q" for r in tape) == result["derived_quote_count"]
    specification = json.loads((OUT / "specification.json").read_text())
    cases = {r["name"]: r for r in specification["cases"]}
    for row in result["outcomes"]:
        verify_case(result["event"], tape, row, cases[row["case"]])
    return {"date": day, "source_messages": messages, "selected_symbol_messages": len(selected),
            "derived_quotes": result["derived_quote_count"], "event_cases": len(result["outcomes"]),
            "session_sha256": expected_hash}


def aggregate_check(actual, rows):
    chosen = [r for r in rows if (r["case"], r["fill_model"]) == (actual["case"], actual["fill_model"])]
    known = [r for r in chosen if r["net_usd"] is not None]
    values = sorted([Decimal(r["net_usd"]) for r in known], reverse=True)
    net, drop = sum(values, Decimal(0)), sum(values[3:], Decimal(0))
    assert actual["events"] == len(chosen) and actual["known_events"] == len(known)
    assert actual["unknown_events"] == len(chosen) - len(known)
    assert actual["outcomes"] == dict(Counter(r["outcome"] for r in chosen))
    assert actual["conditionally_priced_entries"] == sum(r["outcome"] == "conditional_priced" for r in known)
    assert actual["positive_events"] == sum(v > 0 for v in values)
    assert actual["negative_events"] == sum(v < 0 for v in values)
    assert Decimal(actual["known_component_usd"]) == net
    assert Decimal(actual["drop_best_three_known_component_usd"]) == drop
    assert actual["maximum_known_event_usd"] == (str(values[0]) if values else None)
    assert actual["maximum_exposure_ns"] == max((r.get("exposure_ns", 0) for r in known), default=0)
    if len(known) == len(chosen):
        assert Decimal(actual["full_conditional_net_usd"]) == net
        assert Decimal(actual["drop_best_three_full_conditional_net_usd"]) == drop
    else:
        assert actual["full_conditional_net_usd"] is actual["drop_best_three_full_conditional_net_usd"] is None


def main():
    result_path = OUT / "results.json"
    results = json.loads(result_path.read_text())
    spec = json.loads((OUT / "specification.json").read_text())
    assert not results["errors"] and results["sessions_completed"] == results["selected_events"]
    verified = []
    with ProcessPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(one_day, day, h): day for day, h in results["session_hashes"].items()}
        for job in as_completed(jobs):
            row = job.result()
            verified.append(row)
            print(json.dumps(row), flush=True)
    event_rows, calendar_rows = [], []
    selected_dates = {e["date"] for e in spec["selected_events"]}
    for day in spec["dates"]:
        if day in selected_dates:
            path = OUT / "sessions" / (day + ".json")
            rows = json.loads(path.read_text())["outcomes"]
            calendar_rows.extend(rows)
            event_rows.extend(rows)
        else:
            unknown = day in spec["unknown_admission_dates"]
            for model in spec["fill_models"]:
                for case in spec["cases"]:
                    calendar_rows.append({"date": day, "symbol": None, "case": case["name"], "fill_model": model,
                                          "outcome": "unknown_source_before_signal" if unknown else "conditional_no_selected_signal",
                                          "net_usd": None if unknown else "0", "actual_execution_verified": False})
    assert calendar_rows == results["calendar_case_rows"]
    assert len(calendar_rows) == len(spec["dates"]) * len(spec["cases"]) * len(spec["fill_models"])
    for row in results["scenario_results"]:
        aggregate_check(row, calendar_rows)
    for row in results["observed_selected_cohort_results"]:
        aggregate_check(row, event_rows)
    output = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
              "dates_verified": len(verified),
              **{key + "_verified": sum(r[key] for r in verified) for key in (
                  "source_messages", "selected_symbol_messages", "derived_quotes", "event_cases")},
              "calendar_case_rows_verified": len(calendar_rows), "aggregate_checks": 20,
              "unknown_admission_dates": spec["unknown_admission_dates"],
              "results_sha256": sha(result_path), "auditor_sha256": sha(Path(__file__)),
              "independent_decoder_sha256": sha(ROOT / "research_scout/audit_iex_deep_20261002.py"),
              "independent_policy_auditor_sha256": sha(ROOT / "research_scout/audit_iex_spread_probe_20261002.py"),
              "sessions": sorted(verified, key=lambda r: r["date"]),
              "actual_execution_verified": False, "reliable_edge_established": False,
              "scope": "Independent raw DEEP, native-event-time atomic displayed books, conditional allocations/cash and calendar unknown propagation. No queue, hidden-liquidity, acceptance or actual execution proof; inherited probe ignores future depth."}
    (OUT / "independent_verification.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({k: v for k, v in output.items() if k != "sessions"}), flush=True)


if __name__ == "__main__":
    main()
