"""Save audited negative local Databento experiment and the next research checkpoint."""

import json
from datetime import UTC, datetime
from decimal import Decimal

from research_scout.prepare_databento_fast_20261002 import OUT, ROOT, sha, write


def main():
    screen = json.loads((OUT / "screen_results.json").read_text())
    result = json.loads((OUT / "replay_results.json").read_text())
    audit = json.loads((OUT / "independent_verification.json").read_text())
    assert screen["selected_count"] == 180 and screen["groups_checked"] == 563
    assert audit["verified"] and audit["screen_sha256"] == sha(OUT / "screen_results.json")
    assert audit["results_sha256"] == sha(OUT / "replay_results.json")
    assert all(Decimal(r["known_component_usd"]) < 0 for r in result["scenario_results"])
    rows = [r for p in sorted((OUT / "replay_sessions").glob("*.json")) for r in json.loads(p.read_text())["outcomes"]]
    baseline = [r for r in rows if r["case"] == "base_1ms" and r["net_usd"] is not None]
    assert baseline and not any(Decimal(r["net_usd"]) > 0 for r in baseline)
    complete = [r for r in result["scenario_results"] if r["observed_event_cohort_usd"] is not None]
    report = OUT / "REPORT.txt"
    text = ["LOCAL DATABENTO MILLISECOND SWEEP RESPONSE: NO PROFITABLE BASELINE TRADE",
            "Updated " + datetime.now(UTC).isoformat(), "",
            "Result: no reliable edge. All32rule/holding-period/scenario aggregates have negative known components. Four observed-event cohorts are complete and negative; all32full-calendar totals remain unknown. None of the344priced baseline event/horizon cases is profitable after the frozen conservative costs. These cases reuse180selected events; they are not344independent trades or2880independent observations.",
            "No network, API or paid call was made. Only existing local Databento DBN files were read. No new data purchase, account operation or trading order occurred.", "",
            "DATA:192previously exposed2023opening sessions from EQUS.MINI mbp-1,46,428,207records. Six ETFs:SPY,SSO,UPRO,SH,SDS,SPXU. The broader local cache has806daily MBP-1 files; later-year returns were not opened for this experiment. The parent had563source-verified large completed multi-price trade sweeps. All563were considered,including events previously rejected by the slower signal rule.",
            "SIGNAL:Decision at the first whole millisecond strictly after complete sweep receive+1ms,information cutoff decision-1ms. The latest complete book must be strictly earlier,valid,no older than5ms by capture and native clocks,with both sides displaced in the sweep direction and spread<=5bp. Fixed quantity<=10%of both signal touch sizes and<=10000USD at the2%cent-rounded buy collar. Causal ask-to-bid roundtrip cost<=12bp. Same conservative commission,adverse allowance and levy assumptions as earlier work.",
            "SELECTED:221raw admissions;180after causal ranking and6s global/60s symbol cooldown.93follow-buy-sweep longs and87fade-sell-sweep longs. One- and five-second holds yield4economic configurations. Eight cases each:1/5/25/250ms delays,doubled fees,doubled adverse allowance,and fixed-1/+1ms clock shifts. Processing assumption50us. These are feasibility assumptions,not verified infrastructure latency.",
            "EXECUTION MODEL:At the fixed future receive-clock reference,use the last valid completed quote,requiring a later quote to bracket arrival. Equal timestamps,future native events,staleness or missing references are unknown. IOC buy at ask if within the causal collar;fixed requested quantity is never resized from future data,while assumed fill is capped by future displayed ask size. Exit only priced when displayed bid size covers the assumed filled inventory;otherwise residual inventory/PnL stays unknown. No best-future-price search.", "",
            "Rule | hold milliseconds | case | priced/selected | unknown events | known USD | complete observed-event cohort USD"]
    for r in result["scenario_results"]:
        text.append(f"{r['rule']} | {r['hold_ms']} | {r['case']} | {r['priced_events']}/{r['event_cases']} | {r['unknown_events']} | {r['known_component_usd']} | {r['observed_event_cohort_usd']}")
    text += ["", "BASELINE DECOMPOSITION:rule | hold milliseconds | gross USD | commission+levy USD | adverse USD | net USD"]
    for rule in ("follow_buy_sweep", "fade_sell_sweep"):
        for hold in (1000, 5000):
            cohort = [r for r in baseline if r["rule"] == rule and r["hold_ms"] == hold]
            values = {k: sum((Decimal(r["cash"][k]) for r in cohort), Decimal(0))
                      for k in ("gross", "commissions", "sell_levies", "adverse", "net")}
            text.append(f"{rule} | {hold} | {values['gross']} | {values['commissions'] + values['sell_levies']} | {values['adverse']} | {values['net']}")
    text += ["", "Gross aggregate cash is already negative for all four baseline cohorts before commissions and adverse allowances. This is not a candidate rescued merely by a lower fee assumption.",
             "UNKNOWN HANDLING:2784event-case calculations priced,30unknown from insufficient exit depth,32unknown from exit clock/book conditions,34unknown from entry clock/book conditions. SPY2023-03-28 andUPRO2023-07-31 have BAD_TS_RECV source records;their admission remains unknown and prevents a complete calendar claim in every scenario. Known components do not bound the missing inventory outcomes.",
             "AUDIT:Independent DBN field/group,signal,cooldown/ranking,receive-clock reference,quantity,cash and32aggregate calculations verified:46,428,207source records,all563reported qualified groups,180selected events and2880event cases. Both paths use the Databento SDK binary decoder;this is not a separate binary-format audit. Earlier rejected-group enumeration remains unaudited and would be required for promotion. Eight focused implementation tests plus two new clock-regression tests passed;Ruff passed.",
             "AUDIT REPAIR:The first audit disagreed on one SPY signal because NumPy searching a uint64 array with a Python-int key could promote to floating point. It incorrectly excluded a quote36ns before cutoff. Explicit uint64 audit keys repaired it;the production int64 path was correct. All192sessions were rerun and passed. The frozen strategy,selected quantity and PnL records were not changed. SeeAUDIT_CLOCK_ERRATUM.txt.",
             "LIMITS:EQUS.MINI is an anonymized component-venue BBO feed,not consolidated NBBO or private fills. Venue routing,price protection,acceptance,hidden liquidity and actual client latency remain unproven. Negative conditional results warrant no promotion;they are not a universal impossibility proof. No live competition performance or funded portfolio has been established.",
             "SEARCH LEDGER:143economic configurations,195implementation versions,431focused tests. Goal active;no reliable edge. This experiment adds4economic configurations and4implementation versions. Ten tests were added for this Databento branch. Earlier IEX fast-displacement work added10tests and zeroeconomic variants.", "",
             "Specification SHA256: " + sha(OUT / "specification.json"),
             "Screen SHA256: " + sha(OUT / "screen_results.json"),
             "Replay SHA256: " + sha(OUT / "replay_results.json"),
             "Independent audit SHA256: " + sha(OUT / "independent_verification.json")]
    report.write_text("\n".join(text) + "\n")
    next_note = OUT / "NEXT_RESEARCH.txt"
    next_note.write_text(
        "User's latest instruction:use accessible Databento data without paid calls. Keep original goal active:strict HFT,stocks/ETFs/crypto,raw outperformance and real reliability,conservative fees. No validated edge. No orders,paid APIs,account changes,external messages,subagents or country-block bypass.\n\n"
        "Completed immediate own-ETF sweep response is negative:180events,4economic configurations,32cases,all known aggregates negative,and no positive baseline priced event. Do not optimize its holding times or latency to manufacture a win. All output andsource/cash checks are saved here. Eight implementation tests plus2clock-regression tests passed. Totals143/195/431. No process remains active at this checkpoint.\n\n"
        "Next distinct hypothesis to formalize before any return calculation:short cross-ETF price response after SPY price discovery using the same local1922023MBP-1 development sessions. Earlier cross-ETF regressions and static index-arbitrage budgets already failed at slower horizons;do not repackage them as new evidence. An event-driven millisecond lead/follower dislocation must be explicit,causal and economically large enough after spread,depth and costs. Consider SPY as leader and existing leveraged/inverse funds as long-only followers,with price-gap sign determined by each fund's stated multiplier. Determine exact common reference clocks,quote-age limits,leader move/flow predicate,lag budget,fixed sizing,ranking/cooldowns and1s/5s exits before scanning. A market-neutral or short position is not authorized by this proposed long-only research rule.\n\n"
        "Use cachedDBN files only. Preserve integer timestamps,especially np.searchsorted signed/unsigned scalar types:an auditor's mixed uint64/Python-int comparison previously lost36ns. Preserve F_LAST,invalid-book states,BAD_TS_RECV unknown dates andnative-event/receive-clock separation. Do not assume the anonymous aggregated feed is a unified exchange matching engine.\n\n"
        "If any candidate survives,independently reconstruct all rejected and accepted source groups,not just selected events;check source clocks,cash,concentration,multiple-search effects,NBBO/routeability and actual execution feasibility. Require a newly frozen temporal validation sample;these192days are development data already used repeatedly. A positive incomplete known component is not an edge.\n\n"
        "IEX fallback code research_scout/iex_fast_early_20261002.py was prepared but never frozen or executed;deferred after the user's Databento instruction. Its late-window parent was fully audited with zero signals. Do not accidentally count an early IEX study as completed.\n")
    erratum = OUT / "AUDIT_CLOCK_ERRATUM.txt"
    with erratum.open("a") as handle:
        handle.write("\nFull rerun completed successfully:192sessions,46,428,207records,563groups,180selected events,2880event cases and32aggregates reconciled. Audit SHA256:" + sha(OUT / "independent_verification.json") + "\n")
    checkpoint = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    state = json.loads(checkpoint.read_text())
    assert (state["current_configurations"], state["implementation_versions"], state["focused_tests_total"]) == (143, 195, 429)
    state.update(updated_at_utc=datetime.now(UTC).isoformat(), status="active", focused_tests_total=431,
                 latest_report=str(report), next_research_note=str(next_note), active_research_jobs=[],
                 databento_fast_report=str(report), databento_fast_independently_verified=True,
                 databento_fast_source_rows=46428207, databento_fast_selected_events=180,
                 databento_fast_event_cases=2880, databento_fast_economic_configurations_executed=4,
                 databento_fast_complete_observed_cases=len(complete), databento_fast_complete_calendar_cases=0,
                 databento_fast_positive_known_aggregates=0, databento_fast_positive_baseline_cases=0,
                 databento_fast_actual_execution_verified=False, databento_fast_network_calls=0,
                 databento_fast_candidates_for_promotion=[], previous_goal_turn_classification="progress",
                 remaining_evidence_work="Local Databento immediate sweep experiment fully audited;all32known aggregates negative,4complete observed cohorts negative,calendar unknown. No reliable edge. Next:formally freeze distinct causal cross-ETF millisecond lead/follower signal using local data only;see NEXT_RESEARCH.txt.")
    write(checkpoint, state)
    print(json.dumps({"report": str(report), "counts": [143, 195, 431], "network_calls": 0,
                      "positive_known_aggregates": 0, "reliable_edge_found": False}))


if __name__ == "__main__":
    main()
