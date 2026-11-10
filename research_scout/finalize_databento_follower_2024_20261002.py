"""Save the audited 2024 expansion and an honest combined discovery checkpoint."""

import json
from datetime import UTC, datetime
from decimal import Decimal

from research_scout.databento_follower_2024_20261002 import OUT, PARENT
from research_scout.prepare_databento_fast_20261002 import ROOT, sha, write


def main():
    current = json.loads((OUT / "screen_results.json").read_text())
    audit = json.loads((OUT / "independent_verification.json").read_text())
    previous = json.loads((PARENT / "screen_results.json").read_text())
    previous_audit = json.loads((PARENT / "independent_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == sha(OUT / "screen_results.json")
    assert previous_audit["verified"] and previous_audit["results_sha256"] == sha(PARENT / "screen_results.json")
    assert current["selected_count"] == previous["selected_count"] == 0
    assert Decimal(current["best_projected_net_bp"]) < 0 and Decimal(previous["best_projected_net_bp"]) < 0
    report = OUT / "REPORT.txt"
    lines = [
        "DATABENTO SPY/FOLLOWER PRICE GAP: NO QUALIFYING SIGNAL IN 2023 OR 2024",
        "Updated " + datetime.now(UTC).isoformat(), "",
        "No edge has been established. The unchanged causal signal produced no selected event in either development period. All computable hypothetical convergence budgets were negative after the specified costs. No future price replay or economic configuration was executed for this family.", "",
        "Period | cached sessions processed | source records | SPY sweeps | valid leader signals | follower checks | budgets | best projected net bp | selected",
    ]
    for label, r in (("2023", previous), ("2024", current)):
        lines.append(f"{label} | {r['sessions']} | {r['source_rows']} | {r['leader_groups']} | {r['valid_leader_signals']} | {r['follower_checks']} | {r['budgets']} | {r['best_projected_net_bp']} | {r['selected_count']}")
    combined = {k: current[k] + previous[k] for k in (
        "sessions", "source_rows", "leader_groups", "valid_leader_signals", "follower_checks", "budgets")}
    lines += ["", f"Combined: {combined['sessions']} cached sessions, {combined['source_rows']:,} source records and {combined['budgets']} budgets. These are opportunity checks, not executed trades or independent profit observations.",
              "All market-data reads were from existing local Databento DBN files. The runners made zero market-data API or paid calls. Issuer documentation was separately consulted to verify fund identities and daily objectives; it was not used to select trading outcomes.", "",
              "RULES HELD FIXED",
              "A previously defined large, completed, single-side SPY multi-price trade group triggers a decision at the first whole millisecond strictly after its capture time plus 1ms. The information cutoff is decision minus 1ms, within 09:30:05–09:39:30 ET. The common reference is exactly one second earlier. Use only the latest complete F_LAST state strictly before each cutoff. Current SPY quote age is at most 5ms; reference SPY and both follower snapshots at most 250ms by receive/native clocks. Both SPY bid and ask must move in the initiating direction. Positive uncrossed cent prices and spreads at most 5bp are required.",
              "A positive SPY move can select a long SSO or UPRO position; a negative move can select long SH, SDS or SPXU. The projected follower mid equals its reference mid times [1 + beta * (current SPY mid / reference SPY mid - 1)]. Subtract the current follower half-spread and round down to cents for the modeled liquidation price. The published multipliers are daily targets; their use over one second is an unverified forecasting assumption, not a price guarantee or proof of arbitrage.",
              "Fixed quantity is at most 10% of both current touches and at most $10,000 at a buy collar 2% above current ask, rounded up to cents. Costs retain two max($1, $0.005/share) commissions, 1bp adverse allowance on each notional, and sale charges. Current roundtrip cost must be at most 12bp, and the projected net gain at least 2bp. Rank projected dollars, then projected basis points; impose 6s global and 60s symbol cooldowns. No threshold, fee, size or timing rule changed for 2024.", "",
              "2024 AUDIT",
              f"Independently enumerated {audit['trade_groups_verified']:,} SPY trade-bearing groups, including {audit['rejected_groups_verified']:,} rejected groups and {audit['qualified_groups_verified']:,} qualifying groups. Recomputed all reference clocks, eligible follower checks, {audit['budgets_verified']} projected prices and cash budgets, and zero selections. Whole-cent projected exit prices were independently derived from integer rational arithmetic. All source hashes and source-record totals agreed.",
              "Both implementations use the Databento SDK to decode DBN. The audit is independent field, grouping and calculation logic, not a separate binary-format decoder. The 2023 audit covered all reported qualifying SPY groups and their downstream checks, but did not independently enumerate every earlier rejected group; the 2024 audit now does.", "",
              "UNKNOWN DATA AND LIMITS",
              "SPY on 2024-04-10 has BAD_TS_RECV and is unassessable; it is not evidence of no opportunity that day. Earlier source unknowns remain SPY on 2023-03-28 and UPRO on 2023-07-31. No missing signal or inventory was assigned zero profit. EQUS.MINI is an anonymized component-venue feed; consolidated NBBO, routing, acceptance, hidden liquidity and private fills are not established. Actual client latency is unmeasured.",
              "The cached files cover opening windows, not complete trading days. This does not reject all intraday, stock or crypto HFT strategies, and it does not prove that no opportunity existed outside these windows or in unassessable data. The planned 1s/5s execution cases were not run because there was no selected signal.",
              "2024 was a discovery expansion after an empty 2023 signal screen. Unrelated earlier research had already used 2024 data; this is not an untouched validation claim. No 2025 or 2026 DBN outcomes were opened for this family.", "",
              "NEXT WORK",
              "A final unchanged supply expansion can inspect all 250 cached 2025 opening sessions before rejecting this particular sweep-triggered follower hypothesis over the available development years. Freeze source hashes and rules first; do not cherry-pick volatility dates or relax thresholds. Keep the 112 cached 2026 files out of this family until a candidate is selected and a separate temporal evaluation is frozen. If 2025 supply is also empty, stop revising this signal and move to a structurally different HFT mechanism.",
              "Keep all source-quality failures explicit. A positive hypothetical budget would only justify replay; it would still need independent causal execution/cash checks, complete source enumeration, concentration and multiple-search assessment, temporal replication and actual execution feasibility. No reliable edge or competition win is claimed.", "",
              "Global ledger: 143 economic configurations, 195 implementation versions, 439 focused tests. This 2024 expansion reused frozen tested rules and adds no economic configuration or test count. Goal remains active.",
              "Specification SHA256: " + sha(OUT / "specification.json"),
              "Results SHA256: " + sha(OUT / "screen_results.json"),
              "Audit SHA256: " + sha(OUT / "independent_verification.json")]
    report.write_text("\n".join(lines) + "\n")
    next_note = OUT / "NEXT_RESEARCH.txt"
    next_note.write_text(
        "User: strict HFT; stocks, ETFs and crypto; prioritize raw outperformance and actual reliability. Latest explicit direction is to use available Databento without paid calls. No reliable edge. Goal active, no live research process at this checkpoint.\n\n"
        "The unchanged SPY sweep/follower lag screen is fully complete on cached 2023 and 2024 opening windows: 444 sessions processed, 106,504,078 source records, 2,040 reported qualifying SPY sweeps, 806 valid leader signals, 4,030 follower checks, 825 computed budgets; all budgets negative, zero selected events. Best2023=-4.8574842767bp; best2024=-2.3443413729bp. No economic replay or configuration was run for this family.\n\n"
        "2024 independently rebuilt every accepted AND rejected SPY trade group: 346,319 total, 1,482 accepted, 344,837 rejected. The audit also verified all leader/follower snapshots and 623budgets using integer-rational projected prices. Shared Databento SDK decoder, separate calculation logic.2023 audit earlier rejection enumeration remains incomplete, though every reported accepted group and downstream predicate was audited.\n\n"
        "Source unknowns: SPY2023-03-28, UPRO2023-07-31, SPY2024-04-10. Do not treat unassessable source dates as no opportunity or zero PnL. The family uses daily fund multipliers as a second-scale modeling hypothesis, not an actual intraday tracking guarantee.\n\n"
        "Next safe step: freeze a final supply-only expansion with IDENTICAL signal/cost/size/timing rules on all250cached2025files. Source directory external_artifacts/databento_cash_etf_mbp1_open_v55/EQUS.MINI/mbp-1. Keep112cached2026files out of this family until a positive candidate and a separate validation protocol exist.2025was used in unrelated earlier work, so call this discovery expansion, not globally untouched validation. If empty, stop refining this sweep/follower hypothesis.\n\n"
        "Reuse immutable research/equity_follower_lag.py, research/equity_sweep.py and research/equity_resilience.py. Do NOT edit their frozen code. The2024driver and independent auditor have output folders bound at module level; use a new explicit adapter/version for2025 instead of silently overwriting2024artifacts. Audit all rejected groups and source errors; detect nonmonotone capture clocks before pretending an invalid symbol-session is known. Maintain signed/unsigned integer precision: np.searchsorted must receive an explicit matching integer dtype, never an implicit float conversion near epoch nanoseconds.\n\n"
        "Global ledger143economic configurations/195implementation versions/439focused tests. Last goal turn is progress, not blocked. No paid APIs, account changes, orders, external messages, subagents or country-access bypass. Future positive conditional results need actual routeability/clock/depth/acceptance corroboration, independent accounting, concentration and multiple-search controls and temporal/forward replication before any reliability claim.\n")
    checkpoint = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    state = json.loads(checkpoint.read_text())
    assert (state["current_configurations"], state["implementation_versions"], state["focused_tests_total"]) == (143, 195, 439)
    state.update(updated_at_utc=datetime.now(UTC).isoformat(), status="active", active_research_jobs=[],
                 latest_report=str(report), next_research_note=str(next_note),
                 databento_follower_2024_report=str(report), databento_follower_2024_verified=True,
                 databento_follower_2024_all_group_rejections_verified=True,
                 databento_follower_2024_source_rows=current["source_rows"],
                 databento_follower_2024_trade_groups=current["group_counts"]["trade_bearing_groups"],
                 databento_follower_2024_candidates=0, databento_follower_2024_economic_configurations_executed=0,
                 databento_follower_2024_best_projected_net_bp=current["best_projected_net_bp"],
                 databento_follower_combined_supply=combined,
                 previous_goal_turn_classification="progress",
                 remaining_evidence_work="Unchanged follower admission fully audited on2023/2024cacheddata;825negative budgets,zero signals. Next freeze final unchanged2025supply expansion;reserve2026forseparateevaluation. No reliable edge, actual execution or paid call.")
    write(checkpoint, state)
    print(json.dumps({"report": str(report), "combined": combined, "counts": [143, 195, 439],
                      "reliable_edge_established": False, "market_data_api_calls": 0}))


if __name__ == "__main__":
    main()
