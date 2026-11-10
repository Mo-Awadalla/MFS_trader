"""Compile delegated-review reconciliation and V42 terminal evidence."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RS = ROOT / "research_scout"
PRIOR_JSON = RS / "cash_etf_auction_research_results_v41.json"
PRIOR_REPORT = RS / "SPY_CASH_ETF_AUCTION_RESEARCH_REPORT_V41.md"
V42_AUDIT = RS / "spy_late_closing_auction_market_urgency_returns_blind_audit_v42.json"
OUTPUT_JSON = RS / "cash_etf_auction_research_results_v42.json"
OUTPUT_REPORT = RS / "SPY_CASH_ETF_AUCTION_RESEARCH_REPORT_V42.md"


def main() -> int:
    prior = json.loads(PRIOR_JSON.read_text(encoding="utf-8"))
    v42 = json.loads(V42_AUDIT.read_text(encoding="utf-8"))
    if v42.get("returns_read") is not False:
        raise RuntimeError("V42 audit is not returns-blind")
    prior["status"] = "v37_v42_all_failed_frozen_returns_blind_gates_no_new_pnl_opened"
    prior["new_candidate_returns_viewed"] = False
    prior["new_candidate_pnl_calculated"] = False
    prior["delegated_adversarial_reconciliation"] = {
        "exact_reference_pin_proposal": "rejected before feasibility by independent review",
        "implemented_v37_difference": "used relative indicative-versus-reference returns rather than exact endpoint equality",
        "remaining_semantic_decision": "V37 downgraded to a stable auction-repricing diagnostic; not a desk-ready mechanism",
        "late_closing_recommendation": "completed independently before V41 feasibility was read and frozen as V42",
    }
    prior["candidates"]["V42"] = {
        "name": "SPY late Closing-auction market-urgency acceleration",
        "audit": V42_AUDIT.name,
        "status": v42["status"],
        "chronology": v42["chronology"],
        "feature_development": v42["feature_development_2021_2023"],
        "executable_development": v42["executable_development_2023_overlap"],
        "all_overlap": v42["all_overlap"],
        "by_year": v42["by_year"],
        "adjacent_window_stability": v42["adjacent_window_stability"],
        "quantity_break": v42["quantity_break"],
        "returns_blind_controls": v42["returns_blind_controls"],
        "failed_gates": [name for name, passed in v42["gates"].items() if not passed],
        "decision": "terminal_no_pnl",
    }
    prior["program_limitations_demonstrated"].append(
        "The independently proposed 15:50/15:55 closing market-urgency rule passed 93.33% complete execution coverage but produced only 0.288 development signals/week, unstable neighboring-window membership, and no 2026/post-break participation."
    )
    prior["next_independent_evidence"]["research"] = "V35-V42 are locked. Another historical auction timing or market-quantity variant is not justified; require a genuinely different defining observable or prospective data."
    OUTPUT_JSON.write_text(json.dumps(prior, indent=2) + "\n", encoding="utf-8")

    base = PRIOR_REPORT.read_text(encoding="utf-8").replace(
        "# Institutional Cash-ETF and Auction Research Report v41",
        "# Institutional Cash-ETF and Auction Research Report v42",
        1,
    )
    appendix = f"""

## Delegated-review reconciliation

The delayed independent review changed two interpretations without changing any locked rule or opening any return:

1. It rejected the earlier exact-reference-endpoint V37 proposal. `ref_price` is an imbalance-calculation reference rather than a fundamental price anchor, and indicative repricing does not identify unresolved inventory. The implemented V37 used a different relative-return construction, but the semantic objection remains. V37 is downgraded from a promising mechanism to a stable auction-repricing diagnostic that also failed execution coverage.
2. It independently recommended a later Closing-auction market-urgency rule. That recommendation was dispatched before V41 feasibility was read, so it was eligible for one frozen returns-blind audit as V42 rather than being selected from V41's result.

## V42 — late Closing-auction market urgency

Frozen rule:

- regular 16:00 Closing auction;
- same nonneutral side at 15:50 and 15:55;
- positive `market_imbalance_qty` at both clocks and strictly larger at 15:55;
- bid side -> SPY; ask side -> SH;
- primary first valid ask after 15:56;
- first valid bid after 15:59, strictly before 16:00.

Returns-blind result:

- development features: {v42['feature_development_2021_2023']['signals']} ({v42['feature_development_2021_2023']['signals_per_declared_week']:.3f}/week);
- executable 2023 development: {v42['executable_development_2023_overlap']['signals']} ({v42['executable_development_2023_overlap']['signals_per_declared_week']:.3f}/week);
- complete 1/5/60-second-plus-exit coverage: {v42['all_overlap']['complete_quote_coverage_pct']:.2f}% — this gate passed;
- adjacent shifted-window action including cash: {v42['adjacent_window_stability']['15:49:50_15:54:50']['identical_action_including_cash_pct']:.2f}% and {v42['adjacent_window_stability']['15:50:10_15:55:10']['identical_action_including_cash_pct']:.2f}% — both failed 60%;
- 2026 signals: {v42['by_year']['2026']['signals']};
- post-2025-11-13 signals: {v42['quantity_break']['postbreak_signals']};
- causal pre-signal SPY-momentum control coverage: {v42['returns_blind_controls']['presignal_spy_momentum_coverage_pct']:.2f}% versus required 80%.

**V42 is terminal without P&L.** Its execution evidence was adequate, but the economic state was sparse, unstable to neighboring clocks, and absent from the temporal extension/new quantity regime.

## Updated stopping conclusion

The independent recommendation has now been honored exactly once and rejected without outcome inspection. V35–V42 are immutable. Additional historical opening/closing cutoff variants would be timing search, not creativity.

The next legitimate move requires either:

- complete quote-update/official BBO data for a genuinely new defining observable;
- ETF primary-market data such as baskets, creations/redemptions, shares outstanding, or premium/NAV evidence; or
- a prospective untouched forward collection with a separately frozen mechanism.

## Additional reproducibility

- V42 extraction: `python research_scout/extract_spy_late_closing_v42.py`
- V42 feasibility: `python research_scout/audit_spy_late_closing_auction_market_urgency_v42.py`
- V42 compiler: `python research_scout/compile_cash_etf_research_report_v42.py`
"""
    OUTPUT_REPORT.write_text(base.rstrip() + appendix + "\n", encoding="utf-8")
    print(json.dumps({"results": str(OUTPUT_JSON.relative_to(ROOT)), "report": str(OUTPUT_REPORT.relative_to(ROOT))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
