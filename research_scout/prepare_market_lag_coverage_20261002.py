"""Freeze the full-day acquisition preselector; final native thresholds stay fixed."""

import json
from datetime import UTC, datetime
from pathlib import Path

from research_scout.prepare_market_lag_20261002 import OUT as PARENT
from research_scout.prepare_market_lag_20261002 import ROOT, sha

OUT = ROOT / "research_scout/market_lag_coverage_hft_20261002"


def main():
    OUT.mkdir(exist_ok=True)
    audit = json.loads((PARENT / "independent_verification.json").read_text())
    assert audit["verified"] and audit["coherent_leader_grids"] == 0
    files = []
    for month in range(7, 13):
        day = f"2024-{month:02d}-01"
        path = ROOT / "research_scout/liquidation_event_20260930/raw/book_snapshot_5" / day / "BTCUSDT.csv.gz"
        manifest = json.loads(path.with_suffix(path.suffix + ".json").read_text())
        digest = sha(path)
        assert digest == manifest["sha256"] and path.stat().st_size == manifest["bytes"]
        files.append({"date": day, "path": str(path.relative_to(ROOT)), "compressed_sha256": digest,
                      "compressed_bytes": path.stat().st_size, "original_manifest_path": str(path.with_suffix(path.suffix + ".json").relative_to(ROOT))})
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "relationship": "Broader development coverage for the unchanged coherent BTC/ETH-lag hypothesis. The initial 60 sparse minute samples contained zero common moves. This locates possible shock MINUTES in six full cached BTC days; it does not change the final 20bp joint-leader rule or target cost budget, and does not evaluate an economic strategy.",
        "parent_specification_sha256": sha(PARENT / "specification.json"),
        "parent_audit_sha256": sha(PARENT / "independent_verification.json"),
        "sources": files,
        "decisions": "Every 250ms from second 2.00 through 58.75 in every minute of each listed UTC day, preserving parent in-minute signal timing. Latest normalized top-five snapshot strictly before d-250ms and d-1.25s, using local capture microseconds only; ages <=1s. Require finite positive uncrossed bid/ask. No future row, return or execution outcome is used.",
        "prefilter": "Select a possible acquisition minute if both BTC bid and ask moved >=+15bp, or both <=-15bp, between the two prior captures. This intentionally looser 15bp acquisition threshold allows normalized snapshot aggregation/clock differences; it is NEVER an entry rule. No normalized timestamp is called native matching T, and missing disconnect/sequence data cannot establish final eligibility. Native BTC AND ETH must still each pass every unchanged 20bp/freshness/depth/spread gate before any target is considered.",
        "capture_precision": "Normalized local_timestamp is retained as int64 microseconds. Exclude records at the cutoff microsecond, even if a native higher-precision time could precede it. Source rows are recorded for later native verification. No claim of complete full-day native BBO recall from normalized snapshots.",
        "numeric_guard": "Use vectorized float64 only for acquisition candidates; separately mark any return within 1e-8 bp of the 15bp boundary for exact Decimal reconciliation before final minute selection. Preserve all passing grids and source-row references, then exact-check their threshold, ordering, freshness and spread validity.",
        "native_acquisition_if_any": "Distinct candidate minutes in chronological order, initial batch at most twelve minutes. Fetch all-symbol Binance perpetual native bookTicker for each one-minute slice, then run the unchanged parent information-time and coherent-major/lag predicates. Preserve all remaining minutes as queued, not failed. Freeze exact job list and byte/time caps before network requests. No trade/response outcomes yet.",
        "selection_2025_opened": False, "future_returns_evaluated": False,
        "economic_implementations": 0, "actual_execution_verified": False,
        "reliable_edge_established": False, "preparation_sha256": sha(Path(__file__)),
    }
    with (OUT / "specification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"source_files": len(files), "compressed_bytes": sum(r["compressed_bytes"] for r in files),
                      "specification_sha256": sha(OUT / "specification.json")}))


if __name__ == "__main__":
    main()
