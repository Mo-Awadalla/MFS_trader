"""Audit every native quote and all targets at the preselected causal clocks."""

import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

import pandas as pd

from research_scout.audit_perp_shock_20261002 import compare, verify
from research_scout.prepare_market_lag_targets_20261002 import HYPOTHESIS, OUT, PARENT, ROOT, sha


def check(job):
    source, window, events, hypothesis, parent_window = job
    original = verify((source, window))
    quotes = pd.read_parquet(ROOT / window["quotes_path"]).to_dict("records")
    metrics = pd.read_parquet(ROOT / window["signals_path"]).to_dict("records")
    indexed = {(r["decision_ns"], r["symbol"]): r for r in quotes}
    assert sha(ROOT / parent_window["quotes_path"]) == parent_window["quotes_sha256"]
    previous_quotes = {(r["decision_ns"], r["symbol"]): r for r in pd.read_parquet(ROOT / parent_window["quotes_path"]).to_dict("records")}
    assert sha(ROOT / window["targets_path"]) == window["targets_sha256"]
    stored = pd.read_parquet(ROOT / window["targets_path"]).to_dict("records")
    expected, selected, previous = [], [], -1
    maximum = D(0)
    for event in sorted(events, key=lambda e: e["decision_ns"]):
        decision = int(event["decision_ns"])
        for clock in (decision - 10**9, decision):
            for symbol in ("BTCUSDT", "ETHUSDT"):
                old, new = previous_quotes[(clock, symbol)], indexed[(clock, symbol)]
                for field in ("receive_ns", "transaction_ns", "publication_ns", "update_id", "bid", "ask", "bid_quantity", "ask_quantity", "sequence_ok", "transaction_order_ok"):
                    assert old[field] == new[field]
        possibilities = []
        for marginal in metrics:
            if marginal["decision_ns"] != decision or marginal["symbol"] in hypothesis["excluded_symbols"]:
                continue
            symbol = marginal["symbol"]
            row = {"date": source["date"], "offset_minutes": source["offset"], "decision_ns": decision,
                   "symbol": symbol, "direction": event["direction"], "common_move_bps": event["common_move_bps"],
                   "target_supply": False, "reason": "target_endpoint_spread_or_depth", "selected": False}
            first, last = indexed[(decision - 10**9, symbol)], indexed[(decision, symbol)]
            quality = marginal["valid_endpoints"]
            if quality:
                quality = all(4000 * (D(q["ask"]) - D(q["bid"])) <= D(q["ask"]) + D(q["bid"])
                              and D(q["bid"]) * D(q["bid_quantity"]) >= 2000
                              and D(q["ask"]) * D(q["ask_quantity"]) >= 2000 for q in (first, last))
            if quality:
                signed = [(D(last[k]) - D(first[k])) * (10000 * event["direction"]) / D(first[k]) for k in ("bid", "ask")]
                spreads = [(D(q["ask"]) - D(q["bid"])) * 20000 / (D(q["ask"]) + D(q["bid"])) for q in (first, last)]
                gap = D(event["common_move_bps"]) - max(signed)
                budget = gap - sum(spreads, D(14))
                row.update(gap_bps=gap, budget_bps=budget, minimum_signed_target_return_bps=min(signed))
                row["reason"] = "large_opposite_target_move" if min(signed) < -5 else "insufficient_hypothesis_budget" if gap < 20 or budget <= 2 else "requires_native_trade_confirmation"
                row["target_supply"] = row["reason"] == "requires_native_trade_confirmation"
            expected.append(row)
            if row["target_supply"]:
                possibilities.append(row)
        if possibilities and decision - previous >= 30 * 10**9:
            chosen = sorted(possibilities, key=lambda r: (-r["budget_bps"], r["symbol"]))[0]
            chosen["selected"] = True
            selected.append(chosen)
            previous = decision
    assert len(stored) == len(expected) == window["target_rows"]
    for actual, calculated in zip(stored, expected, strict=True):
        maximum = max(maximum, compare(actual, calculated))
    assert len(selected) == len(window["selected_targets"])
    for actual, calculated in zip(window["selected_targets"], selected, strict=True):
        maximum = max(maximum, compare(actual, calculated))
    reasons = dict(Counter(r["reason"] for r in expected))
    assert reasons == window["target_reasons"]
    assert sum(r["target_supply"] for r in expected) == window["raw_target_candidates"]
    return {**original, "target_rows": len(expected), "raw_target_candidates": window["raw_target_candidates"],
            "selected_target_events": len(selected), "target_reasons": reasons,
            "maximum_target_numeric_difference": str(maximum)}


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    impl = json.loads((OUT / "implementation.json").read_text())
    results = json.loads((OUT / "screen_results.json").read_text())
    sources = json.loads((OUT / "source_manifest.json").read_text())
    hypothesis = json.loads((HYPOTHESIS / "specification.json").read_text())
    parent = json.loads((PARENT / "screen_results.json").read_text())
    assert sources["complete"] and sha(OUT / "specification.json") == impl["specification_sha256"]
    assert sha(OUT / "source_manifest.json") == impl["source_manifest_sha256"]
    assert sha(OUT / "implementation.json") == results["implementation_sha256"]
    assert sha(PARENT / "screen_results.json") == spec["native_parent_results_sha256"]
    assert sha(PARENT / "independent_verification.json") == spec["native_parent_audit_sha256"]
    assert sha(HYPOTHESIS / "specification.json") == spec["hypothesis_specification_sha256"]
    assert sha(ROOT / spec["admitted_leader_grids_path"]) == spec["admitted_leader_grids_sha256"]
    events = pd.read_parquet(ROOT / spec["admitted_leader_grids_path"]).to_dict("records")
    for path, digest in impl["code_sha256"].items():
        assert sha(ROOT / path) == digest
    indexed = {(s["date"], s["offset"]): s for s in sources["files"]}
    prior = {(s["date"], s["offset"]): s for s in parent["windows"]}
    jobs = [(indexed[(w["date"], w["offset"])], w,
             [e for e in events if e["date"] == w["date"] and e["offset_minutes"] == w["offset"]],
             hypothesis, prior[(w["date"], w["offset"])]) for w in results["windows"]]
    verified, counts, reasons = [], Counter(), Counter()
    with ProcessPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(check, job) for job in jobs]):
            row = future.result()
            verified.append(row)
            counts.update(row["source_counts"])
            reasons.update(row["target_reasons"])
            print(json.dumps({k: row[k] for k in ("date", "offset", "target_rows", "selected_target_events")}), flush=True)
    assert dict(counts) == results["source_counts"] and dict(reasons) == results["target_reasons"]
    assert sum(r["target_rows"] for r in verified) == results["target_rows"]
    assert sum(r["raw_target_candidates"] for r in verified) == results["raw_target_candidates"]
    assert sum(r["selected_target_events"] for r in verified) == results["selected_target_events"]
    assert sha(OUT / "selected.parquet") == results["selected_sha256"]
    assert pd.read_parquet(OUT / "selected.parquet").to_dict("records") == [r for w in results["windows"] for r in w["selected_targets"]]
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
             "source_files_verified": len(verified), "source_counts": dict(counts),
             "quote_rows_verified": sum(r["quote_rows"] for r in verified),
             "marginal_signal_rows_verified": sum(r["signal_rows"] for r in verified),
             "target_rows_verified": results["target_rows"], "selected_target_events_verified": results["selected_target_events"],
             "maximum_target_numeric_difference": str(max(D(r["maximum_target_numeric_difference"]) for r in verified)),
             "results_sha256": sha(OUT / "screen_results.json"), "auditor_sha256": sha(Path(__file__)),
             "independent_raw_reconstruction_helper_sha256": sha(ROOT / "research_scout/audit_perp_shock_20261002.py"),
             "scope": "Complete independent raw-source clock/quote/marginal-gate reconciliation, both original leader endpoint identities, and every permitted target's exact-price spread/depth/relative-move/cost predicate plus ranking and cooldown. All final signal clocks were prospectively restricted to causal acquisition candidates. No P&L or future-return computation.",
             "economic_implementations": 0, "future_returns_evaluated": False,
             "actual_execution_verified": False, "reliable_edge_established": False}
    with (OUT / "independent_verification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
