"""Independent source and integer-rational cross-ETF admission audit."""

import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

from research_scout.audit_databento_fast_20261002 import cash
from research_scout.audit_equity_burst_20261002 import book_valid
from research_scout.audit_equity_sweep_candidates_20261002 import verify_group
from research_scout.prepare_databento_fast_20261002 import PARENT, ROOT, sha, write
from research_scout.prepare_databento_follower_20261002 import OUT

NS = 1000000000
D = Decimal


def point(raw, ends, cutoff, maximum_age):
    index = int(np.searchsorted(raw["ts_recv"][ends], np.uint64(cutoff), side="left")) - 1
    if index < 0:
        return None, "invalid_latest_book"
    pos = int(ends[index])
    q = raw[pos]
    if not book_valid(q):
        return None, "invalid_latest_book"
    r, e = int(q["ts_recv"]), int(q["ts_event"])
    if not cutoff - maximum_age <= r < cutoff or not cutoff - maximum_age <= e <= cutoff:
        return None, "quote_age_or_native_clock"
    bid, ask = int(q["bid_px_00"]), int(q["ask_px_00"])
    if bid % 10000000 or ask % 10000000:
        return None, "noncent_price"
    if (ask - bid) * 20000 > 5 * (bid + ask):
        return None, "spread"
    return {"quote_index": index, "source_index": pos, "receive_ns": r, "event_ns": e,
            "bid_int": bid, "ask_int": ask, "bid_size": int(q["bid_sz_00"]), "ask_size": int(q["ask_sz_00"])}, None


