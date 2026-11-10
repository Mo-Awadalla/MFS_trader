"""Save the verified coverage screen and negative ENA execution results."""

import json
from datetime import UTC, datetime
from pathlib import Path

from research_scout.prepare_spot_perp_20261002 import sha

ROOT = Path(__file__).resolve().parents[1]
INITIAL = ROOT / "research_scout/spot_perp_hft_20261002"
EXPANDED = ROOT / "research_scout/spot_perp_clock_hft_20261002"
RESPONSE = ROOT / "research_scout/spot_perp_response_hft_20261002"


def read(path):
    return json.loads(path.read_text())


def main():
    first, expanded, response = [read(p) for p in (
        INITIAL / "screen_results.json", EXPANDED / "screen_results.json", RESPONSE / "replay_v1/results.json")]
    audits = [read(p) for p in (INITIAL / "independent_verification.json", EXPANDED / "independent_verification.json",
                               RESPONSE / "replay_v1/independent_verification.json")]
    for audit, result_path in zip(audits, (INITIAL / "screen_results.json", EXPANDED / "screen_results.json",
                                         RESPONSE / "replay_v1/results.json"), strict=True):
        assert audit["verified"] and audit["results_sha256"] == sha(result_path)
    total_rows = first["grid_rows"] + expanded["grid_rows"]
    total_messages = sum(r["source_counts"][v + "_native_messages"]
                         for r in (first, expanded) for v in ("spot", "perpetual"))
    common = (
        "Frozen mechanism: compare a USDT perpetual with its exact-symbol spot counterpart. "
        "Use only native books captured before each decision minus 250ms. Require current "
        "one-second freshness, at least eight of the prior ten paired one-second observations, "
        "median-ratio dispersion <=10bp, current discrepancy >=25bp, both sides of both books "
        ">=2000 USDT, and a hypothetical full-convergence budget >5bp after two 6bp taker fees "
        "and two 1bp adverse allowances. Require all gates in two consecutive seconds with "
        "the same direction. Only the perpetual would be traded. The recent ratio is a "
        "reference, not a known fair value or a promise of convergence.\n\n"
    )
    (INITIAL / "REPORT.txt").write_text(
        "SPOT/PERPETUAL HFT DISCREPANCY — INITIAL SUPPLY SCREEN\n\n"
        "No selected entry and no P&L test in the initial screen. No reliable edge established.\n\n"
        + common +
        "Coverage: 09:00–09:01 UTC on the first day of each month in 2024. Twelve complete paired "
        "minutes; 3,952,265 spot messages and 5,733,723 perpetual messages; 163,750 symbol/decision rows. "
        "All contemporaneous native USDT perpetuals were considered, including absent spot counterparts. "
        "Symbols were not selected from today's surviving markets.\n\n"
        "Only AEVOUSDT at 09:00:59 on April 1 passed the one-observation price/depth/budget gates. "
        "It lacked the required preceding qualifying observation, so no entry was selected inside "
        "the frozen window. This does not establish what happened after the window.\n\n"
        "Independent validation passed for all 24 source files and every grid decision. A separate "
        "native parser and time-bucket reconstruction checked reference ratios, dispersion, costs "
        "and selection. Maximum Decimal difference 4.9999e-24. Ten focused causal/source tests passed. "
        "The first audit's economically zero direction-label rounding discrepancy is documented in "
        "AUDIT_NUMERIC_NOTE.txt; no production rule or result changed.\n\n"
        "Most rows failed quote freshness, anchor coverage or the price-gap threshold. Failure of "
        "a deliberate freshness gate does not establish that an older standing quote was invalid. "
        "Spot BBO messages lack an exchange matching timestamp; capture time is preserved without "
        "inventing one. The screen cannot prove private fills, contract eligibility or global absence "
        "of opportunities. Family-specific 2025 validation is unopened.\n\n"
        "Evidence: specification.json, spot_manifest.json, screen_implementation.json, grid_states.parquet, "
        "screen_results.json, independent_verification.json. The separately frozen clock expansion "
        "is in ../spot_perp_clock_hft_20261002/.\n",
        encoding="utf-8",
    )
    (EXPANDED / "REPORT.txt").write_text(
        "SPOT/PERPETUAL HFT DISCREPANCY — EXPANDED CLOCK COVERAGE\n\n"
        "One event requires execution testing; no reliable edge established by the screen.\n\n"
        + common +
        "Coverage was expanded prospectively to 00:00, 06:00, 12:00 and 18:00 UTC on the same twelve "
        "2024 dates. All economic thresholds stayed fixed. This is a dependent coverage expansion, "
        "not an independent discovery. Ninety-six complete new native files contain 39,705,696 "
        "messages and produce 654,750 symbol/decision rows. There are two observed perpetual "
        "disconnects; source state is reset instead of carried through them.\n\n"
        f"Including the initial 09:00 sample: {total_messages:,} native messages, {total_rows:,} "
        "decision rows, 60 paired minute windows across 12 dates and five clock times. These rows "
        "are highly dependent; they are not that many independent trading opportunities.\n\n"
        "Five expanded one-observation gates survive, all from ENAUSDT on September 1 at midnight. "
        "The earliest confirmed event is 00:00:16 UTC: approximately +33.8106bp perpetual deviation "
        "and +15.5014bp hypothetical convergence budget. The latter is an assumption-based budget, "
        "not observed return. Exactly one event is retained; no alternate winning time is selected.\n\n"
        "Independent verification passed for all 96 files and all 654,750 decisions. The independent "
        "parser preserves exact source clock fractions, verifies capture/event ordering, and "
        "reconstructs all costs and gates. Maximum Decimal difference 5e-24. Three additional "
        "midnight/evening boundary tests passed. Original sources and both screen versions remain intact.\n\n"
        "The predeclared follow/fade response test is separately reported in "
        "../spot_perp_response_hft_20261002/REPORT.txt. A single event is insufficient for any "
        "statistical reliability claim. No 2025 family validation was opened.\n",
        encoding="utf-8",
    )
    lines = [
        "SPOT/PERPETUAL HFT RESPONSE — BOTH CONTROLS FAIL AFTER COSTS", "",
        "No reliable edge or promoted candidate. All twelve conditional scenario results are complete and negative. They are twelve tests of one event, not twelve independent observations.", "",
        f"Supply: {total_messages:,} native messages and {total_rows:,} causal symbol/time checks across 60 paired minute windows on twelve 2024 dates selected one ENAUSDT event, September 1 at 00:00:16 UTC. Selection was independently reconciled before P&L. All failed and missing-source states remain in the screens.", "",
        "Frozen controls: fade the observed relative-price deviation, or follow it. Trade only ENAUSDT perpetual; spot is a predictor. Both plans use 800 ENA, about 189.5 USDT notional, fixed from the causal quote. The verified price tick is 0.0001; the coarse 100-ENA quantity increment and historical account permissions remain conditional. Full notional is reserved, with no leverage.", "",
        "Timing: 250ms signal feed delay, 50ms processing, one-second outbound and ACK in base. Exit decision fifteen seconds after entry ACK. The native next-funding timestamp was observed before entry and lies safely beyond the latest stressed exit. No funding or rebate is credited.", "",
        "Execution uses native transaction time T, publication E and capture time separately. Every compatible quote, including tied predecessor states, must fit the entire quantity inside the fixed 10bp entry collar. Exit requires full touch depth. No passive queue or deeper liquidity is invented. Unknown outcomes would remain unknown; this cohort has no submitted unknowns.", "",
        "CONDITIONAL RESULTS (USDT; scenarios are alternatives, never summed)",
    ]
    for row in response["scenarios"]:
        lines.append(f"{row['rule']} / {row['scenario']}: {row['net_lower']} to {row['net_upper']}; {row['outcome']}.")
    lines.extend([
        "", "Base fade: gross -0.32 USDT; total fees/adverse allowance 0.26544; net -0.58544. Base follow: gross +0.16; the same 0.26544 cost; net -0.10544. Both also lose with 250ms or three-second order latency, doubled fees, doubled adverse allowance and 100ms clock uncertainty. The convergence budget did not materialize within the frozen holding interval.",
        "", "Independent execution and cash verification passed: all 2,796 selected-contract messages (2,736 BBOs and 60 funding-clock updates), two intents, 24 quote envelopes and 12 cash rectangles/aggregates, with zero numeric difference. Eight focused execution tests passed. Together with the two supply stages, 21 new focused tests passed.",
        "", "Limits: these are conditional historical quote executions, not private fills. Exact historical LOT_SIZE and account permissions are unverified. A launch notice and subsequent tick-size update establish relevant public contract facts but are not a complete historical exchange-rule archive. Even a profitable outcome on this one event would not establish reliability. No 2025 validation was opened, and no real orders or paid data purchases occurred.",
        "", "Primary contract references:",
        "https://www.binance.com/en/support/announcement/detail/db4b4fc4fd0349a892eca0c47293d136",
        "https://www.binance.com/en/support/announcement/detail/aa2bfe791cca4fbc9db2764249b19592",
        "", "Frozen evidence: specification.json; source_manifest.json; ena_native.ndjson.gz; replay_v1/implementation.json; intents.json; all twelve scenario files; results.json; independent_verification.json. Original result audit flags remain as frozen; separate verification artifacts record the completed checks.",
    ])
    (RESPONSE / "REPORT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    next_note = {
        "reviewed_at_utc": datetime.now(UTC).isoformat(),
        "status": "Possible next research direction only; no new strategy or P&L run",
        "observation": "Primary Binance notices document zero maker fees for seven FDUSD spot pairs, while regular-user taker fees became 0.100% on 2024-04-25. The 2026-01-29 update removes the remaining taker promotion for other tiers while retaining zero maker fees. Do not assume VIP status or current zero taker fees.",
        "sources": ["https://www.binance.com/en/support/announcement/detail/3d8514bbc817423eba52fb23483bcbed",
                    "https://www.binance.com/en-TR/support/announcement/detail/4856a6d4e4014d4e8a5a29ec5fb44857"],
        "possible_test": "Check a separately frozen necessary spread/depth budget in those published maker-fee pairs using already cached all-symbol spot books. Preserve conservative adverse execution, nonzero fee stress and full 10bp taker cost for emergency exits. If no supply exists, stop at the screen. Any actual replay needs native passive queue/trade evidence, full residual inventory, matching-clock uncertainty, historical order rules and FDUSD valuation/conversion costs. Do not modify old fee assumptions to rescue old strategies.",
        "not_an_edge": True,
    }
    note_path = RESPONSE / "NEXT_RESEARCH.txt"
    note_path.write_text(json.dumps(next_note, indent=2) + "\n", encoding="utf-8")
    checkpoint_path = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    checkpoint = read(checkpoint_path)
    assert checkpoint["current_configurations"] in (128, 130)
    checkpoint.update(
        status="active", paused_at_user_request=False, reliable_edge_found=False,
        current_configurations=130, implementation_versions=180, focused_tests_total=271,
        report=str(RESPONSE / "REPORT.txt"), updated_at_utc=datetime.now(UTC).isoformat(),
        active_research_jobs=[],
        last_research_process={"operation": "Independent spot/perpetual coverage and ENA execution/cash audits", "exit_code": 0},
        spot_perp_screen_reports=[str(INITIAL / "REPORT.txt"), str(EXPANDED / "REPORT.txt")],
        spot_perp_screen_native_messages=total_messages, spot_perp_screen_decision_rows=total_rows,
        spot_perp_screen_paired_minutes=60, spot_perp_screen_dates=12,
        spot_perp_screen_selected_events=1, spot_perp_screen_independently_verified=True,
        spot_perp_response_report=str(RESPONSE / "REPORT.txt"),
        spot_perp_response_economic_configurations=2, spot_perp_response_scenario_cases=12,
        spot_perp_response_complete_scenarios=12, spot_perp_response_profitable_complete_scenarios=0,
        spot_perp_response_base_net_usdt={"fade_basis": -0.58544, "follow_basis": -0.10544},
        spot_perp_response_independent_execution_and_cash_verified=True,
        spot_perp_response_actual_execution_verified=False, spot_perp_response_candidates=[],
        spot_perp_selection_2025_opened=False,
        next_research_note=str(note_path),
        remaining_evidence_work=(
            "The expanded spot/perpetual discrepancy screen and both ENA response controls are complete and independently audited. "
            "All twelve conditional execution scenarios lose; no reliable edge or candidate. No research process remains running. "
            "The next possible direction is a separately frozen spread/depth screen of publicly documented zero-maker-fee FDUSD spot pairs, "
            "using already cached all-symbol quotes and conservative adverse, fee-stress and forced-taker-exit costs. "
            "Do not assume zero taker fees, VIP status, private fills or a stablecoin conversion at par; see NEXT_RESEARCH.txt. "
            "Preserve all failed variants, unopened 2025 family validation and the user requirement to stay strictly HFT."
        ),
    )
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"reports_written": 3, "configurations": 130, "focused_tests_total": 271,
                      "native_screen_messages": total_messages, "screen_rows": total_rows,
                      "reliable_edge_found": False, "running_jobs": []}), flush=True)


if __name__ == "__main__":
    main()
