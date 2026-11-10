"""Frozen economic admission before expensive multi-leg execution simulation."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from research.cross_venue_gate import sampled_book, screen_day
from research.crypto_symbol_cache import digest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout/cross_venue_20260930"
DATES = [f"2024-{month:02d}-01" for month in range(7, 13)]


def run_day(day):
    books, audits = {}, []
    for venue in ("binance", "bybit"):
        base = (ROOT / "research_scout/liquidation_event_20260930" if venue == "binance" else OUTPUT / "bybit")
        path = base / "raw/book_snapshot_5" / day / "BTCUSDT.csv.gz"
        cache = OUTPUT / "cache" / venue / f"{day}.npz"
        audit = sampled_book(path, day, cache)
        audits.append({"venue": venue, **audit})
        with np.load(cache) as archive:
            books[venue] = {key: archive[key] for key in archive.files}
    return screen_day(books["binance"], books["bybit"], day), audits


def main():
    spec_path = OUTPUT / "gate_specification.json"
    if spec_path.exists():
        raise FileExistsError("Frozen cross-venue admission already started")
    code = [ROOT / path for path in ("research/cross_venue_gate.py", "research_scout/run_cross_venue_gate_20260930.py")]
    spec = {"created_at_utc": datetime.now(UTC).isoformat(), "dates": DATES,
            "hypothesis": "BTCUSDT perpetual basis differences between Binance and Bybit may offer a sufficiently large initial price advantage to fund a four-fill convergence trade.",
            "fees": "6bp per fill at both venues, without VIP discounts or rebates; 1bp adverse execution allowance per fill. Four fills imply an approximate 28bp round-trip cost floor on one-leg notional, before exit spread and residual basis.",
            "fee_sources": ["https://www.bybit.com/en/help-center/article/Trading-Fee-Structure"],
            "gate": "33bp opening bid-short minus ask-long gap, divided by mean leg price. Five-bp cushion is additional to the estimated 28bp floor.",
            "capital": "$10000 prefunded account notionally split $5000 per venue; equal BTC amounts, max $1000 per leg, <=10% both visible entry sizes, 0.001 BTC grid, min $100 per leg.",
            "clocks": "100ms receive-clock grid; latest observation strictly before boundary; both quotes <=250ms old; source delay -1ms..1s. Freshness sensitivities of 100ms and 1s are diagnostics, not tuned strategies.",
            "arrival_diagnostics": "200ms/1s/3s later snapshots and 1bp per-leg collars are diagnostic only. No future availability filters the initial opportunity count.",
            "progression": "Only an opening opportunity above the fixed gate justifies a full four-leg replay with failed-leg unwinds, funding and exit-basis risk. No P&L or reliable edge is claimed by this admission screen.",
            "limits": "Six calendar-selected first-of-month dates; price convergence is not guaranteed. Cross-venue orders are not atomic. Provider reconstruction and capture-location differences remain; no actual fills or impact are observed.",
            "code_sha256": {str(path.relative_to(ROOT)): digest(path) for path in code}}
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    results, audits = [], []
    with ProcessPoolExecutor(max_workers=2) as pool:
        for job in as_completed([pool.submit(run_day, day) for day in DATES]):
            result, source_audits = job.result()
            audits.extend(source_audits)
            results.append(result)
            primary = result["quality_sensitivities"]["250ms"]["directions"]
            maximum = max(row["max_opening_gap_bps"] for row in primary.values() if row["max_opening_gap_bps"] is not None)
            print(f"{result['date']}: largest capacity-qualified gap {maximum:.3f}bp; {len(result['opportunities'])} gate intervals", flush=True)
    results.sort(key=lambda row: row["date"])
    opportunities = [opportunity for result in results for opportunity in result["opportunities"]]
    pd.DataFrame(opportunities).to_parquet(OUTPUT / "opening_opportunities.parquet", index=False)
    assert all(digest(path) == spec["code_sha256"][str(path.relative_to(ROOT))] for path in code)
    output = {"verdict": "OPENING_OPPORTUNITIES_REQUIRE_NONATOMIC_REPLAY" if opportunities else "NO_COST_QUALIFIED_OPENING",
              "opportunity_intervals": len(opportunities), "results": results, "source_audits": audits,
              "realized_pnl_computed": False, "edge_established": False}
    (OUTPUT / "gate_results.json").write_text(json.dumps(output, indent=2) + "\n")
    print(output["verdict"], flush=True)


if __name__ == "__main__":
    main()
