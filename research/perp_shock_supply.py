"""Native causal quote displacement; trade confirmation and returns are separate."""

import json
import math
from collections import Counter
from decimal import Decimal as D

from research.spot_perp_supply import NS, capture_ns, midnight_ns, update_book

STEP = 250_000_000


def quote_gate(state, cutoff):
    if state is None:
        return "missing_book"
    if not state["sequence_ok"]:
        return "conflicting_or_regressing_id"
    if not state["transaction_order_ok"]:
        return "regressing_matching_clock"
    values = [float(state[k]) for k in ("bid", "ask", "bid_quantity", "ask_quantity")]
    if not all(math.isfinite(x) and x > 0 for x in values) or values[0] >= values[1]:
        return "invalid_book"
    capture, transaction, publication = [state[k] for k in ("receive_ns", "transaction_ns", "publication_ns")]
    if not 0 < cutoff - capture <= STEP:
        return "capture_freshness_gate"
    if not (0 < cutoff - transaction <= STEP and 0 < cutoff - publication <= STEP
            and max(transaction, publication) <= capture + 1_000_000
            and transaction <= publication + 1_000_000):
        return "native_clock_gate"
    return None


def evaluate(anchor, current, decision):
    row = {"valid_endpoints": False, "supply": False, "direction": 0}
    for name, state, cutoff in (("anchor", anchor, decision - NS - STEP), ("current", current, decision - STEP)):
        error = quote_gate(state, cutoff)
        if error:
            return {**row, "reason": name + "_" + error}
    if anchor["epoch"] != current["epoch"]:
        return {**row, "reason": "disconnect_between_endpoints"}
    b0, a0, b1, a1 = [D(state[k]) for state in (anchor, current) for k in ("bid", "ask")]
    bid_return, ask_return = (b1 / b0 - 1) * 10000, (a1 / a0 - 1) * 10000
    spread0, spread1 = (a0 - b0) / (a0 + b0) * 20000, (a1 - b1) / (a1 + b1) * 20000
    minimum = min(D(state[price]) * D(state[size]) for state in (anchor, current)
                  for price, size in (("bid", "bid_quantity"), ("ask", "ask_quantity")))
    direction = 1 if bid_return >= 30 and ask_return >= 30 else -1 if bid_return <= -30 and ask_return <= -30 else 0
    spread_ok, depth_ok = max(spread0, spread1) <= 10, minimum >= 2000
    supply = bool(direction and spread_ok and depth_ok)
    return {**row, "valid_endpoints": True, "supply": supply, "direction": direction,
            "bid_return_bps": str(bid_return), "ask_return_bps": str(ask_return),
            "anchor_spread_bps": str(spread0), "current_spread_bps": str(spread1),
            "minimum_touch_usdt": str(minimum), "spread_gate": spread_ok, "depth_gate": depth_ok,
            "reason": "requires_native_trade_confirmation" if supply else "displacement_gate" if not direction else "spread_gate" if not spread_ok else "depth_gate"}


def sample(lines, day, offset):
    midnight = midnight_ns(day)
    start = midnight + offset * 60 * NS
    grids = list(range(start + NS, start + 59 * NS, STEP))
    states, ids, high_water, seen, snapshots = {}, {}, {}, set(), []
    counts, previous, cursor, epoch = Counter(), start - 1, 0, 0
    for number, line in enumerate(lines):
        if not line.strip():
            counts["disconnects"] += 1
            states.clear()
            ids.clear()
            high_water.clear()
            epoch += 1
            continue
        stamp, payload = line.rstrip("\r\n").split(" ", 1)
        received = capture_ns(stamp, midnight)
        assert stamp[:10] == day and start <= received < start + 60 * NS and received >= previous
        previous = received
        while cursor < len(grids) and grids[cursor] - STEP <= received:
            snapshots.append(dict(states))
            cursor += 1
        counts["native_messages"] += 1
        message = json.loads(payload)
        if not message.get("stream", "").endswith("@bookTicker"):
            continue
        counts["book_messages"] += 1
        raw = message["data"]
        symbol = raw["s"]
        if not symbol.endswith("USDT") or not symbol.isalnum():
            continue
        seen.add(symbol)
        counts["universe_book_messages"] += 1
        update_book(raw, received, number, "perpetual", states, ids, counts)
        state = states[symbol]
        if state["source_line"] != number:
            continue
        transaction = state["transaction_ns"]
        ordered = transaction >= high_water.get(symbol, transaction)
        if state["sequence_ok"]:
            high_water[symbol] = max(transaction, high_water.get(symbol, transaction))
            if not ordered:
                counts["regressing_matching_clocks"] += 1
        state.update(transaction_order_ok=ordered, epoch=epoch)
    while cursor < len(grids):
        snapshots.append(dict(states))
        cursor += 1
    rows, quotes = [], []
    for symbol in sorted(seen):
        last_selected = start - 30 * NS
        for index, (decision, snapshot) in enumerate(zip(grids, snapshots, strict=True)):
            current = snapshot.get(symbol)
            quotes.append({"date": day, "offset_minutes": offset, "symbol": symbol,
                           "decision_ns": decision, **(current or {})})
            if index < 4:
                continue
            anchor = snapshots[index - 4].get(symbol)
            result = evaluate(anchor, current, decision)
            selected = result["supply"] and decision - last_selected >= 30 * NS
            if selected:
                last_selected = decision
            rows.append({"date": day, "offset_minutes": offset, "symbol": symbol,
                         "decision_ns": decision, **result, "selected": selected})
    return rows, quotes, dict(counts), len(seen)
