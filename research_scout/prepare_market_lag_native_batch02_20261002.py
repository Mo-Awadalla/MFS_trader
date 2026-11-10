"""Continue all previously queued acquisition minutes without outcome ranking."""

import json
from datetime import UTC, datetime
from pathlib import Path

from research_scout.prepare_market_lag_native_20261002 import COVERAGE, HYPOTHESIS, ROOT, sha
from research_scout.prepare_market_lag_native_20261002 import OUT as FIRST

OUT = ROOT / "research_scout/market_lag_native_hft_20261002/batch02"


def main():
    coverage = json.loads((COVERAGE / "screen_results.json").read_text())
    initial = json.loads((FIRST / "specification.json").read_text())
    assert coverage["queued_native_jobs"] == initial["queued_jobs"]
    audit = json.loads((COVERAGE / "independent_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == sha(COVERAGE / "screen_results.json")
    OUT.mkdir(parents=True, exist_ok=True)
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "relationship": "Complete the other 37 minutes already queued by the fixed whole-day normalized prefilter. All queued minutes, chronological order, unchanged BTC/ETH native thresholds and target gates. No selection based on the first batch's target budgets or any trading outcome.",
        "hypothesis_specification_sha256": sha(HYPOTHESIS / "specification.json"),
        "coverage_results_sha256": sha(COVERAGE / "screen_results.json"),
        "coverage_audit_sha256": sha(COVERAGE / "independent_verification.json"),
        "first_batch_specification_sha256": sha(FIRST / "specification.json"),
        "causal_alignment_specification_sha256": sha(FIRST / "causal_selection_specification_v2.json"),
        "jobs": coverage["queued_native_jobs"], "queued_jobs": [],
        "download": initial["download"],
        "screen": initial["screen"],
        "causal_alignment": "As in the audited first batch, native-positive grids are diagnostic only until joined to the exact same (date, offset_minutes, decision_ns) normalized prefilter candidate. A selected minute never authorizes earlier or other grid times. Any all-symbol target acquisition and final target selection must use only this causally aligned set.",
        "progression": "Native leader qualification first, then independently audited all-symbol target budgets only in causally positive minutes. Native trade confirmation and separately frozen response replay follow only if targets survive. Do not read later outcomes to rank, stop or select candidate minutes.",
        "economic_implementations": 0, "future_returns_evaluated": False, "selection_2025_opened": False,
        "reliable_edge_established": False, "preparation_sha256": sha(Path(__file__)),
    }
    with (OUT / "specification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"native_minutes": len(spec["jobs"]), "specification_sha256": sha(OUT / "specification.json")}))


if __name__ == "__main__":
    main()
