"""Freeze and run the native spread/liquidity screen on every sampled minute."""

import gzip
import hashlib
import json
from datetime import UTC, datetime

import pandas as pd

from research.wide_tick_supply import screen
from research_scout.prepare_wide_tick_20260930 import OUT, ROOT


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if (OUT / "screen_results.json").exists():
        raise RuntimeError("Preserve original wide-spread screen")
    manifest = json.loads((OUT / "complete_manifest_v1.json").read_text())
    assert manifest["complete"] and len(manifest["files"]) == 12
    freeze = {"created_at_utc": datetime.now(UTC).isoformat(),
              "input_sha256": {name: sha(OUT / name) for name in ["specification.json", "source_semantics_addendum.json", "complete_manifest_v1.json"]},
              "implementation_sha256": {name: sha(ROOT / name) for name in ["research/wide_tick_supply.py", "research_scout/screen_wide_tick_20260930.py"]},
              "strategy_pnl_tested": False}
    (OUT / "screen_implementation.json").write_text(json.dumps(freeze, indent=2)+"\n")
    grids, summaries, diagnostics = [], [], []
    for item in manifest["files"]:
        path = ROOT / item["path"]
        assert sha(path) == item["compressed_sha256"]
        payload = gzip.decompress(path.read_bytes())
        assert hashlib.sha256(payload).hexdigest() == item["decoded_sha256"]
        rows, summary, diag = screen(payload.decode().splitlines(), item["date"])
        grids.extend({"date": item["date"], **row} for row in rows)
        summaries.extend({"date": item["date"], **row} for row in summary)
        diagnostics.append({"date": item["date"], **diag})
        print(json.dumps({"date": item["date"], "symbols": len(summary), "qualified": sum(r["qualified"] for r in summary), "selected": sum(r["selected"] for r in summary)}), flush=True)
    frame = pd.DataFrame(grids)
    for column in frame:
        if column.endswith("_ns") or column in {"source_line", "update_id"}:
            frame[column] = pd.array([row.get(column) for row in grids], dtype="Int64")
    summary = pd.DataFrame(summaries)
    frame.to_parquet(OUT / "grid_states.parquet", index=False)
    summary.to_parquet(OUT / "symbol_date_supply.parquet", index=False)
    selected = summary.loc[summary.selected].copy()
    selected.to_parquet(OUT / "selected.parquet", index=False)
    result = {"source_minutes": 12, "unique_symbols": int(summary.symbol.nunique()), "symbol_dates": len(summary),
              "grid_states": len(frame), "valid_grid_states": int(frame.valid.sum()), "supply_grid_states": int(frame.supply.sum()),
              "qualified_symbol_dates": int(summary.qualified.sum()), "selected_symbol_dates": len(selected),
              "grid_outcomes": frame.reason.value_counts().to_dict(), "symbol_date_outcomes": summary.reason.value_counts().to_dict(),
              "diagnostics": diagnostics, "source_decoded_bytes": sum(r["decoded_bytes"] for r in manifest["files"]),
              "source_compressed_bytes": sum(r["compressed_bytes"] for r in manifest["files"]),
              "output_sha256": {name: sha(OUT / name) for name in ["grid_states.parquet", "symbol_date_supply.parquet", "selected.parquet"]},
              "strategy_pnl_tested": False, "reliable_edge_established": False}
    (OUT / "screen_results.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({k: v for k, v in result.items() if k != "diagnostics"}), flush=True)
    print(selected.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
