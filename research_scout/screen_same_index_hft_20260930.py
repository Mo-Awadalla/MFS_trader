"""Screen all preset paired quote states without opening future return labels."""

import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from research.crypto_symbol_cache import digest
from research.same_index_supply import Quotes, decision
from research_scout.prepare_same_index_hft_20260930 import OUT, ROOT


def main():
    if (OUT/"supply_results.json").exists():
        raise RuntimeError("Preserve frozen source screen")
    spec = json.loads((OUT/"specification.json").read_text())
    manifest = json.loads((OUT/"quote_manifest.json").read_text())
    assert len(manifest["files"]) == manifest["expected_files"] == 72
    assert digest(OUT/"specification.json") == manifest["specification_sha256"]
    source = {(r["date"], r["symbol"]): r for r in manifest["files"]}
    freeze = {"created_at_utc": datetime.now(UTC).isoformat(), "protocol_sha256": digest(OUT/"specification.json"),
              "manifest_sha256": digest(OUT/"quote_manifest.json"),
              "implementation_sha256": {p: digest(ROOT/p) for p in ["research/same_index_supply.py", "research_scout/screen_same_index_hft_20260930.py"]},
              "future_returns_evaluated": False}
    (OUT/"supply_implementation.json").write_text(json.dumps(freeze, indent=2)+"\n")
    rows, summaries, attempts, failures = [], [], [], []
    for day in spec["dates"]:
        first = pd.Timestamp(day+" 09:32", tz="America/New_York").value
        grid = first+np.arange(600, dtype=np.int64)*250_000_000
        for symbols in spec["pairs"]:
            pair = "_".join(symbols)
            items = [source[(day, symbol)] for symbol in symbols]
            if not all(r["complete"] for r in items):
                failures.append({"date": day, "pair": pair, "reason": "unknown_source", "decisions": 600})
                continue
            frames = []
            for item in items:
                p = ROOT/item["path"]
                assert digest(p) == item["sha256"]
                frames.append(Quotes(pd.read_parquet(p)))
            local, last = [], None
            for instant in grid:
                row = {"date": day, "pair": pair, **decision(*frames, int(instant))}
                local.append(row)
                if row["eligible"] and (last is None or int(instant)-last >= 60_000_000_000):
                    attempts.append(row.copy())
                    last = int(instant)
            rows.extend(local)
            frame = pd.DataFrame(local)
            sized = frame.loc[frame.get("net_if_converged", pd.Series(np.nan, index=frame.index)).notna()]
            summary = {"date": day, "pair": pair, "decisions": len(local), "eligible_decisions": int(frame.eligible.sum()),
                       "hypothetical_attempts": sum(r["date"] == day and r["pair"] == pair for r in attempts),
                       "maximum_budget_bps": float(sized.budget_bps.max()) if len(sized) else None,
                       "outcomes": frame.reason.value_counts().to_dict()}
            summaries.append(summary)
            print(json.dumps(summary), flush=True)
    for name, records in [("supply_decisions", rows), ("supply_attempts", attempts)]:
        frame = pd.DataFrame(records)
        for field in frame:
            if field.endswith("_ns") or field in {"index_a", "index_b", "quantity_a", "quantity_b"}:
                frame[field] = pd.array([r.get(field) for r in records], dtype="Int64")
        frame.to_parquet(OUT/f"{name}.parquet", index=False)
    advance = []
    totals = {}
    for symbols in spec["pairs"]:
        pair = "_".join(symbols)
        selected = [r for r in attempts if r["pair"] == pair]
        totals[pair] = {"attempts": len(selected), "dates": len({r["date"] for r in selected}),
                        "eligible_decisions": sum(r["eligible_decisions"] for r in summaries if r["pair"] == pair),
                        "unknown_source_dates": sum(r["pair"] == pair for r in failures)}
        if len(selected) >= 12 and totals[pair]["dates"] >= 6 and not totals[pair]["unknown_source_dates"]:
            advance.append(pair)
    result = {"daily_summaries": summaries, "totals": totals, "failed_sources": failures,
              "advance_to_economics": advance, "future_returns_evaluated": False,
              "economic_implementations": 0, "actual_execution_verified": False, "reliable_edge_established": False}
    (OUT/"supply_results.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({"totals": totals, "advance_to_economics": advance}))


if __name__ == "__main__":
    main()
