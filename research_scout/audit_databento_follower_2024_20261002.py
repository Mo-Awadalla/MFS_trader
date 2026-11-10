"""Independently enumerate all SPY trade groups and audit every 2024 follower decision."""

import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

from research_scout.audit_databento_follower_20261002 import normalized, spy_signal, target
from research_scout.audit_equity_burst_20261002 import book_valid
from research_scout.audit_equity_sweep_candidates_20261002 import verify_group
from research_scout.databento_follower_2024_20261002 import OUT
from research_scout.prepare_databento_fast_20261002 import ROOT, sha, write

NS = 1000000000


def enumerate_groups(raw, ends):
    """Start from every T record, independently recovering event partitions and first failure."""
    closing_groups = {int(np.searchsorted(ends, int(t), side="left")) for t in np.flatnonzero(raw["action"] == b"T")}
    accepted, rejected, counts = [], [], Counter()
    for closing in sorted(closing_groups):
        counts["trade_bearing_groups"] += 1
        if closing == len(ends):
            reason = "incomplete_group"
            counts[reason] += 1
            rejected.append({"first_source": int(ends[-1]) + 1 if len(ends) else 0,
                             "last_source": len(raw) - 1, "reason": reason})
            continue
        first = int(ends[closing - 1]) + 1 if closing else 0
        last = int(ends[closing])
        segment = raw[first:last + 1]
        received, event = int(raw[last]["ts_recv"]), int(raw[last]["ts_event"])
        prints = segment[segment["action"] == b"T"]
        prices, quantities = [int(r["price"]) for r in prints], [int(r["size"]) for r in prints]
        side = bytes(prints[0]["side"])
        direction = {b"B": 1, b"A": -1}.get(side, 0)
        reason = None
        if any(int(r["ts_recv"]) != received or int(r["ts_event"]) != event or int(r["flags"]) & 12 for r in segment):
            reason = "mixed_clocks_or_bad_group"
        elif (direction == 0 or any(bytes(r["side"]) != side for r in prints) or min(quantities) <= 0
              or any(p <= 0 or p >= 10**16 for p in prices)):
            reason = "unknown_mixed_side_or_invalid_trade"
        elif max(prices) - min(prices) < 10000000 or any(direction * (b - a) < 0 for a, b in zip(prices, prices[1:], strict=False)):
            reason = "not_monotonic_multiple_price_levels"
        elif closing == 0 or not book_valid(raw[int(ends[closing - 1])]):
            reason = "invalid_immediate_prestate"
        else:
            before = raw[int(ends[closing - 1])]
            dr, de = received - int(before["ts_recv"]), event - int(before["ts_event"])
            if not (0 < dr <= 250000000 and 0 <= de <= 250000000 and -1000000 <= received - event <= NS):
                reason = "ambiguous_stale_or_inconsistent_prestate"
            else:
                level = "ask" if direction == 1 else "bid"
                pre_price, pre_size = int(before[level + "_px_00"]), int(before[level + "_sz_00"])
                quantity = sum(quantities)
                notional = sum(p * q for p, q in zip(prices, quantities, strict=True))
                if any(direction * (p - pre_price) < 0 for p in prices):
                    reason = "print_inside_prestate_touch"
                elif quantity < pre_size or notional < 100000 * NS:
                    reason = "insufficient_burst_size_or_notional"
                else:
                    accepted.append({"burst_first_source": first, "burst_last_source": last,
                                     "burst_receive_ns": received, "burst_event_ns": event,
                                     "burst_pre_quote_index": closing - 1, "burst_quantity": quantity,
                                     "burst_notional_int": notional, "burst_pre_quantity": pre_size,
                                     "direction": direction, "trade_records": len(prints),
                                     "distinct_prices": len(set(prices)), "minimum_trade_price_int": min(prices),
                                     "maximum_trade_price_int": max(prices), "pre_bid_int": int(before["bid_px_00"]),
                                     "pre_ask_int": int(before["ask_px_00"])})
        if reason is not None:
            counts[reason] += 1
            rejected.append({"first_source": first, "last_source": last, "reason": reason})
    counts["prestate_qualified_sweeps"] = len(accepted)
    return accepted, rejected, dict(counts)


