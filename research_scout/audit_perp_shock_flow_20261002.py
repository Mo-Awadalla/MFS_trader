"""Independent native execution prefix, ID integrity and exact flow aggregation."""

import calendar
import gzip
import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

import pandas as pd

from research_scout.prepare_perp_shock_flow_20261002 import OUT, PARENT, ROOT, sha


def native(source):
    midnight = calendar.timegm(datetime.strptime(source["date"], "%Y-%m-%d").timetuple()) * 10**9
    start, last = midnight + source["offset"] * 60 * 10**9, -1
    records, disconnects, counts, decoded = [], [], Counter(), 0
    path = ROOT / source["path"]
    assert source["complete"] and sha(path) == source["compressed_sha256"]
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        for number, line in enumerate(stream):
            decoded += len(line.encode("utf-8"))
            if not line.strip():
                disconnects.append(last if last >= 0 else start - 1)
                counts["disconnects"] += 1
                continue
            stamp, payload = line.strip().split(" ", 1)
            whole, fraction = stamp[:-1].split(".") if "." in stamp else (stamp[:-1], "0")
            clock = datetime.fromisoformat(whole)
            received = midnight + (clock.hour * 3600 + clock.minute * 60 + clock.second) * 10**9 + int(fraction.ljust(9, "0"))
            assert stamp[:10] == source["date"] and start <= received < start + 60 * 10**9 and received >= last
            last = received
            counts["native_messages"] += 1
            envelope = json.loads(payload)
            if envelope.get("stream", "").rsplit("@", 1)[-1] != "trade":
                continue
            raw = envelope["data"]
            if raw["s"] not in source["symbols"]:
                continue
            assert raw["e"] == "trade" and envelope["stream"] == raw["s"].lower() + "@trade"
            counts["relevant_trade_messages"] += 1
            records.append((number, received, raw))
    assert decoded == source["decoded_bytes"]
    return records, disconnects, counts


def check_row(actual, expected):
    for field, value in expected.items():
        if value is None:
            assert pd.isna(actual[field])
        else:
            assert actual[field] == value, (field, actual[field], value)
    for field in actual.keys() - expected.keys():
        assert pd.isna(actual[field]), (field, actual[field])


