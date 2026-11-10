"""Freeze causal SPY-to-follower lag budgets on local Databento development data."""

import json
from datetime import UTC, datetime

from research.equity_follower_lag import MULTIPLIERS
from research_scout.prepare_databento_fast_20261002 import OUT as FAST
from research_scout.prepare_databento_fast_20261002 import PARENT, ROOT, sha, write

OUT = ROOT / "research_scout/databento_follower_hft_20261002"


def main():
    previous = json.loads((FAST / "independent_verification.json").read_text())
    assert previous["verified"] and previous["results_sha256"] == sha(FAST / "replay_results.json")
    inherited = json.loads((FAST / "specification.json").read_text())
    spec = {k: inherited[k] for k in ("sources", "symbols", "parent_sessions", "inherited_unknown_symbol_dates",
                                    "hold_ms", "cases", "costs", "bad_data", "feed_limits",
                                    "timing", "reference", "conditional_fills")}
    files = ("research/equity_follower_lag.py", "research/equity_sweep_fast.py", "research/equity_resilience.py",
             "research/exact_json.py", "research_scout/run_databento_fast_20261002.py",
             "research_scout/run_databento_follower_20261002.py")
    spec.update(
        created_at_utc=datetime.now(UTC).isoformat(),
        family="SPY source sweep followed by a causal projected price gap in an index follower",
        relationship="Distinct event-driven millisecond lead/follower budget after own-ETF fast sweep results were negative. Related slower regressions and static same-index convergence have already failed. Same repeatedly exposed1922023sessions;this is development,not independent validation.",
        leader="All parent prestate-qualified SPY multi-price groups,not just profitable or selected parent events. Prior group source verification covers identity,clocks,single initiating side,>=100000USD notional,monotonic multi-price span>=.01 andquantity>=immediate prestate touch. Earlier group-rejection enumeration remains required before promotion.",
        decision="First whole millisecond strictly after SPY burst capture+1ms;cutoff decision-1ms;09:30:05..09:39:30ET. Common reference cutoff exactly1s earlier. Latest F_LAST quote strictly before each cutoff,positive uncrossed cent prices,spread<=5bp,no fallback from invalid latest state. Current SPY capture/event ages<=5ms;all other snapshots<=250ms;native event<=its own cutoff. Current SPY book must include completed burst;both SPY bid and ask must move in burst direction since1s reference.",
        multipliers=MULTIPLIERS,
        targets="After a buy SPY burst,only longSSO/UPRO are eligible. After a sell SPY burst,only longSH/SDS/SPXU are eligible. No short sale or borrowed share. Both target snapshots obey the same completed-book/clock gates.",
        projection="Let L0,L1 be common-anchor/current SPY mids;T0 target anchor mid;beta the named fund's daily multiplier. Projected target mid=T0*(1+beta*(L1/L0-1)). Subtract the CURRENT target half-spread and round DOWN to cents to form hypothetical liquidation price. This daily-beta local response is an unverified one-second model,not guaranteed convergence,NAV equivalence or actual arbitrage.",
        sizing="Buy limit102%of current target ask rounded UP to cents. Quantity=min(floor10000USD/limit,floor10%current target bid quantity,floor10%current target ask quantity). Fixed before future references; no future resizing.",
        admission="Current ask-to-current bid cost<=12bp. Hypothetical ask-to-projected-bid cash must net>=2bp of entry notional after unchanged conservative per-order commissions,levy and adverse allowance. Use exact Decimal arithmetic and integer prices. Do not use future follower prices to select candidates.",
        ranking="One shared long slot. Order all qualifying candidates by decision time,descending projected net USD,descending projected net bp,symbol,leader source index. Require6s global and60s symbol cooldown;selected event starts cooldown independent of later fills. Same selected cohort for1s and5s horizons.",
        aggregation="Twoeconomic hold configurations,8cases each only if admission exists. Keep inherited unknown symbol/date conditions as full-calendar unknown. Report known components and observed selected-cohort results separately. No zero for unresolved inventory,unknown entry or missing signal. Diagnostic sums are not an executed portfolio.",
        validation="Eight new focused causal/clock/model/selection tests passed. Independently verify every leader group,reference clock,model price,cost and ranking. A positive realized conditional result needs complete rejection enumeration,execution/NBBO corroboration,concentration/multiple-search controls and newly frozen temporal validation. Do not lower thresholds after seeing this screen.",
        network="Local immutable DBN reads only,no Databento API client,paid call,new download,account mutation or order.",
        sources_for_daily_objectives={s: "https://www.proshares.com/our-etfs/leveraged-and-inverse/" + s.lower() for s in MULTIPLIERS},
        objective_source_scope="Issuer pages checked2026-10-03UTC for fund identity and daily objectives only. Their definitions do not guarantee second-scale beta;historical product details remain necessary if a candidate survives.",
        parent_screen_sha256=sha(PARENT / "screen_results.json"),
        parent_candidate_audit_sha256=sha(PARENT / "candidate_verification.json"),
        preceding_fast_audit_sha256=sha(FAST / "independent_verification.json"),
        code_sha256={p: sha(ROOT / p) for p in files},
        economic_configurations_executed=0, actual_execution_verified=False, reliable_edge_established=False)
    OUT.mkdir(exist_ok=True)
    assert not (OUT / "specification.json").exists()
    write(OUT / "specification.json", spec)
    checkpoint = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    state = json.loads(checkpoint.read_text())
    assert state["focused_tests_total"] == 431
    state.update(focused_tests_total=439, updated_at_utc=datetime.now(UTC).isoformat(),
                 active_research_jobs=["Local Databento SPY-follower causal budget screen"],
                 databento_follower_specification=str(OUT / "specification.json"),
                 remaining_evidence_work="Frozen SPY-to-index-follower millisecond price-gap admission;8focused tests passed. Local2023DBN only. No future returns yet; no reliable edge.")
    write(checkpoint, state)
    print(json.dumps({"specification_sha256": sha(OUT / "specification.json"), "source_sessions": len(spec["sources"])}))


if __name__ == "__main__":
    main()
