"""Compile V37-V41 continuation evidence into final machine results and report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RS = ROOT / "research_scout"
OUTPUT_JSON = RS / "cash_etf_auction_research_results_v41.json"
OUTPUT_REPORT = RS / "SPY_CASH_ETF_AUCTION_RESEARCH_REPORT_V41.md"

FILES = {
    "V37": "spy_auction_indicative_leadership_returns_blind_audit_v37.json",
    "V38": "spy_core_open_uncross_overshoot_rejection_returns_blind_audit_v38.json",
    "V39": "spy_late_market_order_urgency_returns_blind_audit_v39.json",
    "V40": "leveraged_etf_opening_auction_demand_consensus_returns_blind_audit_v40.json",
    "V41": "spy_closing_auction_market_urgency_returns_blind_audit_v41.json",
}


def load(name: str) -> dict[str, Any]:
    return json.loads((RS / name).read_text(encoding="utf-8"))


def failed(payload: dict[str, Any]) -> list[str]:
    return [name for name, passed in payload["gates"].items() if not passed]


def main() -> int:
    audits = {version: load(filename) for version, filename in FILES.items()}
    if any(payload.get("returns_read") is not False for payload in audits.values()):
        raise RuntimeError("A continuation artifact is not returns-blind")

    results = {
        "status": "v37_v41_all_failed_frozen_returns_blind_gates_no_new_pnl_opened",
        "new_candidate_returns_viewed": False,
        "new_candidate_pnl_calculated": False,
        "paid_api_calls_made": False,
        "prior_canonical_results": "research_scout/cash_etf_auction_research_results_v36.json",
        "registry": "research_scout/CASH_ETF_HYPOTHESIS_REGISTRY_V34.md",
        "candidates": {
            "V37": {
                "name": "SPY auction indicative leadership",
                "audit": FILES["V37"],
                "status": audits["V37"]["status"],
                "feature_development": audits["V37"]["feature_development_2021_2023"],
                "executable_development": audits["V37"]["executable_development_overlap_2023_03_28_2023_12_31"],
                "all_overlap": audits["V37"]["all_overlap"],
                "adjacent_stability": audits["V37"]["adjacent_cutoff_stability"],
                "failed_gates": failed(audits["V37"]),
                "decision": "terminal_no_pnl",
            },
            "V38": {
                "name": "SPY Core-Open uncross overshoot rejection",
                "audit": FILES["V38"],
                "status": audits["V38"]["status"],
                "development": audits["V38"]["development_2023_03_28_2023_12_31"],
                "all_overlap": audits["V38"]["all_overlap"],
                "adjacent_stability": audits["V38"]["adjacent_stability"],
                "failed_gates": failed(audits["V38"]),
                "decision": "terminal_no_pnl",
            },
            "V39": {
                "name": "SPY late Core-Open market-order urgency",
                "audit": FILES["V39"],
                "status": audits["V39"]["status"],
                "feature_development": audits["V39"]["feature_development_2021_2023"],
                "all_overlap": audits["V39"]["all_overlap"],
                "market_order_condition": audits["V39"]["market_order_condition"],
                "failed_gates": failed(audits["V39"]),
                "decision": "terminal_no_pnl",
            },
            "V40": {
                "name": "leveraged/inverse official opening-auction demand consensus",
                "audit": FILES["V40"],
                "status": audits["V40"]["status"],
                "feature_development": audits["V40"]["feature_development_2021_2023"],
                "executable_development": audits["V40"]["executable_development_overlap_2023_03_28_2023_12_31"],
                "all_overlap": audits["V40"]["all_overlap"],
                "rolling_window_stability": audits["V40"]["rolling_window_stability"],
                "returns_blind_controls": audits["V40"]["returns_blind_controls"],
                "failed_gates": failed(audits["V40"]),
                "decision": "terminal_no_pnl",
            },
            "V41": {
                "name": "SPY Closing-auction market-urgency pre-close hedge window",
                "audit": FILES["V41"],
                "status": audits["V41"]["status"],
                "feature_development": audits["V41"]["feature_development_2021_2023"],
                "executable_development": audits["V41"]["executable_development_overlap_2023_03_28_2023_12_31"],
                "all_overlap": audits["V41"]["all_overlap"],
                "market_order_condition": audits["V41"]["market_order_condition"],
                "adjacent_stability": audits["V41"]["adjacent_cutoff_stability"],
                "failed_gates": failed(audits["V41"]),
                "decision": "terminal_no_pnl",
            },
        },
        "program_limitations_demonstrated": [
            "V37 had strong cadence, balance, temporal participation, and cutoff stability but failed its frozen all-timing actuator coverage gate at 88.37% versus 90%.",
            "V40 had coherent daily official-auction demand consensus but failed primary coverage at 89.44% and relevant-side ladder evidence at 69.85%.",
            "V38 and V41 were too sparse for the required two trades per week; V39's selected opening market-order state was effectively absent before 2026.",
            "The trade-event-conditioned EQUS.MINI feed repeatedly withholds complete same-session actuator and cross-ladder observations even when the causal feature is frequent and stable.",
        ],
        "next_independent_evidence": {
            "data": "Complete quote-update or official consolidated BBO history for SPY/SSO/UPRO/SH/SDS/SPXU, or prospective collection of that feed.",
            "research": "A genuinely new mechanism must be frozen under a new number; V35-V41 conditions and gates cannot be repaired.",
            "forward": "Prospective observation may measure V37/V40 quote availability, but their historical rules are not authorized for P&L or paper activation.",
        },
    }
    OUTPUT_JSON.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    v37 = audits["V37"]
    v38 = audits["V38"]
    v39 = audits["V39"]
    v40 = audits["V40"]
    v41 = audits["V41"]
    report = f"""# Institutional Cash-ETF and Auction Research Report v41