def audit(source):
    spec = json.loads((OUT / "specification.json").read_text())
    results = json.loads((OUT / "screen_results.json").read_text())
    day, file = source["date"], ROOT / source["path"]
    assert sha(file) == source["sha256"]
    path = OUT / "sessions" / (day + ".json")
    assert sha(path) == results["session_hashes"][day]
    observed = json.loads(path.read_text())
    store = db.read_dbn(file)
    assert store.metadata.dataset == "EQUS.MINI" and str(store.metadata.schema) == "mbp-1"
    raw = store.to_ndarray()
    assert len(raw) == observed["source_rows"]
    data, endpoints, errors = {}, {}, []
    for symbol in spec["symbols"]:
        ids = [int(m["symbol"]) for m in store.metadata.mappings[symbol]
               if str(m["start_date"]) <= day < str(m["end_date"])]
        assert len(ids) == 1
        subset = raw[raw["instrument_id"] == ids[0]]
        assert np.all(subset["ts_recv"][1:] >= subset["ts_recv"][:-1])
        if np.any(subset["flags"] & 8):
            errors.append({"symbol": symbol, "reason": "BAD_TS_RECV record: no removal or timestamp repair"})
        else:
            data[symbol], endpoints[symbol] = subset, np.flatnonzero(subset["flags"] & 128)
    assert errors == observed["source_errors"]
    if "SPY" in data:
        groups, rejected, group_counts = enumerate_groups(data["SPY"], endpoints["SPY"])
    else:
        groups, rejected, group_counts = [], [], {}
    assert group_counts == observed["group_counts"]
    assert rejected == observed["rejected_groups"]
    assert groups == [r["group"] for r in observed["leader_checks"]]
    opening = int(pd.Timestamp(day + " 09:30:00", tz="America/New_York").tz_convert("UTC").value)
    failures, admitted, checks, leaders, budgets = Counter(), [], [], 0, 0
    for g, expected in zip(groups, observed["leader_checks"], strict=True):
        verify_group(data["SPY"], endpoints["SPY"], g)
        signal, why = spy_signal(data["SPY"], endpoints["SPY"], g, opening)
        assert signal == expected["signal"] and why == expected["reason"]
        if why:
            failures[why] += 1
            continue
        leaders += 1
        for symbol, beta in spec["multipliers"].items():
            if symbol in data:
                detail, why = target(data[symbol], endpoints[symbol], symbol, beta, signal)
            else:
                detail, why = None, "unknown_follower_source"
            if why:
                failures[why] += 1
            if detail is not None:
                budgets += 1
                if why is None:
                    detail["date"] = day
                    admitted.append(detail)
            checks.append({"symbol": symbol, "signal": signal, "reason": why, "budget": detail,
                           "event": detail if why is None else None})
    assert len(checks) == len(observed["follower_checks"])
    for actual, expected in zip(observed["follower_checks"], checks, strict=True):
        assert (actual["symbol"], actual["signal"], actual["reason"]) == (expected["symbol"], expected["signal"], expected["reason"])
        assert normalized(actual["budget"]) == normalized(expected["budget"])
        assert normalized(actual["event"]) == normalized(expected["event"])
    assert dict(failures) == observed["rejections"]
    assert admitted == [normalized(r) for r in observed["admitted"]]
    ranked = sorted(admitted, key=lambda r: (r["decision_ns"], -r["projected_cash"]["net"],
                                            -r["projected_net_bp"], r["symbol"], r["group"]["burst_last_source"]))
    selected = []
    for e in ranked:
        if all(e["decision_ns"] - old["decision_ns"] >= 6 * NS and
               (e["symbol"] != old["symbol"] or e["decision_ns"] - old["decision_ns"] >= 60 * NS) for old in selected):
            selected.append(e)
    assert selected == [normalized(r) for r in observed["selected"]]
    return {"date": day, "source_rows": len(raw), "trade_groups": group_counts.get("trade_bearing_groups", 0),
            "qualified_groups": len(groups), "rejected_groups": len(rejected), "valid_leaders": leaders,
            "follower_checks": len(checks), "budgets": budgets, "selected": len(selected)}


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    results = json.loads((OUT / "screen_results.json").read_text())
    assert not results["errors"] and results["sessions"] == 252
    records, errors = [], []
    with ProcessPoolExecutor(max_workers=2) as pool:
        jobs = {pool.submit(audit, s): s["date"] for s in spec["sources"]}
        for n, job in enumerate(as_completed(jobs), 1):
            try:
                records.append(job.result())
                if n % 36 == 0 or n == len(jobs):
                    print(json.dumps({"sessions_verified": len(records), "trade_groups_verified": sum(r["trade_groups"] for r in records)}), flush=True)
            except Exception as exc:
                e = {"date": jobs[job], "error": f"{type(exc).__name__}: {exc}"}
                errors.append(e)
                print(json.dumps(e), flush=True)
    assert not errors, errors
    report = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(), "sessions_verified": len(records),
              **{k + "_verified": sum(r[k] for r in records) for k in (
                  "source_rows", "trade_groups", "qualified_groups", "rejected_groups", "valid_leaders", "follower_checks", "budgets", "selected")},
              "results_sha256": sha(OUT / "screen_results.json"), "auditor_sha256": sha(Path(__file__)),
              "signal_auditor_sha256": sha(ROOT / "research_scout/audit_databento_follower_20261002.py"),
              "scope": "Independent enumeration of ALLaccepted/rejected2024SPYtrade groups,source clock flags,common-clock leader/follower quotes,integer-rational projected prices,Decimal costs and ranking. Shared DatabentoSDKbinary decoder. No future returns or actual executions.",
              "returns_calculated": False, "actual_execution_verified": False, "reliable_edge_established": False}
    assert report["trade_groups_verified"] == results["group_counts"]["trade_bearing_groups"]
    for a, b in (("source_rows_verified", "source_rows"), ("qualified_groups_verified", "leader_groups"),
                 ("valid_leaders_verified", "valid_leader_signals"), ("follower_checks_verified", "follower_checks"),
                 ("budgets_verified", "budgets"), ("selected_verified", "selected_count")):
        assert report[a] == results[b]
    sessions = [json.loads(p.read_text()) for p in sorted((OUT / "sessions").glob("*.json"))]
    all_budgets = [Decimal(c["budget"]["projected_net_bp"]) for s in sessions for c in s["follower_checks"] if c["budget"] is not None]
    assert str(max(all_budgets)) == results["best_projected_net_bp"]
    write(OUT / "independent_verification.json", report)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
