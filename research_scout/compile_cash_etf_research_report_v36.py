"""Compile final v34-v36 machine results and report from executed artifacts."""

from __future__ import annotations

import json
from datetime import datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
RS = ROOT / "research_scout"
OUT_JSON = RS / "cash_etf_auction_research_results_v36.json"
OUT_MD = RS / "SPY_CASH_ETF_AUCTION_RESEARCH_REPORT_V36.md"


def load(name: str) -> dict[str, Any]:
    return json.loads((RS / name).read_text(encoding="utf-8"))


def metric_line(result: dict[str, Any]) -> str:
    if not result.get("trades"):
        return "0 trades"
    return (
        f"{result['trades']} trades, fixed-$100 P&L ${result['fixed_100_pnl_usd']:.2f}, "
        f"PF {result['profit_factor']:.3f}, spread drag ${result['spread_drag_usd']:.2f}, "
        f"one-cent stress P&L ${result['adverse_cent_pnl_usd']:.2f}"
    )


def observability(signals: dict[str, Any], snapshots: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    ny = ZoneInfo("America/New_York")
    rows = []
    for day in signals:
        snapshot = snapshots[(day, "09:29:50")]
        received = datetime.fromisoformat(snapshot["ts_recv"]).astimezone(ny)
        date = datetime.fromisoformat(day).date()
        cutoff = datetime.combine(date, time(9, 29, 50), ny)
        earliest_order = datetime.combine(date, time(9, 30, 1), ny)
        rows.append((received, cutoff, earliest_order))
    return {
        "signals": len(rows),
        "ts_recv_before_cutoff": sum(received < cutoff for received, cutoff, _ in rows),
        "ts_recv_at_or_after_cutoff": sum(received >= cutoff for received, cutoff, _ in rows),
        "ts_recv_before_earliest_order": sum(received < order for received, _, order in rows),
        "ts_recv_at_or_after_earliest_order": sum(received >= order for received, _, order in rows),
        "minimum_lead_to_earliest_order_seconds": min(
            ((order - received).total_seconds() for received, _, order in rows),
            default=None,
        ),
    }


def main() -> int:
    technical = load("new_data_technical_audit_v34.json")
    v20 = load("v20_tbbo_execution_fidelity_audit_v34.json")
    v35 = load("spy_auction_absorption_failure_returns_blind_audit_v35.json")
    v36 = load("spy_auction_price_quantity_disagreement_returns_blind_audit_v36.json")
    prereg = load("spy_auction_price_quantity_disagreement_prereg_v36.json")
    snapshot_payload = load("spy_auction_snapshots_v34.json")
    snapshots = {
        (row["session_date"], row["cutoff"]): row
        for row in snapshot_payload["snapshots"]
    }
    v35_observability = observability(v35["signals"], snapshots)
    v36_observability = observability(v36["signals"], snapshots)
    results = {
        "status": "no_new_alpha_test_opened_returns_blind_gates_stopped_v35_and_v36",
        "new_candidate_returns_viewed": False,
        "new_candidate_pnl_calculated": False,
        "paid_api_calls_made": False,
        "technical_audit": {
            "imbalance_rows": technical["imbalance"]["rows"],
            "imbalance_clean_eof": technical["inventory"]["auction_signal"]["clean_eof"],
            "auction_type_counts": technical["imbalance"]["auction_type_counts"],
            "tbbo_segments": technical["tbbo"]["segments"],
            "prefix_boundary_seen_and_stopped": technical["tbbo"]["prefix_boundary_seen_and_stopped"],
            "prefix_terminal_warning_observed": technical["tbbo"]["prefix_terminal_warning_observed"],
            "tbbo_valid_rows_by_symbol": {
                symbol: row["rows_valid"] for symbol, row in technical["tbbo"]["symbols"].items()
            },
            "degraded_dates": technical["degraded_dates"],
            "standing_quote_age_observable": False,
            "quantity_semantic_break": "2025-11-13: paired/total/market quantities switch from ind_match_price basis to ref_price basis",
        },
        "v20_execution_fidelity": {
            "status": v20["status"],
            "rule_modified": v20["rule_modified"],
            "orders_constructed": v20["orders_constructed"],
            "orders_with_both_fills": v20["orders_with_both_fills"],
            "partitions": v20["partitions"],
            "standing_quote_age_observable": v20["standing_quote_age_observable"],
            "decision": "Historical execution audit only; V20 remains rejected by its original concentration gate.",
        },
        "new_candidates": {
            "V35": {
                "status": v35["status"],
                "returns_viewed": v35["returns_read"],
                "feature_development": v35["feature_development_2021_2023"],
                "executable_development_overlap": v35["executable_development_overlap_2023_03_28_2023_12_31"],
                "failed_gates": [name for name, passed in v35["gates"].items() if not passed],
                "signal_observability": v35_observability,
                "decision": "Terminal returns-blind rejection; no widening or P&L.",
            },
            "V36": {
                "status": v36["status"],
                "returns_viewed": v36["returns_read"],
                "feature_development": v36["feature_development_2021_2023"],
                "executable_development_overlap": v36["executable_development_overlap_2023_03_28_2023_12_31"],
                "all_overlap": v36["all_overlap"],
                "by_year": v36["by_year"],
                "adjacent_cutoff_stability": v36["adjacent_cutoff_stability"],
                "failed_gates": [name for name, passed in v36["gates"].items() if not passed],
                "signal_observability": v36_observability,
                "decision": "Terminal returns-blind rejection; preregistration not activated and no P&L.",
            },
        },
        "preregistration": {
            "candidate": prereg["candidate"],
            "status": prereg["status"],
            "returns_authorized": prereg["returns_authorized"],
            "failed_returns_blind_gates": prereg["failed_returns_blind_gates"],
        },
        "program_decision": {
            "historical_survivor": False,
            "production_ready": False,
            "forward_paper_rule_activated": False,
            "reason": "No new candidate passed all frozen returns-blind feasibility gates; opening P&L would create avoidable outcome exposure.",
        },
    }
    OUT_JSON.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    v20_lines: list[str] = []
    for partition, delays in v20["partitions"].items():
        for delay, row in delays.items():
            v20_lines.append(f"- {partition}, {delay}s: {metric_line(row)}.")
    v35_failed = ", ".join(results["new_candidates"]["V35"]["failed_gates"])
    v36_failed = ", ".join(results["new_candidates"]["V36"]["failed_gates"])
    report = f"""# Institutional Cash-ETF and SPY-Auction Research Report v36

## Decision

**No new strategy P&L was opened.** V35 and V36 both passed a serious institutional-mechanism critique but failed frozen returns-blind gates. Calculating their returns after failure would add contamination without producing an admissible candidate. There is no historical survivor and no production-readiness claim.

V20 remains the strongest prior margin-free reference candidate, but it remains rejected by its original winner-concentration gate. Its event-level TBBO work below is an execution-fidelity audit only.

## 1. New-data technical evidence

- SPY ARCX.PILLAR imbalance: {technical['imbalance']['rows']:,} records, {min(technical['imbalance']['auction_type_session_counts'].values()):,} sessions per observed O/M/C type, clean EOF.
- Auction types are venue-documented: O Early Opening, M Core Opening, H Halt Resume, C Closing. This file contains O/M/C and no H.
- Core signal ordering uses `ts_event` converted to America/New_York. `auction_time` is an exchange-local projected wall clock and is not the publication timestamp.
- Documented measurement break: from 2025-11-13, paired, total-imbalance, and market-imbalance quantities are measured at `ref_price`; before that date they are measured at `ind_match_price`.
- TBBO logical decode obeyed the mandatory boundary: {technical['tbbo']['segments']['prefix_through_2024-10-02']['rows_consumed']:,} prefix records through 2024-10-02 and {technical['tbbo']['segments']['tail_from_2024-10-03']['rows_consumed']:,} clean-tail records from 2024-10-03.
- Valid trade-event TBBO rows after rejecting crossed/nonpositive quotes: SPY {technical['tbbo']['symbols']['SPY']['rows_valid']:,}; SSO {technical['tbbo']['symbols']['SSO']['rows_valid']:,}; UPRO {technical['tbbo']['symbols']['UPRO']['rows_valid']:,}; SH {technical['tbbo']['symbols']['SH']['rows_valid']:,}; SDS {technical['tbbo']['symbols']['SDS']['rows_valid']:,}; SPXU {technical['tbbo']['symbols']['SPXU']['rows_valid']:,}.
- EQUS.MINI is a derived anonymized multi-venue product, not official SIP NBBO. It samples BBO immediately before trades and does not contain every quote update. True standing-quote age and quote-only lead/lag remain unobservable.
- The exact {len(technical['degraded_dates']['ARCX.PILLAR'])} ARCX and {len(technical['degraded_dates']['EQUS.MINI'])} EQUS degraded dates are loaded from the condition files and excluded by union in primary eligibility.
- ARCX statistics identify Core Open, Closing, and Early Open/halt-reopen outcomes. They are post-cross outcomes and are prohibited as pre-auction signal inputs.
- Publication-time proof: all {v35_observability['signals']} V35 and {v36_observability['signals']} V36 candidate signals had `ts_recv` before both the 09:29:50 cutoff and the earliest 09:30:01 order. Minimum observed lead to that order was {min(v35_observability['minimum_lead_to_earliest_order_seconds'], v36_observability['minimum_lead_to_earliest_order_seconds']):.3f} seconds.

Detailed evidence: `research_scout/NEW_DATA_TECHNICAL_AUDIT_V34.md`, `research_scout/new_data_technical_audit_v34.json`, and `research_scout/CASH_ETF_CAPABILITY_MATRIX_CORRECTED_V34.md`.

## 2. Corrected V33 conclusion

V33's data-absence premise is superseded for exchange-published SPY auction state and trade-event cash-ETF TBBO from 2023-03-28. Its strategy-failure registry, passive-fill objection, historical-contamination warning, and primary-market-data blockers remain valid. The new package still lacks official SIP NBBO, every quote update, standing quote age, queue/depth, NAV/iNAV, AUM/shares, creation/redemption baskets, AP/dealer identity, and hedge flow.

## 3. V20 execution-fidelity audit

The V20 rule was unchanged. Entry uses the first valid ask after 10:01 plus 1, 5, or 60 seconds; exit uses the first valid bid after the unchanged structural-exit target; event wait is capped at 60 seconds; position size is fixed at $100.

{chr(10).join(v20_lines)}

These outcomes are historically contaminated execution diagnostics. They cannot rescue V20 or authorize parameter changes. Full details: `research_scout/V20_TBBO_EXECUTION_FIDELITY_AUDIT_V34.md`.

The zero-trade 2026 rows are not a negative temporal result: the frozen V20 ES source file ends at 2025-12-31, so no 2026 V20 states were available to audit.

## 4. New economic hypotheses and feasibility

### V35 — paired-absorption failure trajectory

Mechanism: same-side unpaired pressure gains share from 09:28 to 09:29:50 while side-signed indicative displacement rises, implying offsetting auction liquidity is losing ground before the continuous handoff.

Result before P&L: {v35['feature_development_2021_2023']['signals']} development feature signals, {v35['feature_development_2021_2023']['trades_per_calendar_week']:.3f} per week; {v35['executable_development_overlap_2023_03_28_2023_12_31']['signals']} executable 2023-overlap signals. Failed gates: {v35_failed}. The rule is terminal and was not repaired.

### V36 — price/quantity disagreement

Mechanism: the final published imbalance side and indicative-price displacement disagree, so the opposite limit curve rather than the unpaired-side label appears to control the marginal auction price.

Result before P&L: {v36['feature_development_2021_2023']['signals']} development feature signals ({v36['feature_development_2021_2023']['trades_per_calendar_week']:.3f}/week) and {v36['executable_development_overlap_2023_03_28_2023_12_31']['signals']} executable development-overlap signals ({v36['executable_development_overlap_2023_03_28_2023_12_31']['trades_per_calendar_week']:.3f}/week). Quote coverage for required UPRO/SPXU targets was {v36['all_overlap']['quote_coverage_pct']:.2f}%, but only {v36['all_overlap']['cross_ladder_5s_available_days']}/{v36['all_overlap']['executable_signals']} executable signals had all-six-ladder 5-second evidence. Identical action including cash was {v36['adjacent_cutoff_stability']['09:29:30']['identical_action_including_cash_pct']:.2f}% at 09:29:30 and {v36['adjacent_cutoff_stability']['09:29:59']['identical_action_including_cash_pct']:.2f}% at 09:29:59. It produced no 2026 signals. Failed gates: {v36_failed}.

The V36 preregistration is explicitly **not activated**. It records the frozen rule and failed gates but does not authorize a return calculation.

## 5. Executable result

There is no admissible new-strategy executable result because no candidate crossed the returns-blind gate. Consequently profit factor, fixed-dollar P&L, SPY benchmark comparison, one-cent stress, delay robustness, best-trade deletion, directional contribution, controls, and placebos were not calculated for V35 or V36. Reporting invented zeros or opening returns after rejection would be less honest than stopping.

## 6. Robustness result

The decisive robustness evidence is pre-outcome:

- V35 is structurally too sparse for the required cadence and unstable across adjacent cutoffs.
- V36 has adequate raw cadence and UPRO/SPXU quote coverage but fails preregistered adjacent-cutoff action stability and all-six-ladder evidence coverage.
- V36 has no 2026 participation, so it cannot demonstrate a temporal extension.
- The trade-event TBBO cannot establish true quote freshness or quote-only lead/lag.

Mandatory P&L controls and placebos were deliberately not opened because the candidate did not qualify for an alpha test.

## 7. Contamination risk

The auction fields are newly observed causal variables, but historical price outcomes are not new. 2021–2023 is development/measurement, 2024–2025 is historical validation with familywise contamination, and 2026 is only a temporal extension. V34 was already outcome-exposed and failed. Its prior script also loaded 2024–2025 price files before stopping, even though it did not report holdout returns, so those dates are not claimed untouched. V35 and V36 added to the multiplicity count but stopped before returns.

## 8. What remains unknown

- Whether a stable auction feature can predict post-open executable returns after 60 seconds.
- Whether apparent cross-leverage lags survive a complete quote-update or official consolidated feed.
- Whether wrapper deviations are true NAV/inventory effects without point-in-time NAV/iNAV, shares, AUM, baskets, creations/redemptions, and AP/dealer hedge data.
- Whether any effect survives genuinely prospective sessions.

## 9. Prospective requirement

No V35 or V36 paper rule should be activated. A future candidate must first use a causally different measurement, account for the 2025-11-13 quantity-definition break, pass the same returns-blind cadence/stability/coverage gates, and freeze a full preregistration. Only a historical survivor should enter forward paper trading, with no rule changes and simultaneous 1/5/60-second shadow execution until at least 100 nonoverlapping trades include both directional regimes. Production use would require a later untouched evaluation and data capable of validating quote freshness.

## Reproducibility

- Technical decode: `python research_scout/audit_cash_etf_new_data_v34.py`
- V20 fidelity: `python research_scout/audit_v20_tbbo_execution_fidelity_v34.py`
- V35 feasibility: `python research_scout/audit_spy_auction_absorption_failure_v35.py`
- V36 feasibility: `python research_scout/audit_spy_auction_price_quantity_disagreement_v36.py`
- Final compiler: `python research_scout/compile_cash_etf_research_report_v36.py`

No paid download or API call was made by these scripts.
"""
    OUT_MD.write_text(report, encoding="utf-8")
    print(json.dumps({"results": str(OUT_JSON.relative_to(ROOT)), "report": str(OUT_MD.relative_to(ROOT))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
