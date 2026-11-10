"""Independent native prefix audits plus the distinct three-role flow predicates."""

import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

import pandas as pd

from research_scout.audit_perp_shock_flow_20261002 import native, verify_event
from research_scout.prepare_market_lag_flow_20261002 import OUT, ROOT, sha


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    impl = json.loads((OUT / "implementation.json").read_text())
    results = json.loads((OUT / "screen_results.json").read_text())
    sources = json.loads((OUT / "source_manifest.json").read_text())
    assert sha(OUT / "specification.json") == impl["specification_sha256"]
    assert sha(OUT / "source_manifest.json") == impl["source_manifest_sha256"]
    assert sha(OUT / "implementation.json") == results["implementation_sha256"]
    for path, digest in {**impl["code_sha256"], **impl["parent_audits_sha256"]}.items():
        assert sha(ROOT / path) == digest
    helper = ROOT / "research_scout/audit_perp_shock_flow_20261002.py"
    prior = json.loads((ROOT / "research_scout/perp_shock_flow_hft_20261002/independent_verification.json").read_text())
    assert sha(helper) == prior["auditor_sha256"]
    indexed = {(s["date"], s["offset"]): s for s in sources["files"]}
    joint_rows, counts, prefix_rows, counted, components = [], Counter(), 0, 0, 0
    for window in results["windows"]:
        records, disconnects, native_counts = native(indexed[(window["date"], window["offset"])])
        assert dict(native_counts) == window["source_counts"]
        counts.update(native_counts)
        for bundle in window["bundles"]:
            event = bundle["event"]
            assert event in spec["events"]
            parts = {}
            for saved in bundle["components"]:
                expected, n, c = verify_event(records, disconnects, saved["event"], saved)
                assert expected["symbol"] not in parts
                assert all(expected[k] == event[k] for k in ("date", "offset_minutes", "decision_ns", "direction"))
                parts[expected["symbol"]] = expected
                prefix_rows += n
                counted += c
                components += 1
            assert set(parts) == {"BTCUSDT", "ETHUSDT", event["symbol"]}
            source_ok = all(r["source_integrity_ok"] for r in parts.values())
            activity = all(parts[s]["native_market_trade_count"] >= 5 and D(parts[s]["total_notional_usdt"]) >= 5000 for s in ("BTCUSDT", "ETHUSDT"))
            direction = all(D(parts[s]["aligned_notional_usdt"]) >= D(parts[s]["total_notional_usdt"]) * D("0.75") for s in ("BTCUSDT", "ETHUSDT"))
            target = parts[event["symbol"]]
            target_ok = target["native_market_trade_count"] >= 5 and D(target["total_notional_usdt"]) >= 5000
            selected = source_ok and activity and direction and target_ok
            reason = ("source_integrity_unknown" if not source_ok else "insufficient_leader_activity" if not activity
                      else "insufficient_aligned_leader_activity" if not direction else "insufficient_target_activity" if not target_ok
                      else "requires_response_replay")
            joint = {**event, "source_integrity_ok": source_ok, "leader_activity_gate": activity,
                     "leader_direction_gate": direction, "target_activity_gate": target_ok, "selected": selected, "reason": reason}
            assert joint == bundle["joint"]
            joint_rows.append(joint)
    assert dict(counts) == results["source_counts"] and components == results["component_checks"]
    for name, expected in (("joint", joint_rows), ("selected", [r for r in joint_rows if r["selected"]])):
        assert sha(OUT / f"{name}.parquet") == results[f"{name}_sha256"]
        assert pd.read_parquet(OUT / f"{name}.parquet").to_dict("records") == expected
    assert len(joint_rows) == results["candidate_events"] and sum(r["selected"] for r in joint_rows) == results["selected_events"]
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
             "source_files_verified": len(indexed), "source_counts": dict(counts),
             "precutoff_prefix_rows_verified": prefix_rows, "counted_window_executions_verified": counted,
             "components_verified": components, "selected_events_verified": results["selected_events"],
             "maximum_numeric_difference": "0", "results_sha256": sha(OUT / "screen_results.json"),
             "auditor_sha256": sha(Path(__file__)), "independent_prefix_helper_sha256": sha(helper),
             "scope": "Independent native source and every pre-cutoff execution/ID/clock/integrity record, exact Decimal directional notional, both leaders' activity/imbalance and target's activity-only gate. No production flow or joint-gate function called.",
             "economic_implementations": 0, "future_returns_evaluated": False,
             "actual_execution_verified": False, "reliable_edge_established": False}
    with (OUT / "independent_verification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
