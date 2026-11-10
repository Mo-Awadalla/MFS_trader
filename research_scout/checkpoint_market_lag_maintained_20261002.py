"""Close the acquisition-only extension when it adds no untested candidate."""

import json
from datetime import UTC, datetime

from research_scout.prepare_market_lag_maintained_v2_20261002 import ORIGINAL, OUT, ROOT, sha


def main():
    result = json.loads((OUT / "screen_results.json").read_text())
    audit = json.loads((OUT / "independent_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == sha(OUT / "screen_results.json")
    assert result["acquisition_candidates"] == result["original_fresh_candidates"] == 1
    assert result["jobs"] == [{"date": "2024-10-01", "offset": 987, "symbol": "TRXUSDT"}]
    report = ORIGINAL / "REPORT.txt"
    report.write_text(
        "MAINTAINED-QUOTE EXTENSION — NO ADDITIONAL ACQUISITION CANDIDATES\n\n"
        "A separate dependent acquisition experiment kept all seven original causal BTC/ETH grids and "
        "all spread, displayed-depth and economic budget thresholds. Endpoint capture/T/E age up to five "
        "seconds was permitted solely to locate candidates for a mandatory fresh sequenced-depth proof. "
        "This acquisition allowance was never an executable signal or a claim that old quotes remain available.\n\n"
        "The corrected screen checks 1,953 targets from 320,624 previously audited quote rows. There are "
        "1,916 spread/depth failures, 30 insufficient gap/budget failures, six quote-age failures and one "
        "acquisition candidate: the original fresh TRX event. The independent exact-price/source-identity "
        "audit passed and confirmed the original candidate was preserved. No additional symbol or time survived.\n\n"
        "V1 is superseded: it rejected all rows because nullable epoch/update_id values loaded as integral "
        "floats. Its independent predicate repeated that type assumption. V2 accepts only finite exact "
        "metadata integers below 2**53, retains original integer nanosecond clocks and adds an original-candidate "
        "retention assertion. Source data and economic thresholds were unchanged; both versions are preserved. "
        "Six initial boundary tests and two new serialization tests passed (eight unique new tests total).\n\n"
        "No depth acquisition or final maintained-book confirmation was run: the sole possible observation "
        "already lost under all eleven calculable fixed-response cases, and the twelfth had unknown exit "
        "inventory. Extra signal confirmation could retain or reject this event, but cannot add a profitable "
        "observation under the frozen response rules. This is a bounded research triage decision, not a "
        "new trading backtest or proof that every maintained-book strategy loses.\n\n"
        "No new economic configuration, no execution claim, no 2025 selection data. The goal remains ACTIVE. "
        "Cumulative 134 economic configurations, 184 implementation versions and 350 focused tests. "
        "Next investigate lower-cost equity HFT with a rapid net-return ceiling before expensive replay; "
        "keep unsuccessful hypotheses and reserve full execution/stability audits for prospective survivors.\n",
        encoding="utf-8")
    path = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    checkpoint = json.loads(path.read_text())
    assert (checkpoint["current_configurations"], checkpoint["implementation_versions"], checkpoint["focused_tests_total"]) == (134, 184, 342)
    checkpoint.update(status="active", reliable_edge_found=False, focused_tests_total=350,
                      updated_at_utc=datetime.now(UTC).isoformat(), report=str(report), active_research_jobs=[],
                      market_lag_maintained_report=str(report), market_lag_maintained_acquisition_verified=True,
                      market_lag_maintained_target_checks=1953, market_lag_maintained_additional_candidates=0,
                      market_lag_maintained_depth_confirmation_run=False,
                      market_lag_maintained_economic_implementations=0,
                      remaining_evidence_work="Common-move branch closed without a survivor. Maintained-quote acquisition extension adds no new candidate after an audited nullable-metadata repair. Next inspect available equity HFT data and freeze a distinct low-cost execution hypothesis; use quick optimistic net-return rejection before detailed replay.")
    path.write_text(json.dumps(checkpoint, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report), "focused_tests_total": 350, "economic_configurations": 134}))


if __name__ == "__main__":
    main()
