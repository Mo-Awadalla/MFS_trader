"""Independent exact-price reconciliation of acquisition clues, not trading signals."""

import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal as D
from numbers import Integral
from pathlib import Path

import pandas as pd

from research_scout.prepare_market_lag_maintained_20261002 import HYPOTHESIS, OUT, ROOT, sha


def compare(actual, expected):
    for key, value in expected.items():
        if isinstance(value, str) and (key.endswith("bps") or key == "minimum_touch_usdt"):
            assert abs(D(actual[key]) - D(value)) < D("1e-18"), (key, actual[key], value)
        else:
            assert actual[key] == value, (key, actual[key], value)
    for key in actual.keys() - expected.keys():
        assert pd.isna(actual[key]), (key, actual[key])


def independent(anchor, current, leader, decision):
    out = {"acquisition_candidate": False, "trade_eligible": False, "depth_confirmed": False}
    for name, row, at in (("anchor", anchor, decision - 1_250_000_000), ("current", current, decision - 250_000_000)):
        error = None
        if row is None or row.get("sequence_ok") is not True or row.get("transaction_order_ok") is not True:
            error = "missing_or_untrusted_quote"
        elif not isinstance(row.get("epoch"), Integral):
            error = "missing_epoch"
        elif not all(isinstance(row.get(k), Integral) for k in ("receive_ns", "transaction_ns", "publication_ns", "update_id")):
            error = "missing_native_identity"
        else:
            values = [D(row[k]) for k in ("bid", "ask", "bid_quantity", "ask_quantity")]
            c, t, e = (int(row[k]) for k in ("receive_ns", "transaction_ns", "publication_ns"))
            if not all(v.is_finite() and v > 0 for v in values) or values[0] >= values[1]:
                error = "invalid_quote"
            elif any(at - x <= 0 or at - x > 5_000_000_000 for x in (c, t, e)):
                error = "outside_acquisition_age"
            elif t > c + 1_000_000 or e > c + 1_000_000 or t > e + 1_000_000:
                error = "inconsistent_native_clocks"
        if error:
            return {**out, "reason": name + "_" + error}
    if anchor["epoch"] != current["epoch"]:
        return {**out, "reason": "disconnected_endpoints"}
    b0, a0, b1, a1 = [D(q[k]) for q in (anchor, current) for k in ("bid", "ask")]
    # Independent cross-product returns avoid the production division/subtraction order.
    bid_return, ask_return = (b1 - b0) * 10000 / b0, (a1 - a0) * 10000 / a0
    spread0, spread1 = (a0 - b0) * 20000 / (a0 + b0), (a1 - b1) * 20000 / (a1 + b1)
    depth = min(D(q[k]) * D(q[k + "_quantity"]) for q in (anchor, current) for k in ("bid", "ask"))
    out.update(bid_return_bps=str(bid_return), ask_return_bps=str(ask_return),
               anchor_spread_bps=str(spread0), current_spread_bps=str(spread1), minimum_touch_usdt=str(depth))
    ages = {name + "_" + field + "_age_ns": cutoff - int(q[field])
            for name, q, cutoff in (("anchor", anchor, decision - 1_250_000_000), ("current", current, decision - 250_000_000))
            for field in ("receive_ns", "transaction_ns", "publication_ns")}
    out.update(**ages, original_freshness_passed=all(a <= 250_000_000 for a in ages.values()))
    if max(spread0, spread1) > 5 or depth < 2000:
        return {**out, "reason": "target_endpoint_spread_or_depth"}
    signed = [int(leader["direction"]) * r for r in (bid_return, ask_return)]
    gap = D(leader["common_move_bps"]) - max(signed)
    budget = gap - D(14) - spread0 - spread1
    out.update(gap_bps=str(gap), budget_bps=str(budget), minimum_signed_target_return_bps=str(min(signed)))
    if min(signed) < -5:
        return {**out, "reason": "large_opposite_target_move"}
    if gap < 20 or budget <= 2:
        return {**out, "reason": "insufficient_hypothesis_budget"}
    return {**out, "acquisition_candidate": True, "reason": "requires_sequenced_depth_proof"}


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    result = json.loads((OUT / "screen_results.json").read_text())
    impl = json.loads((OUT / "implementation.json").read_text())
    assert sha(OUT / "specification.json") == impl["specification_sha256"]
    assert sha(OUT / "implementation.json") == result["implementation_sha256"]
    for p, digest in impl["code_sha256"].items():
        assert sha(ROOT / p) == digest
    assert sha(HYPOTHESIS / "specification.json") == spec["parent_hypothesis_sha256"]
    excluded = json.loads((HYPOTHESIS / "specification.json").read_text())["excluded_symbols"]
    assert sha(OUT / "clues.parquet") == result["clues_sha256"]
    assert sha(OUT / "acquisition_candidates.parquet") == result["candidates_sha256"]
    rows = pd.read_parquet(OUT / "clues.parquet").to_dict("records")
    actual = {(r["decision_ns"], r["symbol"]): r for r in rows}
    expected_rows, source_count = [], 0
    for parent in spec["parents"]:
        native, target = ROOT / parent["native_path"], ROOT / parent["target_path"]
        assert sha(native / "independent_verification.json") == parent["native_audit_sha256"]
        assert sha(native / "admitted_leader_grids.parquet") == parent["events_sha256"]
        assert sha(target / "independent_verification.json") == parent["target_audit_sha256"]
        assert sha(target / "screen_results.json") == parent["target_results_sha256"]
        events = pd.read_parquet(native / "admitted_leader_grids.parquet").to_dict("records")
        for window in json.loads((target / "screen_results.json").read_text())["windows"]:
            assert sha(ROOT / window["quotes_path"]) == window["quotes_sha256"]
            frame = pd.read_parquet(ROOT / window["quotes_path"])
            source_count += len(frame)
            indexed = {(r["decision_ns"], r["symbol"]): r for r in frame.to_dict("records")}
            symbols = sorted(s for s in frame.symbol.unique() if s not in excluded)
            for event in events:
                if (event["date"], event["offset_minutes"]) != (window["date"], window["offset"]):
                    continue
                d = int(event["decision_ns"])
                for symbol in symbols:
                    expected = {"date": event["date"], "offset_minutes": event["offset_minutes"],
                                "decision_ns": d, "symbol": symbol, "direction": int(event["direction"]),
                                "common_move_bps": event["common_move_bps"],
                                **independent(indexed.get((d - 10**9, symbol)), indexed.get((d, symbol)), event, d)}
                    compare(actual[d, symbol], expected)
                    expected_rows.append(expected)
    assert len(rows) == len(expected_rows) == result["target_checks"]
    assert Counter(r["reason"] for r in expected_rows) == result["reasons"]
    candidates = sorted([r for r in expected_rows if r["acquisition_candidate"]], key=lambda r: (r["decision_ns"], r["symbol"]))
    saved = pd.read_parquet(OUT / "acquisition_candidates.parquet").to_dict("records")
    assert len(candidates) == len(saved) == result["acquisition_candidates"]
    for a, b in zip(saved, candidates, strict=True):
        compare(a, b)
    jobs = sorted({(r["date"], r["offset_minutes"], r["symbol"]) for r in candidates})
    assert result["jobs"] == [{"date": d, "offset": o, "symbol": s} for d, o, s in jobs]
    assert len(jobs) == result["distinct_symbol_minutes"]
    assert sum(r["original_freshness_passed"] for r in candidates) == result["original_fresh_candidates"]
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
             "parent_quote_rows_hash_verified": source_count, "causal_grids_verified": 7,
             "target_checks_verified": len(expected_rows), "acquisition_candidates_verified": len(candidates),
             "distinct_symbol_minutes_verified": len(jobs), "numeric_tolerance": "1e-18 bp",
             "results_sha256": sha(OUT / "screen_results.json"), "auditor_sha256": sha(Path(__file__)),
             "scope": "Independent as-of identity, native age/clock/integrity predicates and cross-product Decimal gap/cost arithmetic on all hash-verified parent ledgers. Parent raw-source audits pinned. No production gate import.",
             "depth_confirmation_complete": False, "economic_implementations": 0,
             "future_returns_evaluated": False, "reliable_edge_established": False}
    with (OUT / "independent_verification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
