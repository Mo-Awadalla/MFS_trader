"""Predeclare two post-settlement price responses without credited funding."""

import json
from datetime import UTC, datetime
from pathlib import Path

from research_scout.prepare_single_funding_20261002 import OUT as SOURCE
from research_scout.prepare_single_funding_20261002 import ROOT, sha

OUT = ROOT/"research_scout/post_funding_hft_20261002"


def main():
    OUT.mkdir(exist_ok=True)
    assert not (OUT/"specification.json").exists()
    assert not (SOURCE/"native_manifest.json").exists(), "Declare before price outcomes are acquired"
    parent = json.loads((SOURCE/"specification.json").read_text())
    pilot = json.loads((SOURCE/"payment_pilot.json").read_text())
    assert pilot["http_status"] == 403 and not pilot["complete"]
    plan = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "family": "Post-funding unwind continuation and reversal over 15 seconds",
        "reason": "The single-venue payment-capture hypothesis cannot yet be evaluated because the exchange's public realized-funding API returned a country-access block. This separate price-only test opens after the scheduled cycle has advanced and assumes no credited payment. It is declared before acquiring or inspecting post-settlement quote outcomes.",
        "relationship": "Same dependent 90-event, 12-date 2024 development cohort. Two mirrored direction hypotheses count as two tests, not independent confirmation.",
        "events_path": str((SOURCE/"events.parquet").relative_to(ROOT)), "events_sha256": parent["events_sha256"],
        "universe": "All 90 original valid Bybit events with absolute pre-settlement rate >=14bp; keep every event and missing-source result.",
        "decision": "T+10 seconds; quotes and ticker fields use only captures strictly before T+9.75 seconds. Require <=5-second source capture/publication/transaction ages and coherent sequence.",
        "settlement_gate": "A native post-settlement ticker must have explicitly advanced nextFundingTime beyond T+35 seconds by the decision cutoff. Reject missing, invalid, stale or unadvanced state. If a funding time falls inside an executed holding interval, mark its cash flow unknown; do not silently assume zero.",
        "rules": {"unwind_continuation": "Buy for positive pre-settlement funding; sell for negative, following hypothesized receiving-side position liquidation.",
                  "unwind_reversal": "Sell for positive pre-settlement funding; buy for negative, testing reversal of the initial adjustment."},
        "exit": "Fixed exit decision T+25 seconds. Base one-second outbound and acknowledgement delay; three-second stress. Entry T+11/T+13 and exit T+26/T+28. Maximum inventory duration including uncertainty <=30 seconds.",
        "spread_gate": "Positive uncrossed native bid/ask, full spread <=20bp of mid. No future price or P&L filter.",
        "quantity": "Multiple of ten whole quantity units; <=200 USDT ask notional, <=10% of both displayed touch quantities, >=100 USDT bid notional. Historical order grid and account permissions remain conditional.",
        "portfolio": "10,000 USDT per date, reserve the full entry notional plus worst scenario costs before sending. Sort simultaneous symbols lexicographically; do not recycle contingent profits. Each rule has its own account.",
        "execution": "Conditional taker fills on native matching-time book states at order arrival. Include all possible states across +/-1ms or +/-100ms clock intervals and timestamp ties. Both entry and exit need at least the full order quantity in every possible executable touch. Missing depth, book state, clock or funding continuity after submission makes the event and date unknown; never delete an unfavorable or ambiguous fill. Include both fees, per-execution adverse costs and actual bid/ask movement.",
        "cash": "No funding receipt is assumed. Cash is signed quantity times exit-minus-entry price minus both taker fees and adverse allowances. Retain worst/best joint cash bounds and component costs.",
        "scenarios": parent["scenario_grid"],
        "native_source_specification": str((SOURCE/"specification.json").relative_to(ROOT)),
        "native_acquisition": "Reuse the already bounded 23 two-minute Tardis native ticker/orderbook windows from the unrun payment test. No payment API retry or geographic rerouting.",
        "validation": "Freeze implementation and focused clock/depth/cash tests before outcomes. Reconcile source selection and cash independently. Examine returns by date, concentration and removal of best events/dates; negative or unknown complete evidence cannot pass. Keep 2025 unopened until a development candidate survives cost/latency stress.",
        "economic_configurations_run": 0, "selection_2025_opened": False, "actual_execution_verified": False,
        "reliable_edge_established": False, "preparation_sha256": sha(Path(__file__))}
    (OUT/"specification.json").write_text(json.dumps(plan, indent=2)+"\n")
    (SOURCE/"STATUS.txt").write_text("UNRUN: actual historical funding payment unavailable.\nThe first chronological unauthenticated exchange API request returned HTTP 403 with a country-access restriction. No API rerouting or repeated attempts were made. Forecast rates have not been substituted for realized payments. The hypothesis and source error are preserved. No economic P&L is claimed.\nA separately frozen post-settlement price-only experiment uses the same native source acquisition, without claiming funding receipts.\n")
    print(json.dumps({"prepared": True, "economic_rules": 2, "specification_sha256": sha(OUT/"specification.json")}), flush=True)


if __name__ == "__main__":
    main()
