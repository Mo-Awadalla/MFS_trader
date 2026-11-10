"""Record the completed common-move experiment without promoting a losing event."""

import json
from datetime import UTC, datetime

from research_scout.prepare_market_lag_replay_20261002 import FLOW, OUT, ROOT, TARGET, sha


def read(path):
    return json.loads(path.read_text())


def main():
    replay = OUT / "replay_v1"
    for parent, name in ((TARGET, "screen_results.json"), (FLOW, "screen_results.json"), (replay, "results.json")):
        audit = read(parent / "independent_verification.json")
        assert audit["verified"] and audit["results_sha256"] == sha(parent / name)
    result = read(replay / "results.json")
    audit = read(replay / "independent_verification.json")
    assert result["events"] == 1 and result["positive_complete_scenarios"] == 0
    (TARGET / "REPORT.txt").write_text(
        "LAGGING TARGETS — SECOND BATCH AUDITED\n\n"
        "Two complete all-symbol minutes on 2024-10-01 at 16:27 and 16:56 UTC; 1,589,929 native messages. "
        "137,344 saved quote states and 134,976 marginal signal rows. Four causally admitted BTC/ETH grids "
        "produced 1,172 target checks: 1,160 quality failures, 11 gap/budget failures and one selected TRX event. "
        "The decision was 16:27:57.500 UTC, using information strictly before 16:27:57.250 UTC.\n\n"
        "All native sources, original leader endpoints, target predicates, ranking and cooldown were "
        "independently reconciled; maximum Decimal arithmetic difference 4.06e-24. This completes target "
        "screening across the seven coherent leader grids from the fixed 49-minute native cohort. The "
        "separate earlier 60 sparse minutes had no qualifying common move. No threshold was lowered.\n\n"
        "One selected target is a hypothesis observation, not an edge. See ../../market_lag_flow_hft_20261002/REPORT.txt "
        "and ../../market_lag_response_hft_20261002/REPORT.txt.\n", encoding="utf-8")
    (FLOW / "REPORT.txt").write_text(
        "COMMON-MOVE TRADE CONFIRMATION — AUDITED\n\n"
        "The one TRX candidate passed the predeclared joint trade gate. In the preceding matching-time second, "
        "captured strictly before the decision cutoff: BTC had 5,111 trades and 41,072,942.94340 USDT, with "
        "96.9784% sell notional; ETH had 2,090 trades and 7,391,206.65340 USDT, with 87.8302% sell notional; "
        "TRX had 57 trades and 24,762.78212 USDT. Both leaders required at least 75% directional notional. "
        "The target required activity only, although all its counted trades were sells.\n\n"
        "The independent audit checked all 27,286 source executions, 20,592 pre-cutoff integrity rows, "
        "7,258 counted trades, all three role gates and selection. Exact match. Four new joint-gate tests passed; "
        "unchanged parent parser tests were not counted again. One event proceeds to both predeclared controls.\n",
        encoding="utf-8")
    lines = [
        "COMMON-MOVE HFT RESPONSE — NO PROFITABLE SURVIVOR", "",
        "Both predeclared directions were tested on the one flow-confirmed TRX event. Orders were fixed "
        "before transmission, at most 200 USDT and 10% of causal touch size; minimum entry 100 USDT, "
        "10bp FOK collar, full notional reserved with 2% buffer, no leverage. Exit decision: 15 seconds "
        "after entry acknowledgement. Fees: 6bp plus 1bp adverse allowance on EACH leg. No funding credited.", "",
        "Rule | Scenario | Conditional net lower / upper USDT | Completed round trips | Outcome"]
    for row in result["scenarios"]:
        net = f"{row['net_lower']} / {row['net_upper']}" if row["complete"] else "UNKNOWN"
        lines.append(f"{row['rule']} | {row['scenario']} | {net} | {row['completed_round_trips']} | {row['outcomes']}")
    lines.extend(["",
        "All eleven calculable scenario cases lost after costs. Baseline follow: -0.379335680 USDT; "
        "baseline fade: -0.212926720 to -0.200135680 USDT. Follow under 100ms clock uncertainty has an "
        "unknown exit because at least one compatible state lacks enough touch quantity. Unknown P&L "
        "is not zero. Neither direction is promoted.", "",
        f"Independent audit: {audit['source_counts']['native_messages']:,} native messages, two fixed intents, "
        f"{audit['quote_envelopes_verified']} execution envelopes, {audit['cash_rectangles_verified']} cash "
        "rectangles and all twelve scenario aggregates matched exactly. The unchanged execution engine's "
        "14 existing tests were reused without inflating the cumulative test count. New scripts passed Ruff.", "",
        "These are conditional displayed-book outcomes, not private fill evidence. Historical price/lot "
        "filters and account permissions remain unverified. One event would be insufficient for reliability "
        "even if positive. No 2025 selection data was opened for this family. This dependent development "
        "experiment adds two economic configurations and two implementation versions.", "",
        "Cumulative accounting: 134 economic configurations, 184 implementation versions, 342 focused tests. "
        "The goal remains ACTIVE; no reliable edge or competition win established.", "",
        "Next research: separately freeze a maintained-depth confirmation experiment. An unchanged BBO "
        "is an acquisition clue only; require a bridged snapshot, uninterrupted native depth sequence and "
        "fresh capture/T/E proof before admitting any resting quote. Keep the same seven causal leader "
        "grids, price-gap/cost gates and all search history. No simple relaxation of quote freshness."])
    (OUT / "REPORT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    path = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    checkpoint = read(path)
    assert (checkpoint["current_configurations"], checkpoint["implementation_versions"], checkpoint["focused_tests_total"]) == (132, 182, 338)
    reports = list(checkpoint["market_lag_reports"])
    reports.extend(str(p / "REPORT.txt") for p in (TARGET, FLOW, OUT))
    checkpoint.update(
        status="active", reliable_edge_found=False, current_configurations=134, implementation_versions=184,
        focused_tests_total=342, updated_at_utc=datetime.now(UTC).isoformat(), report=str(OUT / "REPORT.txt"),
        active_research_jobs=[], paused_at_user_request=False, market_lag_reports=reports,
        market_lag_targets_batch02_verified=True, market_lag_targets_batch02_selected_events=1,
        market_lag_flow_verified=True, market_lag_flow_selected_events=1,
        market_lag_economic_implementations=2, market_lag_execution_and_cash_verified=True,
        market_lag_scenario_cases=12, market_lag_complete_scenarios=11,
        market_lag_positive_complete_scenarios=0, market_lag_actual_execution_verified=False,
        market_lag_selection_2025_opened=False, market_lag_candidates=[],
        remaining_evidence_work="Market-lag target/flow/execution stages completed and independently audited; all 11 calculable cases lost, one exit unknown. Next freeze a separate maintained-depth confirmation experiment before new target-return calculations; source sequence and state evidence required.")
    path.write_text(json.dumps(checkpoint, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(OUT / "REPORT.txt"), "current_configurations": 134,
                      "implementation_versions": 184, "focused_tests_total": 342, "reliable_edge_found": False}))


if __name__ == "__main__":
    main()
