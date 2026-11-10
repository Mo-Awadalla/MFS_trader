"""Stage native major-coin confirmation before broad all-symbol acquisition."""

import json
from datetime import UTC, datetime
from pathlib import Path

from research_scout.prepare_market_lag_coverage_20261002 import OUT as COVERAGE
from research_scout.prepare_market_lag_coverage_20261002 import ROOT, sha

HYPOTHESIS = ROOT / "research_scout/market_lag_hft_20261002"
OUT = ROOT / "research_scout/market_lag_native_hft_20261002/batch01"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = json.loads((COVERAGE / "screen_results.json").read_text())
    audit = json.loads((COVERAGE / "independent_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == sha(COVERAGE / "screen_results.json")
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "relationship": "Operational two-stage acquisition refinement, frozen before new native records. First download BTC/ETH only for the same first twelve chronological candidate minutes. The unchanged joint-leader gate can reject a minute without downloading target symbols. Only native-positive minutes progress to all-symbol quote acquisition; targets and strategy thresholds do not change. This saves bandwidth and does not rank by or inspect any future trading return.",
        "hypothesis_specification_sha256": sha(HYPOTHESIS / "specification.json"),
        "coverage_results_sha256": sha(COVERAGE / "screen_results.json"),
        "coverage_audit_sha256": sha(COVERAGE / "independent_verification.json"),
        "jobs": results["initial_native_jobs"], "queued_jobs": results["queued_native_jobs"],
        "download": {"exchange": "binance-futures", "slice_minutes": 1, "symbols": ["btcusdt", "ethusdt"],
                     "channels": ["bookTicker"], "workers": 2, "per_slice_decoded_cap": 96_000_000,
                     "request_deadline_seconds": 180, "authenticated": False, "paid_fallback": False},
        "screen": "Reconstruct native full books on the original quarter-second information grid; apply the unchanged complete BTC/ETH 20bp same-direction, 5bp spread, 2000-USDT depth and 250ms freshness gates. Preserve all grids, IDs, T/E/capture clocks and source lines. No normalized candidate is assumed to be a valid native signal. Independently audit native eligibility before target or execution promotion.",
        "economic_implementations": 0, "future_returns_evaluated": False,
        "selection_2025_opened": False, "reliable_edge_established": False,
        "preparation_sha256": sha(Path(__file__)),
    }
    with (OUT / "specification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"native_minutes": len(spec["jobs"]), "queued_minutes": len(spec["queued_jobs"]),
                      "specification_sha256": sha(OUT / "specification.json")}))


if __name__ == "__main__":
    main()
