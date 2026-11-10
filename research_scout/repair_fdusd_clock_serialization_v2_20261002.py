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
        # Parquet restores optional object fields as None, while DataFrame
        # construction uses NaN. Compare missingness, then exact observed data.
        left, right = original.drop(columns=clocks), exact.drop(columns=clocks)
        pd.testing.assert_frame_equal(left.isna(), right.isna())
        left = left.astype(object).where(left.notna(), None)
        right = right.astype(object).where(right.notna(), None)
        pd.testing.assert_frame_equal(left, right, check_dtype=False, check_exact=True)
        for column in clocks:
            for old_value, raw in zip(original[column], records, strict=True):
                value = raw.get(column)
                if value is None:
                    assert pd.isna(old_value)
                else:
                    error = abs(int(old_value) - value)
                    result["maximum_original_rounding_ns"] = max(result["maximum_original_rounding_ns"], error)
                    result["rounded_original_clock_values"] += int(error != 0)
        target = OUT / ("precise_grids_v2" if kind == "grid" else "precise_fx_v2") / original_path.name
        exact.to_parquet(target, index=False)
        restored = pd.read_parquet(target)
        for column in clocks:
            assert str(restored[column].dtype) == "Int64"
            pd.testing.assert_series_equal(restored[column], exact[column])
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
            "previous_plan_sha256": sha(OUT / "clock_serialization_repair_plan.json"),
            "previous_attempt": "Failed before completion because pandas None and NaN representations in optional object fields compared unequal. This attempt verifies identical missingness and exactly identical observed non-clock fields after canonicalizing missing representations. Prior script, plan and partial files are preserved.",
            "changes": "Rebuild native rows with unchanged frozen signal code and sources. Write precise_grids_v2/ and precise_fx_v2/ using nullable Int64 clocks from original Python integers. Preserve originals; compare non-clock missingness and observed fields, selected windows and source counts exactly.",
            "economic_configuration_changed": False, "future_returns_evaluated": False}
    with (OUT / "clock_serialization_repair_plan_v2.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(plan, indent=2) + "\n")
    for folder in ("precise_grids_v2", "precise_fx_v2"):
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
    manifest = {"complete": len(windows) == 60, "plan_sha256": sha(OUT / "clock_serialization_repair_plan_v2.json"),
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
