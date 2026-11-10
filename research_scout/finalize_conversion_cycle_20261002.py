"""Save a verified rejection without promoting displayed budgets to profits."""

import json
from datetime import UTC, datetime

from research_scout.prepare_conversion_cycle_20261002 import OUT, ROOT, sha


def main():
    results = json.loads((OUT / "screen_results.json").read_text())
    audit = json.loads((OUT / "independent_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == sha(OUT / "screen_results.json")
    assert results["selected_events"] == results["supply_rows"] == 0
    lines = [
        "SAME-VENUE THREE-MARKET HFT CONVERSION — NO SUPPLY AFTER COSTS", "",
        "No qualifying route, P&L test or reliable edge. The displayed conversion budgets are not executions.", "",
        "A separately frozen cash-identity screen reuses sixty native Binance spot minutes: 00:00, 06:00, 09:00, 12:00 and 18:00 UTC on the first day of each 2024 month. Every contemporaneously recorded BASE/BTC, BASE/ETH or BASE/BNB market with the corresponding BASE/USDT and bridge/USDT books is considered. There is no current-survivor list or return-based coin selection.", "",
        "Each direction starts with 200 USDT and converts through all three actual bid/ask sides back to USDT. Every leg charges 10bp in the received asset plus 1bp adverse execution allowance; fee and adverse stress budgets are separately doubled. Each gross base-asset quantity must fit within 10% of that leg's displayed touch. A positive result would still require historical quantity/tick validation and sequential execution with partial-inventory cleanup.", "",
        "All books must be captured strictly before decision minus 250ms, with capture age no more than one second. Exact duplicates cannot refresh age; invalid latest states are retained. Two consecutive positive budgets above 2bp would be required before selection. This deliberately avoids treating a single asynchronous observation as a tradable cycle.", "",
        f"Coverage: {results['source_counts']['native_messages']:,} native messages; {results['source_counts']['relevant_book_messages']:,} relevant books; {results['quote_rows']:,} saved quote observations; {results['route_rows']:,} directed route/time checks. These highly dependent checks are not independent statistical trials.", "",
        f"All three books pass validity/freshness in {results['valid_books']:,} route/time checks. Of these, 406,599 fail directional depth; the remaining 53,621 all fail the net cash hurdle. Best depth-eligible displayed budget: {float(results['best_depth_eligible_budget_bps']):.6f}bp. No route passes even once, so none can pass the confirmation rule. No later native execution data were acquired.", "",
        f"Independent verification re-parsed every native envelope and reconstructed every saved quote/route state. A separate algebraic product calculation checked base and stressed cash, and independently computed each leg's gross quantity. It reconciled source clocks, rejection reasons, confirmation/cooldown state and aggregate selection. Maximum Decimal difference: {audit['maximum_numeric_difference']}. Seven focused tests and Ruff passed.", "",
        "Limits: the budget relaxes exchange order grids, does not establish historical account eligibility and does not model actual sequential fills. Spot bookTicker supplies no matching-engine timestamp. Freshness rejection does not prove an older standing order expired. The result rejects this frozen screen in these sampled periods; it does not prove that all triangular trading is unprofitable. Previously exposed source history is not pristine validation. Family-specific 2025 validation remains unopened.", "",
        "Evidence: specification.json; screen_implementation.json; quotes/; routes/; selected.parquet; screen_results.json; independent_verification.json. Original results retain their pre-audit flag; the separate verification artifact records completion. An initial audit invocation occurred before the final result file existed, exited without reading outcomes and was rerun unchanged after screen completion.", "",
        "Primary book-field reference: https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams",
    ]
    (OUT / "REPORT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    next_note = {
        "reviewed_at_utc": datetime.now(UTC).isoformat(),
        "status": "Next hypothesis under consideration; no parameter freeze or new economic run",
        "observation": "Displayed three-leg spot conversion gaps do not cover conservative all-leg costs. The FDUSD passive branch separately lacked two-sided trade activity. Neither branch justifies an execution backtest or loosening its original costs.",
        "next_direction": "A broad contemporaneous crypto-perpetual universe may supply brief, large price displacements with independently observed aggressive trade flow. Unlike selecting by liquidation broadcasts, first detect shocks in both bid and ask using native capture/matching clocks, then require actual same-contract trades before considering fixed 15-second follow and fade controls. This is a related price/flow extension, not an independent or unprecedented discovery.",
        "first_step": "Freeze displacement, spread, depth, clock and cooldown gates before inspecting new selected outcomes; reuse the sixty already cached first-of-month 2024 perpetual BBO slices. Retain every symbol and failure. Acquire only pre-decision trades for any surviving events to test whether the shock is backed by executions, then freeze execution before subsequent returns.",
        "constraints": "Strictly HFT, <=30-second planned inventory, conservative costs, no future resizing, no paid data or real orders. Preserve prior failed liquidation, absorption, spot/perpetual and macro-response results. No current survivor list, forward fill of invalid states or claim of globally untouched historical holdout.",
        "not_an_edge": True,
    }
    note_path = OUT / "NEXT_RESEARCH.txt"
    note_path.write_text(json.dumps(next_note, indent=2) + "\n", encoding="utf-8")
    checkpoint_path = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text())
    assert checkpoint["current_configurations"] == 130 and checkpoint["implementation_versions"] == 180
    assert checkpoint["focused_tests_total"] in (289, 296)
    checkpoint.update(
        status="active", paused_at_user_request=False, reliable_edge_found=False,
        focused_tests_total=296, updated_at_utc=datetime.now(UTC).isoformat(),
        report=str(OUT / "REPORT.txt"), active_research_jobs=[],
        last_research_process={"operation": "Independent native quote and three-market cash-identity audit", "exit_code": 0},
        conversion_cycle_report=str(OUT / "REPORT.txt"),
        conversion_cycle_native_messages=results["source_counts"]["native_messages"],
        conversion_cycle_route_rows=results["route_rows"], conversion_cycle_quote_rows=results["quote_rows"],
        conversion_cycle_depth_eligible_rows=53621, conversion_cycle_selected_events=0,
        conversion_cycle_best_displayed_budget_bps=float(results["best_depth_eligible_budget_bps"]),
        conversion_cycle_independently_verified=True, conversion_cycle_economic_implementations=0,
        conversion_cycle_actual_execution_verified=False, conversion_cycle_selection_2025_opened=False,
        next_research_note=str(note_path),
        remaining_evidence_work=(
            "FDUSD spread/activity and same-venue conversion screens are complete and independently "
            "verified; no surviving candidate and no new P&L implementation. No jobs remain active. "
            "Next consider a separately frozen broad crypto-perpetual price-displacement and native "
            "aggressor-flow screen using cached sources, before any fixed 15-second response test; "
            "see NEXT_RESEARCH.txt. Preserve all prior failures and strictly HFT constraints."
        ),
    )
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(OUT / "REPORT.txt"), "configurations": 130,
                      "implementation_versions": 180, "focused_tests_total": 296,
                      "reliable_edge_found": False, "active_research_jobs": []}))


if __name__ == "__main__":
    main()
