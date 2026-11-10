"""Freeze and screen passive spread budgets in the single free NVDA sample."""

import argparse
import json
from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq

from research.nasdaq_spread_supply import (
    CASH_SCALE,
    CENT,
    budget_units,
    size_at_quote,
    snapshot_indices,
)
from research_scout.inspect_databento_public_sample_20261003 import OUT as PARENT
from research_scout.prepare_databento_fast_20261002 import ROOT, sha, write

OUT = PARENT / "spread_supply"


def prepare():
    inventory = json.loads((PARENT / "inventory.json").read_text())
    audit = json.loads((PARENT / "book_verification_v3.json").read_text())
    assert audit["verified"] and audit["source_inventory_sha256"] == sha(PARENT / "inventory.json")
    quote = next(s for s in inventory["sources"] if s["schema"] == "mbp1")
    OUT.mkdir(exist_ok=True)
    assert not (OUT / "specification.json").exists()
    spec = {"created_at_utc": datetime.now(UTC).isoformat(), "source": quote,
            "source_book_audit_sha256": sha(PARENT / "book_verification_v3.json"),
            "code_sha256": {str(p.relative_to(ROOT)): sha(p) for p in (Path(__file__), ROOT / "research/nasdaq_spread_supply.py")},
            "kind": "Pre-trade passive bid-to-ask spread budget screen, not a trading-return backtest or a claim of fillability.",
            "date": "2025-09-16", "symbol": "NVDA", "decision_grid": "Every 10ms from09:30:05ET through15:59:30ET inclusive.",
            "causality": "Information cutoff decision minus1ms. Use final quote record strictly before cutoff, including all rows sharing its capture timestamp. Require this latest row to carry F_LAST; no fallback to an earlier valid row. Both capture/native ages must be positive and <=5ms. Never inspect a future quote for admission.",
            "book": "Both positive sizes,5<=bid<ask<=1000USD,whole-cent prices,spread at most50bp of midpoint. Reject every other grid explicitly.",
            "size": "Whole shares, at most10% of BOTH current touches and10000USD at a2% collar above current ask rounded up to cents. Fixed using present information.",
            "cash": "Hypothetical purchase at current bid and sale at current ask; each commission max(1USD,0.005USD/share),adverse0.0001 each leg notional,sale0.00003notional+0.000166/share. No rebates. Require net>=2bp of entry notional. All cash uses exact integer1e-14USD arithmetic.",
            "next_gate": "Any eligible cell only earns a separate causal order/queue/latency protocol with <=15s inventory; spread alone does not establish profit. The sample is one vendor-selected day,not untouched temporal validation.",
            "economic_configurations_executed": 0, "returns_calculated": False, "paid_calls": 0}
    write(OUT / "specification.json", spec)
    print(json.dumps({"specification_sha256": sha(OUT / "specification.json")}))


def screen():
    spec = json.loads((OUT / "specification.json").read_text())
    assert not (OUT / "results.json").exists()
    for path, expected in spec["code_sha256"].items():
        assert sha(ROOT / path) == expected
    source = spec["source"]
    assert sha(Path(source["typed_path"])) == source["typed_sha256"]
    table = pq.read_table(source["typed_path"])
    arrays = {name: pc.fill_null(table[name], 0).to_numpy().astype(np.int64) for name in (
        "ts_recv", "ts_event", "flags", "bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00", "source_row")}
    start = int(pd.Timestamp(spec["date"] + " 09:30:05", tz="America/New_York").value)
    end = int(pd.Timestamp(spec["date"] + " 15:59:30", tz="America/New_York").value)
    decisions = np.arange(start, end + 1, 10000000, dtype=np.int64)
    indexes = snapshot_indices(arrays["ts_recv"], decisions)
    assert np.all(indexes >= 0)
    bid, ask = arrays["bid_px_00"][indexes], arrays["ask_px_00"][indexes]
    bq, aq = arrays["bid_sz_00"][indexes], arrays["ask_sz_00"][indexes]
    cutoff = decisions - 1000000
    ra, ea = cutoff - arrays["ts_recv"][indexes], cutoff - arrays["ts_event"][indexes]
    book = ((bid >= 5 * 1000000000) & (ask > bid) & (ask <= 1000 * 1000000000) &
            (bid % CENT == 0) & (ask % CENT == 0) & (bq > 0) & (aq > 0) &
            ((arrays["flags"][indexes] & 128) != 0))
    fresh = book & (ra > 0) & (ra <= 5000000) & (ea > 0) & (ea <= 5000000)
    spread = fresh & ((ask - bid) * 20000 <= (bid + ask) * 50)
    cells = np.flatnonzero(spread)
    quantity = size_at_quote(bq[cells], aq[cells], ask[cells])
    nonzero = quantity > 0
    cells, quantity = cells[nonzero], quantity[nonzero]
    cash = budget_units(bid[cells], ask[cells], quantity)
    entry = quantity * bid[cells]
    passing = np.flatnonzero(cash >= 20 * entry)
    best = max(range(len(cells)), key=lambda i: Fraction(int(cash[i]), int(entry[i]))) if len(cells) else None

    def detail(i):
        cell = int(cells[i])
        return {"decision_ns": int(decisions[cell]), "quote_source_row": int(indexes[cell]),
                "bid_price_int": int(bid[cell]), "ask_price_int": int(ask[cell]), "quantity": int(quantity[i]),
                "net_cash_units": int(cash[i]), "entry_notional_price_units": int(entry[i]),
                "projected_net_usd": str(Decimal(int(cash[i])) / CASH_SCALE),
                "projected_net_bp": str(Decimal(int(cash[i])) / (10 * Decimal(int(entry[i]))))}

    result = {"created_at_utc": datetime.now(UTC).isoformat(), "grid_cells": len(decisions),
              "invalid_or_incomplete_book": int(np.count_nonzero(~book)),
              "quote_age_rejected": int(np.count_nonzero(book & ~fresh)),
              "spread_rejected": int(np.count_nonzero(fresh & ~spread)),
              "quantity_rejected": int(np.count_nonzero(~nonzero)), "computed_budgets": len(cells),
              "positive_budgets": int(np.count_nonzero(cash > 0)), "eligible_cells": len(passing),
              "best_budget": detail(best) if best is not None else None,
              "eligible": [detail(int(i)) for i in passing], "specification_sha256": sha(OUT / "specification.json"),
              "economic_configurations_executed": 0, "returns_calculated": False, "paid_calls": 0,
              "reliable_edge_established": False}
    assert result["grid_cells"] == sum(result[k] for k in (
        "invalid_or_incomplete_book", "quote_age_rejected", "spread_rejected", "quantity_rejected", "computed_budgets"))
    write(OUT / "results.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "eligible"}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "screen"))
    args = parser.parse_args()
    prepare() if args.action == "prepare" else screen()
