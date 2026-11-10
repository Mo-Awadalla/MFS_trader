"""Freeze native one-second two-sided price displacement before its response."""

import json
from datetime import UTC, datetime
from pathlib import Path

from research_scout.prepare_spot_perp_20261002 import ROOT, sha

OUT = ROOT / "research_scout/perp_shock_hft_20261002"


def main():
    OUT.mkdir(exist_ok=True)
    manifests = [ROOT / "research_scout/wide_tick_hft_20260930/complete_manifest_v1.json",
                 ROOT / "research_scout/spot_perp_clock_hft_20261002/source_manifest.json"]
    sources = []
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text())
        assert manifest["complete"]
        for source in manifest["files"]:
            if source.get("venue", "perpetual") != "perpetual":
                continue
            sources.append({**source, "offset": source.get("offset", source["params"]["offset"]),
                            "parent_manifest": str(manifest_path.relative_to(ROOT)),
                            "parent_manifest_sha256": sha(manifest_path)})
    sources.sort(key=lambda s: (s["date"], s["offset"]))
    audits = [ROOT / "research_scout/spot_perp_hft_20261002/independent_verification.json",
              ROOT / "research_scout/spot_perp_clock_hft_20261002/independent_verification.json"]
    assert len(sources) == len({(s["date"], s["offset"]) for s in sources}) == 60
    assert all(json.loads(p.read_text())["verified"] for p in audits)
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "family": "Broad native perpetual price displacement with subsequent pre-decision trade confirmation",
        "relationship": "Dependent extension of the prior failed liquidation, absorption and short-horizon response families. Selection starts with both sides of the native market moving, rather than a liquidation broadcast or a cross-market basis. Prior failed variants remain; globally exposed historical data are not pristine validation.",
        "sources": sources, "parent_audits": [{"path": str(p.relative_to(ROOT)), "sha256": sha(p)} for p in audits],
        "universe": "Every recorded native alphanumeric USDT perpetual symbol, retaining multiplier prefixes. No current survivor list, cross-asset identity substitution, symbol ranking or dated-future suffixes. Every source symbol appears in every frozen decision row, including missing early quotes.",
        "decisions": "Quarter-second decisions at minute seconds 2.00 through 58.75 inclusive (228 decisions). At d use the last full book captured strictly before d-250ms; compare with the last full book strictly before d-1.25s. Both information cutoffs are separated by one second. Warmup observation grids start at second 1.00.",
        "quote_admission": "Each endpoint has positive finite bid/ask/sizes, bid<ask; latest capture is strictly before its cutoff and at most 250ms old at that cutoff. Transaction T and publication E are each at most 250ms old relative to that cutoff and no more than 1ms ahead of capture; T<=E+1ms. Full books retain original nanosecond capture and millisecond-derived T/E. No substitution of E for matching time.",
        "integrity": "Increasing update IDs; exact equal-ID identical records never refresh age; conflicting/regressing IDs poison until a strictly higher ID. A rising-ID transaction clock below its previously observed high-water mark is invalid until the matching clock recovers. Clear source state/IDs/high-water marks on disconnect; endpoints separated by a disconnect cannot form a price displacement.",
        "displacement": "Both bid and ask increase at least 30bp, or both decrease at least 30bp, between the two causal endpoints. Both endpoint full spreads <=10bp. Both sides at BOTH endpoints must display >=2000 USDT. These are event/liquidity gates, not expected or realized returns.",
        "selection": "Keep earliest qualifying quarter-second event per symbol, then a fixed 30-second same-symbol cooldown within each source minute. Preserve every grid/rejection and all selected signals without return ranking. Events on the same market move are dependent.",
        "flow_confirmation_before_returns": "For every selected shock, count raw same-symbol trade executions captured strictly before d-250ms with matching time in [d-1.25s,d-250ms). Require at least five unique trade IDs, at least 5000 USDT notional total and >=75% of total notional aggressing in the displacement direction. Raw m=true means sell aggressor. No aggregate/raw double counting. Duplicates, ID gaps, disconnects and inconsistent clocks must be audited; unresolved source evidence is not zero activity or zero P&L.",
        "response_controls_if_flow_survives": "Separately freeze both follow and fade controls, fixed exit decision 15 seconds after entry ACK, planned inventory <=30s, conservative 6bp taker fee plus 1bp adverse allowance on each side. Include doubled fees/adverse, 250ms and 3s order latency, matching-clock uncertainty, fixed causal quantities, full touch depth, guarded FOK entry, unknown inventory and forced cleanup. Verify historical contract/order rules and funding-boundary clearance. Do not acquire extra future minutes or compute post-event returns before that implementation is frozen.",
        "selection_2025_opened": False, "economic_implementations": 0,
        "future_returns_evaluated": False, "actual_execution_verified": False,
        "reliable_edge_established": False, "preparation_sha256": sha(Path(__file__)),
        "primary_native_source": "https://docs.tardis.dev/historical-data-details/binance-futures",
    }
    with (OUT / "specification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"source_minutes": len(sources), "new_downloads": 0, "decision_spacing_ms": 250}))


if __name__ == "__main__":
    main()
