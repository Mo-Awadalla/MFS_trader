"""Save verified negative/unknown findings and an honest continuation checkpoint."""

import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIR = ROOT/"research_scout/bybit_funding_hft_20261002"
SINGLE = ROOT/"research_scout/single_funding_hft_20261002"
POST = ROOT/"research_scout/post_funding_hft_20261002"


def read(path):
    return json.loads(path.read_text())


def main():
    paired = read(PAIR/"all_states_screen_results.json")
    pair_audit = read(PAIR/"all_states_independent_verification.json")
    quote_audit = read(PAIR/"quote_gate_independent_verification.json")
    post = read(POST/"replay_v1/results.json")
    post_audit = read(POST/"replay_v1/independent_verification.json")
    assert pair_audit["verified"] and quote_audit["verified"] and post_audit["verified"]
    assert paired["pairs_sha256"] == pair_audit["pairs_sha256"] == quote_audit["full_pairs_sha256"]
    (PAIR/"REPORT.txt").write_text(
        "BYBIT-FIRST PAIRED FUNDING HFT — SOURCE SCREEN COMPLETE\n\n"
        "No viable candidate or reliable edge established. No paired trading P&L was run.\n\n"
        "This dependent extension checks Bybit-only extreme funding rates omitted by the earlier Binance-first screen. Scope: the first day of each month of 2024 at 08:00 and 16:00 UTC, using information captured strictly before settlement minus 10.25 seconds. The original rate, freshness and conservative cost gates remained fixed.\n\n"
        "Coverage: 24 native windows, 1,432,850 Bybit native messages, 8,857 symbol/windows, 481 symbols. Short delta windows omitted 5,519 funding rates; a separately frozen recovery downloaded 12 complete full-universe normalized source files (3,274,038,156 compressed bytes) and read 159,983,313 records. All 8,857 original observations have a recovered state. Recovered does not mean fresh, complete, tradable or profitable.\n\n"
        "Full screen: 5,952 usable Bybit source states, 90 large Bybit rate observations, 19 usable exact-symbol Binance pairs. Outcomes: 5,862 below the rate prescreen; 1,984 stale/invalid/wrong-time normalized states; 921 stale/invalid native states; 71 missing exact Binance counterparts; 17 pairs below the fee hurdle; two candidates above the fee-only hurdle. No native/normalized field conflicts occurred among usable comparisons. The originally missing-rate group adds no new candidate above costs.\n\n"
        "The two candidates are AXLUSDT on 2024-03-01 at 16:00 UTC and STEEMUSDT on 2024-05-01 at 08:00 UTC. Their projected equal-unit payment gaps are 34.77777bp and 29.26103bp before spreads. After both full spreads and four 6bp taker fees plus four 1bp adverse allowances, the projected budgets are -3.01865bp and -4.82767bp. Both also fail the frozen displayed-size gate. These are payment-alone budgets with unchanged quotes, not actual cash profits or a settlement price forecast.\n\n"
        "Independent validation passed: 107,100,000 normalized prefix rows, 8,868 CSV states (including 11 states outside the original native universe), 1,861,370 combined Bybit/Binance native messages, 10,524 native fields and all 8,857 decision flags were reconciled. A separate raw-quote/Decimal audit verified both spread budgets. Six native-field tests, three aggregate reconstruction tests and seven pair-gate tests passed.\n\n"
        "Limits: stale/invalid states remain unusable rather than zero opportunities. Exact historical trading permissions, full native initialization/disconnect history for carried fields and actual execution/funding credits are not established. The two observed negative budgets do not prove that every funding strategy fails. The 2025 validation sample for this branch remains unopened.\n\n"
        "Frozen artifacts: specification.json; native_states.parquet; all_states_recovery_plan.json; all_states_manifest.json; all_states_screen_implementation.json; all_funding_pairs.parquet; all_states_screen_results.json; all_states_independent_verification.json; quote_gate_results.json; quote_gate_independent_verification.json. Earlier partial screens remain intact.\n",
        encoding="utf-8")
    lines = [
        "POST-FUNDING PRICE RESPONSE HFT — DEVELOPMENT DOES NOT ESTABLISH AN EDGE",
        "", "Neither rule qualifies as a candidate. Every aggregate scenario is UNKNOWN because at least one submitted position has unresolved execution or data continuity. Known-component P&L is not portfolio P&L.",
        "", "Frozen rules: follow receiving-side position unwind, or trade its reversal, using only the pre-settlement quoted funding-rate sign. Enter at target +10 seconds, exit decision at +25 seconds; one-second order/acknowledgement delay in base and three seconds in stress. Planned inventory duration is 15 seconds plus clock uncertainty. Require a native nextFundingTime update beyond target +35 seconds before entering. No funding payment is credited or assumed.",
        "", "Sources: 23 complete two-minute windows, 125,203 native messages (90,662 books and 34,541 tickers), 13 disconnects, and 90 predeclared events across 12 dates. Both independent source clocks and disconnect resets are preserved.",
        "", "Only three events pass the frozen entry gates: STEEMUSDT on May 1 at 08:00 UTC; GFTUSDT and XEMUSDT on December 1 at 16:00 UTC. The remaining 87 are retained: 58 fail displayed size, eight exceed the spread gate, 17 lack observed funding-cycle advancement, one lacks a fresh ticker and three lack a valid book.",
        "", "SCENARIO RESULTS (USDT; known components only)",
    ]
    for row in post["scenarios"]:
        lines.append(f"{row['rule']} / {row['scenario']}: {row['known_component_lower']} to {row['known_component_upper']}; {row['known_submitted']} priced, {row['unknown_events']} unknown; full aggregate UNKNOWN.")
    lines.extend([
        "", "Base continuation: one priced losing event, -1.12014 USDT, with two unknowns. Base reversal: one positive and one negative priced event, net -0.00086089 USDT, with one unknown. The small positive upper bound in the reversal clock stress is only a partial component and cannot establish portfolio profitability. STEEM has a post-submission ticker continuity gap; further unknowns arise from physical book depth. None is discarded or booked as zero.",
        "", "Validation: 11 focused execution tests and Ruff passed before P&L. Independent reconstruction then checked all 125,203 native messages, 90 signal plans, 900 ledger rows, 15 submitted unknown outcomes, 35 physical quote paths, 15 cash rectangles and ten scenario aggregates. Maximum numeric difference was 3.21e-15. Original frozen results remain unchanged; the independent verification is a separate artifact.",
        "", "The payment-capture hypothesis prepared immediately before this experiment remains UNRUN: the first unauthenticated Bybit historical-funding API request returned HTTP 403 with a country-access block. No rerouting or repeated symbol requests were used. Projected funding rates were not substituted for realized payments.",
        "", "This is conditional historical quote execution, not private fill evidence. Exact historical contract grids and account permissions remain unverified. Actual inventory duration is unresolved for unknown exits; the 15-second figure describes the planned schedule. No statistical reliability claim is justified by three entry opportunities. The 2025 validation sample for these funding branches remains unopened.",
        "", "Artifacts: specification.json; replay_v1/implementation.json; replay_v1/plans.json; the ten per-rule/scenario ledgers; replay_v1/results.json; replay_v1/independent_verification.json. All original evidence is preserved.",
    ])
    (POST/"REPORT.txt").write_text("\n".join(lines)+"\n", encoding="utf-8")
    checkpoint_path = ROOT/"research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    checkpoint = read(checkpoint_path)
    checkpoint.update(status="active", paused_at_user_request=False, reliable_edge_found=False,
                      current_configurations=126, implementation_versions=176, focused_tests_total=232,
                      report=str(POST/"REPORT.txt"), updated_at_utc=datetime.now(UTC).isoformat(),
                      active_research_jobs=[], last_research_process={"operation": "Independent post-funding and quote-budget audits", "exit_code": 0},
                      bybit_funding_full_source_recovery_complete=True, bybit_funding_source_files_recovered=12,
                      bybit_funding_rows_inspected=159983313, bybit_funding_full_screen=paired,
                      bybit_funding_independent_source_and_pair_screen_verified=True,
                      bybit_funding_quote_budgets_independently_verified=True,
                      bybit_funding_eligible_after_spreads_and_size=0,
                      bybit_funding_candidates=[], bybit_funding_report=str(PAIR/"REPORT.txt"),
                      single_funding_economic_implementations=0,
                      single_funding_payment_source_status="Public exchange API country-access block (HTTP 403); no rerouting, no actual payment record, no P&L run.",
                      post_funding_report=str(POST/"REPORT.txt"), post_funding_economic_configurations=2,
                      post_funding_scenario_cases=10, post_funding_complete_scenarios=0,
                      post_funding_native_messages=125203, post_funding_development_events=90,
                      post_funding_admitted_events=3, post_funding_independent_audit_verified=True,
                      post_funding_actual_execution_verified=False, post_funding_candidates=[],
                      post_funding_selection_2025_opened=False,
                      post_funding_baseline_known_component_usdt={"unwind_continuation": -1.12014, "unwind_reversal": -0.00086089},
                      post_funding_baseline_full_net_usdt={"unwind_continuation": None, "unwind_reversal": None},
                      remaining_evidence_work="Current turn made progress: full Bybit funding recovery and independent source/quote audits; two new post-funding economic rules and ten scenarios independently reconciled. No reliable edge and no candidate advances. No research process remains running. Next safe direction: inspect cached Databento equity/ETF and futures overlap for an untested futures-to-ETF signal while trading only the authorized stock/ETF universe. Reuse existing inventories before acquiring data; freeze a new hypothesis and honest clock/fee model before outcomes. Futures may be a predictor, not a traded instrument. Preserve these failed/unknown funding branches and their unopened 2025 validation samples.")
    if "pause_reason" in checkpoint:
        checkpoint["previous_pause_reason"] = checkpoint.pop("pause_reason")
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2)+"\n")
    print(json.dumps({"checkpoint": str(checkpoint_path), "reports": [str(PAIR/"REPORT.txt"), str(POST/"REPORT.txt")],
                      "reliable_edge_found": False, "research_jobs_running": False}), flush=True)


if __name__ == "__main__":
    main()