def spy_signal(raw, ends, group, opening):
    decision = (group["burst_receive_ns"] // 1000000 + 2) * 1000000
    if not opening + 5 * NS <= decision <= opening + 570 * NS:
        return None, "outside_schedule"
    cutoff, anchor = decision - 1000000, decision - 1001000000
    current, why = point(raw, ends, cutoff, 5000000)
    if why:
        return None, "leader_current_" + why
    if current["source_index"] < group["burst_last_source"]:
        return None, "leader_burst_incomplete"
    reference, why = point(raw, ends, anchor, 250000000)
    if why:
        return None, "leader_reference_" + why
    for key in ("bid_int", "ask_int"):
        if group["direction"] * (current[key] - reference[key]) <= 0:
            return None, "leader_both_sides_not_displaced_over_1s"
    return {"decision_ns": decision, "cutoff_ns": cutoff, "anchor_ns": anchor,
            "leader_current": current, "leader_reference": reference, "group": group}, None


def target(raw, ends, symbol, beta, signal):
    if beta * signal["group"]["direction"] < 0:
        return None, "wrong_long_direction"
    current, why = point(raw, ends, signal["cutoff_ns"], 250000000)
    if why:
        return None, "follower_current_" + why
    reference, why = point(raw, ends, signal["anchor_ns"], 250000000)
    if why:
        return None, "follower_reference_" + why
    limit_cents, remainder = divmod(current["ask_int"] * 102, NS)
    limit = (limit_cents + bool(remainder)) * 10000000
    q = min(10000 * NS // limit, current["bid_size"] // 10, current["ask_size"] // 10)
    if q < 1:
        return None, "quantity"
    l0 = signal["leader_reference"]["bid_int"] + signal["leader_reference"]["ask_int"]
    l1 = signal["leader_current"]["bid_int"] + signal["leader_current"]["ask_int"]
    t0 = reference["bid_int"] + reference["ask_int"]
    # Rational numerator/denominator directly yield whole cents, independently of Decimal rounding.
    numerator = t0 * (l0 + beta * (l1 - l0)) - (current["ask_int"] - current["bid_int"]) * l0
    exit_price = numerator // (2 * l0 * 10000000) * 10000000
    if exit_price <= 0:
        return None, "nonpositive_projected_price"
    projected = cash(current["ask_int"], exit_price, q)
    present = cash(current["ask_int"], current["bid_int"], q)
    entry = D(q * current["ask_int"]) / NS
    net_bp = projected["net"] * 10000 / entry
    cost_bp = -present["net"] * 10000 / entry
    detail = {**signal, "symbol": symbol, "multiplier": beta, "follower_current": current,
              "follower_reference": reference, "quantity": q, "entry_limit_int": limit,
              "leader_move_bp": D(l1 - l0) * 10000 / l0,
              "projected_mid_int": D(t0) / 2 * (D(1) + D(beta * (l1 - l0)) / l0),
              "projected_exit_int": exit_price, "projected_cash": projected,
              "projected_net_bp": net_bp, "causal_cost_bp": cost_bp, "rule": "spy_follower_lag_long"}
    reason = "causal_cost_above_12bp" if cost_bp > 12 else "projected_net_below_2bp" if net_bp < 2 else None
    return detail, reason


def normalized(detail):
    if detail is None:
        return None
    result = detail.copy()
    for k in ("leader_move_bp", "projected_mid_int", "projected_net_bp", "causal_cost_bp"):
        result[k] = D(result[k])
    result["projected_cash"] = {k: D(v) for k, v in result["projected_cash"].items()}
    return result


def one(source):
    spec = json.loads((OUT / "specification.json").read_text())
    results = json.loads((OUT / "screen_results.json").read_text())
    day, file = source["date"], ROOT / source["path"]
    assert sha(file) == source["sha256"]
    saved = OUT / "screen_sessions" / (day + ".json")
    assert sha(saved) == results["session_hashes"][day]
    observed = json.loads(saved.read_text())
    parent_file = PARENT / "sessions" / (day + ".json")
    assert sha(parent_file) == next(r["sha256"] for r in spec["parent_sessions"] if r["date"] == day)
    parent = json.loads(parent_file.read_text())
    groups = [r["group"] for diag in parent["symbol_diagnostics"] if diag["symbol"] == "SPY" for r in diag["observations"]]
    assert groups == [r["group"] for r in observed["leader_checks"]]
    store = db.read_dbn(file)
    assert store.metadata.dataset == "EQUS.MINI" and str(store.metadata.schema) == "mbp-1"
    raw = store.to_ndarray()
    assert len(raw) == observed["source_rows"]
    symbols, endpoints, source_errors = {}, {}, []
    for symbol in spec["symbols"]:
        ids = [int(m["symbol"]) for m in store.metadata.mappings[symbol]
               if str(m["start_date"]) <= day < str(m["end_date"])]
        assert len(ids) == 1
        data = raw[raw["instrument_id"] == ids[0]]
        assert np.all(data["ts_recv"][1:] >= data["ts_recv"][:-1])
        if np.any(data["flags"] & 8):
            source_errors.append({"symbol": symbol, "reason": "BAD_TS_RECV record: no removal or timestamp repair"})
            continue
        symbols[symbol], endpoints[symbol] = data, np.flatnonzero(data["flags"] & 128)
    assert source_errors == observed["source_errors"]
    opening = int(pd.Timestamp(day + " 09:30:00", tz="America/New_York").tz_convert("UTC").value)
    failures, qualified, follower_checks, budgets, signals = Counter(), [], [], 0, 0
    for g, expected in zip(groups, observed["leader_checks"], strict=True):
        verify_group(symbols["SPY"], endpoints["SPY"], g)
        signal, why = spy_signal(symbols["SPY"], endpoints["SPY"], g, opening)
        assert signal == expected["signal"] and why == expected["reason"]
        if why:
            failures[why] += 1
            continue
        signals += 1
        for symbol, beta in spec["multipliers"].items():
            if symbol in symbols:
                detail, why = target(symbols[symbol], endpoints[symbol], symbol, beta, signal)
            else:
                detail, why = None, "unknown_follower_source"
            if why:
                failures[why] += 1
            if detail is not None:
                budgets += 1
                if why is None:
                    detail["date"] = day
                    qualified.append(detail)
            follower_checks.append({"symbol": symbol, "signal": signal, "event": detail if why is None else None,
                                    "reason": why, "budget": detail})
    assert len(follower_checks) == len(observed["follower_checks"])
    for actual, expected in zip(observed["follower_checks"], follower_checks, strict=True):
        assert actual["symbol"] == expected["symbol"] and actual["signal"] == expected["signal"]
        assert actual["reason"] == expected["reason"]
        assert normalized(actual["event"]) == normalized(expected["event"])
        assert normalized(actual["budget"]) == normalized(expected["budget"])
    assert dict(failures) == observed["rejections"]
    assert [normalized(r) for r in qualified] == [normalized(r) for r in observed["admitted"]]
    rank = sorted(qualified, key=lambda r: (r["decision_ns"], -r["projected_cash"]["net"],
                                           -r["projected_net_bp"], r["symbol"], r["group"]["burst_last_source"]))
    selected = []
    for event in rank:
        if all(event["decision_ns"] - old["decision_ns"] >= 6 * NS
               and (event["symbol"] != old["symbol"] or event["decision_ns"] - old["decision_ns"] >= 60 * NS)
               for old in selected):
            selected.append(event)
    assert selected == [normalized(r) for r in observed["selected"]]
    return {"date": day, "source_rows": len(raw), "leader_groups": len(groups), "valid_leaders": signals,
            "follower_checks": len(follower_checks), "budgets": budgets, "selected": len(selected)}


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    results = json.loads((OUT / "screen_results.json").read_text())
    assert not results["errors"] and results["sessions"] == 192
    records, errors = [], []
    with ProcessPoolExecutor(max_workers=2) as pool:
        jobs = {pool.submit(one, s): s["date"] for s in spec["sources"]}
        for n, job in enumerate(as_completed(jobs), 1):
            try:
                records.append(job.result())
                if n % 32 == 0 or n == len(jobs):
                    print(json.dumps({"sessions_verified": len(records), "budgets_verified": sum(r["budgets"] for r in records)}), flush=True)
            except Exception as exc:
                e = {"date": jobs[job], "error": f"{type(exc).__name__}: {exc}"}
                errors.append(e)
                print(json.dumps(e), flush=True)
    assert not errors, errors
    report = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(), "sessions_verified": len(records),
              "source_rows_verified": sum(r["source_rows"] for r in records),
              "leader_groups_verified": sum(r["leader_groups"] for r in records),
              "valid_leaders_verified": sum(r["valid_leaders"] for r in records),
              "follower_checks_verified": sum(r["follower_checks"] for r in records),
              "budgets_verified": sum(r["budgets"] for r in records),
              "selected_verified": sum(r["selected"] for r in records),
              "results_sha256": sha(OUT / "screen_results.json"), "auditor_sha256": sha(Path(__file__)),
              "cash_helper_sha256": sha(ROOT / "research_scout/audit_databento_fast_20261002.py"),
              "group_helper_sha256": sha(ROOT / "research_scout/audit_equity_sweep_candidates_20261002.py"),
              "book_helper_sha256": sha(ROOT / "research_scout/audit_equity_burst_20261002.py"),
              "scope": "Independent raw DBN field/group,common-clock snapshot,integer-rational projected cent price,cost and ranking checks. Shared SDK binary decoder. No future return or execution proof. Earlier parent group-rejection enumeration remains outside this audit.",
              "actual_execution_verified": False, "returns_calculated": False, "reliable_edge_established": False}
    for a, b in (("source_rows_verified", "source_rows"), ("leader_groups_verified", "leader_groups"),
                 ("valid_leaders_verified", "valid_leader_signals"), ("follower_checks_verified", "follower_checks"),
                 ("budgets_verified", "budgets"), ("selected_verified", "selected_count")):
        assert report[a] == results[b]
    write(OUT / "independent_verification.json", report)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
