"""Freeze a historical universe screen for wider-spread passive HFT."""

import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/wide_tick_hft_20260930"


def main():
    OUT.mkdir(exist_ok=True)
    path = OUT / "specification.json"
    if path.exists():
        raise RuntimeError("Preserve initial supply-screen specification")
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "family": "Passive HFT in crypto contracts with persistent relative spreads large enough to cover conservative costs",
        "relation_to_prior": "BTC, ETH and SOL passive/liquidation studies failed previously. This is a dependent change of instrument universe motivated by the spread-to-fee constraint. No candidate is an independent discovery merely because it uses another symbol.",
        "dates": [f"2024-{month:02d}-01" for month in range(1, 13)],
        "exchange": "binance-futures",
        "channels": ["bookTicker", "trade"],
        "universe": "All contemporaneously recorded native symbols ending USDT. Exclude dated suffixes and non-USDT contracts. Do not select from a present-day survivor list.",
        "window": "09:00:00 inclusive through 09:01:00 UTC exclusive, by capture time, on each sampled day. This is a liquidity/spread screen with no subsequent prices or P&L labels.",
        "grid": "50 one-second decisions at 09:00:10 through 09:00:59 UTC. At each decision use only book messages received strictly earlier. Require full finite positive b/B/a/A, b<a, native T and E not later than receipt plus 1 ms, T<=E+1 ms; both capture and transaction age must be positive and at most five seconds. A disconnect clears all book states. No stale fallback past a new invalid state.",
        "source_clock": "Native bookTicker T is transaction time; E is publication time. They are stored separately. Trade T is match time, and m identifies a buyer-maker / sell aggressor when true. Capture time defines information availability.",
        "per_grid_supply": "Relative spread (a-b)/mid from 12 through 100 bp inclusive, and both displayed best-side notionals at least 2,000 USDT. This permits a hypothetical 200 USDT order at at most 10 percent of observed touch depth. No fill is inferred.",
        "symbol_date_supply": "At least 40 of 50 grid points have a valid causal book, and at least 30 of 50 meet per-grid supply. During capture interval 09:00:10 to 09:01:00 require at least ten executions in each aggressor direction and at least 5,000 USDT executed notional in each direction. Trade records must have positive finite price and quantity, ordered capture, and match/publication/capture clocks consistent within 1 ms and five seconds.",
        "selection": "Retain every qualifying symbol/date. If more than four qualify on a date, select four by descending minimum of buy/sell executed notionals; break ties by symbol. Selection happens at 09:01:00; any later execution study starts after that time. Preserve all excluded and failed-source rows. No quantity/tick rules are inferred as verified merely from historical prices.",
        "economic_motivation": "Minimum 12 bp spread budgets two 3 bp maker fees, two 1 bp adverse allowances and a 4 bp remainder before queue loss and inventory risk. A forced taker exit costs 6 bp plus 1 bp adverse allowance. Fee assumptions are research constraints, not account-specific entitlements.",
        "next_stage": "Only genuine supply warrants a frozen native queue replay with delayed arrival/cancellation, all partial inventory, full displayed queue ahead, actual aggressor executions and trade-through evidence, maximum 30-second inventory, and failure unwind. Verify historical order grids, native trade/book order, source gaps and contract lifecycle before any profitability claim. Do not assume a touch or an inside-spread print fills a passive order.",
        "download": {"per_slice_decoded_cap": 128_000_000, "total_decoded_cap": 1_536_000_000, "workers": 3, "slice_minutes": 1, "authenticated": False, "paid_fallback": False},
        "sources": ["https://docs.tardis.dev/historical-data-details/binance-futures.md", "https://docs.tardis.dev/api/http-api-reference.md"],
        "strategy_pnl_tested": False, "reliable_edge_established": False, "selection_2025_opened": False,
    }
    path.write_text(json.dumps(spec, indent=2)+"\n")
    print(json.dumps({"native_slices": 12, "future_returns_used": False, "economic_implementations": 0}))


if __name__ == "__main__":
    main()
