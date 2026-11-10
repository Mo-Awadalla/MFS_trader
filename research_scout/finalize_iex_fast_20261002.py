"""Checkpoint the independently verified, no-signal fast displacement screen."""

import json
from datetime import UTC, datetime

from research_scout.prepare_iex_fast_20261002 import OUT, ROOT, sha, write


def main():
    result = json.loads((OUT / "screen_results.json").read_text())
    audit = json.loads((OUT / "independent_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == sha(OUT / "screen_results.json")
    assert result["candidate_count"] == len(result["selected"]) == 0 and not result["errors"]
    report = OUT / "REPORT.txt"
    report.write_text(
        "NATIVE IEX FAST DISPLACEMENT: NO QUALIFYING SIGNAL IN THE LATER OPENING INTERVAL\n"
        "Updated " + datetime.now(UTC).isoformat() + "\n\n"
        "Result: no signal qualified; no subsequent returns, order fills or strategy profit were evaluated. This rejects the supply of the frozen signal in this limited development window, not every HFT opportunity. No reliable edge has been established.\n\n"
        "Scope: the same24fixed2023dates;23intact native DEEP sources. November29 has missing initial sequence/book history and remains unknown. Every100ms decision from09:30:30 through09:31:00 ET;1ms information-age assumption; strictly prior captured information, native event/send clocks at or before cutoff. Reference snapshot1s earlier. No2024+holdout opened. Existing local, generation-pinned free data only.\n\n"
        f"Independent reconstruction verified {result['source_messages_checked']:,} native messages, {result['decision_grids']:,} decision grids and {result['symbol_grids']:,} symbol/grid checks. Complete atomic DEEP books, trade eligibility, broken-trade handling, freshness, rejection counts and candidate selection were independently rebuilt. Ten focused tests and Ruff passed.\n\n"
        "Frozen admission: active normal trading; non-test candidate symbol; latest current trade at most100ms old and reference trade at most250ms old, with capture and native clocks checked. Both snapshots need a complete quote at most250ms old. Trades must be inside their respective BBO. At least5distinct native trade times and$25,000notional in the prior1s; absolute trade-price change>=30bp and both bid and ask confirming direction. Current spread<=5bp;reference spread<=50bp.\n\n"
        "Fixed order quantity is at most10%of each current touch, with max$10,000at a cent-rounded buy limit2%above current ask. Ask-to-bid cost includes two max($1,$.005/share) commissions,1bp adverse allowance perleg and sale levy. Cost<=12bp and observed displacement>=3times cost. Separate long-only rise-following and fall-fading rules;6s global and30s symbol cooldown,6event/date cap perrule.\n\n"
        "Observed rejection counts (ordered first failure):\n" +
        "\n".join(f"{k}: {v:,}" for k, v in result["outcomes"].items()) + "\n\n"
        "There were382symbol/grid observations past the recent-trade and30bp-move filters:300failed minimum activity,57spread,23quote age and2valid-price checks. These are repeated snapshots, not382independent opportunities. None reached the cost-admitted signal stage.\n\n"
        "The planned1/5/25/250ms arrival-delay cases have NOT been economically tested because admission was empty. Actual client latency, venue/simulator access, NBBO protection and acceptance remain unverified. The1ms information age is an explicit feasibility assumption, not a measured infrastructure capability.\n\n"
        "Next, per the user's latest steering: use existing local Databento data without paid calls. A new immediate response to verified ETF multi-price sweeps will test explicit millisecond delay assumptions with fixed causal size and bounded L1 fills. The earlier IEX window was prepared only as code; it was not frozen or run and is deferred.\n\n"
        "Global search ledger:139economic configurations,191implementation versions,421focused tests. This signal-only screen adds no economic configuration. Goal active.\n"
        "Data provided for free by IEX. By accessing or using IEX Historical Data, you agree to the IEX Historical Data Terms of Use. https://www.iex.io/legal/hist-data-terms\n\n"
        "Specification SHA256: " + sha(OUT / "specification.json") + "\n"
        "Results SHA256: " + sha(OUT / "screen_results.json") + "\n"
        "Audit SHA256: " + sha(OUT / "independent_verification.json") + "\n")
    checkpoint = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    state = json.loads(checkpoint.read_text())
    assert (state["current_configurations"], state["implementation_versions"], state["focused_tests_total"]) == (139, 191, 421)
    state.update(updated_at_utc=datetime.now(UTC).isoformat(), status="active", active_research_jobs=[],
                 latest_report=str(report), iex_fast_report=str(report),
                 iex_fast_admission_verified=True, iex_fast_candidates=0,
                 iex_fast_source_messages=result["source_messages_checked"],
                 iex_fast_symbol_grids=result["symbol_grids"], iex_fast_actual_execution_verified=False,
                 previous_goal_turn_classification="progress",
                 next_research_note=str(ROOT / "research_scout/databento_fast_sweep_20261002/specification.json"),
                 remaining_evidence_work="Fast IEX displacement independently verified,zero signals; no economic replay. User requests Databento without paid calls:next freeze and run immediate ETF sweep response on192local2023sessions. Early IEX window code unexecuted and deferred. No reliable edge.")
    write(checkpoint, state)
    print(json.dumps({"report": str(report), "counts": [139, 191, 421], "reliable_edge_found": False}))


if __name__ == "__main__":
    main()
