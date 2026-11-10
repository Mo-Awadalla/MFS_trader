"""Screen cached native books for the predeclared FDUSD spread supply."""

import gzip
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from research.fdusd_maker_supply import sample
from research_scout.prepare_fdusd_maker_20261002 import OUT, ROOT, sha


def screen_source(source):
    day, offset = source["date"], source["offset"]
    path = ROOT / source["path"]
    assert source["complete"] and sha(path) == source["compressed_sha256"]
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        rows, windows, fx, counts = sample(stream, day, offset)
    tag = f"{day}_{offset:04d}"
    frame = pd.DataFrame(rows)
    frame.to_parquet(OUT / "grids" / f"{tag}.parquet", index=False)
    pd.DataFrame(fx).to_parquet(OUT / "fx" / f"{tag}.parquet", index=False)
    return {"date": day, "offset_minutes": offset, "source_counts": counts,
            "grid_rows": len(rows), "symbol_windows": windows,
            "selected_windows": sum(r["selected"] for r in windows),
            "valid_grids": sum(r["valid"] for r in rows), "supply_grids": sum(r["supply"] for r in rows),
            "reasons": dict(Counter(r["reason"] for r in rows)),
            "grid_path": str((OUT / "grids" / f"{tag}.parquet").relative_to(ROOT)),
            "grid_sha256": sha(OUT / "grids" / f"{tag}.parquet"),
            "fx_path": str((OUT / "fx" / f"{tag}.parquet").relative_to(ROOT)),
            "fx_sha256": sha(OUT / "fx" / f"{tag}.parquet")}


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    for record in spec["parent_source_audits"]:
        path = ROOT / record["path"]
        assert sha(path) == record["sha256"] and json.loads(path.read_text())["verified"]
    for record in spec["sources"]:
        assert sha(ROOT / record["parent_manifest"]) == record["parent_manifest_sha256"]
    frozen = {"frozen_at_utc": datetime.now(UTC).isoformat(),
              "specification_sha256": sha(OUT / "specification.json"),
              "code_sha256": {str(p.relative_to(ROOT)): sha(p) for p in (
                  Path(__file__), ROOT / "research/fdusd_maker_supply.py", ROOT / "research/spot_perp_supply.py",
                  ROOT / "tests/unit/test_fdusd_maker_supply.py")},
              "focused_tests_passed": 7, "economic_implementations": 0,
              "future_returns_evaluated": False}
    with (OUT / "screen_implementation.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(frozen, indent=2) + "\n")
    for folder in ("grids", "fx"):
        (OUT / folder).mkdir(exist_ok=True)
    windows, counts, reasons = [], Counter(), Counter()
    with ProcessPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(screen_source, source) for source in spec["sources"]]
        for task in as_completed(tasks):
            window = task.result()
            windows.append(window)
            counts.update(window["source_counts"])
            reasons.update(window["reasons"])
            print(json.dumps({k: window[k] for k in ("date", "offset_minutes", "grid_rows", "valid_grids", "supply_grids", "selected_windows")}), flush=True)
    windows.sort(key=lambda r: (r["date"], r["offset_minutes"]))
    summaries = pd.DataFrame([r for window in windows for r in window["symbol_windows"]])
    summaries.to_parquet(OUT / "symbol_window_supply.parquet", index=False)
    selected = summaries.loc[summaries.selected]
    selected.to_parquet(OUT / "selected.parquet", index=False)
    results = {"windows": windows, "source_counts": dict(counts), "reasons": dict(reasons),
               "sampled_minutes": len(windows), "symbol_windows": len(summaries),
               "symbols": summaries.symbol.nunique(), "grid_rows": sum(r["grid_rows"] for r in windows),
               "valid_grids": sum(r["valid_grids"] for r in windows), "supply_grids": sum(r["supply_grids"] for r in windows),
               "selected_windows": len(selected), "selected_symbols": sorted(selected.symbol.unique()),
               "selected_dates": selected.date.nunique(), "selected_sha256": sha(OUT / "selected.parquet"),
               "summaries_sha256": sha(OUT / "symbol_window_supply.parquet"),
               "implementation_sha256": sha(OUT / "screen_implementation.json"),
               "economic_implementations": 0, "future_returns_evaluated": False,
               "independent_audit_complete": False, "actual_execution_verified": False,
               "selection_2025_opened": False, "reliable_edge_established": False}
    with (OUT / "screen_results.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(results, indent=2) + "\n")
    print(json.dumps({k: results[k] for k in ("source_counts", "sampled_minutes", "symbols", "symbol_windows", "grid_rows", "supply_grids", "selected_windows", "selected_symbols", "selected_dates")}), flush=True)


if __name__ == "__main__":
    main()
