"""Independently verify every reported qualifying sweep and all its admission outcomes.

Enumeration of earlier rejected groups is hash-pinned but not independently rerun
in this candidate audit. That remains a requirement for a positive survivor.
"""

import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

from research_scout.audit_equity_burst_20261002 import book_valid
from research_scout.prepare_equity_sweep_20261002 import OUT, ROOT, SYMBOLS, sha


def verify_group(raw, ends, g):
    first, last, pre = g["burst_first_source"], g["burst_last_source"], g["burst_pre_quote_index"]
    assert int(ends[pre]) + 1 == first and int(ends[pre + 1]) == last
    segment = raw[first:last + 1]
    r, e = g["burst_receive_ns"], g["burst_event_ns"]
    assert all(int(x["ts_recv"]) == r and int(x["ts_event"]) == e and not int(x["flags"]) & 12 for x in segment)
    trades = [x for x in segment if x["action"] == b"T"]
    prices = [int(x["price"]) for x in trades]
    quantities = [int(x["size"]) for x in trades]
    sign = g["direction"]
    assert sign in (-1, 1) and all(x["side"] == (b"B" if sign > 0 else b"A") for x in trades)
    assert all(0 < p < 10**16 for p in prices) and min(quantities) > 0
    assert max(prices) - min(prices) >= 10_000_000
    assert all(sign * (b - a) >= 0 for a, b in zip(prices, prices[1:]))
    previous = raw[int(ends[pre])]
    assert book_valid(previous)
    assert 0 < r - int(previous["ts_recv"]) <= 250_000_000
    assert 0 <= e - int(previous["ts_event"]) <= 250_000_000 and -1_000_000 <= r - e <= 10**9
    side = "ask" if sign > 0 else "bid"
    touch, size = int(previous[side + "_px_00"]), int(previous[side + "_sz_00"])
    assert all(sign * (p - touch) >= 0 for p in prices)
    quantity, notional = sum(quantities), sum(p * q for p, q in zip(prices, quantities, strict=True))
    assert quantity >= size and notional >= 100_000 * 10**9
    expected = {"burst_first_source": first, "burst_last_source": last, "burst_receive_ns": r, "burst_event_ns": e,
                "burst_pre_quote_index": pre, "burst_quantity": quantity, "burst_notional_int": notional,
                "burst_pre_quantity": size, "direction": sign, "trade_records": len(trades),
                "distinct_prices": len(set(prices)), "minimum_trade_price_int": min(prices),
                "maximum_trade_price_int": max(prices), "pre_bid_int": int(previous["bid_px_00"]),
                "pre_ask_int": int(previous["ask_px_00"])}
    assert g == expected


def admission(raw, ends, group, opening):
    threshold = group["burst_receive_ns"] + 500_000_000
    offset = (threshold - opening) // 100_000_000 + 1
    d = opening + offset * 100_000_000
    if d < opening + 5_000_000_000 or d > opening + 570_000_000_000:
        return None, "outside_fixed_decision_schedule"
    cutoff = d - 250_000_000
    candidates = ends[raw["ts_recv"][ends] < cutoff]
    if not len(candidates):
        return None, "invalid_latest_signal_quote"
    position = int(candidates[-1])
    q = raw[position]
    qi = len(candidates) - 1
    if not book_valid(q):
        return None, "invalid_latest_signal_quote"
    if any(not 0 < cutoff - int(q[k]) <= 250_000_000 for k in ("ts_recv", "ts_event")):
        return None, "stale_signal_quote"
    if (int(q["ts_recv"]) - group["burst_receive_ns"] < 250_000_000
            or int(q["ts_event"]) - group["burst_event_ns"] < 250_000_000):
        return None, "missing_postburst_quarter_second"
    bid, ask = int(q["bid_px_00"]), int(q["ask_px_00"])
    if (D(ask) - D(bid)) / (D(ask) + D(bid)) * 20000 > 5:
        return None, "signal_spread"
    sign = group["direction"]
    if min(sign * (bid - group["pre_bid_int"]), sign * (ask - group["pre_ask_int"])) <= 0:
        return None, "both_sides_not_displaced"
    return {**group, "decision_ns": d, "signal_cutoff_ns": cutoff, "signal_quote_index": qi,
            "signal_source_index": position, "signal_receive_ns": int(q["ts_recv"]), "signal_event_ns": int(q["ts_event"]),
            "signal_bid_int": bid, "signal_ask_int": ask, "signal_bid_quantity": int(q["bid_sz_00"]),
            "signal_ask_quantity": int(q["ask_sz_00"]),
            "rule": "buy_sweep_continuation_long" if sign > 0 else "sell_sweep_reversal_long"}, None


