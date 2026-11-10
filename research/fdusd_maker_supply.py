"""Native FDUSD spot screen; hypothetical spread budgets are not profits."""

import json
import math
from collections import Counter
from decimal import Decimal as D

from research.spot_perp_supply import NS, capture_ns, midnight_ns, update_book


def budgets(bid, ask):
    b, a = D(bid), D(ask)
    gross = a - b
    passive = gross - (b + a) * D("0.0002")
    stressed = gross - (b + a) * D("0.0003")
    failure = b * D("0.0013")
    return {"spread_bps": str(20000 * gross / (a + b)),
            "passive_budget_bps": str(passive / b * 10000),
            "double_fee_reserve_budget_bps": str(stressed / b * 10000),
            "double_adverse_budget_bps": str(stressed / b * 10000),
            "flat_forced_exit_bps": str(-failure / b * 10000),
            "simplified_required_passive_exit_fraction": str(failure / (failure + passive)) if passive > 0 else None}


def evaluate(state, decision):
    row = {"valid": False, "supply": False, "reason": "missing_state"}
    if state is None:
        return row
    row.update(state)
    if not state["sequence_ok"]:
        return {**row, "reason": "conflicting_or_regressing_update"}
    prices = [float(state[k]) for k in ("bid", "ask", "bid_quantity", "ask_quantity")]
    if not all(math.isfinite(p) and p > 0 for p in prices) or prices[0] >= prices[1]:
        return {**row, "reason": "invalid_book"}
    age = decision - state["receive_ns"]
    if not 250_000_000 < age <= 5 * NS:
        return {**row, "reason": "signal_freshness_gate"}
    b, a, bq, aq = [D(state[k]) for k in ("bid", "ask", "bid_quantity", "ask_quantity")]
    values = budgets(b, a)
    spread = D(values["spread_bps"])
    minimum_touch = min(b * bq, a * aq)
    supply = 8 <= spread <= 100 and minimum_touch >= 2000
    return {**row, **values, "valid": True, "supply": supply,
            "minimum_touch_fdusd": str(minimum_touch),
            "reason": "spread_and_depth_supply" if supply else "spread_or_depth_gate"}


def sample(lines, day, offset):
    midnight = midnight_ns(day)
    start = midnight + offset * 60 * NS
    grids = [start + second * NS for second in range(10, 60)]
    states, ids, seen, snapshots, fx_rows = {}, {}, set(), [], []
    counts = Counter()
    last, cursor = -1, 0

    def save_grid(decision):
        snapshots.append({symbol: evaluate(states.get(symbol), decision) for symbol in seen})
        fx = evaluate(states.get("FDUSDUSDT"), decision)
        fx_rows.append({"decision_ns": decision, "base_currency": "FDUSD", "quote_currency": "USDT",
                        "valid": fx["valid"], "reason": "valid_fx_quote" if fx["valid"] else fx["reason"],
                        **{key: fx[key] for key in ("receive_ns", "source_line", "update_id", "bid", "ask", "bid_quantity", "ask_quantity") if key in fx}})

    for line_index, line in enumerate(lines):
        if not line.strip():
            counts["disconnects"] += 1
            states.clear()
            ids.clear()
            continue
        counts["native_messages"] += 1
        # Native capture ordering of every source record was already separately
        # audited. Only relevant symbols need JSON decoding in this reuse pass.
        if "FDUSD" not in line:
            continue
        stamp, payload = line.rstrip("\r\n").split(" ", 1)
        received = capture_ns(stamp, midnight)
        assert stamp[:10] == day and start <= received < start + 60 * NS and received >= last
        last = received
        while cursor < len(grids) and grids[cursor] - 250_000_000 <= received:
            save_grid(grids[cursor])
            cursor += 1
        message = json.loads(payload)
        if not message.get("stream", "").endswith("@bookTicker"):
            continue
        raw, symbol = message["data"], message["data"]["s"]
        if not (symbol.endswith("FDUSD") and symbol.isalnum()) and symbol != "FDUSDUSDT":
            continue
        counts["relevant_book_messages"] += 1
        if symbol.endswith("FDUSD"):
            seen.add(symbol)
        update_book(raw, received, line_index, "spot", states, ids, counts)
    while cursor < len(grids):
        save_grid(grids[cursor])
        cursor += 1
    rows, summaries = [], []
    for symbol in sorted(seen):
        symbol_rows = []
        for decision, snapshot in zip(grids, snapshots, strict=True):
            row = {"date": day, "offset_minutes": offset, "symbol": symbol, "decision_ns": decision,
                   **snapshot.get(symbol, {"valid": False, "supply": False, "reason": "not_observed_before_cutoff"})}
            symbol_rows.append(row)
        rows.extend(symbol_rows)
        valid = sum(r["valid"] for r in symbol_rows)
        supply = sum(r["supply"] for r in symbol_rows)
        qualified = valid >= 40 and supply >= 30
        summaries.append({"date": day, "offset_minutes": offset, "symbol": symbol,
                          "grid_points": len(symbol_rows), "valid_grids": valid, "supply_grids": supply,
                          "selected": qualified,
                          "reason": "requires_native_queue_study" if qualified else "insufficient_valid_coverage" if valid < 40 else "insufficient_spread_depth_persistence"})
    return rows, summaries, fx_rows, dict(counts)
