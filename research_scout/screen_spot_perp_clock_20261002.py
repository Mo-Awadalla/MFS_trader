"""Screen the fixed four-clock expansion with unchanged economic gates."""

import gzip
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from research.spot_perp_clock_supply import sample_native_at
from research.spot_perp_supply import screen_pair
from research_scout.prepare_spot_perp_clock_20261002 import OUT, ROOT, sha


def screen_window(job):
    day, offset = job["date"], job["offset"]
    counts, pair = Counter(), {}
    for venue in ("spot", "perpetual"):
        source = job[venue]
        path = ROOT / source["path"]
        assert source["complete"] and sha(path) == source["compressed_sha256"]
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            pair[venue] = sample_native_at(stream, day, venue, offset)
        counts.update({venue + "_" + key: value for key, value in pair[venue]["counts"].items()})
    rows = screen_pair(pair["spot"], pair["perpetual"], day)
    frame = pd.DataFrame(rows)
    frame["offset_minutes"] = offset
    target = OUT / "grids" / f"{day}_{offset:04d}.parquet"
    frame.to_parquet(target, index=False)
    return {"date": day, "offset_minutes": offset, "grid_rows": len(rows),
            "selected_events": int(frame.selected.sum()), "raw_eligible_grids": int(frame.raw_eligible.sum()),
            "spot_symbols": len(pair["spot"]["symbols"]), "perpetual_symbols": len(pair["perpetual"]["symbols"]),
            "source_counts": dict(counts), "reasons": dict(Counter(r["reason"] for r in rows)),
            "path": str(target.relative_to(ROOT)), "sha256": sha(target)}


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    manifest = json.loads((OUT / "source_manifest.json").read_text())
    assert manifest["complete"] and len(manifest["files"]) == 96
    assert sha(ROOT / spec["parent_specification"]) == spec["parent_specification_sha256"]
    frozen = {"frozen_at_utc": datetime.now(UTC).isoformat(),
              "specification_sha256": sha(OUT / "specification.json"),
              "manifest_sha256": sha(OUT / "source_manifest.json"),
              "runner_sha256": sha(Path(__file__)),
              "reader_sha256": sha(ROOT / "research/spot_perp_clock_supply.py"),
              "original_signal_module_sha256": sha(ROOT / "research/spot_perp_supply.py"),
              "tests_sha256": sha(ROOT / "tests/unit/test_spot_perp_clock_supply.py"),
              "future_returns_evaluated": False}
    with (OUT / "screen_implementation.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(frozen, indent=2) + "\n")
    (OUT / "grids").mkdir(exist_ok=True)
    sources = {(r["date"], r["offset"], r["venue"]): r for r in manifest["files"]}
    jobs = [{"date": day, "offset": offset,
             **{venue: sources[(day, offset, venue)] for venue in ("spot", "perpetual")}}
            for day in spec["dates"] for offset in spec["offset_minutes"]]
    windows, counts, reasons = [], Counter(), Counter()
    with ProcessPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(screen_window, job) for job in jobs]
        for task in as_completed(tasks):
            window = task.result()
            windows.append(window)
            counts.update(window["source_counts"])
            reasons.update(window["reasons"])
            print(json.dumps({k: window[k] for k in ("date", "offset_minutes", "grid_rows", "raw_eligible_grids", "selected_events")}), flush=True)
    windows.sort(key=lambda x: (x["date"], x["offset_minutes"]))
    selected = []
    for window in windows:
        frame = pd.read_parquet(ROOT / window["path"])
        selected.append(frame.loc[frame.selected])
    cohort = pd.concat(selected, ignore_index=True)
    cohort.to_parquet(OUT / "selected.parquet", index=False)
    result = {"windows": windows, "source_counts": dict(counts), "reasons": dict(reasons),
              "grid_rows": sum(w["grid_rows"] for w in windows), "selected_events": len(cohort),
              "raw_eligible_grids": sum(w["raw_eligible_grids"] for w in windows),
              "selected_dates": cohort.date.nunique(), "selected_sha256": sha(OUT / "selected.parquet"),
              "implementation_sha256": sha(OUT / "screen_implementation.json"),
              "economic_implementations": 0, "future_returns_evaluated": False,
              "independent_verification_complete": False, "actual_execution_verified": False,
              "selection_2025_opened": False, "reliable_edge_established": False}
    with (OUT / "screen_results.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("grid_rows", "selected_events", "selected_dates", "raw_eligible_grids", "source_counts")}), flush=True)


if __name__ == "__main__":
    main()
