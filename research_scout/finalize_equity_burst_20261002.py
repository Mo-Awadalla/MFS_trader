"""Record the fully audited burst-survival failure without inventing returns."""

import json
from datetime import UTC, datetime

from research_scout.prepare_equity_burst_20261002 import OUT, ROOT, sha


def main():
    result = json.loads((OUT / "screen_results.json").read_text())
    audit = json.loads((OUT / "independent_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == sha(OUT / "screen_results.json")
    assert result["selected_events"] == 0 and audit["candidate_windows_verified"] == 159
    report = OUT / "REPORT.txt"
    report.write_text(
        "SINGLE-BURST EQUITY RESILIENCE — NO CONFIRMED ENTRY\n\n"
        "Goal ACTIVE. No reliable edge or competition win established. This is a signal-supply result; "
        "no execution or return was calculated. Strict HFT, stocks/ETFs/crypto eligibility and conservative "
        "fees remain unchanged.\n\n"
        "The separate hypothesis required one complete same-clock F_LAST source event to trade at least "
        "10000 USD and five times BOTH anchor and immediately pre-burst visible quantity at a defended "
        "price. Its own quantity had to account for at least 80% of completed window volume, including "
        "unknown-side trades in the denominator. Before the signal cutoff, valid quotes had to show "
        "250ms of survival on capture and native event clocks within a continuously valid two-second "
        "held-price path. A source group is not an identified aggressor, order, venue or iceberg.\n\n"
        "192 local 2023 sessions, 46,428,207 records and 359,650 trade-bearing source groups. Nine bursts "
        "passed the same-clock, side/price, prestate, five-times-size and notional gates. They yielded "
        "159 possible fixed decision windows: 83 failed intervening book validity/freshness; six lacked "
        "the quarter-second post-burst proof; 50 failed price survival; 20 failed endpoint validity/freshness. "
        "Zero seeds therefore imply zero immediate bid entries or later ask-break entries.\n\n"
        "All 192 raw sources and every trade-bearing event group were independently reconstructed. "
        "All nine qualifying bursts, all 159 candidate signal predicates and saved aggregates matched. "
        "The audit imported no production parser, burst detector or price-survival function. Eight "
        "new focused tests passed. Native prices and nanosecond clocks remained integers.\n\n"
        "SPY on 2023-03-28 and UPRO on 2023-07-31 remain unassessable due to BAD_TS_RECV records. "
        "No missing signal/return was booked as zero. No new 2024+ outcome data was opened. Prior "
        "crypto TRX follow/fade results remain negative or unknown, and this experiment provides no "
        "replacement edge.\n\n"
        "Cumulative accounting stays at 134 executed economic configurations and 184 implementation "
        "versions; focused tests rise to 366. Signal-only screens do not inflate economic trial counts. "
        "No active processes remain.\n\n"
        "Next: a separately frozen multi-price sweep hypothesis. The data do not show confirmed static "
        "price resilience under these predicates. Test whether a completed large directional burst that "
        "actually moves through price levels predicts a tradable 15-second continuation or reversal. "
        "Use the existing conservative optimistic price proxy first, then realistic execution and "
        "independent validation only if a lead survives. Preserve all failed hypotheses and their scope.\n",
        encoding="utf-8")
    path = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    checkpoint = json.loads(path.read_text())
    assert (checkpoint["current_configurations"], checkpoint["implementation_versions"], checkpoint["focused_tests_total"]) == (134, 184, 358)
    checkpoint.update(status="active", reliable_edge_found=False, focused_tests_total=366,
                      updated_at_utc=datetime.now(UTC).isoformat(), report=str(report), active_research_jobs=[],
                      equity_burst_report=str(report), equity_burst_supply_verified=True,
                      equity_burst_source_sessions=192, equity_burst_source_rows=46428207,
                      equity_burst_prestate_qualified_groups=9, equity_burst_windows_verified=159,
                      equity_burst_selected_events=0, equity_burst_unknown_symbol_sessions=2,
                      equity_burst_economic_configurations_executed=0,
                      equity_burst_actual_execution_verified=False,
                      remaining_evidence_work="Single-burst resilience completed and independently audited: nine large prestate-qualified bursts, 159 signal windows, zero confirmed seeds. Next freeze and test directional multi-price sweeps with fixed 15-second long-only responses and unchanged conservative costs; no static-price survival premise. No economic replay yet.")
    path.write_text(json.dumps(checkpoint, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report), "economic_configurations": 134,
                      "implementation_versions": 184, "focused_tests_total": 366, "status": "active"}))


if __name__ == "__main__":
    main()
