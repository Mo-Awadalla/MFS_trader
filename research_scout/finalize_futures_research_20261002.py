"""Publish the independently reconciled futures-predictor findings."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCREEN = ROOT / "research_scout/futures_etf_hft_20261002"
RESPONSE = ROOT / "research_scout/futures_response_hft_20261002"


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    screen_audit = read(SCREEN / "independent_verification.json")
    audit = read(RESPONSE / "replay_v1/independent_verification.json")
    result_path = RESPONSE / "replay_v1/results.json"
    result = read(result_path)
    assert screen_audit["verified"] and audit["verified"]
    assert sha(result_path) == audit["results_sha256"]
    assert sha(SCREEN / "spy_budget_results.json") == screen_audit["budget_results_sha256"]
    (SCREEN / "REPORT.txt").write_text(
        "FUTURES-TO-SPY HFT CATCH-UP SCREEN — NO ELIGIBLE OPPORTUNITY\n\n"
        "No reliable edge established. This is a contemporaneous cost-budget screen, not a future-return or P&L test. Futures are predictors only; SPY is the authorized traded asset.\n\n"
        "Source coverage: all 250 XNYS sessions in 2023; 248 complete cached Databento ES trade files covering 15:00–15:30 ET. The two scheduled early closes are excluded by calendar. All file hashes reconcile to the source ledger. The volume-front continuous symbol maps to a single actual contract each day. No futures position is proposed.\n\n"
        "Frozen signal: 250ms decisions, strict capture-time predecessor before decision minus 100ms and one second earlier; endpoint age at most 250ms; absolute one-second price change at least 4bp, at least 100 contracts, and aligned aggressor flow at least 75%. Invalid records, timestamp-lag violations and unsupported flags invalidate the window. Earliest eligible signal wins a 30-second cooldown. This selects 26 impulses on 17 dates from 5,255,266 raw trades and 1,724,096 decision grids.\n\n"
        "Execution-data screen: 26 complete SPY SIP windows, 436,267 raw quotes. Strict predecessors and conflicting tied timestamps are handled explicitly. Pre-2025 displayed sizes use 100-share round lots. Whole-share sizing is capped by $10,000 with a 1% reserve and 10% displayed touch size; minimum order $100. Costs include both sides of the spread, $0.0075/share with $1 minimum per order, sell levies, 1bp adverse allowance per execution and one calendar day of 5% annualized borrow for shorts.\n\n"
        "Results: 23 priced contemporaneous budgets, three invalid/tied quote states, zero orders above the frozen cost hurdle plus 3bp buffer. Maximum signed ES/SPY residual is 3.64972bp; even the best remaining budget is -1.71940bp before the extra buffer. No future price was used to rank these observations. No economic configuration was run in this screen.\n\n"
        "Independent validation: a separate moving-window implementation with exact integer price/flow thresholds reproduced every decision flag, all 26 impulses and all source hashes. An independent raw SIP parser and Decimal cash calculation verified all 23 budgets and three ambiguous states; maximum numeric difference 1.09e-12. Six impulse tests and four quote-budget tests passed.\n\n"
        "Limits: SIP quotes provide conditional execution evidence, not private fills or historical short permissions. An instantaneous residual is not a guarantee of later convergence. This negative result applies to this frozen screen, not all possible futures predictors. Family-specific 2024/2025 validation remains unopened; those years have been used elsewhere in the broader research.\n\n"
        "Evidence: specification.json, source_manifest.json, decisions/, es_impulses.parquet, quote_manifest.json, spy_budgets.parquet, spy_budget_results.json and independent_verification.json. The separately preregistered 15-second response extension is reported in ../futures_response_hft_20261002/REPORT.txt.\n",
        encoding="utf-8",
    )
    lines = [
        "SPY RESPONSE TO FUTURES IMPULSES — NO RELIABLE EDGE",
        "",
        "Both frozen HFT rules fail to qualify. All four complete scenario aggregates lose money. The eight incomplete aggregates remain UNKNOWN; their priced components are not portfolio returns.",
        "",
        "This is a dependent extension of the failed instantaneous catch-up screen. Before reading subsequent quote returns, two rules were frozen: follow the ES impulse or fade it. All 26 original impulses across 17 dates in 2023 remain in each rule. The parent residual/cost gate is not reused to select outcomes. Only SPY is traded.",
        "",
        "Execution: fixed causal whole-share quantity, $10,000/day per independent rule account, 10% predecision displayed depth, inward penny-rounded 10bp FOK entry collar. Base feed delay is 100ms, processing 50ms and outbound/acknowledgement 100ms each. Exit decision occurs 15 seconds after entry acknowledgement. The 250ms and one-second latency stresses retain the original anchor and quantity. A submitted unknown halts every later attempt for that date; no phantom flat reset or zero P&L is assigned.",
        "",
        "Every possible SIP state in the arrival-clock interval, including the complete tied predecessor group, is examined. A fill requires every state to satisfy the fixed collar and full quantity. Uniformly outside-collar states imply no fill; mixed states or inadequate depth remain unknown. Quotes alone do not establish actual fills. Costs match the parent conservative commission, levy, adverse allowance and short-borrow assumptions.",
        "",
        "SCENARIOS (US dollars; independent scenarios must not be added together)",
    ]
    for row in result["scenarios"]:
        value = (
            f"complete net {row['net_lower']} to {row['net_upper']}"
            if row["complete"]
            else f"full net UNKNOWN; priced component {row['known_component_lower']} to {row['known_component_upper']}"
        )
        lines.append(f"{row['rule']} / {row['scenario']}: {value}; {row['priced_events']} priced; {row['outcomes']}.")
    lines.extend([
        "",
        "Complete cases: follow at 250ms loses about $130.25 and at one second $123.46; fade at 250ms loses $94.42 and at one second $97.85, using the conservative interval endpoints. Removing the best three dates leaves every complete case negative. Each base case has one ambiguous submitted entry, 22 priced events and three predecision rejections. Neither the base partial values nor any stress result supports promotion.",
        "",
        "Validation: eight focused execution tests and Ruff passed. The independent auditor imports no production replayer. It reconciled 436,267 raw SIP records, 46 entry intents, six predecision rejections, 504 quote envelopes, 242 cash rectangles enumerating all observed price combinations, 312 ledger rows, 26 submitted unknowns, eight later inventory halts and 12 scenario aggregates. Maximum numeric difference was zero. Original frozen results are unchanged; the completed independent audit is a separate artifact.",
        "",
        "No actual execution, historical short availability or account permissions have been established. Unknown exits cannot be claimed to meet the planned holding time. The family-specific 2024/2025 selection sample remains unopened; it is not globally pristine given older research. This failure does not establish that every HFT strategy loses, and it does not fulfill the competition goal.",
        "",
        "Evidence: specification.json; replay_v1/implementation.json; replay_v1/intents.json; all 12 scenario ledgers; replay_v1/results.json; replay_v1/independent_verification.json.",
    ])
    (RESPONSE / "REPORT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    checkpoint_path = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    checkpoint = read(checkpoint_path)
    assert checkpoint["current_configurations"] in (126, 128)
    complete = [r for r in result["scenarios"] if r["complete"]]
    checkpoint.update(
        status="active", paused_at_user_request=False, reliable_edge_found=False,
        current_configurations=128, implementation_versions=178, focused_tests_total=250,
        report=str(RESPONSE / "REPORT.txt"), updated_at_utc=datetime.now(UTC).isoformat(),
        active_research_jobs=[],
        last_research_process={"operation": "Independent futures-to-SPY screen and response execution/cash audits", "exit_code": 0},
        futures_etf_report=str(SCREEN / "REPORT.txt"), futures_etf_screen_verified=True,
        futures_etf_screen_eligible_orders=0, futures_etf_impulses=26,
        futures_etf_economic_implementations=0,
        futures_response_report=str(RESPONSE / "REPORT.txt"),
        futures_response_economic_configurations=2,
        futures_response_scenario_cases=12,
        futures_response_complete_scenarios=len(complete),
        futures_response_profitable_complete_scenarios=0,
        futures_response_independent_execution_and_cash_verified=True,
        futures_response_actual_execution_verified=False,
        futures_response_candidates=[], futures_response_selection_2024_2025_opened=False,
        futures_response_complete_results=[
            {k: r[k] for k in ("rule", "scenario", "net_lower", "net_upper", "drop_best_three_dates_lower")}
            for r in complete
        ],
        remaining_evidence_work=(
            "Futures-to-SPY contemporaneous residuals do not cover costs, and both 15-second "
            "response rules failed. Independent source, signal, execution-envelope and cash audits passed. "
            "No reliable edge or candidate; no process is running. Continue with a separately frozen "
            "strict-HFT hypothesis whose data can verify the proposed mechanism. Do not tune these "
            "failed events, lower costs, or reopen validation years to rescue the branch."
        ),
    )
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"reports_written": 2, "configurations": 128, "focused_tests": 250,
                      "reliable_edge_found": False, "complete_response_scenarios": len(complete)}))


if __name__ == "__main__":
    main()
