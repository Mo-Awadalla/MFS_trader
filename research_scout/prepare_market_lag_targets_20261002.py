"""Acquire contemporaneous targets only at independently verified causal shocks."""

import json
from datetime import UTC, datetime
from pathlib import Path

from research_scout.prepare_market_lag_native_20261002 import HYPOTHESIS, ROOT, sha
from research_scout.prepare_market_lag_native_20261002 import OUT as PARENT

OUT = ROOT / "research_scout/market_lag_targets_hft_20261002/batch01"


def main():
    audit = json.loads((PARENT / "independent_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == sha(PARENT / "screen_results.json")
    assert sha(PARENT / "admitted_leader_grids.parquet") == audit["admitted_leader_grids_sha256"]
    OUT.mkdir(parents=True, exist_ok=True)
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "relationship": "Second acquisition stage of the unchanged market-lag hypothesis. Only the native common-leader grids that also passed the exact contemporaneous normalized prefilter may admit targets; other times in these source minutes are not additional signals. No lagging-coin return or P&L has been evaluated for these sources.",
        "hypothesis_specification_sha256": sha(HYPOTHESIS / "specification.json"),
        "native_parent_results_sha256": sha(PARENT / "screen_results.json"),
        "native_parent_audit_sha256": sha(PARENT / "independent_verification.json"),
        "admitted_leader_grids_path": str((PARENT / "admitted_leader_grids.parquet").relative_to(ROOT)),
        "admitted_leader_grids_sha256": sha(PARENT / "admitted_leader_grids.parquet"),
        "jobs": audit["target_acquisition_jobs"],
        "download": {"exchange": "binance-futures", "slice_minutes": 1, "channels": ["bookTicker"],
                     "all_symbols": True, "workers": 2, "per_slice_decoded_cap": 384_000_000,
                     "request_deadline_seconds": 240, "authenticated": False, "paid_fallback": False},
        "signal_consistency": "Match both BTC/ETH endpoint native price, quantity, ID, T/E and capture fields to the original audited two-symbol sources before using any target. All target clocks and source integrity must pass the unchanged parent gate.",
        "targets_and_selection": "Use the original hypothesis exclusions, quality gates, >2bp cost budget and 20bp gap, ranking by descending budget then symbol; at most one per grid and 30s global decision cooldown within each disjoint source minute. No grid enters solely because its minute was selected by a later event.",
        "progression": "No profitability computation in this stage. Any selected target needs the already declared causal native aggressor-flow confirmation and separately frozen order-rule/execution review. The other 37 chronological candidate minutes remain queued for native-leader screening, regardless of this batch's outcomes.",
        "economic_implementations": 0, "future_returns_evaluated": False, "selection_2025_opened": False,
        "reliable_edge_established": False, "preparation_sha256": sha(Path(__file__)),
    }
    with (OUT / "specification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"target_source_minutes": len(spec["jobs"]), "specification_sha256": sha(OUT / "specification.json")}))


if __name__ == "__main__":
    main()
