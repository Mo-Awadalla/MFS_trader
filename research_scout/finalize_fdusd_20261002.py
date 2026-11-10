"""Preserve the verified FDUSD screen rejection and update the active checkpoint."""

import json
from datetime import UTC, datetime

import pandas as pd

from research_scout.prepare_fdusd_activity_20261002 import OUT, PARENT, ROOT, sha


def main():
    supply = json.loads((PARENT / "screen_results.json").read_text())
    activity = json.loads((OUT / "screen_results.json").read_text())
    for folder in (PARENT, OUT):
        audit = json.loads((folder / "independent_verification.json").read_text())
        assert audit["verified"] and audit["results_sha256"] == sha(folder / "screen_results.json")
    frame = pd.read_parquet(OUT / "activity.parquet")
    zero_windows = int(((frame.buy_count + frame.sell_count) == 0).sum())
    peak_min_count = int(frame[["buy_count", "sell_count"]].min(axis=1).max())
    (PARENT / "REPORT.txt").write_text(
        "FDUSD MAKER HFT — VERIFIED SPREAD SUPPLY, NO CANDIDATE AFTER ACTIVITY FILTER\n\n"
        "No reliable edge, execution claim or P&L result. A wide quote is not a profitable fill.\n\n"
        "All contemporaneously recorded FDUSD spot symbols were screened in sixty cached one-minute "
        "Binance slices: five fixed clock times on each first-of-month date in 2024. The native source "
        "contains 21,889,483 messages, including 1,972,743 relevant FDUSD or FDUSD/USDT books. "
        "There are 117 symbols, 5,083 symbol/windows and 254,150 one-second grid decisions.\n\n"
        "The frozen gate requires a spread of 8 through 100bp, both touch notionals >=2000 FDUSD, "
        "and sufficient persistence: at least 40 valid and 30 qualifying decisions out of 50. "
        "48 symbol/windows across 16 symbols and ten dates pass. They are supply candidates only.\n\n"
        "Published exchange notices describe zero FDUSD maker fees during this historical sample. "
        "Even so, the screen reserves 1bp fee plus 1bp adverse allowance on each maker leg, separately "
        "doubles either allowance, and budgets a 10bp taker fee plus 1bp adverse allowance for forced "
        "cleanup. No VIP eligibility or zero taker fee is assumed. FDUSD/USDT quotes are retained "
        "separately; FDUSD is never assumed to equal USDT or one US dollar.\n\n"
        "Independent verification reconciles every source envelope, all 254,150 decisions, 3,000 FX "
        "observations, exact cash budgets and the complete selection with zero numeric difference. "
        "Seven focused tests passed. The audit detected optional nanosecond timestamps serialized "
        "as float64. Exact clocks were rebuilt from raw integers: maximum prior rounding 128ns, "
        "219,065 affected values, with every non-clock observation and selection unchanged. "
        "Use precise_grids_v2/ and precise_fx_v2/ with clock_serialization_repair.json. Original "
        "tables and unsuccessful repair/audit evidence remain preserved.\n\n"
        "The follow-up activity test rejects all 48 candidates; see ../fdusd_activity_hft_20261002/REPORT.txt. "
        "No future-minute return, order queue, pair-specific historical order-grid or actual-fill "
        "claim is made. Family-specific 2025 validation remains unopened.\n\n"
        "Primary fee notices:\n"
        "https://www.binance.com/en/support/announcement/detail/0e4155610e6f4e8bbaaa332545dc43a2\n"
        "https://www.binance.com/en/support/announcement/detail/f7c6bd7931db40aa83931556b5a43565\n"
        "https://www.binance.com/en/support/announcement/detail/3d8514bbc817423eba52fb23483bcbed\n",
        encoding="utf-8",
    )
    (OUT / "REPORT.txt").write_text(
        "FDUSD MAKER HFT — PAST-ONLY ACTIVITY FILTER FAILS\n\n"
        "No candidate survives. No P&L test was run and no reliable edge is established.\n\n"
        "All 48 spread/depth windows from the audited parent were retained. Before obtaining trade "
        "data, the follow-up froze a minimum of ten unique executions and 2000 FDUSD executed "
        "notional in EACH aggressor direction. Only matching times at or after second 10, with "
        "capture strictly before minute end minus 250ms, can count. The threshold is an operational "
        "liquidity requirement, not proof that every alternative HFT strategy is impossible.\n\n"
        "The 32 complete, unauthenticated historical responses contain 148 native trades, 127 of "
        "which enter the past-only counting interval. All 48 candidates fail two-sided activity. "
        f"{zero_windows} symbol/windows have no qualifying counted trade; the largest smaller-side "
        f"trade count is {peak_min_count}. Total new decoded data: 29,294 bytes.\n\n"
        "Independent parsing verifies every native trade, exact nanosecond ledger clock, direction, "
        "notional, ID sequence, candidate denominator and selection, with zero difference. There "
        "are no detected pre-cutoff duplicate conflicts, ID gaps, regressions or clock failures. "
        "Eleven focused source/causality tests passed. The auditor has one nonsemantic Ruff B905 "
        "warning for an intentionally adjacent-pair zip; it passes with B905 ignored. The verified "
        "source and auditor hashes are preserved, without editing frozen code for style.\n\n"
        "This rejects the frozen liquidity filter in these sampled windows. Empty responses do "
        "not establish that the asset could not trade, nor does this limited sample prove an "
        "absence of profitable HFT everywhere. No private fill, queue clearance, new executable "
        "quote, future return or historical order-rule eligibility was inferred. No 2025 family "
        "validation, paid acquisition or real order was opened.\n\n"
        "Evidence: specification.json, source_manifest.json, native/, screen_implementation.json, "
        "ledgers/, activity.parquet, selected.parquet, screen_results.json, independent_verification.json.\n",
        encoding="utf-8",
    )
    (PARENT / "SERIALIZATION_REPAIR_COMPLETION.txt").write_text(
        "The v2 repair completed and the independent full-envelope audit passed. Authoritative "
        "clock tables: precise_grids_v2/ and precise_fx_v2/. The earlier precise_grids/ and "
        "precise_fx/ files are incomplete repair-attempt evidence, not downstream inputs. "
        "The first repair failed because optional object nulls compared as None versus NaN; v2 "
        "compares identical missingness and exact observed values. No economic field or selection "
        "changed. See clock_serialization_repair_plan_v2.json and independent_verification.json.\n",
        encoding="utf-8",
    )
    path = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    checkpoint = json.loads(path.read_text())
    assert checkpoint["current_configurations"] == 130 and checkpoint["implementation_versions"] == 180
    assert checkpoint["focused_tests_total"] in (271, 289)
    checkpoint.update(
        status="active", paused_at_user_request=False, reliable_edge_found=False,
        focused_tests_total=289, updated_at_utc=datetime.now(UTC).isoformat(),
        report=str(OUT / "REPORT.txt"), active_research_jobs=[],
        last_research_process={"operation": "Independent FDUSD spread and activity source audits", "exit_code": 0},
        fdusd_supply_report=str(PARENT / "REPORT.txt"), fdusd_activity_report=str(OUT / "REPORT.txt"),
        fdusd_supply_native_messages=supply["source_counts"]["native_messages"],
        fdusd_supply_grid_rows=supply["grid_rows"], fdusd_supply_selected_windows=48,
        fdusd_supply_independently_verified=True, fdusd_clock_serialization_repaired=True,
        fdusd_activity_native_messages=activity["source_counts"]["native_messages"],
        fdusd_activity_candidates=0, fdusd_activity_independently_verified=True,
        fdusd_economic_implementations=0, fdusd_actual_execution_verified=False,
        fdusd_selection_2025_opened=False,
        remaining_evidence_work=(
            "The FDUSD spread/depth screen and activity filter are complete and independently verified. "
            "All 48 supply windows fail the predeclared two-sided native trade activity requirement; "
            "no P&L or private-fill claim. No jobs remain active. Continue a separately frozen strictly "
            "HFT hypothesis using available free data. Preserve prior failures and untouched family-specific "
            "validation; observed spread budgets do not constitute edge or profit."
        ),
    )
    path.write_text(json.dumps(checkpoint, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"reports_written": 2, "configurations": 130, "implementation_versions": 180,
                      "focused_tests_total": 289, "reliable_edge_found": False,
                      "zero_activity_windows": zero_windows, "largest_smaller_side_count": peak_min_count}))


if __name__ == "__main__":
    main()
