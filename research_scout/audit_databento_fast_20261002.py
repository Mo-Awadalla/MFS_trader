"""Independent DBN field, immediate admission, fixed reference and Decimal cash audit."""

import json
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

from research_scout.audit_equity_burst_20261002 import book_valid
from research_scout.audit_equity_sweep_candidates_20261002 import verify_group
from research_scout.prepare_databento_fast_20261002 import OUT, PARENT, ROOT, sha, write

NS = 1000000000
D = Decimal


def cash(buy_int, sell_int, quantity, fee=1, adverse=1):
    q, buy, sell = D(quantity), D(buy_int) / NS, D(sell_int) / NS
    debit, credit = q * buy, q * sell
    commissions = 2 * max(D(1), q / 200) * fee
    levies = (credit * D(".00003") + q * D(".000166")) * fee
    slip = (debit + credit) * D(".0001") * adverse
    return {"gross": credit - debit, "commissions": commissions, "sell_levies": levies,
            "adverse": slip, "net": credit - debit - commissions - levies - slip}


def signal(raw, ends, group, opening):
    d = (group["burst_receive_ns"] // 1000000 + 2) * 1000000
    if d < opening + 5 * NS or d > opening + 570 * NS:
        return None, "outside_schedule"
    cutoff = d - 1000000
    qi = int(np.searchsorted(raw["ts_recv"][ends], np.uint64(cutoff), side="left")) - 1
    if qi < 0:
        return None, "invalid_or_incomplete_signal_book"
    source = int(ends[qi])
    quote = raw[source]
    if not book_valid(quote) or source < group["burst_last_source"]:
        return None, "invalid_or_incomplete_signal_book"
    r, e = int(quote["ts_recv"]), int(quote["ts_event"])
    if r < cutoff - 5000000 or r >= cutoff or e < cutoff - 5000000 or e > cutoff:
        return None, "signal_age_or_clock"
    bid, ask = int(quote["bid_px_00"]), int(quote["ask_px_00"])
    if bid % 10000000 or ask % 10000000:
        return None, "noncent_signal_price"
    if (ask - bid) * 20000 > (bid + ask) * 5:
        return None, "spread"
    direction = group["direction"]
    if direction * (bid - group["pre_bid_int"]) <= 0 or direction * (ask - group["pre_ask_int"]) <= 0:
        return None, "both_sides_not_displaced"
    limit_cents = (D(ask) / NS * D("1.02") * 100).to_integral_value(rounding=ROUND_CEILING)
    limit = int(limit_cents) * 10000000
    bq, aq = int(quote["bid_sz_00"]), int(quote["ask_sz_00"])
    quantity = min(10000 * NS // limit, bq // 10, aq // 10)
    if quantity <= 0:
        return None, "quantity"
    cost = -cash(ask, bid, quantity)["net"]
    bp = cost * 10000 / (D(ask * quantity) / NS)
    if bp > 12:
        return None, "causal_cost"
    return {**group, "decision_ns": d, "cutoff_ns": cutoff, "signal_quote_index": qi,
            "signal_source_index": source, "signal_receive_ns": r, "signal_event_ns": e,
            "signal_bid_int": bid, "signal_ask_int": ask, "signal_bid_quantity": bq,
            "signal_ask_quantity": aq, "quantity": quantity, "entry_limit_int": limit,
            "causal_cost_usd": str(cost), "causal_cost_bp": str(bp),
            "rule": "follow_buy_sweep" if direction == 1 else "fade_sell_sweep"}, None


def normalized(r):
    return {k: D(v) if k in ("causal_cost_usd", "causal_cost_bp") else v for k, v in r.items()}


def reference(raw, ends, at):
    times = raw["ts_recv"][ends]
    after = int(np.searchsorted(times, np.uint64(at), side="left"))
    if after == 0 or after == len(ends):
        return None, "unbracketed_arrival"
    if int(times[after]) == at:
        return None, "equal_capture_clock_boundary"
    pos = int(ends[after - 1])
    q = raw[pos]
    r, e = int(q["ts_recv"]), int(q["ts_event"])
    if not book_valid(q) or e > at or min(r, e) < at - 250000000:
        return None, "invalid_stale_or_future_native_book"
    return {"quote_index": after - 1, "source_index": pos, "receive_ns": r, "event_ns": e,
            "bid_int": int(q["bid_px_00"]), "ask_int": int(q["ask_px_00"]),
            "bid_size": int(q["bid_sz_00"]), "ask_size": int(q["ask_sz_00"])}, None


def verify_case(raw, ends, event, hold, case, actual):
    entry_time = event["decision_ns"] + 50000 + (case["delay_ms"] + case.get("clock_shift_ms", 0)) * 1000000
    exit_time = entry_time + hold * 1000000
    assert (actual["entry_arrival_ns"], actual["exit_arrival_ns"], actual["requested_quantity"]) == (
        entry_time, exit_time, event["quantity"])
    assert 0 < exit_time - entry_time < 30 * NS
    entry, why = reference(raw, ends, entry_time)
    if why:
        assert actual["outcome"] == "unknown_entry_" + why and actual["net_usd"] is None
        return
    assert actual["entry_quote"] == entry
    if entry["ask_int"] > event["entry_limit_int"]:
        assert actual["outcome"] == "conditional_limit_no_entry" and D(actual["net_usd"]) == 0
        assert actual["filled_quantity"] == 0
        return
    shares = min(event["quantity"], entry["ask_size"])
    assert shares == actual["filled_quantity"] > 0
    sale, why = reference(raw, ends, exit_time)
    if why:
        assert actual["outcome"] == "unknown_exit_" + why and actual["net_usd"] is None
        return
    assert actual["exit_quote"] == sale
    if shares > sale["bid_size"]:
        assert actual["outcome"] == "unknown_exit_depth_residual_inventory" and actual["net_usd"] is None
        return
    expected = cash(entry["ask_int"], sale["bid_int"], shares, case["fee_multiple"], case["adverse_multiple"])
    assert actual["outcome"] == "conditional_priced" and actual["holding_ns"] == hold * 1000000
    assert {k: D(v) for k, v in actual["cash"].items()} == expected
    assert D(actual["net_usd"]) == expected["net"]


def audit(source):
    spec = json.loads((OUT / "specification.json").read_text())
    screen = json.loads((OUT / "screen_results.json").read_text())
    replay = json.loads((OUT / "replay_results.json").read_text())
    day, path = source["date"], ROOT / source["path"]
    assert sha(path) == source["sha256"]
    sp, rp = OUT / "screen_sessions" / (day + ".json"), OUT / "replay_sessions" / (day + ".json")
    assert sha(sp) == screen["session_hashes"][day] and sha(rp) == replay["session_hashes"][day]
    observed, economics = json.loads(sp.read_text()), json.loads(rp.read_text())
    parent = json.loads((PARENT / "sessions" / (day + ".json")).read_text())
    assert sha(PARENT / "sessions" / (day + ".json")) == next(x["sha256"] for x in spec["parent_sessions"] if x["date"] == day)
    expected_pairs = [(s["symbol"], r["group"]) for s in parent["symbol_diagnostics"] for r in s["observations"]]
    assert [(r["symbol"], r["group"]) for r in observed["checks"]] == expected_pairs
    store = db.read_dbn(path)
    assert store.metadata.dataset == "EQUS.MINI" and str(store.metadata.schema) == "mbp-1"
    data = store.to_ndarray()
    assert len(data) == observed["source_rows"]
    opening = int(pd.Timestamp(day + " 09:30:00", tz="America/New_York").tz_convert("UTC").value)
    raw_by_symbol, endpoints, errors = {}, {}, []
    for symbol in spec["symbols"]:
        ids = [int(m["symbol"]) for m in store.metadata.mappings[symbol]
               if str(m["start_date"]) <= day < str(m["end_date"])]
        assert len(ids) == 1
        raw = data[data["instrument_id"] == ids[0]]
        assert np.all(raw["ts_recv"][1:] >= raw["ts_recv"][:-1])
        if np.any(raw["flags"] & 8):
            errors.append({"symbol": symbol, "reason": "BAD_TS_RECV record: no removal or timestamp repair"})
            continue
        raw_by_symbol[symbol] = raw
        endpoints[symbol] = np.flatnonzero(raw["flags"] & 128)
    assert errors == observed["source_errors"]
    admissions, rejected = [], Counter()
    for item in observed["checks"]:
        symbol = item["symbol"]
        raw, ends = raw_by_symbol[symbol], endpoints[symbol]
        verify_group(raw, ends, item["group"])
        e, why = signal(raw, ends, item["group"], opening)
        assert why == item["reason"]
        if e is None:
            rejected[why] += 1
            assert item["event"] is None
        else:
            e.update(date=day, symbol=symbol)
            assert normalized(e) == normalized(item["event"])
            admissions.append(e)
    assert dict(rejected) == observed["rejections"]
    assert list(map(normalized, admissions)) == list(map(normalized, observed["admitted"]))
    selected = []
    for rule in ("follow_buy_sweep", "fade_sell_sweep"):
        candidates = sorted([r for r in admissions if r["rule"] == rule],
                            key=lambda r: (r["decision_ns"], -D(r["burst_quantity"]) / r["burst_pre_quantity"],
                                           -r["burst_notional_int"], r["symbol"], r["burst_last_source"]))
        kept = []
        for e in candidates:
            if any(e["decision_ns"] - old["decision_ns"] < 6 * NS
                   or (old["symbol"] == e["symbol"] and e["decision_ns"] - old["decision_ns"] < 60 * NS)
                   for old in kept):
                continue
            kept.append(e)
        selected.extend(kept)
    selected.sort(key=lambda r: (r["decision_ns"], r["rule"], r["symbol"]))
    assert list(map(normalized, selected)) == list(map(normalized, observed["selected"]))
    expected_cases = [(e, h, c) for e in selected for h in spec["hold_ms"] for c in spec["cases"]]
    assert len(expected_cases) == len(economics["outcomes"])
    for (event, hold, case), row in zip(expected_cases, economics["outcomes"], strict=True):
        assert (row["date"], row["symbol"], row["rule"], row["decision_ns"], row["hold_ms"], row["case"]) == (
            day, event["symbol"], event["rule"], event["decision_ns"], hold, case["name"])
        verify_case(raw_by_symbol[event["symbol"]], endpoints[event["symbol"]], event, hold, case, row)
    return {"date": day, "source_rows": len(data), "groups": len(expected_pairs), "selected": len(selected),
            "event_cases": len(expected_cases)}


def aggregate_audit(result, spec, rows):
    mandatory_unknown = {r["date"] for r in spec["inherited_unknown_symbol_dates"]}
    for observed in result["scenario_results"]:
        cohort = [r for r in rows if (r["rule"], r["hold_ms"], r["case"]) == (
            observed["rule"], observed["hold_ms"], observed["case"])]
        daily, unknown, unknown_events, priced = defaultdict(Decimal), set(mandatory_unknown), 0, 0
        for r in cohort:
            if r["net_usd"] is None:
                unknown.add(r["date"])
                unknown_events += 1
            else:
                daily[r["date"]] += D(r["net_usd"])
            priced += r["outcome"] == "conditional_priced"
        net = sum(daily.values(), D(0))
        assert observed["event_cases"] == len(cohort) and observed["unknown_events"] == unknown_events
        assert observed["priced_events"] == priced and D(observed["known_component_usd"]) == net
        assert observed["unknown_calendar_dates"] == sorted(unknown)
        assert observed["full_calendar_usd"] == (None if unknown else str(net))
        assert observed["observed_event_cohort_usd"] == (None if unknown_events else str(net))
        assert {k: D(v) for k, v in observed["daily_known_usd"].items()} == dict(daily)
        assert D(observed["known_drop_best_3_dates_usd"]) == net - sum(sorted(daily.values(), reverse=True)[:3], D(0))


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    results = json.loads((OUT / "replay_results.json").read_text())
    screen = json.loads((OUT / "screen_results.json").read_text())
    assert not results["errors"] and not screen["errors"] and results["sessions"] == screen["sessions"] == 192
    records, errors = [], []
    with ProcessPoolExecutor(max_workers=2) as pool:
        jobs = {pool.submit(audit, s): s["date"] for s in spec["sources"]}
        for n, job in enumerate(as_completed(jobs), 1):
            try:
                records.append(job.result())
                if n % 32 == 0 or n == len(jobs):
                    print(json.dumps({"sessions_verified": len(records), "event_cases_verified": sum(r["event_cases"] for r in records)}), flush=True)
            except Exception as exc:
                failure = {"date": jobs[job], "error": f"{type(exc).__name__}: {exc}"}
                errors.append(failure)
                print(json.dumps(failure), flush=True)
    assert not errors, errors
    rows = [r for p in sorted((OUT / "replay_sessions").glob("*.json")) for r in json.loads(p.read_text())["outcomes"]]
    aggregate_audit(results, spec, rows)
    report = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
              "source_rows_verified": sum(r["source_rows"] for r in records),
              "groups_verified": sum(r["groups"] for r in records),
              "selected_verified": sum(r["selected"] for r in records),
              "event_cases_verified": sum(r["event_cases"] for r in records),
              "aggregates_verified": len(results["scenario_results"]),
              "screen_sha256": sha(OUT / "screen_results.json"), "results_sha256": sha(OUT / "replay_results.json"),
              "auditor_sha256": sha(Path(__file__)),
              "group_auditor_sha256": sha(ROOT / "research_scout/audit_equity_sweep_candidates_20261002.py"),
              "book_helper_sha256": sha(ROOT / "research_scout/audit_equity_burst_20261002.py"),
              "scope": "Independent DBN field/group,signal,ranking,fixed receive-clock reference,L1 fill bounds,cash and aggregate recalculation. Shared Databento SDK DBN decoder;no separate binary decoder. Earlier rejected group enumeration not independently rerun. No venue/NBBO/private fill proof.",
              "actual_execution_verified": False, "reliable_edge_established": False}
    assert report["groups_verified"] == screen["groups_checked"] == 563
    assert report["source_rows_verified"] == screen["source_rows"]
    assert report["selected_verified"] == screen["selected_count"]
    assert report["event_cases_verified"] == results["event_cases"]
    write(OUT / "independent_verification.json", report)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
