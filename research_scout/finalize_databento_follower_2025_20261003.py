"""Close the audited, empty follower hypothesis without consuming 2026."""

import json
from datetime import UTC, datetime
from decimal import Decimal

from research_scout.databento_follower_2025_20261003 import OUT, PARENT
from research_scout.prepare_databento_fast_20261002 import ROOT, sha, write


def main():
    periods = []
    for year, folder in ((2023, PARENT.parent), (2024, PARENT), (2025, OUT)):
        result = json.loads((folder / "screen_results.json").read_text())
        audit = json.loads((folder / "independent_verification.json").read_text())
        assert audit["verified"] and audit["results_sha256"] == sha(folder / "screen_results.json")
        assert result["selected_count"] == result["admitted_count"] == 0
        assert Decimal(result["best_projected_net_bp"]) < 0
        periods.append((year, result, audit))
    combined = {key: sum(result[key] for _, result, _ in periods) for key in (
        "sessions", "source_rows", "leader_groups", "valid_leader_signals", "follower_checks", "budgets")}
    report = OUT / "REPORT.txt"
    assert not report.exists()
    lines = [
        "DATABENTO SPY SWEEP / FOLLOWER LAG: CLOSED AFTER THREE EMPTY DEVELOPMENT PERIODS",
        "Updated " + datetime.now(UTC).isoformat(), "",
        "No qualifying signal and no reliable edge. Every computable projected convergence budget was negative after unchanged conservative costs. These are pre-trade hypothetical budgets, not realized or simulated P&L. No future-return replay or economic configuration was executed for this family.", "",
        "Year | cached sessions | source records | qualified SPY groups | valid leader signals | follower checks | budgets | best projected net bp | selected",
    ]
    for year, result, _ in periods:
        lines.append(f"{year} | {result['sessions']} | {result['source_rows']} | {result['leader_groups']} | {result['valid_leader_signals']} | {result['follower_checks']} | {result['budgets']} | {result['best_projected_net_bp']} | {result['selected_count']}")
    current, audit = periods[-1][1:]
    lines += ["", f"Combined: {combined['sessions']} cached opening windows; {combined['source_rows']:,} source records; {combined['budgets']} computable budgets, all negative. Checks are not independent trades. The cached files are not complete trading days.", "",
              "UNCHANGED RULE",
              "A completed, large, single-side SPY group trading monotonically across multiple prices triggers a decision strictly after capture plus 1ms. Use only complete quotes strictly before decision minus 1ms, with an exactly one-second reference. Both SPY bid and ask must move in the initiating direction. Long SSO/UPRO follows a positive SPY move; long SH/SDS/SPXU follows a negative move. Quotes must be positive, uncrossed and cent-priced; spreads at most 5bp. Current SPY quote age is at most 5ms; all other reference/current ages at most 250ms by capture and native clocks.",
              "The reference follower mid is projected using the fund's daily objective multiplier and the one-second SPY move. The current follower half-spread is subtracted and the exit price rounded down to cents. Daily objectives do not guarantee second-scale tracking; this is an unverified forecasting model, not an arbitrage identity.",
              "Quantity is fixed causally at at most 10% of both current touch quantities and $10,000 at a 2% buy collar. Costs remain two max($1, $0.005/share) commissions, 1bp adverse allowance on each leg, plus specified sales charges. Current roundtrip cost must not exceed 12bp and projected net gain must reach 2bp. Rank projected dollars then basis points, with 6s global and 60s symbol cooldowns. No economic parameter was changed for either annual expansion.", "",
              "2025 INDEPENDENT AUDIT",
              f"Rebuilt all {audit['trade_groups_verified']:,} SPY trade-bearing groups: {audit['qualified_groups_verified']} qualified, {audit['rejected_groups_verified']:,} rejected. Recomputed all leader/follower clocks, {audit['budgets_verified']} budgets with integer-rational projected prices and exact Decimal cash, ranking, source hashes and zero selections. No 2025 symbol-session failed the source clock check.",
              "The 2024 audit also independently enumerated all rejected source groups. The 2023 audit checked every reported qualifying group and downstream decision, but did not independently enumerate all earlier rejections. Audits share the Databento SDK binary decoder while using separate field and calculation logic.",
              "Five additional focused tests verify nanosecond distinctions, backward-clock precedence, unsigned timestamp overflow and BAD_TS_RECV handling in the 2025 auditor. Ruff and all five tests passed. Production economic/source code and prior results remained unchanged.", "",
              "SOURCE LIMITS",
              "Unassessable source data remain explicit: SPY 2023-03-28, UPRO 2023-07-31, and SPY 2024-04-10. No missing opportunity is called zero profit or proof of no signal. EQUS.MINI is an anonymous component-venue quote feed. Consolidated NBBO, routeability, order acceptance, hidden liquidity, private fills and actual client latency are not established.",
              "All market data for this family came from files already on disk: zero market-data API calls and zero paid calls. The 2025 expansion is additional discovery; unrelated prior work already used 2025. The 112 cached 2026 files were not opened for this family.", "",
              "DECISION",
              "Close this exact SPY-sweep-triggered follower hypothesis over the cached 2023-2025 windows. Do not lower its thresholds, alter costs or consume 2026 merely to rescue an empty signal. This does not reject every HFT strategy or opportunities outside these source windows.",
              "The next investigation is free public Databento Nasdaq order-level samples. First establish source completeness, native clocks, order identifiers and usable history. An identified venue and MBO data may support more defensible queue research; they do not themselves establish an edge or private execution. No paid query, account credit consumption or contact with a third party is authorized or needed for public sample inspection.", "",
              "Global ledger: 143 economic configurations, 195 implementation versions, 444 focused tests. Goal remains active; no reliable edge or competition win has been established.",
              "Specification SHA256: " + sha(OUT / "specification.json"),
              "Results SHA256: " + sha(OUT / "screen_results.json"),
              "Audit SHA256: " + sha(OUT / "independent_verification.json")]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    next_note = OUT / "NEXT_RESEARCH.txt"
    next_note.write_text(
        "Strict HFT; stocks, ETFs and crypto; raw outperformance and actual reliability. Continue only no-paid-call data access. No reliable edge; goal active.\n\n"
        "The unchanged SPY sweep/follower signal is now closed after 2023-2025 supply screens: "
        + json.dumps(combined) + ". All budgets negative, zero selected signals, zero economic replay. 2025 audit independently verifies every accepted/rejected group. Preserve all prior immutable source/code/spec/result hashes. Do not consume the 112 cached 2026 files to rescue this hypothesis.\n\n"
        "Next: inspect official public Databento Nasdaq MBO sample downloads, linked from https://databento.com/tick-data. The public sample endpoint is https://hist.databento.com/v0/dataset/sample/download/xnas.itch/mbo?sample_type=equities . No API key, billing, order, signup or messaging is needed. First determine actual date range, symbols, complete start/reset history and native timestamp precision. A sample may be too small for reliability; do not claim independent validation from a single sample.\n\n"
        "Global counts143 economic configurations/195 implementation versions/444 focused tests. New five tests are auditor clock-quality cases, not economic variants. Preserve unknown outcomes. No subagents, actual trades or external messages. Latest turn made progress, not blocked.\n",
        encoding="utf-8")
    checkpoint = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    state = json.loads(checkpoint.read_text())
    assert (state["current_configurations"], state["implementation_versions"], state["focused_tests_total"]) == (143, 195, 439)
    state.update(updated_at_utc=datetime.now(UTC).isoformat(), status="active", active_research_jobs=[],
                 focused_tests_total=444, latest_report=str(report), next_research_note=str(next_note),
                 databento_follower_2025_report=str(report), databento_follower_2025_verified=True,
                 databento_follower_2025_all_group_rejections_verified=True,
                 databento_follower_2025_source_rows=current["source_rows"],
                 databento_follower_2025_trade_groups=current["group_counts"]["trade_bearing_groups"],
                 databento_follower_2025_candidates=0, databento_follower_2025_economic_configurations_executed=0,
                 databento_follower_2025_best_projected_net_bp=current["best_projected_net_bp"],
                 databento_follower_combined_supply=combined, databento_follower_family_closed=True,
                 previous_goal_turn_classification="progress",
                 remaining_evidence_work="2023-2025 follower signal closed: every computable budget negative, zero signals. Inspect official free Databento Nasdaq MBO samples for an identified-venue execution basis. No paid call or reliable edge.")
    write(checkpoint, state)
    print(json.dumps({"report": str(report), "combined": combined, "counts": [143, 195, 444],
                      "reliable_edge_established": False, "market_data_api_calls": 0}))


if __name__ == "__main__":
    main()
