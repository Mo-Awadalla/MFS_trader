"""Freeze a past-only two-sided activity filter before native trade acquisition."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from research_scout.prepare_fdusd_maker_20261002 import OUT as PARENT
from research_scout.prepare_fdusd_maker_20261002 import ROOT, sha

OUT = ROOT / "research_scout/fdusd_activity_hft_20261002"


def main():
    OUT.mkdir(exist_ok=True)
    audit = json.loads((PARENT / "independent_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == sha(PARENT / "screen_results.json")
    rows = pd.read_parquet(PARENT / "selected.parquet").to_dict("records")
    grouped = {}
    for row in rows:
        grouped.setdefault((row["date"], row["offset_minutes"]), []).append(row["symbol"])
    windows = [{"date": day, "offset": offset, "symbols": sorted(symbols)}
               for (day, offset), symbols in sorted(grouped.items())]
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "family": "FDUSD maker HFT past-only activity filter",
        "relationship": "Dependent liquidity filter on every one of the 48 frozen spread/depth candidates. Thresholds fixed before acquiring or evaluating these raw trade streams. This is an operational filter, not a mathematical necessary condition for every possible HFT strategy.",
        "parent_audit_sha256": sha(PARENT / "independent_verification.json"),
        "parent_selection_sha256": sha(PARENT / "selected.parquet"),
        "windows": windows, "candidate_windows": rows,
        "selection_time": "End of the original screening minute. Count raw trades with matching time at or after second 10, captured strictly before minute end minus 250ms. No future-minute prices or return labels are opened.",
        "activity_gate": "At least ten unique raw executions and at least 2000 FDUSD executed notional in EACH aggressor direction during the past interval. No cross-side netting. All passing windows retained without ranking. These are not fills or profits.",
        "source_integrity": "Require complete unauthenticated response, ordered capture clocks, expected channel/symbol, positive finite price/quantity, integer native trade IDs/T/E. Deduplicate equal symbol+trade-ID fingerprints. Conflicting duplicates, unknown regressing IDs, interior ID gaps or explicit disconnections before the availability cutoff invalidate that symbol/window. Do not infer completeness solely from a lack of trades.",
        "clock_gate": "T is exchange matching time, E is publication time, both milliseconds in the 2024 source. Require T<=E, E<=capture+1ms, and capture-T<=1s for trades that would otherwise enter the counting interval. A violation makes that symbol/window ineligible, not a zero-return observation. Late records after the availability cutoff cannot change past eligibility.",
        "direction": "m=true means the buyer was maker, so the aggressor sold; m=false means the aggressor bought. Native quantity is base-asset units and price*quantity is FDUSD; no SIP lot multiplier or stablecoin-at-par assumption.",
        "next_stage": "If activity survives, freeze a long-only maker queue/partial inventory replay before acquiring future minutes. Preserve 15s central hold, at most 30s planned inventory and conservative parent costs. Native execution, historical symbol filters, source clocks and FDUSD terminal valuation still require separate verification.",
        "download": {"channel": "trade", "slice_minutes": 1, "workers": 3,
                     "per_slice_decoded_cap": 8_000_000, "total_decoded_cap": 320_000_000,
                     "request_deadline_seconds": 75, "automatic_retries": 0},
        "primary_sources": ["https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams",
                            "https://docs.tardis.dev/historical-data-details/binance"],
        "economic_implementations": 0, "future_returns_evaluated": False,
        "actual_execution_verified": False, "selection_2025_opened": False,
        "reliable_edge_established": False, "preparation_sha256": sha(Path(__file__)),
    }
    assert len(windows) * spec["download"]["per_slice_decoded_cap"] <= spec["download"]["total_decoded_cap"]
    with (OUT / "specification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"candidate_windows": len(rows), "source_minutes": len(windows)}))


if __name__ == "__main__":
    main()
