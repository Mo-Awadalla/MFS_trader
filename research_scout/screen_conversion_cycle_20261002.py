"""Run the frozen conversion identity screen on cached full native books."""

import gzip
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

import pandas as pd

from research.conversion_cycle_supply import sample
from research.precise_ledger import ledger_frame
from research_scout.prepare_conversion_cycle_20261002 import OUT, ROOT, SOURCE_SCREEN, sha


def run_source(source):
    path = ROOT / source["path"]
    assert source["complete"] and sha(path) == source["compressed_sha256"]
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        rows, quotes, counts, cycles = sample(stream, source["date"], source["offset"])
    tag = f"{source['date']}_{source['offset']:04d}.parquet"
    quote_path, route_path = OUT / "quotes" / tag, OUT / "routes" / tag
    ledger_frame(quotes).to_parquet(quote_path, index=False)
    ledger_frame(rows).to_parquet(route_path, index=False)
    best = max((D(r["base_budget_bps"]) for r in rows if r.get("depth_gate")), default=None)
    return {"date": source["date"], "offset": source["offset"], "source_counts": counts,
            "cycles": cycles, "route_rows": len(rows), "quote_rows": len(quotes),
            "valid_books": sum(r["valid_books"] for r in rows), "supply_rows": sum(r["supply"] for r in rows),
            "selected": [r for r in rows if r["selected"]], "reasons": dict(Counter(r["reason"] for r in rows)),
            "best_depth_eligible_budget_bps": str(best) if best is not None else None,
            "quotes_path": str(quote_path.relative_to(ROOT)), "quotes_sha256": sha(quote_path),
            "routes_path": str(route_path.relative_to(ROOT)), "routes_sha256": sha(route_path)}


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    assert spec["parent_full_source_audit_sha256"] == sha(SOURCE_SCREEN / "independent_verification.json")
    frozen = {"frozen_at_utc": datetime.now(UTC).isoformat(), "specification_sha256": sha(OUT / "specification.json"),
              "code_sha256": {str(p.relative_to(ROOT)): sha(p) for p in (
                  Path(__file__), ROOT / "research/conversion_cycle_supply.py", ROOT / "research/precise_ledger.py",
                  ROOT / "research/spot_perp_supply.py", ROOT / "tests/unit/test_conversion_cycle_supply.py")},
              "focused_tests_passed": 7, "economic_implementations": 0, "future_returns_evaluated": False}
    with (OUT / "screen_implementation.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(frozen, indent=2) + "\n")
    for name in ("quotes", "routes"):
        (OUT / name).mkdir(exist_ok=True)
    windows, counts, reasons = [], Counter(), Counter()
    with ProcessPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(run_source, source) for source in spec["sources"]]
        for task in as_completed(jobs):
            row = task.result()
            windows.append(row)
            counts.update(row["source_counts"])
            reasons.update(row["reasons"])
            print(json.dumps({k: row[k] for k in ("date", "offset", "cycles", "route_rows", "supply_rows", "best_depth_eligible_budget_bps")}), flush=True)
    windows.sort(key=lambda r: (r["date"], r["offset"]))
    selected = [r for w in windows for r in w["selected"]]
    pd.DataFrame(selected).to_parquet(OUT / "selected.parquet", index=False)
    best = max((D(w["best_depth_eligible_budget_bps"]) for w in windows if w["best_depth_eligible_budget_bps"] is not None), default=None)
    result = {"windows": windows, "source_counts": dict(counts), "reasons": dict(reasons),
              "source_minutes": len(windows), "route_rows": sum(w["route_rows"] for w in windows),
              "quote_rows": sum(w["quote_rows"] for w in windows), "valid_books": sum(w["valid_books"] for w in windows),
              "supply_rows": sum(w["supply_rows"] for w in windows), "selected_events": len(selected),
              "best_depth_eligible_budget_bps": str(best) if best is not None else None,
              "selected_sha256": sha(OUT / "selected.parquet"),
              "implementation_sha256": sha(OUT / "screen_implementation.json"),
              "economic_implementations": 0, "future_returns_evaluated": False,
              "independent_audit_complete": False, "actual_execution_verified": False,
              "selection_2025_opened": False, "reliable_edge_established": False}
    with (OUT / "screen_results.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "windows"}), flush=True)


if __name__ == "__main__":
    main()
