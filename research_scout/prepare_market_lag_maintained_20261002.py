"""Freeze a separate maintained-book experiment before its acquisition screen."""

import json
from datetime import UTC, datetime
from pathlib import Path

from research_scout.prepare_market_lag_native_20261002 import HYPOTHESIS, ROOT, sha

OUT = ROOT / "research_scout/market_lag_maintained_hft_20261002"


def main():
    OUT.mkdir(exist_ok=True)
    parents = []
    for batch in ("batch01", "batch02"):
        native = ROOT / "research_scout/market_lag_native_hft_20261002" / batch
        target = ROOT / "research_scout/market_lag_targets_hft_20261002" / batch
        for path in (native, target):
            audit = json.loads((path / "independent_verification.json").read_text())
            assert audit["verified"] and audit["results_sha256"] == sha(path / "screen_results.json")
        parents.append({"batch": batch, "native_path": str(native.relative_to(ROOT)),
                        "native_audit_sha256": sha(native / "independent_verification.json"),
                        "events_sha256": sha(native / "admitted_leader_grids.parquet"),
                        "target_path": str(target.relative_to(ROOT)),
                        "target_results_sha256": sha(target / "screen_results.json"),
                        "target_audit_sha256": sha(target / "independent_verification.json")})
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "family": "Coherent BTC/ETH shocks with independently maintained target top-of-book state",
        "relationship": "Dependent model-extension research after the fresh-BBO branch failed. All seven causal leader grids from all 49 native minutes remain fixed. Include the losing TRX quote if it passes this acquisition filter. Preserve all prior results and search multiplicity; no 2025 selection data.",
        "parents": parents, "parent_hypothesis_sha256": sha(HYPOTHESIS / "specification.json"),
        "rationale": "BBO messages are emitted on price/quantity changes; a resting unchanged quote need not expire solely because no new BBO message arrived. This is a hypothesis about a possible quality-filter false negative, not permission to assume old liquidity is available.",
        "acquisition_filter": "Use hash-verified audited full BBO ledgers at exactly the same anchor/current cutoffs. Require original ID/order/disconnect integrity and clock consistency; permit endpoint capture/T/E ages in (0,5 seconds] solely to identify depth data worth acquiring. Keep <=5bp endpoint spreads, >=2000 USDT each touch, signed target return floor -5bp, gap>=20bp and gap-14bp-both endpoint spreads>2bp. No ranking or cooldown until final depth proof. Do not call this filter an eligible trading signal.",
        "final_confirmation": "Both endpoint states require native depth captured strictly before their own cutoff, with latest capture/T/E ages in (0,250ms], no clock inconsistency and an uninterrupted pu/u chain. Bridge an initial snapshot to depth U<=snapshot_update_id<=u and retain only the known snapshot range. A full generated REST snapshot may seed the book; an independently audited full-BBO quote may seed a bounded one-level snapshot only if the overlap is verified and both reconstructed top prices/quantities remain proven within the original known boundaries. Never infer deeper levels after range exhaustion. Independently reconstruct each endpoint and match all four BBO fields. Any missing bridge, gap, disconnect, regression, unknown boundary or disagreement is not confirmed. Freeze exact depth implementation and bounded acquisition before parsing new depth.",
        "selection_and_flow": "After depth confirmation, unchanged descending budget/symbol ranking and global 30-second cooldown per disjoint minute. Both leaders require >=5 MARKET trades, >=5000 USDT and >=75% aligned notional in the causal one-second window; target requires >=5 trades and >=5000 USDT. Freeze/reuse source acquisition and integrity checks. Do not drop known losing observations.",
        "response_if_confirmed": "Both follow_common_move and fade_common_move; retain fixed <=200-USDT, <=10% causal touch, >=100-USDT minimum, full reserve, inward 10bp FOK collar, 15-second exit after ACK, strict <30-second planned inventory. 6bp fees +1bp adverse per leg, fee/adverse doubles, 250ms/1s/3s delay and 100ms clock stress. Fresh depth can certify the signal but cannot manufacture execution fills; missing execution state remains unknown. All future outcome work requires separate frozen mechanics and independent audit.",
        "primary_references": [
            "https://github.com/binance/binance-futures-connector-python/blob/main/binance/websocket/um_futures/websocket_client.py",
            "https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/How-to-manage-a-local-order-book-correctly",
            "https://docs.tardis.dev/historical-data-details/binance-futures"],
        "economic_implementations": 0, "future_returns_evaluated": False,
        "actual_execution_verified": False, "reliable_edge_established": False,
        "preparation_sha256": sha(Path(__file__)),
    }
    with (OUT / "specification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"specification_sha256": sha(OUT / "specification.json"), "causal_leader_grids": 7}))


if __name__ == "__main__":
    main()
