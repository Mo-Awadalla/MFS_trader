"""Freeze a dependent external-price quote-protection experiment and sources."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "research_scout/wide_tick_hft_20260930"
OUT = ROOT / "research_scout/external_quote_hft_20261002"


def main():
    OUT.mkdir(exist_ok=True)
    original = json.loads((PARENT/"replay_specification.json").read_text())
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "hypothesis": "An external venue's causally observed quote can identify a passive quote whose remaining price cushion no longer covers the round-trip cost. Stop offering that side, with full cancellation latency, before another adverse fill.",
        "dependence": "An extension of the failed wide-tick passive family using a newly acquired Bybit input. Not an independent discovery. No symbol, day, threshold or schedule is chosen from the prior per-cycle profit distribution.",
        "parent_specification_sha256": hashlib.sha256((PARENT/"replay_specification.json").read_bytes()).hexdigest(),
        "selected_sha256": hashlib.sha256((PARENT/"selected.parquet").read_bytes()).hexdigest(),
        "cohorts": original["cohorts"],
        "decisions_utc": original["decisions_utc"],
        "rest_seconds": [10, 22],
        "economic_configurations_planned": 2,
        "economic_implementations_run": 0,
        "binance_model": "Reuse the frozen native Binance source, clocks, entry-size gate, queue initialization, price limits, no-cancellation FIFO model, trade-volume caps, capital and funding checks. One fixed quote per eligible side, no recentering.",
        "external_source": "Bybit orderbook.1 native full snapshots for identical symbols/dates, strictly received before the information cutoff. This is a predictive input; no Bybit orders or assumed Bybit fills.",
        "external_validity": "Require a full positive uncrossed one-level snapshot, coherent nondecreasing update/sequence IDs, and captured/publication ages <=5s at the information cutoff; source messages arriving exactly at a cutoff are excluded. For snapshots with cts, also enforce matching-clock consistency and freshness. Missing historical cts is recorded, but does not invalidate an otherwise causal predictive input: Bybit prices are never used to price executions. New snapshot u=1 resets state; exact repeated-u snapshots must retain prices/sizes. A disconnect or invalid message invalidates the input until a new valid full snapshot.",
        "entry": "At each original decision D use the last Bybit snapshot captured strictly before D-250ms. A Binance buy quote at price P is admitted iff Bybit_bid-P-P*0.0004-Bybit_bid*0.0007 > 0. A sell at P is admitted iff P-Bybit_ask-P*0.0004-Bybit_ask*0.0007 > 0. Test sides independently. This price cushion is an entry/cancel signal, not locked-in profit or an execution guarantee.",
        "cancellation": "For each admitted side, find the first causally available external update after decision for which that side's price cushion is nonpositive or source state is invalid; observation time is capture+250ms, strictly after that boundary. Also cancel at the first freshness expiry if no newer valid observation arrives. Cancellation physically arrives after the scenario outbound delay. Cancel no later than original arrival+rest. A cancellation before order arrival cannot remove any arrival uncertainty; retain the original +/- clock envelopes and trade-at-boundary ambiguity.",
        "clock_strictness": "Bybit update availability is capture+250ms+1ns. Freshness expiry is min(capture,publication,cts-if-present)+5s+250ms+1ns. Events with identical availability are processed in native source order; retain any invalidation even if a later tied event recovers the state.",
        "exit": "Flatten residual only after all admitted cancellations are acknowledged, then another outbound delay: latest physical cancellation plus 2*delay. Each side's queue-volume bounds use its own cancellation time. Every partial fill and rejection is retained. Any unpriced submitted inventory makes the whole date UNKNOWN after accounting for its already-submitted contemporaneous batch.",
        "costs_and_stresses": "Same six parent scenarios. All use the original 3bp maker + 6bp taker + 1bp adverse per execution to define the unchanged external-price signal; stress fees change realized cost only. Delays and uncertainty change execution and cancellation arrival as declared.",
        "capital_usdt": 10000,
        "maximum_holding_seconds": 30,
        "validation": "Only complete positive development evidence that survives fees, latency, adverse allowance, queue and clock stresses may advance to unchanged 2025 cohort selection and day-block/multiple-search reliability tests. Keep no-fill, unknown and losing observations. No threshold grid or retrospective symbol selection.",
        "source_references": ["https://docs.tardis.dev/historical-data-details/bybit.md", "https://bybit-exchange.github.io/docs/v5/websocket/public/orderbook"],
        "download": {"exchange": "bybit", "channel": "orderbook.1", "offsets": [540, 550, 560], "slice_minutes": 10,
                     "per_slice_decoded_cap": 96000000, "total_decoded_cap": 2880000000, "workers": 3,
                     "authenticated": False, "paid_fallback": False},
        "selection_2025_opened": False, "reliable_edge_established": False,
    }
    with (OUT/"specification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(spec, indent=2)+"\n")
    print(json.dumps({"specification": str(OUT/"specification.json"), "cohorts": len(spec["cohorts"])}))


if __name__ == "__main__":
    main()
