"""Freeze a cheap, explicitly optimistic equity microstructure rejection screen."""

import json
from datetime import UTC, datetime
from pathlib import Path

from research_scout.prepare_market_lag_native_20261002 import ROOT, sha

DATA = ROOT / "external_artifacts/databento_cash_etf_mbp1_open_v55/EQUS.MINI/mbp-1"
OUT = ROOT / "research_scout/equity_resilience_hft_20261002"
SYMBOLS = ("SPY", "SSO", "UPRO", "SH", "SDS", "SPXU")


def main():
    OUT.mkdir(exist_ok=True)
    files = sorted(DATA.glob("2023-*.dbn.zst"))
    assert len(files) == 192
    source = [{"date": p.name[:10], "path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size,
               "sha256": sha(p)} for p in files]
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "family": "ETF bid resilience and subsequent ask break under heavy executed volume",
        "relationship": "New dependent development screen on previously exposed 2023 Databento sessions. Prior generic own/cross ETF regressions and crypto absorption tests failed. This is an explicit two-second state/print mechanism on lower-fee equities, not another fitted predictor. Preserve the whole search history. No new 2024/2025/2026 outcomes opened for this family.",
        "sources": source, "symbols": list(SYMBOLS), "workers": 2,
        "signal_clock": "100ms decisions from 09:30:05 through 09:39:30 America/New_York. Information cutoff d-250ms; anchor cutoff two seconds earlier. Use last F_LAST quote strictly before each cutoff. Endpoint capture and event-clock ages in (0,250ms]. All intermediate completed books valid, uncrossed, positive, with no receive gap >250ms. Current spread <=5bp. Native fixed-point prices and integer timestamps retained.",
        "bad_data": "Any BAD_TS_RECV record makes that symbol-session's screen unassessable; do not silently delete it and resurrect a prior quote. Invalid completed books remain in the path. Matching timestamps may differ across anonymized component venues, so do not invent a global matching sequence or venue mapping. Clock consistency permits at most 1ms event-ahead-of-capture and at most 1s capture delay per input; endpoints have the stricter 250ms ages. Unassessable sessions and unknown reference windows are never zero P&L.",
        "flow": "All native T records captured in [cutoff-2s,cutoff), with event time also inside that interval, valid positive quantity/price and completion by the latest F_LAST source position. Unknown-side volume remains in the denominator. Pressure at the exact defended price must be >=5 times anchor displayed quantity, >=80% of all window volume, >=10000 USD, and at least five distinct capture timestamps. Fragments at one capture clock count once for the five-clock gate but all reported executed size is retained.",
        "rules": {"bid_resilience_long": "All completed bids stay exactly at the anchor bid for two seconds despite qualifying sell-side pressure; buy after detection.",
                  "ask_break_long": "All completed asks stay at the anchor ask despite qualifying buy-side pressure. Watch for ten seconds after detection; buy only when a later causal fresh ask exceeds that price. An invalid intervening book clears the watch."},
        "selection": "Per-symbol 60s cooldown after each corresponding resilience observation. Ask watch expires in 10s. Each rule independently chooses at most one event per decision, ranked by pressure/anchor-quantity, then pressure notional, then symbol; global 35s decision cooldown regardless of later hypothetical fills. All raw events retained. Long only, including inverse ETFs; no borrow or short-sale assumption.",
        "sizing": "Freeze whole shares from the signal: min(floor(10000/(1.02*ask)),floor(10% displayed ask quantity)). Quantity never resized using future liquidity. Independent 10000-USD event budget is for triage only; diagnostic sums are not a funded portfolio path. A 10bp limit rounded inward to 0.01 is conditional historical tick assumption. If even the favorable observed entry exceeds it, record no fill.",
        "timing": "50ms processing plus outbound delay; entry ACK after another outbound delay; exit decision 15 seconds after entry ACK then 50ms processing and outbound. Entry d+50ms+delay, exit d+15.1s+3*delay. Planned inventory <30s for all cases. No slower horizon.",
        "optimism": "For each frozen arrival clock choose the most favorable observed ask/bid in arrival +/-clock radius including the last preceding state, require a successor and a predecessor no more than 250ms old. Ignore future depth constraints and assume full fills inside the collar. This future-aware price choice is a cheap rejection proxy, not an implementable timing rule, execution audit, full-market bound or deployable return. Favorable results must survive fixed causal execution, capital, complete-path and independent source audits before any promotion.",
        "costs": "Each leg pays max(1 USD,0.005 USD/share) commission and 1bp adverse allowance; sell leg additionally pays 0.00003*notional +0.000166 USD/share. Frozen conservative assumptions, not asserted historical or competition fees. Observed spread is in entry/exit prices.",
        "scenarios": [
            {"name": "base", "delay_ms": 1000, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 1},
            {"name": "fees_2x", "delay_ms": 1000, "clock_ms": 1, "fee_multiple": 2, "adverse_multiple": 1},
            {"name": "adverse_2x", "delay_ms": 1000, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 2},
            {"name": "latency_250ms", "delay_ms": 250, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 1},
            {"name": "latency_3s", "delay_ms": 3000, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 1},
            {"name": "clock_100ms", "delay_ms": 1000, "clock_ms": 100, "fee_multiple": 1, "adverse_multiple": 1}],
        "progression": "No parameter tuning on these outcomes. A positive complete optimistic base or delay case is only a lead for a separate realistic replay, never an edge. Inspect event/date concentration and all negative controls. If no such lead, reject within this approximate feed/model scope or report missing evidence explicitly. Later 2024 data is not automatically opened by this script.",
        "feed_limits": "EQUS.MINI is an anonymized aggregated component-venue BBO, not SIP NBBO or private fills. Native side denotes initiating trade side when supplied. No passive queue inference. A positive candidate needs routeable quote corroboration and realistic execution before reliability testing.",
        "references": ["https://databento.com/docs/schemas-and-data-formats/mbp-1",
                       "https://databento.com/docs/venues-and-datasets/equs-mini"],
        "reliable_edge_established": False, "actual_execution_verified": False,
        "preparation_sha256": sha(Path(__file__)),
    }
    with (OUT / "specification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"source_sessions": len(files), "bytes": sum(r["bytes"] for r in source),
                      "rules": 2, "specification_sha256": sha(OUT / "specification.json")}))


if __name__ == "__main__":
    main()