def session(source):
    assert sha(ROOT / source["path"]) == source["sha256"]
    saved = json.loads((OUT / "sessions" / f"{source['date']}.json").read_text())
    store = db.read_dbn(ROOT / source["path"])
    all_records = store.to_ndarray()
    assert len(all_records) == saved["source_rows"]
    opening = pd.Timestamp(source["date"] + " 09:30:00", tz="America/New_York").tz_convert("UTC").value
    events, counters, rejected, errors = [], Counter(), Counter(), []
    groups_checked, admitted = 0, 0
    for symbol in SYMBOLS:
        ids = [int(m["symbol"]) for m in store.metadata.mappings[symbol] if str(m["start_date"]) <= source["date"] < str(m["end_date"])]
        assert len(ids) == 1
        raw = all_records[all_records["instrument_id"] == ids[0]]
        assert np.all(raw["ts_recv"][1:] >= raw["ts_recv"][:-1])
        if np.any(raw["flags"] & 8):
            errors.append({"symbol": symbol, "reason": "BAD_TS_RECV record: no removal or timestamp repair"})
            continue
        ends = np.flatnonzero(raw["flags"] & 128)
        diagnostic = next(x for x in saved["symbol_diagnostics"] if x["symbol"] == symbol)
        counters.update(diagnostic["counts"])
        local = []
        for observation in diagnostic["observations"]:
            verify_group(raw, ends, observation["group"])
            expected, reason = admission(raw, ends, observation["group"], opening)
            assert expected == observation["event"] and reason == observation["reason"]
            groups_checked += 1
            if expected is None:
                rejected[reason] += 1
            else:
                local.append({**expected, "date": source["date"], "symbol": symbol})
                admitted += 1
        assert local == diagnostic["admitted_events"]
        recent, retained = {}, []
        for event in sorted(local, key=lambda r: (r["decision_ns"], r["burst_receive_ns"], r["burst_last_source"])):
            if event["decision_ns"] >= recent.get(event["rule"], -1):
                retained.append(event)
                recent[event["rule"]] = event["decision_ns"] + 60_000_000_000
        assert retained == diagnostic["after_symbol_cooldown"]
        events.extend(retained)
    assert events == saved["events"] and errors == saved["source_errors"]
    chosen = []
    for rule in ("buy_sweep_continuation_long", "sell_sweep_reversal_long"):
        eligible = sorted([r for r in events if r["rule"] == rule],
                          key=lambda r: (r["decision_ns"], -D(r["burst_quantity"]) / D(r["burst_pre_quantity"]),
                                         -r["burst_notional_int"], r["symbol"]))
        available = -1
        for event in eligible:
            if event["decision_ns"] >= available:
                chosen.append(event)
                available = event["decision_ns"] + 35_000_000_000
    assert chosen == saved["selected_events"] and dict(counters) == saved["group_counters"]
    assert dict(rejected) == saved["admission_rejections"]
    return {"date": source["date"], "qualified_groups_checked": groups_checked, "admissions_checked": admitted,
            "selected": chosen, "rejections": dict(rejected), "errors": errors}


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    impl = json.loads((OUT / "implementation.json").read_text())
    result = json.loads((OUT / "screen_results.json").read_text())
    assert sha(OUT / "specification.json") == impl["specification_sha256"]
    assert sha(OUT / "implementation.json") == result["implementation_sha256"]
    for path, digest in impl["code_sha256"].items():
        assert sha(ROOT / path) == digest
    for entry in result["session_files"]:
        assert sha(OUT / "sessions" / f"{entry['date']}.json") == entry["sha256"]
    rows = []
    with ProcessPoolExecutor(max_workers=2) as pool:
        for n, future in enumerate(as_completed([pool.submit(session, s) for s in spec["sources"]]), 1):
            rows.append(future.result())
            if n % 24 == 0 or n == len(spec["sources"]):
                print(json.dumps({"sessions_verified": n, "events_verified": sum(len(r["selected"]) for r in rows)}), flush=True)
    selected = sorted([e for r in rows for e in r["selected"]], key=lambda r: (r["decision_ns"], r["rule"], r["symbol"]))
    assert sha(OUT / "selected.parquet") == result["selected_sha256"]
    assert selected == pd.read_parquet(OUT / "selected.parquet").to_dict("records")
    assert len(selected) == result["selected_events"]
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(), "source_sessions_hash_verified": len(rows),
             "qualified_groups_verified": sum(r["qualified_groups_checked"] for r in rows),
             "admissions_before_cooldown_verified": sum(r["admissions_checked"] for r in rows),
             "selected_events_verified": len(selected), "results_sha256": sha(OUT / "screen_results.json"),
             "auditor_sha256": sha(Path(__file__)),
             "independent_book_helper_sha256": sha(ROOT / "research_scout/audit_equity_burst_20261002.py"),
             "scope": "All reported prestate-qualified sweep identities, exact volume/notional, every fixed-clock admission/rejection, both cooldown stages, global ranking and final selected ledger independently reconciled from source. No production sweep or admission import.",
             "earlier_group_rejection_enumeration_independently_recomputed": False,
             "remaining_positive_survivor_audit": "Recompute all earlier group-rejection enumeration before reliability promotion.",
             "future_returns_evaluated": False, "actual_execution_verified": False, "reliable_edge_established": False}
    with (OUT / "candidate_verification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
