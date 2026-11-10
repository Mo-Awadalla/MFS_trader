"""Persist the audited coverage extension and the exact remaining work."""

import argparse
import json
from datetime import UTC, datetime

from research_scout.prepare_market_lag_coverage_20261002 import OUT as COVERAGE
from research_scout.prepare_market_lag_native_20261002 import HYPOTHESIS
from research_scout.prepare_market_lag_native_20261002 import OUT as NATIVE1
from research_scout.prepare_market_lag_native_batch02_20261002 import OUT as NATIVE2
from research_scout.prepare_market_lag_targets_20261002 import OUT as TARGET1
from research_scout.prepare_market_lag_targets_20261002 import ROOT


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--active-session", type=int)
    parser.add_argument("--active-job")
    args = parser.parse_args()
    audits = [read(p / "independent_verification.json") for p in (HYPOTHESIS, COVERAGE, NATIVE1, TARGET1)]
    assert all(a["verified"] for a in audits)
    assert audits[-1]["selected_target_events_verified"] == 0
    acquisition = read(NATIVE2 / "source_manifest.json")
    assert acquisition["complete"] and len(acquisition["files"]) == 37
    native2_results = read(NATIVE2 / "screen_results.json") if (NATIVE2 / "screen_results.json").exists() else None
    native2_audit = read(NATIVE2 / "independent_verification.json") if (NATIVE2 / "independent_verification.json").exists() else None
    if native2_audit:
        progress = (f"The remaining 37 native minutes are screened and independently audited: "
                    f"{native2_audit['causally_admitted_leader_grids']} causally admitted leader grids. "
                    "Next freeze and fetch all-symbol targets only for their admitted minutes, then apply the unchanged gates.")
    elif native2_results:
        progress = (f"The remaining 37 native minutes are screened: {native2_results['coherent_leader_grids']} diagnostic coherent grids. "
                    "Independent native audit and exact acquisition-grid alignment remain necessary before any target acquisition.")
    else:
        progress = "The remaining 37 native BTC/ETH minute files are downloaded and complete; native screening and its independent audit remain outstanding."
    (HYPOTHESIS / "REPORT.txt").write_text(
        "COHERENT BTC/ETH MOVE AND LAGGING COINS — INITIAL SPARSE SCREEN COMPLETE\n\n"
        "The unchanged hypothesis requires both sides of both BTC and ETH to move at least 20bp in the same "
        "direction over one second, with fresh captured/native clocks, <=5bp spreads and >=2000-USDT touches. "
        "Targets must pass the same quality limits and show a lag sufficient for 14bp round-trip fees/adverse "
        "costs, both endpoint spread reserves and >2bp remaining hypothesis budget. No catch-up is guaranteed.\n\n"
        "All 13,680 grids in sixty cached 2024 minute windows were independently checked. No qualifying "
        "joint leader move occurred; the largest same-direction common move among quality-valid pairs was "
        "6.84405481513215295156394bp. This sample supplies no test of target profitability. Six focused tests passed.\n\n"
        "Coverage was broadened prospectively using six full cached BTC days; final native thresholds were "
        "not lowered. See ../market_lag_coverage_hft_20261002/REPORT.txt. No economic implementation at this stage.\n", encoding="utf-8")
    (NATIVE1 / "REPORT.txt").write_text(
        "NATIVE LEADER CONFIRMATION — FIRST BATCH AUDITED\n\n"
        "Twelve chronological candidate minutes, 603,350 native BTC/ETH book messages, 5,568 saved quote states "
        "and 2,736 joint decision grids. Three native joint moves passed the unchanged rule. All three also "
        "matched an exact contemporaneous normalized prefilter candidate, so none was admitted by a later "
        "shock in the same minute. The exact-grid alignment correction was frozen before target data or P&L.\n\n"
        "Full independent source/clock/quality/return audit passed; maximum joint Decimal difference 4.979e-24. "
        "An initial final-table check failed on NaN versus JSON None; only the audit's missing-value comparison "
        "was repaired. Original sources, signals and numeric results were unchanged.\n\n"
        "Qualified minutes: July 1 at 02:11 UTC; August 1 at 05:25 and 15:01 UTC. "
        "These identify market shocks, not profitable target trades. Target screen: "
        "../../market_lag_targets_hft_20261002/batch01/REPORT.txt.\n", encoding="utf-8")
    (TARGET1 / "REPORT.txt").write_text(
        "LAGGING TARGETS — FIRST BATCH HAS NO SURVIVOR\n\n"
        "Three all-symbol native source minutes: 2,333,493 messages, 183,280 quote states, 180,120 marginal "
        "signal rows. All original BTC/ETH endpoint identities matched the independently audited source. "
        "Targets were evaluated only at the three exact causally admitted decision timestamps.\n\n"
        "781 target checks: 768 failed endpoint freshness/validity/spread/depth quality; the remaining 13 "
        "failed the unchanged price-gap/cost-budget gate. Zero selected targets, zero execution tests, "
        "and no strategy P&L claim. Independent full native-source and target audit passed, maximum "
        "target arithmetic difference 3.922e-24.\n\n"
        "This is only the first twelve acquisition minutes of the fixed 49-minute cohort. "
        "The other 37 remain part of the investigation, not failed observations.\n", encoding="utf-8")
    jobs = [] if args.active_session is None else [{"session_id": args.active_session, "job": args.active_job}]
    summary = [
        "HFT EDGE SEARCH — MARKET-LAG COVERAGE CHECKPOINT", "",
        "Goal ACTIVE. No reliable edge or competition win established. Stocks, ETFs and crypto remain "
        "authorized; this branch tests crypto only. Strict HFT and conservative costs are unchanged.", "",
        "Completed prior branch: five own-price-shock events and both follow/fade controls across six "
        "execution scenarios. Follow baseline -3.6702489 USDT. Fade baseline unknown due to insufficient "
        "entry depth; known-component profit depended on one event. Fade at 250ms lost 0.2203602 USDT; "
        "the 3s control gained only 0.217154 USDT from three trades on two dates. Not a reliable survivor. "
        "Independent native/execution/cash audit passed; see ../perp_shock_response_hft_20261002/REPORT.txt.", "",
        "New hypothesis: fresh lagging-coin quotes after a coherent BTC/ETH shock. The initial 60 sparse "
        "minute sources contained no joint leader event. Broader coverage was frozen before further data.", "",
        "Full-day acquisition prefilter: all six cached first-of-month BTC top-five histories, July–December "
        "2024. 8,071,556 normalized rows, 1,969,920 quarter-second grids, 174 candidate grids across 49 minutes. "
        "The 15bp BTC-only prefilter locates data to acquire; final native signals still require the original "
        "20bp move in BOTH BTC and ETH and all original quality gates. Full independent as-of/Decimal "
        "candidate audit passed with zero difference. Normalized timestamps never prove native matching "
        "clocks or execution, and these historical dates were previously exposed to research.", "",
        "First twelve native minutes independently audited: three causal joint leader events. All-symbol "
        "target screen on those three minutes independently audited: 781 checks, zero eligible targets. "
        "No economic implementation or future-return calculation for this market-lag family.", "",
        progress, "",
        "Remaining-data acquisition: all 37 files complete, "
        f"{sum(r['decoded_bytes'] for r in acquisition['files']):,} decoded bytes. Free public endpoint only; "
        "no authentication, paid API, order or account changes. All source/code/spec/result hashes preserved.", "",
        "Search accounting: 132 economic configurations, 182 implementation versions, 338 focused tests. "
        "The market-lag extension adds six gate tests and five acquisition-filter tests; reused tests are not "
        "counted again. The second-batch screen retains a style-only Ruff I001 import-format warning to "
        "preserve its frozen hash; other Ruff checks pass. No 2025 selection data opened for these families.", "",
        "Active process handles: " + json.dumps(jobs),
    ]
    (COVERAGE / "REPORT.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
    path = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    checkpoint = read(path)
    assert checkpoint["current_configurations"] == 132 and checkpoint["implementation_versions"] == 182
    checkpoint.update(status="active", reliable_edge_found=False, focused_tests_total=338,
                      updated_at_utc=datetime.now(UTC).isoformat(), report=str(COVERAGE / "REPORT.txt"),
                      active_research_jobs=jobs, remaining_evidence_work=progress,
                      market_lag_reports=[str(p / "REPORT.txt") for p in (HYPOTHESIS, COVERAGE, NATIVE1, TARGET1)],
                      market_lag_sparse_screen_verified=True, market_lag_sparse_selected_events=0,
                      market_lag_full_day_prefilter_verified=True, market_lag_prefilter_candidate_minutes=49,
                      market_lag_native_batch01_verified=True, market_lag_native_batch01_admitted_grids=3,
                      market_lag_targets_batch01_verified=True, market_lag_targets_batch01_selected_events=0,
                      market_lag_native_batch02_acquisition_complete=True,
                      market_lag_native_batch02_screen_complete=native2_results is not None,
                      market_lag_native_batch02_verified=native2_audit is not None,
                      market_lag_native_batch02_admitted_grids=native2_audit["causally_admitted_leader_grids"] if native2_audit else None,
                      market_lag_economic_implementations=0, market_lag_actual_execution_verified=False,
                      market_lag_selection_2025_opened=False, market_lag_candidates=[])
    path.write_text(json.dumps(checkpoint, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(COVERAGE / "REPORT.txt"), "status": "active", "focused_tests_total": 338,
                      "remaining_evidence_work": progress, "active_research_jobs": jobs}))


if __name__ == "__main__":
    main()