## Decision

**Five additional mechanisms were frozen and tested returns-blind. None authorized P&L.** V37–V41 all failed at least one preregistered feasibility gate. Their outcomes were not repaired, inverted, or threshold-searched.

This continuation materially strengthens the limitation claim: the process produced two coherent, frequent, stable signals (V37 and V40), but the supplied trade-event-conditioned execution feed could not meet their frozen coverage/evidence requirements. Three other mechanisms were structurally sparse or unavailable.

## Candidate ledger

| Version | Mechanism | Returns-blind evidence | Terminal reason |
|---|---|---|---|
| V37 | Indicative-match leadership over reference revision | {v37['feature_development_2021_2023']['signals']} development features, {v37['feature_development_2021_2023']['trades_per_declared_calendar_week']:.3f}/week; {v37['executable_development_overlap_2023_03_28_2023_12_31']['signals']} executable development; adjacent cash-including stability {v37['adjacent_cutoff_stability']['09:29:30']['identical_action_including_cash_pct']:.2f}% / {v37['adjacent_cutoff_stability']['09:29:59']['identical_action_including_cash_pct']:.2f}% | Actuator coverage {v37['all_overlap']['actuator_quote_coverage_pct']:.2f}% < frozen 90% |
| V38 | Official uncross overshoot rejected by first continuous SPY midpoint | {v38['development_2023_03_28_2023_12_31']['signals']} development signals, {v38['development_2023_03_28_2023_12_31']['trades_per_declared_calendar_week']:.3f}/week | Sparse, imbalanced, unstable, and undercovered |
| V39 | Late Core-Open market-order urgency | {v39['feature_development_2021_2023']['signals']} development signals; {v39['market_order_condition']['selected_signal_days']} total selected days | Selected opening state effectively absent before 2026 |
| V40 | 2x/3x long-inverse official opening-quantity consensus | {v40['feature_development_2021_2023']['signals']} development features, {v40['feature_development_2021_2023']['trades_per_declared_calendar_week']:.3f}/week; {v40['executable_development_overlap_2023_03_28_2023_12_31']['signals']} executable development; 10/40-window stability {v40['rolling_window_stability']['10']['identical_action_including_cash_pct']:.2f}% / {v40['rolling_window_stability']['40']['identical_action_including_cash_pct']:.2f}% | Primary coverage {v40['all_overlap']['primary_quote_coverage_pct']:.2f}% < 90%; ladder evidence {v40['all_overlap']['relevant_side_ladder_coverage_pct']:.2f}% < 80% |
| V41 | Closing-auction hard-flow hedge window, flat before close | {v41['feature_development_2021_2023']['signals']} development features, {v41['feature_development_2021_2023']['trades_per_declared_calendar_week']:.3f}/week; adjacent stability {v41['adjacent_cutoff_stability']['15:29:30']['identical_action_including_cash_pct']:.2f}% / {v41['adjacent_cutoff_stability']['15:29:59']['identical_action_including_cash_pct']:.2f}% | Cadence {v41['executable_development_overlap_2023_03_28_2023_12_31']['trades_per_declared_calendar_week']:.3f}/week, side balance, coverage, and ladder evidence failed |

