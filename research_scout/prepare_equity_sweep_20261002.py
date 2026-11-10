"""Freeze a distinct large-sweep response before selecting events or returns."""

import json
from datetime import UTC, datetime
from pathlib import Path

from research_scout.prepare_equity_burst_20261002 import OUT as BURST
from research_scout.prepare_equity_resilience_20261002 import OUT as PARENT
from research_scout.prepare_equity_resilience_20261002 import ROOT, SYMBOLS, sha  # noqa: F401

OUT = ROOT / "research_scout/equity_sweep_hft_20261002"


def main():
    previous = json.loads((BURST / "independent_verification.json").read_text())
    assert previous["verified"] and previous["results_sha256"] == sha(BURST / "screen_results.json")
    original = json.loads((PARENT / "specification.json").read_text())
    spec = {k: original[k] for k in ("sources", "symbols", "workers", "bad_data", "sizing", "timing", "optimism", "costs", "scenarios", "feed_limits", "references")}
    spec.update(
        created_at_utc=datetime.now(UTC).isoformat(),
        family="Large completed multi-price sweep followed by short equity continuation or reversal",
        relationship="Distinct dependent hypothesis after two static-price resilience screens produced no confirmed entries. It tests displaced prices, not a rescued static-price rule. Same 192 previously exposed 2023 sessions; retain all failed hypotheses, costs and strict HFT scope. No new 2024+ outcomes for selection.",
        prior_burst_audit_sha256=sha(BURST / "independent_verification.json"),
        original_cost_timing_specification_sha256=sha(PARENT / "specification.json"),
        event_identity="Same instrument's native segment between consecutive F_LAST boundaries, with at least one trade and all records sharing exactly the same ts_recv and ts_event. No bad clock/book flags. All trades have one known initiating side, positive integer quantities, and at least two distinct prices spanning >=0.01 USD. Buy prices must be nondecreasing in source order; sell prices nonincreasing. No aggressor, order, venue or private-fill identity is inferred.",
        prestate="Immediately preceding completed BBO must be positive, valid, uncrossed and fresh: capture strictly before the burst by <=250ms, native event time no later than the burst and <=250ms older. Same-capture prestate is rejected, never replaced by an older quote. Every buy print price must be at or above that pre-ask; every sell print at or below the pre-bid. Total burst quantity >= prestate directional displayed quantity and total exact trade notional >=100000 USD. A transiently locked completion BBO does not establish a signal; the later signal state has its own mandatory valid-book gate.",
        decision="For each qualifying burst, use exactly the first 100ms RTH grid STRICTLY after burst capture+500ms, with decisions limited to 09:30:05 through 09:39:30 America/New_York. Do not wait or resample until a favorable signal state appears. Information cutoff d-250ms; latest completed quote strictly before it must be valid and have capture/event ages in (0,250ms], current spread<=5bp, and both clocks at least 250ms after the burst. Its bid AND ask must remain strictly displaced in the initiating direction versus the prestate. No future price or P&L gate, no two-second static-price premise.",
        rules={"buy_sweep_continuation_long": "After a qualifying buy-initiated multi-price sweep and a displaced current quote, buy that ETF and use the frozen 15-second exit after entry ACK.",
               "sell_sweep_reversal_long": "After a qualifying sell-initiated sweep and a displaced current quote, buy that ETF as the fixed opposite-direction response, with identical quantity, timing and costs."},
        selection="Per rule and per symbol, keep the first admitted decision then apply 60s cooldown regardless of later fills. Across symbols at the same grid rank by burst quantity / prestate directional quantity, then burst notional, then symbol. At most one event per rule per grid, with 35s global decision cooldown. Both rules are long only; inverse ETFs are permitted as members of the existing universe, not dynamically substituted for shorts. Preserve all rejected and admitted burst records.",
        progression="First build and independently check causal event identities and admission. Then run unchanged favorable-quote triage with all six fee/latency cases. A positive complete base or delay proxy is a lead only; require fixed causal execution, capital/unknown handling, independent cash/source audit, concentration checks and separately frozen later validation before any reliability claim. Do not lower thresholds or choose a direction/exit from these outcomes.",
        stage="Specification only. No sweep event selection or future-return calculation yet.",
        economic_implementations_run=0, actual_execution_verified=False, reliable_edge_established=False,
        preparation_sha256=sha(Path(__file__)))
    OUT.mkdir(exist_ok=True)
    with (OUT / "specification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"source_sessions": len(spec["sources"]), "rules": list(spec["rules"]),
                      "specification_sha256": sha(OUT / "specification.json")}))


if __name__ == "__main__":
    main()
