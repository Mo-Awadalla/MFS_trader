"""Persist audited zero supply and the precise next research question."""

import json
from datetime import UTC, datetime

from research_scout.prepare_equity_resilience_20261002 import OUT, ROOT, sha


def main():
    result = json.loads((OUT / "results.json").read_text())
    audit = json.loads((OUT / "independent_supply_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == sha(OUT / "results.json")
    assert result["raw_events"] == result["selected_events"] == audit["resilience_seeds"] == 0
    c = audit["counters"]
    report = OUT / "REPORT.txt"
    report.write_text(
        "STRICT HFT EDGE SEARCH — AUDITED EQUITY RESILIENCE SCREEN\n\n"
        "Goal ACTIVE. No reliable edge, deployable strategy, or competition win established.\n\n"
        "Most recent economic experiment: the one flow-confirmed TRX lagging-coin event failed. Both "
        "predeclared directions used a 15-second exit after entry ACK and conservative fees. All eleven "
        "calculable cases lost; the remaining case had unknown exit depth under clock uncertainty. The "
        "complete native-source/execution/cash audit matched exactly. A separate maintained-quote "
        "acquisition extension added no new candidate after its nullable-metadata reader was corrected. "
        "See ../market_lag_response_hft_20261002/REPORT.txt and ../market_lag_maintained_hft_20261002/REPORT.txt.\n\n"
        "NEW EQUITY EXPERIMENT\n"
        "All 192 cached 2023 opening sessions, six equity ETFs, 100ms decisions and a 250ms information "
        "buffer. Two long-only rules: buy a bid that survives heavy selling; or buy a later break above an "
        "ask that survived heavy buying. Resilience required two seconds of a constant defended price, "
        "fresh valid quotes, at least 10000 USD of directional prints, five times the initial displayed "
        "quantity, 80% directional volume and five distinct trade capture clocks. Unknown-side volume "
        "remained in the denominator. Native fixed-point prices and integer clocks were retained.\n\n"
        f"Independent source audit: {audit['source_rows_verified']:,} native records; "
        f"{c['assessable_symbol_sessions']:,} assessable symbol-sessions; {c['decision_grids']:,} decision grids. "
        f"There were {c['continuous_clean_book_grids']:,} continuous, clean, tight-spread book windows; "
        f"{c['held_bid_grids']:,} held-bid and {c['held_ask_grids']:,} held-ask observations. These overlapping "
        "windows are not independent events.\n\n"
        "ZERO entries qualified. Most held-price observations had no completed trade flow. In held-price "
        "windows with valid flow, 2141 bid-side and 2182 ask-side checks failed the five-distinct-clock "
        "requirement. Other remaining checks failed notional, directional-share or five-times-size gates. "
        "The maximum at-level/initial-display multiple was 19 on the bid and 5.0866666667 on the ask, "
        "but neither statistic means all the other entry conditions passed. No threshold was tuned.\n\n"
        "Two symbol-sessions were unassessable because a BAD_TS_RECV record was present: SPY on "
        "2023-03-28 and UPRO on 2023-07-31. Their signals/returns remain unknown. They were not assigned "
        "zero P&L, nor were bad records removed to reuse an older quote. This is not a full-calendar "
        "portfolio or a statement that every equity resilience strategy loses.\n\n"
        "The planned cheap price proxy deliberately chooses favorable quotes and ignores execution "
        "depth, while charging commission max(1 USD,0.005 USD/share) on each leg, 1bp adverse allowance "
        "per leg and conservative sell levies. It would only identify leads for realistic replay. Because "
        "there were no orders, no cash calculation or economic replay actually ran. The result file's "
        "two economic_screen_configurations denotes two specified hypotheses; it must NOT add two "
        "executed economic configurations to cumulative accounting.\n\n"
        "Eight new focused tests passed. The independent audit used prefix counts and direct trade-window "
        "aggregation, without importing the production detector; all sources and implementation hashes "
        "were verified. No paid data, no real orders, no new 2024/2025/2026 outcomes for this family. "
        "EQUS.MINI is an anonymized component-venue aggregate, not routeable NBBO or private fill evidence.\n\n"
        "Cumulative completed accounting: 134 economic configurations, 184 implementation versions, "
        "358 focused tests. No background processes remain. Next question is saved in NEXT_RESEARCH.txt.\n",
        encoding="utf-8")
    (OUT / "NEXT_RESEARCH.txt").write_text(
        "NEXT QUESTION — A SINGLE LARGE COMPLETED BURST WITH DIRECT PRICE-SURVIVAL PROOF\n\n"
        "The repeated-flow screen found no entries, while some directional volume multiples were large "
        "in fewer than five capture clocks. This motivates a distinct, dependent hypothesis, not a silent "
        "relaxation or repair of the prior experiment. No future returns have been inspected for this question.\n\n"
        "Before testing, freeze a separate specification and code. A proposed candidate must contain one "
        "completed native event/burst at the defended price whose directional quantity alone is at least "
        "five times BOTH the original anchor quantity and the immediately pre-burst displayed quantity. "
        "Require at least 10000 USD and the unchanged 80% full-window volume share; do not exclude unknown "
        "trade sides from that denominator. Determine burst identity and completion from actual native "
        "timestamps and F_LAST boundaries, without inventing an aggressor ID.\n\n"
        "Also require at least 250ms of observed, valid, fresh quotes after that completed burst and before "
        "the signal cutoff, with the defended price surviving throughout. The original two-second held-price "
        "path, current spread, capture buffer and integrity constraints remain. If the feed cannot prove "
        "event completion or the pre/post state, no candidate. Retain both bid-resilience and later ask-break "
        "long-only mechanisms, fixed 15-second responses, conservative costs and the whole search history. "
        "A volume/quote pattern does not identify an iceberg, a specific trader, or all market liquidity.\n\n"
        "Use the same 192 local 2023 sessions for dependent development. Audit signal/event identities "
        "before any outcome-based choice. If candidates exist, run the already designed cheap optimistic "
        "price proxy without tuning, then realistic replay only for surviving leads. Keep 2024+ unopened "
        "for selection in this family until its progression rule is fixed. Do not confuse a proxy gain "
        "with actual outperformance or reliability.\n", encoding="utf-8")
    path = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    checkpoint = json.loads(path.read_text())
    assert (checkpoint["current_configurations"], checkpoint["implementation_versions"], checkpoint["focused_tests_total"]) == (134, 184, 350)
    checkpoint.update(status="active", reliable_edge_found=False, focused_tests_total=358,
                      updated_at_utc=datetime.now(UTC).isoformat(), report=str(report), active_research_jobs=[],
                      equity_resilience_report=str(report), equity_resilience_supply_verified=True,
                      equity_resilience_source_sessions=192, equity_resilience_source_rows=46428207,
                      equity_resilience_events_found=0, equity_resilience_unknown_symbol_sessions=2,
                      equity_resilience_hypotheses_screened=2, equity_resilience_economic_configurations_executed=0,
                      equity_resilience_actual_pnl_evaluations=0, equity_resilience_realistic_execution_run=False,
                      equity_resilience_economic_screen_rules_started=2,
                      next_research_note=str(OUT / "NEXT_RESEARCH.txt"),
                      remaining_evidence_work="Equity repeated-flow resilience screen and independent source audit completed: zero seeds across 1150 assessable symbol-sessions, two symbol-sessions unknown. Next separately freeze a single-completed-burst hypothesis requiring five-times both anchor and pre-burst size plus 250ms post-burst price survival. No new economic replay yet; retain strict HFT and conservative costs.")
    path.write_text(json.dumps(checkpoint, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report), "current_configurations": 134, "implementation_versions": 184,
                      "focused_tests_total": 358, "active_jobs": [], "status": "active"}))


if __name__ == "__main__":
    main()
