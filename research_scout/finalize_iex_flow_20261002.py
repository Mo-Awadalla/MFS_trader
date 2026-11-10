"""Save the fully audited activity-selected negative result and next HFT research direction."""

import json
from datetime import UTC, datetime
from decimal import Decimal

from research_scout.prepare_iex_flow_20261002 import OUT, ROOT, digest


def main():
    flow = json.loads((OUT / "screen_results.json").read_text())
    assert flow["candidate_checks"] == 52 and flow["qualified"] == 2
    flow_audit = json.loads((OUT / "independent_verification.json").read_text())
    probe = OUT / "price_probe_v1"
    result = json.loads((probe / "results.json").read_text())
    audit = json.loads((probe / "independent_verification.json").read_text())
    assert flow_audit["verified"] and flow_audit["results_sha256"] == digest(OUT / "screen_results.json")
    assert audit["verified"] and audit["results_sha256"] == digest(probe / "results.json")
    known = [Decimal(r["known_component_usd"]) for r in result["scenario_results"]]
    assert sum(v < 0 for v in known) == 8 and sum(v == 0 for v in known) == 2
    assert all(r["full_conditional_net_usd"] is None for r in result["scenario_results"])
    assert all(r["full_conditional_net_usd"] is not None for r in result["observed_selected_cohort_results"])
    lines = [
        "IEX TWO-SIDED ACTIVITY: NO PROFITABLE CONDITIONAL CASE",
        "Updated " + datetime.now(UTC).isoformat(), "",
        "The added past-activity filter did not produce an edge worth promotion.",
        "Causal admission: all 52 parent DEEP budget candidates across 23 intact 2023 dates. A candidate needed at least 3 distinct native trade-event times at/below its current bid and at least 3 at/above its current ask during the previous 30 seconds, with at least 5 times its fixed order quantity printed on each side. Native capture, event and send cutoffs, trade flags and causally known breaks were enforced. Unchanged daily ranking; no future return used in admission.",
        "Independent source/count/ranking audit: 20,472,349 native messages, 1,150 retained trade/break records, all 52 candidate checks. Two candidates qualified: TQQQ on 2023-01-11 and RBLX on 2023-08-09. Six focused causal-activity tests passed.",
        "TQQQ: planned quantity 410 shares; prior buy-limit activity 16 distinct timestamps / 5,905 shares; sell-limit activity 12 timestamps / 4,400 shares; required quantity 2,050 each side. These are past prints, not proof of executable queue position.",
        "The policy remained fixed: buy at the original bid, cancel entry remainder after 5s, offer at original ask after acknowledgement, cancel target after 15s, then force residual inventory. Same fees, adverse allowance and 250ms/1s/3s delay cases; same touch and strict-through assumptions. Holdings remain under 30s.",
        "RBLX's exact event, policy and ten previously audited no-entry outcomes were reused. TQQQ was newly replayed from a previously cached native DEEP prefix. Reuse is not independent temporal validation.",
        "Fresh replay audit: 1,489,879 native messages; 28,885 selected-symbol rows; 28,424 derived atomic venue-clock quotes; 10 fresh event-case calculations. A further 10 prior audited outcomes were reused exactly. All 240 calendar rows and 20 aggregate calculations independently verified.",
        "", "Model | case | known conditional USD | observed two-event cohort USD | full-calendar USD",
    ]
    cohort = {(r["fill_model"], r["case"]): r for r in result["observed_selected_cohort_results"]}
    for r in result["scenario_results"]:
        other = cohort[r["fill_model"], r["case"]]
        lines.append(f"{r['fill_model']} | {r['case']} | {r['known_component_usd']} | {other['full_conditional_net_usd']} | {r['full_conditional_net_usd']}")
    lines += ["", "Both models: baseline TQQQ loses $34.632454; doubled fees loses $39.030278; doubled adverse allowance loses $36.167084; 3s delay loses $42.831388. The 250ms case has no entry. RBLX has no entry in every case. Thus eight priced cases lose and two cases have no entry; these are scenarios of the same event, not independent trades.",
              "The observed selected cohort is complete under the conditional model. Full-calendar cash is unknown in every case because 2023-11-29 lacks the initial DEEP source/book history. No missing date was assigned zero. The other 21 dates have no selected signal under the fixed filter.",
              "LIMITS: No private fill, queue, hidden liquidity, historical NBBO protection/routing or acceptance is proven. The inherited probe ignores future execution depth. It is not a funded portfolio or a universal profit bound. Positive past activity did not prevent the price moving against the assumed TQQQ fill. No actual orders or paid API calls occurred.",
              "The current delay assumptions do not settle millisecond HFT feasibility. Any faster model must be separately frozen and clearly conditional on venue/simulator access. A future positive strategy still needs untouched temporal replication, execution/cost/latency stress, concentration and multiple-search assessment.",
              "Global search ledger: 139 economic configurations, 191 implementation versions, 411 focused tests. No reliable edge established; goal remains active.",
              "Data provided for free by IEX. By accessing or using IEX Historical Data, you agree to the IEX Historical Data Terms of Use. https://www.iex.io/legal/hist-data-terms",
              "", "Flow specification SHA256: " + digest(OUT / "specification.json"),
              "Flow results SHA256: " + digest(OUT / "screen_results.json"),
              "Price specification SHA256: " + digest(probe / "specification.json"),
              "Price results SHA256: " + digest(probe / "results.json"),
              "Price audit SHA256: " + digest(probe / "independent_verification.json")]
    report = OUT / "REPORT.txt"
    report.write_text("\n".join(lines) + "\n")
    next_note = OUT / "NEXT_RESEARCH.txt"
    next_note.write_text(
        "Keep the user goal active. Strict HFT only; stocks, ETFs and crypto; conservative fees; prioritize raw outperformance and genuine reliability. No reliable edge exists.\n\n"
        "Static spread capture and the causal two-sided activity variant have no positive priced case. Stop refining those filters on this small sample. The next distinct family should test trade-confirmed fast stock price displacement using the newly validated native DEEP data, then a fixed short holding period.\n\n"
        "Proposed causal admission, to be formally frozen before its first run: use all symbols in the same 24-date 2023 cohort, preserving Nov29 as unknown. Scan 100ms decisions from09:30:30 through09:31:00, with a separately declared 1ms information-age assumption. Use complete atomic DEEP books, valid trading/operational status and exact clocks. Reference the maintained book and latest eligible trade at cutoff minus1s; require both reference/current quotes and trades recent, current trade inside the actual displayed BBO, at least5 distinct eligible native trade events and $25,000 notional in the prior1s. Require an absolute trade move of at least30bp, both bid and ask confirming the direction, current spread<=5bp, and causal aggressive round-trip cost<=12bp under unchanged conservative commissions/slippage/levy. Past move should exceed three times causal cost. Declare sizing, freshness, cooldown, simultaneous-signal ranking and event cap explicitly before running; no future quantity resizing. These are proposals, not yet executed thresholds.\n\n"
        "Potential long-only hypotheses: follow confirmed rises; fade confirmed falls. Inventory under30s. Screen supply first without returns; classify stock/ETF identities before economic replay. Use a separately declared millisecond latency feasibility study (for example1ms,5ms,25ms,250ms), rather than treating previous250ms-to3s cases as evidence about actual HFT. Include the exchange's speed bump in assumed arrival delay; do not claim colocation or fast access is available. Actual venue/simulator latency and order constraints remain unverified.\n\n"
        "All local original DEEP prefixes already cover the current admission endpoint. Reuse them without downloads; maintain hashes and source-gap propagation. Native event ordering is guaranteed per message type/symbol only. Current causal books use capture order and atomic completion; execution books need separate event-clock reconstruction.\n\n"
        "If a positive candidate appears, do not call it an edge from a few events. Require independent source/cash/order-book checks, full depth and queue/acceptance/NBBO uncertainty, untouched temporal holdout, costs/latency stress, concentration and multiple-search assessment. Global counts at this checkpoint:139 economic configurations,191 implementation versions,411 focused tests. No paid API, trading orders, external messages, subagents or country-access bypass are authorized.\n")
    checkpoint = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    state = json.loads(checkpoint.read_text())
    assert (state["current_configurations"], state["implementation_versions"], state["focused_tests_total"]) == (139, 191, 411)
    state.update(updated_at_utc=datetime.now(UTC).isoformat(), status="active", active_research_jobs=[],
                 latest_report=str(report), next_research_note=str(next_note), iex_flow_report=str(report),
                 iex_flow_economic_configurations_executed=1, iex_flow_economic_implementation_versions=1,
                 iex_flow_probe_independently_verified=True, iex_flow_fresh_probe_messages=1489879,
                 iex_flow_complete_selected_cohort_cases=10, iex_flow_positive_selected_cohort_cases=0,
                 iex_flow_full_calendar_complete_cases=0, iex_flow_actual_execution_verified=False,
                 iex_flow_candidates_for_promotion=[],
                 remaining_evidence_work="Activity variant fully audited:2 selected events,1 fresh replay;8 priced cases negative,2 no-entry. Full calendar unknown because Nov29 initial DEEP history is missing. Next:formally freeze trade-confirmed subsecond stock-displacement admission and explicit millisecond latency feasibility; see NEXT_RESEARCH.txt. No reliable edge.")
    checkpoint.write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps({"report": str(report), "counts": [139, 191, 411], "reliable_edge_established": False}))


if __name__ == "__main__":
    main()
