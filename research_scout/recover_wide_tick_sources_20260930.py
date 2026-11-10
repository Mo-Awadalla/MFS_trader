"""Recover the exact two capped minutes with a larger explicit acquisition bound."""

import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import research_scout.fetch_wide_tick_20260930 as fetcher
from research_scout.prepare_wide_tick_20260930 import OUT


def main():
    original = json.loads((OUT / "manifest.json").read_text())
    failed = [r for r in original["files"] if not r["complete"]]
    assert len(failed) == 2
    assert all(r["error"] == "Frozen per-slice decoded bound exceeded" for r in failed)
    spec = copy.deepcopy(json.loads((OUT / "specification.json").read_text()))
    spec["download"].update(per_slice_decoded_cap=512_000_000, total_decoded_cap=1_024_000_000, workers=1)
    recovery = OUT / "acquisition_recovery_v1"
    recovery.mkdir(exist_ok=True)
    (recovery / "native").mkdir(exist_ok=True)
    if (recovery / "manifest.json").exists():
        raise RuntimeError("Preserve original recovery manifest")
    plan = {"created_at_utc": datetime.now(UTC).isoformat(), "dates": [r["date"] for r in failed],
            "reason": "Initial full-channel minutes exceeded 128 MB; retry the identical intervals and filters with a 512 MB per-minute limit. No strategy statistics or return outcomes have been computed.",
            "original_manifest_sha256": hashlib.sha256((OUT / "manifest.json").read_bytes()).hexdigest(),
            "new_download_bounds": spec["download"], "original_results_preserved": True}
    (recovery / "plan.json").write_text(json.dumps(plan, indent=2)+"\n")
    fetcher.OUT = recovery
    records = []
    for item in failed:
        result = fetcher.acquire(item["date"], spec)
        records.append(result)
        (recovery / "manifest.json").write_text(json.dumps({"files": records, "expected_files": 2}, indent=2)+"\n")
        print(json.dumps({"date": result["date"], "complete": result["complete"], "decoded_bytes": result.get("decoded_bytes"), "error": result.get("error")}), flush=True)
    merged = [r for r in original["files"] if r["complete"]] + records
    result = {"files": sorted(merged, key=lambda r: r["date"]), "expected_files": 12,
              "complete": len(merged) == 12 and all(r["complete"] for r in merged),
              "original_manifest_sha256": plan["original_manifest_sha256"],
              "recovery_manifest_sha256": hashlib.sha256((recovery / "manifest.json").read_bytes()).hexdigest(),
              "specification_sha256": hashlib.sha256((OUT / "specification.json").read_bytes()).hexdigest(),
              "recovery_plan_sha256": hashlib.sha256((recovery / "plan.json").read_bytes()).hexdigest(),
              "recovery_implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (OUT / "complete_manifest_v1.json").write_text(json.dumps(result, indent=2)+"\n")


if __name__ == "__main__":
    main()
