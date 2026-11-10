"""Record the completed conditional IEX result without promoting it to execution proof."""

import json
from datetime import UTC, datetime
from decimal import Decimal

from research_scout.prepare_iex_spread_20261002 import OUT, ROOT, digest


def main():
    probe = OUT / "price_probe_v1"
    result = json.loads((probe / "results.json").read_text())
    audit = json.loads((probe / "independent_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == digest(probe / "results.json")
    complete = [r for r in result["scenario_results"] if r["full_conditional_net_usd"] is not None]
    assert len(complete) == 2 and all(Decimal(r["full_conditional_net_usd"]) < 0 for r in complete)
    lines = [
        "IEX NATIVE SPREAD / SHORT-HOLD CONDITIONAL PROBE -- NOT AN ESTABLISHED EDGE",
        "Updated " + datetime.now(UTC).isoformat(), "",
        "Causal supply: 24 fixed 2023 dates; 19,566,059 native TOPS messages;61 spread/activity candidates;22 daily selections in20 stocks/ETFs. Full independent signal/decoder/budget audit passed.",
        "One fixed long-only seconds-long policy: original bid limit, cancel after5s; original ask target after cancellation ACK; cancel target after15s; forced residual exit after ACK. Fixed causal size, partial fills, each nonempty order's commission, conservative fees/adverse allowance. No post-only assumption for2023.",
        "The source/price/print probe extended only to decision+35s. 22dates;23,460,044messages;35,609selected-symbol messages;220event-case rows;10aggregate cases. Independent raw decoder, conditional allocations, inventory and Decimal cash matched exactly.",
        "Eight focused probe tests passed. Seven separate DEEP admission tests passed; no DEEP price outcomes examined by this report.", "",
        "Model | scenario | known conditional USD | full conditional USD | unknown events | priced entries",
    ]
    for r in result["scenario_results"]:
        lines.append(f"{r['fill_model']} | {r['case']} | {r['known_component_usd']} | {r['full_conditional_net_usd']} | {r['unknown_events']} | {r['conditionally_priced_entries']}")
    lines += ["", "Baseline in both models:20 conditional no-entries,1 priced META trade losing$6.191803,1 ALB entry-state unknown. Only250ms has complete observed-cohort outcomes;both models lose$9.291400. The3s known component loses$205.265920. No positive priced trade in any case.",
              "LIMITS: These are conditional price/print calculations, not counterfactual fill or funded-portfolio proof. Touch prints do not establish queue position. Strict-through prints do not establish order acceptance or historical price sliding. Unknown outcomes are not zero. No-entry labels depend on the assumed print model. Forced exits use venue TOPS protected prices and ignore depth; better odd-lot prices can exist in DEEP. This is neither an executable backtest nor a formal universal upper bound on profit.",
              "The2021 IEX odd-lot filing explains that TOPS protected aggregation may omit better-priced displayed odd lots shown inDEEP. Source:https://www.sec.gov/rules/sro/iex/2021/34-90933.pdf . Native depth admission is the next source-quality check; it uses the same fixed dates, cutoff, thresholds and ranking. All development remains exploratory after many searches; no temporal-holdout validation or actual fills are claimed.",
              "No reliable edge established, no paid API, no orders. Current global search ledger:137 economic configurations,189 implementation versions,401 focused tests.",
              "Data provided for free by IEX. By accessing or using IEX Historical Data, you agree to the IEX Historical Data Terms of Use. https://www.iex.io/legal/hist-data-terms",
              "", "Specification SHA256: " + digest(probe / "specification.json"),
              "Results SHA256: " + digest(probe / "results.json"),
              "Audit SHA256: " + digest(probe / "independent_verification.json")]
    report = OUT / "REPORT.txt"
    report.write_text("\n".join(lines) + "\n")
    checkpoint = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    state = json.loads(checkpoint.read_text())
    assert (state["current_configurations"], state["implementation_versions"], state["focused_tests_total"]) == (137, 189, 394)
    state.update(
        focused_tests_total=401, updated_at_utc=datetime.now(UTC).isoformat(), status="active",
        active_research_jobs=[{"session_id": 41343, "job": "First-date native DEEP causal depth admission; fixed24-date cohort, no returns"}],
        remaining_evidence_work="TOPS22-event price/print probe completed and fully independently reconstructed;2complete cases negative,8cases unknown with negative known components. Native DEEP screen frozen and firstdate running to account for better-priced displayed odd lots. No reliable edge.",
        latest_report=str(report), iex_spread_report=str(report),
        iex_spread_probe_independently_verified=True, iex_spread_probe_source_messages=23460044,
        iex_spread_probe_event_case_rows=220, iex_spread_probe_complete_cases=2,
        iex_spread_probe_positive_complete_cases=0, iex_spread_actual_execution_verified=False,
        iex_spread_candidates=[], iex_deep_specification=str(ROOT / "research_scout/iex_deep_hft_20261002/specification.json"),
        iex_deep_economic_configurations_executed=0,
    )
    checkpoint.write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps({"report": str(report), "counts": [137, 189, 401], "reliable_edge_established": False}))


if __name__ == "__main__":
    main()