def verify_event(records, disconnects, event, saved):
    cutoff = int(event["decision_ns"]) - 250_000_000
    beginning = cutoff - 10**9
    prefix = [(n, t, r) for n, t, r in records if r["s"] == event["symbol"] and t < cutoff]
    expected_rows, faults, fingerprints, high = [], set(), {}, None
    if any(d < cutoff for d in disconnects):
        faults.add("disconnect_before_cutoff")
    for number, received, raw in prefix:
        row = {"source_line": number, "receive_ns": received, "symbol": raw["s"], "counted": False}
        expected_rows.append(row)
        if any(type(raw.get(k)) is not int for k in ("t", "T", "E")) or type(raw.get("m")) is not bool:
            faults.add("invalid_native_schema")
            row["reason"] = "invalid_native_schema"
            continue
        uid, match, output = raw["t"], raw["T"] * 10**6, raw["E"] * 10**6
        row.update(trade_id=uid, match_ns=match, publication_ns=output, price=raw["p"], quantity=raw["q"],
                   execution_type=raw.get("X"), aggressor="sell" if raw["m"] else "buy")
        mark = tuple(str(raw.get(k)) for k in ("T", "E", "p", "q", "m", "X"))
        if uid in fingerprints:
            row["reason"] = "exact_duplicate" if fingerprints[uid] == mark else "conflicting_trade_id"
            if row["reason"] == "conflicting_trade_id":
                faults.add(row["reason"])
            continue
        fingerprints[uid] = mark
        if high is not None:
            if uid <= high:
                faults.add("regressing_trade_id")
            elif uid > high + 1:
                faults.add("interior_trade_id_gap")
        high = max(high, uid) if high is not None else uid
        if not beginning <= match < cutoff:
            row["reason"] = "outside_matching_interval"
            continue
        p, q = D(raw["p"]), D(raw["q"])
        if uid < 0 or not p.is_finite() or not q.is_finite() or p <= 0 or q <= 0:
            faults.add("invalid_window_trade")
            row["reason"] = "invalid_window_trade"
        elif match - output > 10**6 or max(match, output) - received > 10**6 or received - match > 250_000_000:
            faults.add("inconsistent_window_trade_clocks")
            row["reason"] = "inconsistent_window_trade_clocks"
        elif raw.get("X") != "MARKET":
            row["reason"] = "non_market_execution"
        else:
            row.update(counted=True, notional_usdt=str(p * q), reason="counted_past_market_execution")
    ledger_path = ROOT / saved["ledger_path"]
    assert sha(ledger_path) == saved["ledger_sha256"]
    actual_rows = pd.read_parquet(ledger_path).to_dict("records")
    assert len(actual_rows) == len(expected_rows)
    for actual, expected in zip(actual_rows, expected_rows, strict=True):
        check_row(actual, expected)
    counted = [r for r in expected_rows if r["counted"]]
    buy = sum((D(r["price"]) * D(r["quantity"]) for r in counted if r["aggressor"] == "buy"), D(0))
    sell = sum((D(r["price"]) * D(r["quantity"]) for r in counted if r["aggressor"] == "sell"), D(0))
    total = buy + sell
    aligned = buy if event["direction"] == 1 else sell
    gate = len(counted) >= 5 and total >= 5000 and 4 * aligned >= 3 * total
    expected = {"date": event["date"], "offset_minutes": event["offset_minutes"], "symbol": event["symbol"],
                "decision_ns": int(event["decision_ns"]), "direction": int(event["direction"]),
                "window_start_ns": beginning, "cutoff_ns": cutoff, "native_market_trade_count": len(counted),
                "buy_notional_usdt": str(buy), "sell_notional_usdt": str(sell), "total_notional_usdt": str(total),
                "aligned_notional_usdt": str(aligned), "aligned_fraction": str(aligned / total) if total else None,
                "source_integrity_ok": not faults, "integrity_problems": "|".join(sorted(faults)),
                "flow_gate": gate, "selected": gate and not faults,
                "reason": "source_integrity_unknown" if faults else "requires_response_replay" if gate else "insufficient_aligned_market_activity"}
    assert expected == saved["result"]
    return expected, len(prefix), len(counted)


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    results = json.loads((OUT / "screen_results.json").read_text())
    impl = json.loads((OUT / "screen_implementation.json").read_text())
    sources = json.loads((OUT / "source_manifest.json").read_text())
    parent_audit = json.loads((PARENT / "independent_verification.json").read_text())
    assert parent_audit["verified"] and parent_audit["results_sha256"] == spec["parent_results_sha256"]
    assert results["implementation_sha256"] == sha(OUT / "screen_implementation.json")
    assert impl["specification_sha256"] == sha(OUT / "specification.json")
    assert impl["source_manifest_sha256"] == sha(OUT / "source_manifest.json")
    for path, digest in impl["code_sha256"].items():
        assert sha(ROOT / path) == digest
    assert sources["acquisition_sha256"] == sha(ROOT / "research_scout/fetch_perp_shock_flow_20261002.py")
    indexed = {(s["date"], s["offset"]): s for s in sources["files"]}
    by_event = {(r["date"], r["symbol"], r["decision_ns"]): r for r in spec["events"]}
    summaries, counts, prefixes, counted = [], Counter(), 0, 0
    for window in results["windows"]:
        records, disconnects, native_counts = native(indexed[(window["date"], window["offset"])])
        assert dict(native_counts) == window["source_counts"]
        counts.update(native_counts)
        for saved in window["events"]:
            result = saved["result"]
            key = result["date"], result["symbol"], result["decision_ns"]
            expected, n, c = verify_event(records, disconnects, by_event[key], saved)
            summaries.append(expected)
            prefixes += n
            counted += c
    assert len(summaries) == len(by_event) == results["candidate_events"]
    assert dict(counts) == results["source_counts"]
    assert sha(OUT / "flow.parquet") == results["flow_sha256"]
    assert sha(OUT / "selected.parquet") == results["selected_sha256"]
    assert pd.read_parquet(OUT / "flow.parquet").to_dict("records") == summaries
    selected = [r for r in summaries if r["selected"]]
    assert pd.read_parquet(OUT / "selected.parquet").to_dict("records") == selected
    assert len(selected) == results["selected_events"]
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
             "source_files_verified": len(indexed), "source_counts": dict(counts),
             "candidate_events_verified": len(summaries), "selected_events_verified": len(selected),
             "precutoff_prefix_rows_verified": prefixes, "counted_window_executions_verified": counted,
             "maximum_numeric_difference": "0", "results_sha256": sha(OUT / "screen_results.json"),
             "parent_audit_sha256": sha(PARENT / "independent_verification.json"),
             "auditor_sha256": sha(Path(__file__)),
             "scope": "Independent native parsing, exact information/matching intervals, every available prefix row, ID/clock/disconnect integrity, MARKET-only directional Decimal aggregation and complete selection. No production signal/parser imports or future-return calculation.",
             "economic_implementations": 0, "future_returns_evaluated": False,
             "actual_execution_verified": False, "reliable_edge_established": False}
    with (OUT / "independent_verification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
