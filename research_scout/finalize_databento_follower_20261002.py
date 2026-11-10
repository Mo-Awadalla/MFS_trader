"""Checkpoint the audited empty 2023 follower screen."""

import json
from datetime import UTC, datetime
from decimal import Decimal

from research_scout.prepare_databento_fast_20261002 import ROOT, sha, write
from research_scout.prepare_databento_follower_20261002 import OUT


def main():
    r = json.loads((OUT / "screen_results.json").read_text())
    audit = json.loads((OUT / "independent_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == sha(OUT / "screen_results.json")
    assert r["selected_count"] == 0 and Decimal(r["best_projected_net_bp"]) < 0
    report = OUT / "REPORT.txt"
    report.write_text(
        "LOCAL DATABENTO SPY-FOLLOWER LAG:2023SUPPLY SCREEN EMPTY\n"
        "Updated " + datetime.now(UTC).isoformat() + "\n\n"
        "No event qualified and no economic replay was run. This is a causal hypothetical convergence budget,not actual profit. No reliable edge.\n\n"
        "Scope:192cached2023opening sessions,46,428,207DBN records,sixETFs.558previously reported and independently verified SPY multi-price sweeps were checked;252had a valid current/reference leader signal.1260follower checks yielded202computable budgets. All202were negative after projected exit spread,conservative commission/levy and1bp adverse allowance perleg. Best projected net was-4.857484276729559748427672956bp;minimum required was+2bp. No future return was evaluated.\n\n"
        "Timing:First whole millisecond strictly after SPY burst capture+1ms;information cutoff decision-1ms;09:30:05..09:39:30ET. Common anchor1s before cutoff. Current SPY quote<=5ms old;all other snapshots<=250ms old by receive/event clocks. Latest completeF_LAST quote only,no fallback from invalid latest state;positive uncrossed cent prices andspread<=5bp. Both SPY sides must move in initiating direction since the anchor.\n\n"
        "Followers:SSO+2,UPRO+3,SH-1,SDS-2,SPXU-3. Only buy followers whose multiplier matches the directional SPY move. Projected mid=T0*(1+beta*(L1/L0-1));subtract current follower half-spread and round down to cents. Published fund multipliers describe daily objectives;their use over1s is only a research model,not guaranteed convergence or arbitrage.\n\n"
        "Size fixed at<=10%of both current touches and<=10000USD at a102%-of-ask cent-rounded buy collar. Current roundtrip cost<=12bp andprojected net>=2bp. Rank projected dollars,thenbp;6s global and60s symbol cooldown. The planned1s/5s execution cases were never run because admission was empty.\n\n"
        "First-failure counts:\n" + "\n".join(f"{k}:{v}" for k, v in r["rejections"].items()) + "\n\n"
        "Independent audit verified all192source hashes and46,428,207source records,558reported group identities,252valid leader signals,1260follower checks,202budgets andzero selected events. Whole-cent projected prices were separately recomputed from an exact integer rational. Eight focused tests andRuff passed. Earlier parent rejected-group enumeration was not independently repeated;source decoding uses the shared Databento SDK.\n\n"
        "SPY2023-03-28 andUPRO2023-07-31 retain bad-source-clock unknown status. EQUS.MINI does not prove venue routeability,NBBO protection,private fills or actual client latency. No full-calendar profitability claim,no live order,no paid API or network data call.\n\n"
        "Next:extend exactly these thresholds to all252locally cached2024sessions,with the same group predicate. Freeze the2024source manifest and code before scanning. This is regime expansion during discovery,not validation of an established edge. No threshold adjustment and no paid call.\n\n"
        "Search counts:143economic configurations,195implementation versions,439focused tests. This screen addszeroeconomic variants. Goal active.\n"
        "Results SHA256:" + sha(OUT / "screen_results.json") + "\n"
        "Audit SHA256:" + sha(OUT / "independent_verification.json") + "\n")
    checkpoint = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    s = json.loads(checkpoint.read_text())
    assert (s["current_configurations"], s["implementation_versions"], s["focused_tests_total"]) == (143, 195, 439)
    s.update(updated_at_utc=datetime.now(UTC).isoformat(), latest_report=str(report),
             active_research_jobs=[], databento_follower_report=str(report),
             databento_follower_supply_verified=True, databento_follower_candidates=0,
             databento_follower_economic_configurations_executed=0,
             databento_follower_best_projected_net_bp=r["best_projected_net_bp"],
             previous_goal_turn_classification="progress",
             remaining_evidence_work="2023SPY-follower signal and202negative budgets independently verified,no candidates. Next freeze identical admission over252cached2024sessions as discovery expansion. No reliable edge or paid calls.")
    write(checkpoint, s)
    print(json.dumps({"report": str(report), "counts": [143, 195, 439], "selected": 0}))


if __name__ == "__main__":
    main()
