"""Freeze short SPY impulse responses before reading post-event returns."""

import json
from datetime import UTC, datetime
from pathlib import Path

from research_scout.screen_futures_etf_20261002 import OUT as PARENT
from research_scout.screen_futures_etf_20261002 import ROOT, sha

OUT = ROOT/"research_scout/futures_response_hft_20261002"


def main():
    OUT.mkdir(exist_ok=True)
    assert not (OUT/"specification.json").exists()
    parent = json.loads((PARENT/"spy_budget_results.json").read_text())
    assert not parent["future_returns_evaluated"] and parent["eligible_events"] == 0
    plan = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "family": "SPY continuation versus reversal after a causal ES trade-flow impulse",
        "relationship": "Dependent extension of the failed ES/SPY instantaneous catch-up budget. SPY had mostly already repriced, but that does not measure its subsequent return. Both fixed directions are declared before reading post-event returns. This is not independent discovery or a pristine validation sample.",
        "events_path": str((PARENT/"es_impulses.parquet").relative_to(ROOT)), "events_sha256": sha(PARENT/"es_impulses.parquet"),
        "quote_manifest_path": str((PARENT/"quote_manifest.json").relative_to(ROOT)), "quote_manifest_sha256": sha(PARENT/"quote_manifest.json"),
        "universe": "SPY only; ES is a predictor and never a traded instrument. All 26 frozen 2023 impulses on 17 dates remain in every ledger. No residual/catch-up filter or outcome-based selection.",
        "rules": {"follow_impulse": "Trade in the sign of the pre-decision one-second ES return.", "fade_impulse": "Trade opposite the sign of that same frozen ES return."},
        "pretrade": "Use the last SPY quote strictly before original decision minus 100ms. Reject incomplete, nonregular, crossed, nonpositive and conflicting same-timestamp quote states. Current full spread <=20bp; no arbitrary expiry of an otherwise standing quote. Historical quote receipt is conditional, not measured client latency.",
        "quantity": "Whole shares fixed at decision: floor(min(10000/(1.01*entry_quote), 10% of direction-specific displayed shares)); notional >=100 dollars. No future resizing. Pre-2025 Alpaca SIP sizes use the previously declared 100-share SPY lot assumption; actual permissions and lot definitions remain conditional.",
        "entry": "Guarded FOK limit 10bp from the known directional quote, rounded inward to the penny. Base feed delay 100ms, processing 50ms, outbound and ACK 100ms each. Slower feed scenarios delay the same frozen signal by feed_delay minus 100ms; quotes and quantity are not replaced with future observations.",
        "exit": "Decision 15 seconds after entry ACK, then processing and outbound delay. Unconditional marketable full-quantity exit under a historical quote model; unresolved depth or state is unknown. Maximum possible modeled inventory interval <=30 seconds, including clock ambiguity. Unknown actual exits do not establish this holding limit.",
        "execution": "Use all valid standing quote states over arrival +/-1ms, including the full tied predecessor group and every timestamp tie in the interval; require a successor to bracket it. A FOK fills only when every state is inside the collar and has full displayed touch depth. If every price is outside the collar, no fill. Mixed/insufficient/invalid states are unknown, never an assumed zero. Exit requires full touch depth in every compatible state.",
        "capital": "Independent 10,000-dollar account per date and rule. Reserve full limit entry notional plus worst frozen fee/adverse/borrow allowance against the known lower cash bound. No short proceeds finance another order. After a submitted order has unresolved inventory, stop all later same-date attempts and mark the date unknown. Never reset an unknown position to flat or aggregate a partial day as a complete return.",
        "costs": {"commission_per_share": .0075, "minimum_per_order": 1., "sell_rate": .00003, "sell_per_share": .0002, "adverse_per_execution": .0001,
                  "short_annual_rate": .05, "minimum_borrow_days": 1},
        "scenarios": [
            {"name": "base", "feed_ms": 100, "outbound_ms": 100, "ack_ms": 100, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 1},
            {"name": "fees_2x", "feed_ms": 100, "outbound_ms": 100, "ack_ms": 100, "clock_ms": 1, "fee_multiple": 2, "adverse_multiple": 1},
            {"name": "adverse_2x", "feed_ms": 100, "outbound_ms": 100, "ack_ms": 100, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 2},
            {"name": "latency_250ms", "feed_ms": 250, "outbound_ms": 250, "ack_ms": 250, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 1},
            {"name": "latency_1s", "feed_ms": 1000, "outbound_ms": 1000, "ack_ms": 1000, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 1},
            {"name": "clock_100ms", "feed_ms": 100, "outbound_ms": 100, "ack_ms": 100, "clock_ms": 100, "fee_multiple": 1, "adverse_multiple": 1}],
        "progression": "Require a complete positive conservative base, fee/adverse/250ms stress survival and positive performance after removing the best three dates before considering a fixed later-date test. Inspect the 1s latency budget explicitly. Account for both mirrored rules and the wider dependent search. No reliability claim without actual quote receipt, routing, borrow and forward execution evidence.",
        "economic_configurations_run": 0, "selection_2024_2025_opened_by_this_family": False,
        "actual_execution_verified": False, "reliable_edge_established": False,
        "preparation_sha256": sha(Path(__file__))}
    (OUT/"specification.json").write_text(json.dumps(plan, indent=2)+"\n")
    print(json.dumps({"prepared": True, "rules": 2, "scenarios": 12, "specification_sha256": sha(OUT/"specification.json")}), flush=True)


if __name__ == "__main__":
    main()
