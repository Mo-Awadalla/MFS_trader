"""Freeze flow integrity and bounded pre-signal evidence acquisition."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from research_scout.prepare_perp_shock_20261002 import OUT as PARENT
from research_scout.prepare_perp_shock_20261002 import ROOT, sha

OUT = ROOT / "research_scout/perp_shock_flow_hft_20261002"


def main():
    OUT.mkdir(exist_ok=True)
    parent = json.loads((PARENT / "specification.json").read_text())
    results = json.loads((PARENT / "screen_results.json").read_text())
    assert results["selected_sha256"] == sha(PARENT / "selected.parquet")
    events = pd.read_parquet(PARENT / "selected.parquet").to_dict("records")
    grouped = {}
    for event in events:
        key = event["date"], event["offset_minutes"]
        grouped.setdefault(key, set()).add(event["symbol"])
    sources = {(s["date"], s["offset"]): s for s in parent["sources"]}
    jobs = []
    for (day, offset), symbols in sorted(grouped.items()):
        job = {"date": day, "offset": offset, "symbols": sorted(symbols)}
        original = sources[(day, offset)]
        if any(c["channel"] == "trade" for c in json.loads(original["params"]["filters"])):
            job["reuse"] = original
        jobs.append(job)
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "family": "Native aggressive-trade confirmation of the frozen two-sided price shocks",
        "relationship": "All parent quote-selected events, no ranking or return filtering. The parent already froze five trades, 5000 USDT and 75% aligned notional; this document specifies integrity and acquisition before these additional trade records are read.",
        "parent_results_sha256": sha(PARENT / "screen_results.json"),
        "parent_selection_sha256": sha(PARENT / "selected.parquet"),
        "parent_independent_audit_required_before_return_test": True,
        "events": events, "jobs": jobs,
        "counting": "Capture strictly before d-250ms and native matching T in [d-1.25s,d-250ms). Count raw trade IDs once. Price*quantity is native USDT notional, preserving multiplier-prefixed contract identity. Use MARKET executions only; insurance-fund, ADL or other X labels are separately excluded, never interpreted as ordinary aggressive demand.",
        "gate": "At least five unique MARKET executions, at least 5000 USDT total notional, and at least 75% of total notional in the shock direction. m=true is seller-aggressed, false buyer-aggressed. Keep every parent event, including unknown source evidence and insufficient activity.",
        "integrity": "Native capture order and requested minute must hold. Inspect only records available before each event cutoff for its decision. Exact symbol/ID fingerprints (T,E,p,q,m,X) are deduplicated. Conflicting duplicate IDs, regressing previously unseen IDs or interior ID gaps in that pre-cutoff symbol prefix invalidate the event. Any explicit pre-cutoff disconnect also invalidates it. No data repair, cross-stream aggregate/raw combination or future-dependent deletion.",
        "clocks": "For matching-window executions require positive finite price/quantity; native integer t/T/E and boolean m; T<=E+1ms, both T/E<=capture+1ms, capture-T<=250ms. An invalid would-be window observation makes the event unknown, not zero volume. A complete empty source proves only lack of confirming evidence, not absence of trading globally.",
        "acquisition": "The native API returns whole minutes. These are the same minutes whose BBOs were already acquired in earlier studies; no extra future minute is requested and no post-event return is computed here. Records captured at/after an event cutoff cannot affect that event's flow or source-integrity decision. Preserve full source files and exact prefix row references for audit.",
        "download": {"channel": "trade", "slice_minutes": 1, "workers": 3,
                     "per_slice_decoded_cap": 16_000_000, "total_decoded_cap": 960_000_000,
                     "request_deadline_seconds": 75, "automatic_retries": 0},
        "next_stage": "After both source audits pass, freeze both 15-second follow and fade execution implementations with conservative costs and historical order/funding checks before any post-event response calculation.",
        "economic_implementations": 0, "future_returns_evaluated": False,
        "actual_execution_verified": False, "selection_2025_opened": False,
        "reliable_edge_established": False, "preparation_sha256": sha(Path(__file__)),
        "primary_native_source": "https://docs.tardis.dev/historical-data-details/binance-futures",
    }
    assert len(jobs) * spec["download"]["per_slice_decoded_cap"] <= spec["download"]["total_decoded_cap"]
    with (OUT / "specification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"events": len(events), "source_minutes": len(jobs), "cached_reuses": sum("reuse" in j for j in jobs)}))


if __name__ == "__main__":
    main()
