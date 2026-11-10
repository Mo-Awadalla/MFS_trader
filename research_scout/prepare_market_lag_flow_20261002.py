"""Freeze native flow confirmation for all surviving market-lag targets."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from research_scout.prepare_market_lag_targets_batch02_20261002 import HYPOTHESIS, ROOT, sha

OUT = ROOT / "research_scout/market_lag_flow_hft_20261002"


def main():
    OUT.mkdir(exist_ok=True)
    parents, events = [], []
    for batch in ("batch01", "batch02"):
        parent = ROOT / "research_scout/market_lag_targets_hft_20261002" / batch
        results = json.loads((parent / "screen_results.json").read_text())
        assert results["selected_sha256"] == sha(parent / "selected.parquet")
        events.extend(pd.read_parquet(parent / "selected.parquet").to_dict("records"))
        parents.append({"path": str(parent.relative_to(ROOT)), "results_sha256": sha(parent / "screen_results.json"),
                        "selection_sha256": sha(parent / "selected.parquet")})
    grouped = {}
    for event in events:
        key = event["date"], event["offset_minutes"]
        grouped.setdefault(key, set()).update(("BTCUSDT", "ETHUSDT", event["symbol"]))
    jobs = [{"date": day, "offset": offset, "symbols": sorted(symbols)} for (day, offset), symbols in sorted(grouped.items())]
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(), "family": "Coherent-major/lagging-target native execution-flow confirmation",
        "relationship": "Every target surviving the complete fixed 49-minute acquisition cohort, not just a chosen winner. The original hypothesis already froze distinct flow requirements for the two leaders and target. No target post-event return has been calculated.",
        "hypothesis_specification_sha256": sha(HYPOTHESIS / "specification.json"), "quote_parents": parents,
        "parent_independent_audits_required_before_pnl": True, "events": events, "jobs": jobs,
        "gate": "BTC and ETH EACH need >=5 unique native MARKET trades, >=5000 USDT total and >=75% notional in the common quote-move direction. The target needs >=5 trades and >=5000 USDT total, without a directional-imbalance requirement. All three causal prefixes must pass integrity checks; missing or ambiguous evidence is not zero volume or a valid signal.",
        "counting": "Same captured-before-d-250ms and matching-T-in-[d-1.25s,d-250ms) interval as frozen in the hypothesis. Deduplicate exact native t IDs; MARKET executions only. Preserve raw m side (true=seller aggressor), prices and quantities as Decimal. No funding, ADL or insurance executions interpreted as ordinary trade flow.",
        "integrity_and_clocks": "Reuse unchanged independently audited native flow-prefix engine: ordered captures within the requested minute, exact native schema, unique contiguous IDs within each symbol prefix, no conflicting/reversed IDs or earlier disconnect, finite positive in-window values, T<=E+1ms, both T/E<=capture+1ms, capture-T<=250ms. Only pre-cutoff data can invalidate a past event. The engine's own 75% legacy target gate is recorded only as a diagnostic; the joint gate implements the original activity-only target requirement.",
        "acquisition": "Retrieve only these same whole minutes, preserving all data but counting causal prefixes only. No additional future minute or return calculation at this stage.",
        "download": {"channel": "trade", "slice_minutes": 1, "workers": 2,
                     "per_slice_decoded_cap": 96_000_000, "total_decoded_cap": 192_000_000,
                     "request_deadline_seconds": 120, "automatic_retries": 0},
        "progression": "After independent quote and flow audits, freeze both previously declared follow_common_move and fade_common_move 15-second execution controls with 6bp fee+1bp adverse per leg, latency/clock/cost stress, historical order checks, funding clearance and unknown-inventory accounting. No rule promotion from one event.",
        "economic_implementations": 0, "future_returns_evaluated": False,
        "actual_execution_verified": False, "selection_2025_opened": False,
        "reliable_edge_established": False, "preparation_sha256": sha(Path(__file__)),
    }
    assert len(jobs) * spec["download"]["per_slice_decoded_cap"] <= spec["download"]["total_decoded_cap"]
    with (OUT / "specification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"candidate_targets": len(events), "source_minutes": len(jobs), "specification_sha256": sha(OUT / "specification.json")}))


if __name__ == "__main__":
    main()
