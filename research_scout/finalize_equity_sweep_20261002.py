"""Save the bounded negative sweep result without promoting proxy returns."""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    folder = root / "research_scout/equity_sweep_hft_20261002"
    result_path = folder / "optimistic_v2/results.json"
    result = json.loads(result_path.read_text())
    audit = json.loads((folder / "optimistic_v2/independent_accounting.json").read_text())
    assert audit["verified"]
    assert audit["results_sha256"] == hashlib.sha256(result_path.read_bytes()).hexdigest()
    assert result["selected_events"] == 172 and result["scenario_cases"] == 12
    assert all(Decimal(row["known_component_usd"]) < 0 for row in result["scenarios"])
    complete = [r for r in result["scenarios"] if r["observed_cohort_proxy_complete"]]
    assert len(complete) == 3
    assert all(Decimal(r["observed_cohort_optimistic_sum_usd"]) < 0 for r in complete)
    path = root / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    checkpoint = json.loads(path.read_text())
    assert (checkpoint["current_configurations"], checkpoint["implementation_versions"],
            checkpoint["focused_tests_total"]) == (134, 184, 366)
    report = folder / "REPORT.txt"
    lines = [
        "EQUITY MULTI-PRICE SWEEPS — NO POSITIVE PRICE-PROXY RESULT",
        "",
        "Goal ACTIVE. No reliable edge, actual portfolio return, execution or competition win established.",
        "192 local 2023 sessions, 46,428,207 native records and 359,650 trade-bearing event groups.",
        "563 groups met the frozen directional multi-price sweep predicates. After a fixed delayed",
        "signal, displaced valid book, costs eligibility, ranking and cooldowns: 172 selected events",
        "on 107 dates (84 buy-sweep continuation longs and 88 sell-sweep reversal longs).",
        "",
        "The separate economic screen gives each event an independent $10,000 budget, limits intended",
        "quantity by causal displayed size, then uses favorable future displayed quote extrema and",
        "unlimited execution depth. It is deliberately optimistic, not a funded portfolio or an",
        "executable-return estimate. Hold is about 15 seconds; the intended order collar is 10bp.",
        "Each leg costs max($1, $0.005/share), plus 1bp adverse movement and a conservative sell levy.",
        "Doubling fees/adverse costs and changing timing are separate diagnostic cases.",
        "",
        "Complete observed-cohort diagnostics (USD):",
    ]
    for row in complete:
        lines.append(f"  {row['rule']}, {row['scenario']}: {row['observed_cohort_optimistic_sum_usd']}")
    lines.extend([
        "All other cases have unknown references and negative known components. No unknown was zeroed.",
        "The full calendar remains unassessable because SPY 2023-03-28 and UPRO 2023-07-31 contain",
        "BAD_TS_RECV source errors. The negative observed sample does not prove universal absence of an edge.",
        "",
        "Independent checks reconstructed all 563 REPORTED qualifying groups, their fixed signal",
        "decisions and the final 172-event ledger from native records. Earlier group rejection",
        "enumeration was not independently repeated. A separate exact accounting audit verified",
        "1,032 event/case rows, 982 priced cash rows and all 12 aggregates; maximum cash difference zero.",
        "Forward favorable-quote extrema were NOT independently rebuilt from raw sources. This scope",
        "is sufficient to record a negative exploratory lead, not to promote a profitable strategy.",
        "No realistic replay or untouched selection-period outcome test was run for this family.",
        "",
        "The first price writer failed on a NumPy int64 quote index. Its artifacts are preserved.",
        "V2 repairs exact integer JSON encoding only; signals, quantities, timing and economics match.",
        "Eight sweep tests and two exact serialization tests passed. The frozen candidate auditor",
        "retains a Ruff B905 adjacent-pair zip style warning; all other audited lint checks passed.",
        "",
        "Cumulative: 136 executed economic configurations, 188 implementation versions, 376 focused tests.",
        "No active research processes remain at finalization. Two configurations and their failed/fixed",
        "implementations are counted; signal-only screens are not counted as economic experiments.",
        "Next: investigate IEX historical quote-size provenance and executable passive-fill evidence",
        "before deciding whether that distinct data source supports a new strict-HFT experiment.",
    ])
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    checkpoint.update(
        status="active", reliable_edge_found=False,
        current_configurations=136, implementation_versions=188, focused_tests_total=376,
        updated_at_utc=datetime.now(UTC).isoformat(), active_research_jobs=[], report=str(report),
        equity_sweep_report=str(report), equity_sweep_economic_configurations_executed=2,
        equity_sweep_economic_implementation_versions=4,
        equity_sweep_independent_accounting_verified=True,
        equity_sweep_forward_quote_extrema_independently_verified=False,
        equity_sweep_complete_observed_cohort_cases=3,
        equity_sweep_positive_complete_cases=0,
        equity_sweep_actual_execution_verified=False,
        equity_sweep_candidates=[],
        remaining_evidence_work=(
            "Sweep price probe completed: three complete observed-cohort cases negative; nine cases "
            "unknown with negative known components. Candidate signal and exact cash audits passed "
            "within documented scope. Full rejection enumeration and forward quote extrema are not "
            "independently audited; no positive strategy claim. Next investigate IEX historical "
            "quote-size units and passive-fill evidence before freezing a distinct experiment."
        ),
    )
    path.write_text(json.dumps(checkpoint, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report), "economic_configurations": 136,
                      "implementation_versions": 188, "focused_tests_total": 376}))


if __name__ == "__main__":
    main()
