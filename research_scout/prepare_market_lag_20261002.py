"""Freeze a coherent-major-move lag hypothesis before its supply is counted."""

import json
from datetime import UTC, datetime
from pathlib import Path

from research_scout.prepare_perp_shock_replay_20261002 import PARENT, ROOT, sha

OUT = ROOT / "research_scout/market_lag_hft_20261002"


def main():
    audit = json.loads((PARENT / "independent_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == sha(PARENT / "screen_results.json")
    OUT.mkdir(exist_ok=True)
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "family": "Coherent BTC/ETH one-second movement versus fresh lagging crypto-perpetual quotes",
        "relationship": "A new dependent research hypothesis, not independent validation: the same 60 cached 2024 minute sources and audited causal returns were already used in the own-price-shock screen. Both prior own-shock controls failed reliability. Retain global search history; do not open 2025 selection outcomes.",
        "parent_results_sha256": sha(PARENT / "screen_results.json"),
        "parent_audit_sha256": sha(PARENT / "independent_verification.json"),
        "information": "Use only independently audited quarter-second decisions, each comparing latest full BBO strictly before d-250ms versus d-1.25s. All capture/T/E clocks at both endpoints must be in (0,250ms] of their own cutoff; inherit source ID/high-water/disconnect-epoch checks. No future quote or return is used.",
        "leaders": ["BTCUSDT", "ETHUSDT"],
        "leader_gate": "Both BTC and ETH must have valid endpoints and all four bid/ask returns at least +20bp, or all at most -20bp. Both endpoint spreads of both leaders <=5bp; all four touches of each leader >=2000 USDT. Direction is their common sign; common_move is the smallest signed return of the four.",
        "targets": "All contemporaneously observed alphanumeric USDT perpetuals except the explicitly listed exclusions. Keep multiplier symbols. No present-day survivor universe.",
        "excluded_symbols": ["BTCUSDT", "ETHUSDT", "USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "USDPUSDT", "DAIUSDT", "PAXGUSDT", "XAUUSDT"],
        "target_gate": "Valid, fresh audited endpoints; each endpoint spread <=5bp; all four touches >=2000 USDT. Neither signed target bid/ask return may be below -5bp, avoiding a large opposite idiosyncratic shock. Gap = common_move - largest signed target bid/ask return. Require gap>=20bp and gap-14bp fees/adverse-anchored spread-current spread>2bp. This is a hypothesis budget assuming catch-up, not an arbitrage or fair-value guarantee; no fitted beta.",
        "selection": "At each grid rank eligible targets by descending hypothesis budget then symbol; take at most the first, with 30 seconds global decision cooldown per disjoint source minute regardless of hypothetical fills. Preserve all candidate rows. No threshold or ranking changes based on supply or P&L.",
        "trade_confirmation_before_pnl": "Require native captured-before-cutoff MARKET executions in the same one-second interval for each leader: at least 5 trades and 5000 USDT, at least 75% notional in the common direction; target needs at least 5 trades and 5000 USDT total. Preserve ID/clock/source integrity. Freeze any acquisition details before reading new trades.",
        "economic_controls_if_supply": ["follow_common_move", "fade_common_move"],
        "response_if_confirmed": "Reuse separately frozen fixed 15-second-after-entry-ACK response mechanics, at most 200 USDT and 10% causal touch, inward 10bp FOK collar, full-touch exit and unknown inventory halts. Verify historical order filters; charge 6bp taker+1bp adverse each side; stress 2x fees/adverse, 250ms/1s/3s delay and 100ms clock uncertainty. No private-fill or reliability claim from quote replay.",
        "scope": "Supply screening only; zero new economic implementations or future-return calculations. No paid data, real orders or account changes.",
        "preparation_sha256": sha(Path(__file__)), "reliable_edge_established": False,
    }
    with (OUT / "specification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"specification_sha256": sha(OUT / "specification.json"), "sources": 60}))


if __name__ == "__main__":
    main()
