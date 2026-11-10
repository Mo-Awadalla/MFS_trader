"""Expand clock coverage without changing the failed spot/perp signal gates."""

import json
from datetime import UTC, datetime
from pathlib import Path

from research_scout.prepare_spot_perp_20261002 import OUT as PARENT
from research_scout.prepare_spot_perp_20261002 import ROOT, sha

OUT = ROOT / "research_scout/spot_perp_clock_hft_20261002"


def main():
    OUT.mkdir(exist_ok=True)
    original = json.loads((PARENT / "specification.json").read_text())
    results = json.loads((PARENT / "screen_results.json").read_text())
    assert results["selected_events"] == 0 and not results["future_returns_evaluated"]
    plan = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "family": "Uniform clock expansion of the same spot/perpetual HFT discrepancy screen",
        "relationship": "Dependent coverage expansion after zero entries in twelve 09:00 minutes. It is not a new economic hypothesis or an independent replication. The preceding original one-second quote-freshness, ten-point median/MAD anchor, 25bp gap, 2000-USDT depth, 5bp net convergence budget and two consecutive observations are unchanged.",
        "parent_specification": str((PARENT / "specification.json").relative_to(ROOT)),
        "parent_specification_sha256": sha(PARENT / "specification.json"),
        "parent_results_sha256": sha(PARENT / "screen_results.json"),
        "dates": original["dates"], "offset_minutes": [0, 360, 720, 1080],
        "coverage": "Four fixed equally spaced clock minutes per date: 00:00, 06:00, 12:00 and 18:00 UTC. Original 09:00 results stay intact and are reported alongside this expansion. No time is selected by subsequent returns, volatility, known events or surviving symbols.",
        "decisions": "Seconds 10 through 59, as of each decision minus 250ms, with ten preceding one-second historical grid states. Earliest qualifying event per symbol/date/clock-window retained for source review. Any subsequent economic replay must enforce account and inventory continuity across all same-day windows.",
        "future_stage": original["if_supply"] + " Midnight signals occur after the first ten seconds; actual funding-cycle and contract-lifecycle evidence is still required before entry and no forecast payment may be credited.",
        "download": {"exchanges": {"spot": "binance", "perpetual": "binance-futures"},
                     "channels": ["bookTicker"], "slice_minutes": 1, "workers": 3,
                     "per_slice_decoded_cap": 512_000_000, "total_decoded_cap": 12_000_000_000,
                     "request_deadline_seconds": 180, "authenticated": False, "paid_fallback": False},
        "implementation_preservation": "Use a separately frozen reader with the clock-window start parameter. Original production code and all source/result hashes remain unchanged. Independent audit must check each shifted clock against the raw timestamps.",
        "economic_implementations": 0, "future_returns_evaluated": False,
        "actual_execution_verified": False, "selection_2025_opened": False,
        "reliable_edge_established": False, "preparation_sha256": sha(Path(__file__)),
    }
    with (OUT / "specification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(plan, indent=2) + "\n")
    print(json.dumps({"additional_paired_minutes": 48, "native_files": 96,
                      "economic_thresholds_changed": False, "future_returns_evaluated": False}))


if __name__ == "__main__":
    main()