## Most interesting non-survivor: V37

V37 is the strongest measurement discovered in this continuation:

- frequent in every year, including 110 feature signals in 2026;
- balanced directions;
- 97.9–98.7% direction agreement on joint adjacent-cutoff signals;
- 85.0–88.3% identical action including cash across adjacent cutoffs;
- only 51.9% agreement with recent reference momentum;
- only 29.8% agreement with final indicative/reference displacement;
- only 54.5% agreement with final imbalance side.

It still failed. The frozen rule demanded complete 1/5/60-second entry and exit evidence on at least 90% of overlap signals; observed coverage was 88.37%. Opening P&L after that near miss would convert a disciplined gate into a suggestion. V37 is locked.

## Most creative independent measurement: V40

V40 used no SPY imbalance sign or indicative price. It self-normalized official opening-auction quantities for four leveraged/inverse ETFs and required 2x/3x pair agreement. It passed cadence, year, side, rolling-window stability, temporal-extension, and price-control gates. It failed because the event-conditioned feed delivered only 89.44% primary actuator coverage and 69.85% relevant-side ladder evidence. V40 is also locked.

## Closing-auction result

The new closing snapshot artifact contains {len(load('spy_closing_auction_market_urgency_returns_blind_audit_v41.json')['signals'])} selected V41 signals across the full feature history after exclusions. Market-order-share growth was stable across nearby cutoffs and all retained exits were before 16:00, but the mechanism produced only 0.550 development features/week and 0.276 executable development trades/week. The closing data therefore resolves the field-availability question but rejects this exact twice-weekly construction.

## Why no alpha results appear

No V37–V41 post-entry return, fixed-dollar P&L, compounded equity, profit factor, SPY benchmark, best-trade deletion, cost stress, or placebo was calculated. Those analyses were conditionally authorized only after every returns-blind gate passed.

The absence of a P&L table is a result of the scientific protocol, not missing implementation.

## Precise demonstrated limitation

The new package supports serious causal auction measurements. It does **not** support a qualifying frequent cash-ETF strategy under the frozen evidence standard because:

1. some economically specific states are too sparse (V38, V41);
2. some nominally available fields do not populate the relevant opening snapshot (V39);
3. the strongest frequent states encounter 88–89% actuator coverage and 52–70% cross-ladder coverage in a trade-event-conditioned feed (V37, V40);
4. true standing quote age and quote-only updates remain absent;
5. historical outcome contamination remains program-wide.

## Next independent move

Do not relax V37 or V40. The highest-value next evidence is a complete quote-update or official consolidated BBO feed, collected prospectively if necessary. That would answer whether their coverage failures are properties of the market or artifacts of EQUS.MINI's trade-conditioned sampling. It would not retroactively authorize their historical P&L.

A future strategy attempt must use a new causal measurement and a new version number. V35–V41 remain immutable failures at their frozen gates.

## Reproducibility

- V37: `python research_scout/audit_spy_auction_indicative_leadership_v37.py`
- V38: `python research_scout/audit_spy_core_open_uncross_overshoot_rejection_v38.py`
- V39: `python research_scout/audit_spy_late_market_order_urgency_v39.py`
- V40: `python research_scout/audit_leveraged_etf_opening_auction_demand_consensus_v40.py`
- Closing snapshots: `python research_scout/extract_spy_closing_auction_snapshots_v41.py`
- V41: `python research_scout/audit_spy_closing_auction_market_urgency_v41.py`
- Compiler: `python research_scout/compile_cash_etf_research_report_v41.py`

No paid API call was made.
"""
    OUTPUT_REPORT.write_text(report, encoding="utf-8")
    print(json.dumps({
        "results": str(OUTPUT_JSON.relative_to(ROOT)),
        "report": str(OUTPUT_REPORT.relative_to(ROOT)),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
