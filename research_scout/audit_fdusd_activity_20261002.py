"""Independent parse and exact aggregation of all activity-screen executions."""

import calendar
import gzip
import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

import pandas as pd

from research_scout.prepare_fdusd_activity_20261002 import OUT, PARENT, ROOT, sha


def verify(source, window):
    day, offset = source["date"], source["offset"]
    midnight = calendar.timegm(datetime.strptime(day, "%Y-%m-%d").timetuple()) * 10**9
    start = midnight + offset * 60 * 10**9
    cutoff = start + 59_750_000_000
    path = ROOT / source["path"]
    ledger_path = ROOT / window["ledger_path"]
    assert source["complete"] and sha(path) == source["compressed_sha256"]
    assert sha(ledger_path) == window["ledger_sha256"]
    saved = pd.read_parquet(ledger_path).to_dict("records")
    rows, last, decoded = [], start - 1, 0
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        for number, line in enumerate(stream):
            decoded += len(line.encode("utf-8"))
            # This data set contains no explicit reconnects, duplicate IDs,
            # gaps or malformed trades. Prove those facts, never assume them.
            assert line.strip()
            stamp, payload = line.strip().split(" ", 1)
            parsed = datetime.fromisoformat(stamp[:19])
            received = midnight + (parsed.hour * 3600 + parsed.minute * 60 + parsed.second) * 10**9
            received += int(stamp[20:-1].ljust(9, "0"))
            assert stamp[:10] == day and start <= received < start + 60 * 10**9 and received >= last
            last = received
            envelope = json.loads(payload)
            item = envelope["data"]
            assert item["s"] in source["symbols"] and item["e"] == "trade"
            assert envelope["stream"] == item["s"].lower() + "@trade"
            assert all(type(item[k]) is int for k in ("T", "E", "t")) and type(item["m"]) is bool
            price, quantity = D(item["p"]), D(item["q"])
            assert all(v.is_finite() and v > 0 for v in (price, quantity)) and item["t"] >= 0
            match, published = item["T"] * 10**6, item["E"] * 10**6
            if received >= cutoff:
                reason = "unavailable_at_cutoff"
            elif match < start + 10 * 10**9:
                reason = "before_counting_interval"
            else:
                assert match <= published <= received + 10**6 and received - match <= 10**9
                reason = "matching_after_cutoff" if match >= cutoff else "counted_past_execution"
            counted = reason == "counted_past_execution"
            expected = {"date": day, "offset_minutes": offset, "symbol": item["s"], "source_line": number,
                        "receive_ns": received, "match_ns": match, "publication_ns": published,
                        "trade_id": item["t"], "price": item["p"], "quantity": item["q"],
                        "aggressor": "sell" if item["m"] else "buy", "counted": counted, "reason": reason}
            if counted:
                expected["notional_fdusd"] = str(price * quantity)
            actual = saved[len(rows)]
            for key, value in expected.items():
                assert actual[key] == value, (source, number, key, actual[key], value)
            if not counted:
                assert "notional_fdusd" not in actual or pd.isna(actual["notional_fdusd"])
            rows.append(expected)
    assert decoded == source["decoded_bytes"] and len(rows) == len(saved)
    counts = {"native_messages": len(rows)} if rows else {}
    assert counts == window["source_counts"]
    for symbol in source["symbols"]:
        known_ids = [r["trade_id"] for r in rows if r["symbol"] == symbol and r["receive_ns"] < cutoff]
        assert len(known_ids) == len(set(known_ids))
        assert all(b == a + 1 for a, b in zip(known_ids, known_ids[1:]))
    summaries = []
    for symbol in sorted(source["symbols"]):
        sums = {}
        for side in ("buy", "sell"):
            selected = [r for r in rows if r["symbol"] == symbol and r["aggressor"] == side and r["counted"]]
            sums[side + "_count"] = len(selected)
            sums[side + "_notional_fdusd"] = str(sum((D(r["price"]) * D(r["quantity"]) for r in selected), D(0)))
        qualifies = min(sums["buy_count"], sums["sell_count"]) >= 10
        qualifies &= min(D(sums["buy_notional_fdusd"]), D(sums["sell_notional_fdusd"])) >= 2000
        summaries.append({"date": day, "offset_minutes": offset, "symbol": symbol, **sums,
                          "source_integrity_ok": True, "integrity_problems": "", "activity_gate": qualifies,
                          "selected": qualifies,
                          "reason": "requires_queue_replay" if qualifies else "insufficient_two_sided_activity"})
    assert summaries == window["summaries"] and sum(r["selected"] for r in summaries) == window["selected"]
    return summaries, len(rows), sum(r["counted"] for r in rows)


def main():
    results = json.loads((OUT / "screen_results.json").read_text())
    implementation = json.loads((OUT / "screen_implementation.json").read_text())
    spec = json.loads((OUT / "specification.json").read_text())
    sources = json.loads((OUT / "source_manifest.json").read_text())
    assert results["implementation_sha256"] == sha(OUT / "screen_implementation.json")
    assert implementation["specification_sha256"] == sha(OUT / "specification.json")
    assert implementation["source_manifest_sha256"] == sha(OUT / "source_manifest.json")
    assert sources["acquisition_sha256"] == sha(ROOT / "research_scout/fetch_fdusd_activity_20261002.py")
    assert spec["parent_selection_sha256"] == sha(PARENT / "selected.parquet")
    assert spec["parent_audit_sha256"] == sha(PARENT / "independent_verification.json")
    for path, digest in implementation["code_sha256"].items():
        assert sha(ROOT / path) == digest
    indexed = {(s["date"], s["offset"]): s for s in sources["files"]}
    assert len(indexed) == len(spec["windows"]) == results["source_minutes"]
    summaries, native, counted = [], 0, 0
    for window in results["windows"]:
        rows, n, c = verify(indexed[(window["date"], window["offset"])], window)
        summaries.extend(rows)
        native += n
        counted += c
    assert sha(OUT / "activity.parquet") == results["summary_sha256"]
    assert sha(OUT / "selected.parquet") == results["selected_sha256"]
    assert pd.read_parquet(OUT / "activity.parquet").to_dict("records") == summaries
    assert pd.read_parquet(OUT / "selected.parquet").to_dict("records") == [r for r in summaries if r["selected"]]
    assert results["source_counts"] == {"native_messages": native}
    assert results["reasons"] == dict(Counter(r["reason"] for r in summaries))
    assert {(r["date"], r["offset_minutes"], r["symbol"]) for r in summaries} == {
        (r["date"], r["offset_minutes"], r["symbol"]) for r in spec["candidate_windows"]}
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
             "native_messages_verified": native, "counted_past_executions_verified": counted,
             "source_files_verified": len(indexed), "candidate_windows_verified": len(summaries),
             "selected_windows_verified": sum(r["selected"] for r in summaries),
             "source_decoded_bytes_verified": sum(r["decoded_bytes"] for r in indexed.values()),
             "maximum_numeric_difference": "0", "results_sha256": sha(OUT / "screen_results.json"),
             "auditor_sha256": sha(Path(__file__)),
             "scope": "Independent raw parsing, all ledger fields/clocks, complete expected candidate set, exact direction-specific native notional/count aggregation, selection and observed source-integrity checks. No production signal/parser import. Empty responses do not prove an instrument could not trade.",
             "economic_implementations": 0, "future_returns_evaluated": False,
             "actual_execution_verified": False, "reliable_edge_established": False}
    with (OUT / "independent_verification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
