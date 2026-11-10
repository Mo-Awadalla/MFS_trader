"""Screen every original native symbol/window after bounded full-state recovery."""

import argparse
import hashlib
import json
from datetime import UTC, datetime

import pandas as pd

from research.bybit_pair_screen import classify
from research_scout.prepare_bybit_funding_20261002 import OUT, ROOT
from research_scout.recover_bybit_funding_20261002 import OLD, binance_states


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    assert not (OUT/"all_states_screen_results.json").exists(), "Preserve the original full-state screen"
    code = ["research_scout/screen_all_bybit_states_20261002.py", "research/bybit_pair_screen.py",
            "tests/unit/test_bybit_pair_screen.py", "research_scout/recover_bybit_funding_20261002.py",
            "research/wide_tick_supply.py"]
    plan = {"created_at_utc": datetime.now(UTC).isoformat(),
            "native_states_sha256": sha(OUT/"native_states.parquet"),
            "recovery_plan_sha256": sha(OUT/"all_states_recovery_plan.json"),
            "code_sha256": {p: sha(ROOT/p) for p in code},
            "universe": "Exactly the original 8,857 native symbol/windows. Do not add CSV-only symbols or discard prior rejections.",
            "reconciliation": "Require original native sequence and publication freshness, fresh complete normalized state, and agreement with every known native funding rate, mark and funding time. Missing native fields may use only the last strictly earlier recovered full state. Field persistence/disconnect provenance remains to be audited before execution.",
            "thresholds": "Unchanged absolute Bybit rate >=14bp; same-time exact Binance counterpart; matched payment difference >28bp before spreads. No P&L here.",
            "strategy_pnl_tested": False}
    plan_path = OUT/"all_states_screen_implementation.json"
    if plan_path.exists():
        old = json.loads(plan_path.read_text())
        for key in ("native_states_sha256", "recovery_plan_sha256", "code_sha256"):
            assert old[key] == plan[key]
    else:
        plan_path.write_text(json.dumps(plan, indent=2)+"\n")
    if args.prepare:
        print(json.dumps({"prepared": True, "implementation_sha256": sha(plan_path)}), flush=True)
        return
    manifest = json.loads((OUT/"all_states_manifest.json").read_text())
    assert manifest["complete"] and len(manifest["files"]) == 12, "Recovery must finish first"
    data = pd.read_parquet(OUT/"native_states.parquet")
    assert len(data) == 8857 and not data.duplicated(["date", "hour", "symbol"]).any()
    records = data.to_dict("records")
    states = {}
    for source in manifest["files"]:
        assert sha(ROOT/source["extraction"]) == source["extraction_sha256"]
        recovered = json.loads((ROOT/source["extraction"]).read_text())
        assert recovered["source_sha256"] == source["sha256"]
        states[source["date"]] = recovered
    native = json.loads((OLD/"native_manifest.json").read_text())
    counterpart = {}
    for event in records:
        key = event["date"], event["hour"]
        if key not in counterpart:
            source = next(s for s in native["files"] if (s["date"], s["hour"]) == key)
            counterpart[key] = binance_states(source, event["settlement_ns"], event["decision_ns"])
    rows = []
    for event in records:
        recovered = states[event["date"]]
        hour = str(event["hour"])
        assert recovered["cutoffs_us"][hour] == event["decision_ns"]//1000
        bybit = recovered["states"][hour].get(event["symbol"])
        binance = counterpart[(event["date"], event["hour"])].get(event["symbol"])
        rows.append(classify(event, bybit, binance))
    frame = pd.DataFrame(rows)
    for key in frame:
        if key.endswith(("_ns", "_us", "_position", "_index")):
            frame[key] = pd.array([r.get(key) for r in rows], dtype="Int64")
    frame.to_parquet(OUT/"all_funding_pairs.parquet", index=False)
    selected = frame.loc[frame.eligible]
    result = {"events": len(frame), "unique_symbols": int(frame.symbol.nunique()),
              "source_files": len(manifest["files"]), "source_rows_inspected": manifest["rows_inspected"],
              "source_compressed_bytes": manifest["source_compressed_bytes"],
              "recovered_observations": int(frame.recovered_state.sum()),
              "bybit_valid": int(frame.bybit_valid.sum()), "large_bybit_rates": int(frame.large_bybit_rate.sum()),
              "usable_pairs": int(frame.usable.sum()), "pairs_above_cost_before_execution": len(selected),
              "outcomes": frame.reason.value_counts().to_dict(),
              "original_missing_rate_outcomes": frame.loc[frame.original_native_reason.eq("unobserved_funding_rate"), "reason"].value_counts().to_dict(),
              "pairs_sha256": sha(OUT/"all_funding_pairs.parquet"), "source_manifest_sha256": sha(OUT/"all_states_manifest.json"),
              "implementation_sha256": sha(plan_path), "native_full_field_provenance_verified": False,
              "lifecycle_checked": False, "actual_execution_verified": False, "strategy_pnl_tested": False,
              "reliable_edge_established": False, "selection_2025_opened": False}
    (OUT/"all_states_screen_results.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result), flush=True)
    print(selected[["date", "hour", "symbol", "bybit_funding_rate", "binance_funding_rate", "quoted_payment_difference_bps"]].to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
