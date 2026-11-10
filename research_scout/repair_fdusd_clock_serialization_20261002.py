"""Rebuild optional nanosecond columns from raw integers; preserve originals."""

import gzip
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from research.fdusd_maker_supply import sample
from research.precise_ledger import ledger_frame
from research_scout.prepare_fdusd_maker_20261002 import OUT, ROOT, sha


def repair(job):
    source, old = job
    source_path = ROOT / source["path"]
    assert sha(source_path) == source["compressed_sha256"]
    with gzip.open(source_path, "rt", encoding="utf-8") as stream:
        rows, summaries, fx, counts = sample(stream, source["date"], source["offset"])
    assert summaries == old["symbol_windows"] and counts == old["source_counts"]
    result = {"date": source["date"], "offset_minutes": source["offset"],
              "non_clock_fields_identical": True, "maximum_original_rounding_ns": 0,
              "rounded_original_clock_values": 0}
    for kind, records in (("grid", rows), ("fx", fx)):
        original_path = ROOT / old[kind + "_path"]
        assert sha(original_path) == old[kind + "_sha256"]
        original, exact = pd.read_parquet(original_path), ledger_frame(records)
        clocks = [c for c in exact.columns if c.endswith("_ns")]
        pd.testing.assert_frame_equal(original.drop(columns=clocks), exact.drop(columns=clocks), check_dtype=False)
        for column in clocks:
            for old_value, raw in zip(original[column], records, strict=True):
                value = raw.get(column)
                if value is None:
                    assert pd.isna(old_value)
                else:
                    error = abs(int(old_value) - value)
                    result["maximum_original_rounding_ns"] = max(result["maximum_original_rounding_ns"], error)
                    result["rounded_original_clock_values"] += int(error != 0)
        target = OUT / ("precise_grids" if kind == "grid" else "precise_fx") / original_path.name
        exact.to_parquet(target, index=False)
        restored = pd.read_parquet(target)
        for column in clocks:
            assert str(restored[column].dtype) == "Int64"
            assert restored[column].tolist() == exact[column].tolist()
        result.update({kind + "_original_sha256": old[kind + "_sha256"],
                       kind + "_path": str(target.relative_to(ROOT)), kind + "_sha256": sha(target)})
    return result


def main():
    results = json.loads((OUT / "screen_results.json").read_text())
    spec = json.loads((OUT / "specification.json").read_text())
    impl = json.loads((OUT / "screen_implementation.json").read_text())
    for path, digest in impl["code_sha256"].items():
        assert sha(ROOT / path) == digest
    plan = {"created_at_utc": datetime.now(UTC).isoformat(),
            "reason": "Pandas inferred float64 for optional receive_ns columns when some symbols had not yet been observed. The independent audit caught rounded saved clocks. All causal decisions were computed using original integer clocks before serialization.",
            "original_results_sha256": sha(OUT / "screen_results.json"),
            "original_implementation_sha256": sha(OUT / "screen_implementation.json"),
            "original_failed_auditor_sha256": sha(ROOT / "research_scout/audit_fdusd_maker_20261002.py"),
            "repair_sha256": sha(Path(__file__)), "exact_frame_helper_sha256": sha(ROOT / "research/precise_ledger.py"),
            "changes": "Rebuild native rows with the unchanged frozen signal code and source files. Write new precise_grids/ and precise_fx/ files using nullable Int64 clocks directly from original Python integers. Preserve every original file and compare every non-clock field, selected window and source count exactly.",
            "economic_configuration_changed": False, "future_returns_evaluated": False}
    with (OUT / "clock_serialization_repair_plan.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(plan, indent=2) + "\n")
    for folder in ("precise_grids", "precise_fx"):
        (OUT / folder).mkdir(exist_ok=True)
    sources = {(r["date"], r["offset"]): r for r in spec["sources"]}
    jobs = [(sources[(w["date"], w["offset_minutes"])], w) for w in results["windows"]]
    windows = []
    with ProcessPoolExecutor(max_workers=2) as pool:
        pending = [pool.submit(repair, job) for job in jobs]
        for task in as_completed(pending):
            window = task.result()
            windows.append(window)
            print(json.dumps({k: window[k] for k in ("date", "offset_minutes", "maximum_original_rounding_ns", "rounded_original_clock_values")}), flush=True)
    manifest = {"complete": len(windows) == 60, "plan_sha256": sha(OUT / "clock_serialization_repair_plan.json"),
                "original_results_sha256": sha(OUT / "screen_results.json"),
                "windows": sorted(windows, key=lambda r: (r["date"], r["offset_minutes"])),
                "maximum_original_rounding_ns": max(r["maximum_original_rounding_ns"] for r in windows),
                "rounded_original_clock_values": sum(r["rounded_original_clock_values"] for r in windows),
                "all_non_clock_fields_identical": all(r["non_clock_fields_identical"] for r in windows),
                "all_selected_windows_unchanged": True, "economic_configuration_changed": False}
    with (OUT / "clock_serialization_repair.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: v for k, v in manifest.items() if k != "windows"}), flush=True)


if __name__ == "__main__":
    main()
