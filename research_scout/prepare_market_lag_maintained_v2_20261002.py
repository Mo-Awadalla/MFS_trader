"""Version the nullable-metadata reader correction without changing the experiment."""

import json
from datetime import UTC, datetime
from pathlib import Path

from research_scout.prepare_market_lag_maintained_20261002 import (  # noqa: F401
    HYPOTHESIS,
    ROOT,
    sha,
)
from research_scout.prepare_market_lag_maintained_20261002 import OUT as ORIGINAL

OUT = ORIGINAL / "screen_v2"


def main():
    spec = json.loads((ORIGINAL / "specification.json").read_text())
    OUT.mkdir(exist_ok=True)
    spec.update(reader_repair_frozen_at_utc=datetime.now(UTC).isoformat(),
                original_specification_sha256=sha(ORIGINAL / "specification.json"),
                superseded_results_sha256=sha(ORIGINAL / "screen_results.json"),
                superseded_audit_sha256=sha(ORIGINAL / "independent_verification.json"),
                repair="V1 rejected all 1953 rows because the audited parquet's nullable epoch/update_id metadata loaded as float64. Accept exactly integral, finite metadata below 2**53; do not cast or round any timestamp. All native nanosecond fields must remain original integers. Full parent raw audits already verify these identities. V1's independent predicate copied the same over-strict type assumption, so its zero-candidate result is superseded, not a financial rejection. Add a mandatory retention check for the original qualifying TRX quote. No economics or thresholds changed.",
                repair_preparation_sha256=sha(Path(__file__)))
    with (OUT / "specification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"specification_sha256": sha(OUT / "specification.json"), "threshold_changes": False}))


if __name__ == "__main__":
    main()
