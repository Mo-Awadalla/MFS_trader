"""Freeze code and source hashes, then run the declared causal supply screen."""

import gzip
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from research.spot_perp_supply import sample_native, screen_pair
from research_scout.prepare_spot_perp_20261002 import OUT, PARENT, ROOT, sha


def main():
    spec_path = OUT / "specification.json"
    spec = json.loads(spec_path.read_text())
    spot_manifest = json.loads((OUT / "spot_manifest.json").read_text())
    perpetual_manifest = json.loads(PARENT.read_text())
    assert spot_manifest["complete"] and perpetual_manifest["complete"]
    assert sha(PARENT) == spec["perpetual_manifest_sha256"]
    source = {
        "spot": {r["date"]: r for r in spot_manifest["files"]},
        "perpetual": {r["date"]: r for r in perpetual_manifest["files"]},
    }
    frozen = {
        "frozen_at_utc": datetime.now(UTC).isoformat(), "specification_sha256": sha(spec_path),
        "runner_sha256": sha(Path(__file__)),
        "module_sha256": sha(ROOT / "research/spot_perp_supply.py"),
        "tests_sha256": sha(ROOT / "tests/unit/test_spot_perp_supply.py"),
        "spot_manifest_sha256": sha(OUT / "spot_manifest.json"),
        "perpetual_manifest_sha256": sha(PARENT),
        "clock_clarification": "All age gates are evaluated at each original grid decision, including its 250ms feed delay. Blank disconnect markers lack a timestamp; pending unobserved grid states are conservatively cleared until the next native update.",
        "future_returns_evaluated": False,
    }
    with (OUT / "screen_implementation.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(frozen, indent=2) + "\n")
    rows, counts, days = [], Counter(), []
    for day in spec["dates"]:
        pair = {}
        for venue in ("spot", "perpetual"):
            record = source[venue][day]
            path = ROOT / record["path"]
            assert record["complete"] and sha(path) == record["compressed_sha256"]
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                pair[venue] = sample_native(stream, day, venue)
            counts.update({f"{venue}_{key}": value for key, value in pair[venue]["counts"].items()})
        daily = screen_pair(pair["spot"], pair["perpetual"], day)
        rows.extend(daily)
        info = {"date": day, "spot_usdt_symbols": len(pair["spot"]["symbols"]),
                "perpetual_usdt_symbols": len(pair["perpetual"]["symbols"]),
                "exact_symbol_intersection": len(pair["spot"]["symbols"] & pair["perpetual"]["symbols"]),
                "grid_rows": len(daily), "selected": sum(r["selected"] for r in daily),
                "reasons": dict(Counter(r["reason"] for r in daily))}
        days.append(info)
        print(json.dumps(info), flush=True)
    frame = pd.DataFrame(rows)
    frame.to_parquet(OUT / "grid_states.parquet", index=False)
    selected = frame.loc[frame.selected]
    selected.to_parquet(OUT / "selected.parquet", index=False)
    result = {"source_counts": dict(counts), "dates": days,
              "grid_rows": len(frame), "selected_events": len(selected),
              "selected_dates": selected.date.nunique(),
              "raw_eligible_grids": int(frame.raw_eligible.sum()),
              "reasons": dict(Counter(r["reason"] for r in rows)),
              "grid_states_sha256": sha(OUT / "grid_states.parquet"),
              "selected_sha256": sha(OUT / "selected.parquet"),
              "screen_implementation_sha256": sha(OUT / "screen_implementation.json"),
              "economic_implementations": 0, "future_returns_evaluated": False,
              "independent_verification_complete": False, "actual_execution_verified": False,
              "selection_2025_opened": False, "reliable_edge_established": False}
    with (OUT / "screen_results.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("grid_rows", "selected_events", "selected_dates", "raw_eligible_grids", "source_counts")}), flush=True)


if __name__ == "__main__":
    main()
