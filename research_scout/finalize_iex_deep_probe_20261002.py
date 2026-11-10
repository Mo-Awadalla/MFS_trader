"""Finalize the depth-qualified rejection diagnostic and preserve the next research step."""

import json
from datetime import UTC, datetime
from decimal import Decimal

from research_scout.prepare_iex_deep_20261002 import OUT, ROOT, digest


def main():
    supply = json.loads((OUT / "screen_results.json").read_text())
    source_audit = json.loads((OUT / "independent_verification.json").read_text())
    probe = OUT / "price_probe_v1"
    results = json.loads((probe / "results.json").read_text())
    audit = json.loads((probe / "independent_verification.json").read_text())
    assert source_audit["verified"] and source_audit["results_sha256"] == digest(OUT / "screen_results.json")
    assert audit["verified"] and audit["results_sha256"] == digest(probe / "results.json")
    assert all(r["full_conditional_net_usd"] is None for r in results["scenario_results"])
    assert all(Decimal(r["known_component_usd"]) < 0 for r in results["scenario_results"])
    assert not any(r["positive_events"] for r in results["scenario_results"])
    complete = [r for r in results["observed_selected_cohort_results"] if r["full_conditional_net_usd"] is not None]
    assert len(complete) == 2 and all(Decimal(r["full_conditional_net_usd"]) < 0 for r in complete)
    report = OUT / "REPORT.txt"
    lines = [
        "IEX DEEP: DISPLAYED-DEPTH ADMISSION AND CONDITIONAL SHORT-HOLD PROBE",
        "Updated " + datetime.now(UTC).isoformat(), "",
        "No reliable edge established. No strategy is promoted for deployment.",
        "Source admission: 24 fixed 2023 dates; 23 intact native DEEP feeds; 22,486,404 messages; 174,007 symbol decisions; 249 cost budgets; 52 candidates; 21 daily selections in 19 stocks/ETFs. Independent decoding, book, cost and ranking audit passed for the intact sources.",
        "The remaining date, 2023-11-29, begins at sequence 45,296 and byte offset 962,448, rather than 1/0. Its 45,295 earlier messages and initial book state are absent. Independent raw inspection reproduced this. Missing admission remains unknown in every full-calendar result.",
        "Among 56 original TOPS candidates with intact DEEP data, 11 had better-priced displayed odd lots; 45 still passed the same budget/activity thresholds. DEEP reconstruction exactly reproduced TOPS protected aggregation for all 56 at the fixed cutoff, assuming a 100-share round lot. This is evidence for those comparisons, not a universal instrument/clock mapping.",
        "Example: RSG on Jan 11 had an original spread budget of $3.0791065. It becomes -$0.9179075 at the actual better 33-share bid. DDOG and TQQQ on Jan 11 retain their original displayed budgets. Displayed budgets are not profits.",
        "", "One new exploratory data-source variant, unchanged policy/costs:",
        "Fixed causal DEEP bid limit; cancel remainder after 5s; after cancellation acknowledgement, target the original DEEP ask; cancel target after 15s; after acknowledgement, force remaining shares. Whole-share size fixed before order; partial print allocations preserved. Per nonempty order: max($1, $.005/share), 1bp adverse on each actual notional, conservative sell levy. Fee/adverse doubling and 250ms/1s/3s delay cases. Touch and strict-through models are conditional assumptions.",
        "Native venue-clock quotes are reconstructed from exact event-time atomic DEEP transitions. Intermediate book updates are never execution references. The causal signal separately uses only pre-cutoff captured messages. Four focused tests cover clock ordering, atomic completion and exact integer preservation.",
        f"Probe audit: {audit['source_messages_verified']:,} native messages; {audit['selected_symbol_messages_verified']:,} selected-symbol messages; {audit['derived_quotes_verified']:,} derived atomic quotes; 210 selected event-case rows; 240 calendar rows; 20 aggregate checks. Independent source, venue-book, conditional allocation and Decimal cash reconstruction passed.",
        "", "Model | case | known conditional USD | full-calendar USD | unknown dates | priced entries",
    ]
    for r in results["scenario_results"]:
        lines.append(f"{r['fill_model']} | {r['case']} | {r['known_component_usd']} | {r['full_conditional_net_usd']} | {r['unknown_events']} | {r['conditionally_priced_entries']}")
    lines += ["", "Baseline: 19 conditional no-entries, 2 known no-signal dates, 1 META conditional trade losing $6.191803, 1 ALB entry-state unknown, 1 source-admission unknown. META is the only priced trade and loses in every case. The 250ms selected-cohort sum is complete and -$9.291400; full-calendar cash remains unknown. The known 3s component of -$205.265920 is based on an IEX displayed bid at $280; actual NBBO/order protection is unresolved.",
              "LIMITS: Public prints do not establish private fills or queue priority. The probe still ignores future execution depth, hidden-liquidity conditions, NBBO routing/protection, historical acceptance/repricing and private clock uncertainty. Even the negative cash figures are conditional, not actual executions or a mathematical bound on all possible implementations. Unknown outcomes are never zero. Independent per-event budgets do not constitute a funded portfolio or benchmark outperformance.",
              "These 250ms-to-3s delay cases and the 250ms information cutoff do not establish the economics of a 1ms HFT implementation. Faster assumptions require a separately frozen feasibility test and actual venue/simulator latency evidence before a reliability claim. No slower intraday strategy is authorized.",
              "All 2023 results are exploratory after repeated search. No new 2024+ economic holdout has been opened in this branch. A positive future candidate requires untouched temporal replication, costs/depth/latency stress, concentration and multiple-search assessment.",
              "Current global ledger: 138 economic configurations, 190 implementation versions, 405 focused tests. No paid API or real orders.",
              "Data provided for free by IEX. By accessing or using IEX Historical Data, you agree to the IEX Historical Data Terms of Use. https://www.iex.io/legal/hist-data-terms",
              "Protocol:https://assets-global.website-files.com/635ad1b3d188c10deb1ebcba/63bd4a1cb0d2bef3cbf36bcc_IEX%20DEEP%20Specification%20v1.08.pdf",
              "Odd-lot aggregation:https://www.sec.gov/rules/sro/iex/2021/34-90933.pdf",
              "", "Supply results SHA256: " + digest(OUT / "screen_results.json"),
              "Probe specification SHA256: " + digest(probe / "specification.json"),
              "Probe results SHA256: " + digest(probe / "results.json"),
              "Probe independent audit SHA256: " + digest(probe / "independent_verification.json")]
    report.write_text("\n".join(lines) + "\n")
    next_note = OUT / "NEXT_RESEARCH.txt"
    next_note.write_text(
        "Research continues. User scope: strictly HFT, stocks/ETFs/crypto, conservative fees, raw outperformance and reliability. No established edge.\n\n"
        "Static wide spreads on these venue books mainly produced no conditional entry. The immediate next inexpensive check should be causal two-sided trade activity at the actual proposed limits, across all 52 depth-budget candidates. Freeze thresholds before parsing outcomes: prior 30s eligible unbroken native T prints; at least 3 distinct native trade-event timestamps at/below current bid and at least 3 at/above current ask; each side cumulative volume >=5 times fixed causal quantity; then unchanged daily ranking. This is a research proposal, not yet a frozen or executed screen. Admission does not prove queue fills.\n\n"
        "Keep Nov 29 source admission unknown. Reuse native DEEP prefixes and parent source/audit hashes; never modify frozen files. No new network needed for this causal screen. No economic configuration increment until a new price policy/variant actually executes.\n\n"
        "If no activity-qualified candidate survives, do not tune these filters on future prices. The next distinct family can use trade-confirmed subsecond stock price displacement with native depth; specify rules and inventory under 30s before testing. Consider an explicit millisecond latency feasibility study: prior broad screens used 250ms information age and 50ms compute plus 250ms-to-3s one-way delay, which is not proof about colocation-scale HFT. Never label assumed fast access as available or reliable without venue/simulator evidence.\n\n"
        "Any positive candidate remains exploratory after 138 economic configurations. Require independent source, cash, queue, depth and order-protection checks; untouched temporal holdout; cost/latency stability; concentration and search-adjusted inference. No paid API, orders, external messages or country-access bypass.\n")
    checkpoint = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    state = json.loads(checkpoint.read_text())
    assert (state["current_configurations"], state["implementation_versions"], state["focused_tests_total"]) == (138, 190, 405)
    state.update(updated_at_utc=datetime.now(UTC).isoformat(), status="active", active_research_jobs=[],
                 latest_report=str(report), next_research_note=str(next_note),
                 iex_deep_report=str(report), iex_deep_probe_independently_verified=True,
                 iex_deep_probe_source_messages=audit["source_messages_verified"],
                 iex_deep_probe_calendar_cases=10, iex_deep_probe_full_calendar_complete_cases=0,
                 iex_deep_probe_selected_cohort_complete_cases=len(complete),
                 iex_deep_probe_positive_priced_events=0, iex_deep_candidates_for_promotion=[],
                 iex_deep_economic_configurations_executed=1, iex_deep_economic_implementation_versions=1,
                 iex_deep_actual_execution_verified=False,
                 remaining_evidence_work="DEEPsupply and21-event conditionalprobe fullyindependently audited;no positive pricedtrade. Allcalendarcasesunknownwithnegativeknowncomponents;2complete selected-cohortcasesnegative. Next:freeze causal two-sided activity admission across52depth-budget candidates;preserveNov29unknown. SeeNEXT_RESEARCH.txt.")
    checkpoint.write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps({"report": str(report), "supply_candidates": supply["candidates"],
                      "counts": [138, 190, 405], "reliable_edge_established": False}))


if __name__ == "__main__":
    main()
