"""Freeze the single-completed-burst extension without changing its failed parent."""

import json
from datetime import UTC, datetime
from pathlib import Path

from research_scout.prepare_equity_resilience_20261002 import OUT as PARENT
from research_scout.prepare_equity_resilience_20261002 import ROOT, SYMBOLS, sha  # noqa: F401

OUT = ROOT / "research_scout/equity_burst_hft_20261002"


def main():
    audit = json.loads((PARENT / "independent_supply_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == sha(PARENT / "results.json")
    spec = json.loads((PARENT / "specification.json").read_text())
    OUT.mkdir(exist_ok=True)
    spec.update(
        created_at_utc=datetime.now(UTC).isoformat(),
        family="Single completed aggressive-price burst followed by observed quote resilience",
        relationship="New dependent hypothesis after the parent repeated-flow screen produced no signals. The five-distinct-capture-clock requirement is replaced by a stricter single-burst size and post-burst survival proof. This is a hypothesis extension, not a reader repair or a hidden retuning of prior results. Same 192 exposed 2023 sources; no outcome-based threshold change and no 2024+ selection access.",
        parent_specification_sha256=sha(PARENT / "specification.json"),
        parent_results_sha256=sha(PARENT / "results.json"),
        parent_audit_sha256=sha(PARENT / "independent_supply_verification.json"),
        flow="Use all native T records in the unchanged two-second information window. An invalid, late or not-yet-in-window event timestamp makes that trade window inadmissible; do not retain only favorable prints. Unknown-side size remains in the denominator. One qualifying completed burst's at-level quantity alone must be >=80% of ALL completed window trade size, >=10000 USD and >=5 times BOTH anchor and immediately pre-burst directional displayed quantities.",
        burst_identity="A source group runs from immediately after the preceding F_LAST record through the next F_LAST record, for one instrument. It must contain trades, and every record in it must share exactly one native ts_recv and ts_event, with no BAD_TS_RECV/MAYBE_BAD_BOOK flag. All trade records must share one known initiating side and one exact fixed-point price. Sum reported quantities; do not invent aggressor/order/venue identity or claim this reveals an iceberg. Incomplete terminal groups fail.",
        burst_prestate="The immediately previous F_LAST state must be valid; its capture is strictly earlier by at most 250ms, its native event timestamp is no later and at most 250ms before the burst's. A same-capture prestate is ambiguous and rejected; never substitute an older smaller quote. The burst price must equal that prestate's relevant touch, and its quantity must be >=5 times that touch. Completion BBO must also be valid.",
        postburst="Before the signal cutoff, observe a completed valid quote at least 250ms after burst completion on BOTH capture and native event clocks. The original two-second defended-price path must remain constant and continuously valid with no >250ms receive gap. Both endpoints retain the parent 250ms freshness rules and the current spread limit. No after-cutoff book is used to verify the signal.",
        rules={"bid_resilience_long": "Buy after a qualifying sell-side burst and two-second held bid with the new pre/post proof.",
               "ask_break_long": "Observe a qualifying buy-side burst and held ask with the same proof; watch ten seconds, then buy only after a later causal fresh ask exceeds that price."},
        selection="Keep the same per-symbol 60s cooldown and later-ask-break watch mechanics. If multiple bursts qualify at a grid, choose larger burst quantity then earlier closing source position; >=80% volume share ordinarily allows only one. Across symbols, rank burst/anchor quantity then burst notional then symbol, one per rule/grid and global 35s decision cooldown. Preserve all groups, seeds and events. No outcome-based selection.",
        stage="Signal supply only. No future return, arrival quote, cash, optimistic proxy or actual execution is evaluated by this stage. Any selected event must be independently verified before the separately frozen parent quote-proxy mechanics are run unchanged.",
        preparation_sha256=sha(Path(__file__)), economic_implementations_run=0,
        reliable_edge_established=False, actual_execution_verified=False)
    with (OUT / "specification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"source_sessions": len(spec["sources"]), "specification_sha256": sha(OUT / "specification.json")}))


if __name__ == "__main__":
    main()
