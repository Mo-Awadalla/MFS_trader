"""Freeze a three-book spot conversion budget, using only already cached sources."""

import json
from datetime import UTC, datetime
from pathlib import Path

from research_scout.prepare_fdusd_maker_20261002 import OUT as SOURCE_SCREEN
from research_scout.prepare_fdusd_maker_20261002 import ROOT, sha

OUT = ROOT / "research_scout/conversion_cycle_hft_20261002"


def main():
    OUT.mkdir(exist_ok=True)
    parent = json.loads((SOURCE_SCREEN / "specification.json").read_text())
    audit = json.loads((SOURCE_SCREEN / "independent_verification.json").read_text())
    assert audit["verified"]
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "family": "Same-venue three-market spot conversion budget",
        "hypothesis": "A simultaneous price discrepancy among BASE/USDT, BASE/BRIDGE and BRIDGE/USDT may leave cash after all three conservative trading costs. Two successive observations are required before an execution study. A displayed cycle is not a simultaneous or atomic fill.",
        "relationship": "A separate dependent hypothesis in the ongoing globally exposed search. This is a three-market cash identity, not a spot/perpetual fair-value forecast or an FDUSD passive-spread strategy. No previous failure is erased.",
        "bridges": ["BTC", "ETH", "BNB"],
        "universe": "Every native contemporaneous alphanumeric BASE/BRIDGE symbol with BASE/USDT and BRIDGE/USDT also recorded in that same minute. Exclude BASE equal to bridge or USDT. No current-symbol survivor list, top-N selection or coin-name whitelist. Missing early books remain rejection rows.",
        "sources": parent["sources"],
        "parent_full_source_audit_sha256": sha(SOURCE_SCREEN / "independent_verification.json"),
        "clock": "One-second decisions at seconds 10..59 in each of the sixty existing first-of-month 2024 minutes. Every source capture timestamp is parsed; only full BBO records captured strictly before decision-250ms are available. Require each of the three books' capture ages <=1s. This is a signal freshness gate, not proof that older quotes expired.",
        "integrity": "Positive finite prices and sizes, strictly uncrossed books, increasing update IDs, no refresh on exact duplicates, poison conflicting/regressing IDs until a strictly higher update, clear book/id state on disconnect. Spot BBOs have no native exchange matching timestamp; none is invented.",
        "routes": {
            "base_first": "200 USDT buys BASE at BASEUSDT ask, sells BASE at BASEBRIDGE bid, sells BRIDGE at BRIDGEUSDT bid.",
            "bridge_first": "200 USDT buys BRIDGE at BRIDGEUSDT ask, buys BASE at BASEBRIDGE ask, sells BASE at BASEUSDT bid."
        },
        "costs": "On EVERY leg charge 10bp fee in the received asset and 1bp adverse price allowance: buy output = input/(ask*1.0001)*0.999; sell output = input*bid*0.9999*0.999. Also calculate each separate double-fee or double-adverse stress. Do not assume any promotion, VIP discount, rebate, borrowing or stablecoin conversion at par.",
        "size": "Start with 200 USDT. For every leg, gross base quantity consumed may be at most 10% of its displayed directional touch. Quantity and price grids are relaxed in this budget only, so it cannot prove executable orders. No future book is used to resize.",
        "selection": "Base final cash must exceed 200*(1+2/10000), with all causal price/depth gates true, in two consecutive one-second decisions for the same directed route. Keep the earliest confirmed event per route with a fixed 30-second cooldown. All raw route rows and rejection reasons retained; no P&L ranking.",
        "next_stage": "Only selected routes justify separately frozen native sequential execution replay. Require actual historical symbol filters, 250ms feed plus 50ms processing and conservative order/ACK latency, explicit leg rejection/partial inventory and emergency unwind, every leg fee in its actual received asset, and <=30s planned inventory. Do not treat three displayed books as simultaneously tradable or an unknown unwind as zero loss.",
        "economic_implementations": 0, "future_returns_evaluated": False,
        "actual_execution_verified": False, "selection_2025_opened": False,
        "reliable_edge_established": False, "preparation_sha256": sha(Path(__file__)),
        "primary_book_schema": "https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams",
    }
    with (OUT / "specification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"source_minutes": len(spec["sources"]), "new_downloads": 0, "bridges": spec["bridges"]}))


if __name__ == "__main__":
    main()
