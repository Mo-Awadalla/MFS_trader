"""Causal three-book conversion budgets, not simulated or actual executions."""

import json
from collections import Counter
from decimal import Decimal as D

from research.spot_perp_supply import NS, capture_ns, midnight_ns, update_book, valid_book

BRIDGES = ("BTC", "ETH", "BNB")


def route_legs(books, direction):
    direct, cross, bridge = books
    if direction == "base_first":
        return ((direct, "buy"), (cross, "sell"), (bridge, "sell"))
    assert direction == "bridge_first"
    return ((bridge, "buy"), (cross, "buy"), (direct, "sell"))


def cash_cycle(books, direction, fee=D("0.001"), adverse=D("0.0001")):
    cash, depth_ok = D(200), True
    legs = []
    for quote, side in route_legs(books, direction):
        if side == "buy":
            price = D(quote["ask"]) * (1 + adverse)
            quantity = cash / price
            touch = D(quote["ask_quantity"])
            output = quantity * (1 - fee)
        else:
            price = D(quote["bid"]) * (1 - adverse)
            quantity = cash
            touch = D(quote["bid_quantity"])
            output = quantity * price * (1 - fee)
        depth_ok &= quantity <= touch / 10
        legs.append({"side": side, "input": str(cash), "gross_base_quantity": str(quantity),
                     "adverse_price": str(price), "output_after_received_asset_fee": str(output)})
        cash = output
    return cash, depth_ok, legs


def evaluate(books, decision, direction):
    for index, book in enumerate(books):
        failure = valid_book(book, decision)
        if failure:
            return {"valid_books": False, "supply": False, "reason": f"leg{index}_{failure}"}
    final, depth, _ = cash_cycle(books, direction)
    double_fee, _, _ = cash_cycle(books, direction, fee=D("0.002"))
    double_adverse, _, _ = cash_cycle(books, direction, adverse=D("0.0002"))
    gross, _, _ = cash_cycle(books, direction, fee=D(0), adverse=D(0))
    price_gate = final > D("200.04")
    return {"valid_books": True, "supply": depth and price_gate,
            "depth_gate": depth, "price_gate": price_gate,
            "gross_budget_bps": str((gross / 200 - 1) * 10000),
            "base_final_usdt": str(final), "base_budget_bps": str((final / 200 - 1) * 10000),
            "double_fee_budget_bps": str((double_fee / 200 - 1) * 10000),
            "double_adverse_budget_bps": str((double_adverse / 200 - 1) * 10000),
            "reason": "requires_sequential_execution_study" if depth and price_gate else "depth_gate" if not depth else "net_budget_gate"}


def sample(lines, day, offset):
    midnight = midnight_ns(day)
    start = midnight + offset * 60 * NS
    grids = [start + i * NS for i in range(10, 60)]
    states, ids, seen, snapshots, counts = {}, {}, set(), [], Counter()
    last, cursor = start - 1, 0
    for number, line in enumerate(lines):
        if not line.strip():
            counts["disconnects"] += 1
            states.clear()
            ids.clear()
            continue
        stamp, payload = line.rstrip("\r\n").split(" ", 1)
        received = capture_ns(stamp, midnight)
        assert stamp[:10] == day and start <= received < start + 60 * NS and received >= last
        last = received
        while cursor < 50 and grids[cursor] - 250_000_000 <= received:
            snapshots.append(dict(states))
            cursor += 1
        counts["native_messages"] += 1
        message = json.loads(payload)
        if not message.get("stream", "").endswith("@bookTicker"):
            continue
        raw = message["data"]
        symbol = raw["s"]
        if not symbol.isalnum() or not symbol.endswith(("USDT", *BRIDGES)):
            continue
        counts["relevant_book_messages"] += 1
        seen.add(symbol)
        update_book(raw, received, number, "spot", states, ids, counts)
    while cursor < 50:
        snapshots.append(dict(states))
        cursor += 1
    routes = []
    for bridge in BRIDGES:
        if bridge + "USDT" not in seen:
            continue
        for cross in sorted(s for s in seen if s.endswith(bridge)):
            base = cross[:-len(bridge)]
            if base and base not in ("USDT", bridge) and base + "USDT" in seen:
                routes.append((base, bridge, (base + "USDT", cross, bridge + "USDT")))
    rows, quotes = [], []
    needed = sorted({s for _, _, path in routes for s in path})
    for index, snapshot in enumerate(snapshots):
        for symbol in needed:
            quotes.append({"symbol": symbol, "decision_ns": grids[index], **snapshot.get(symbol, {})})
    for base, bridge, path in routes:
        for direction in ("base_first", "bridge_first"):
            previous, last_selection = False, start - 30 * NS
            for decision, snapshot in zip(grids, snapshots, strict=True):
                result = evaluate([snapshot.get(s) for s in path], decision, direction)
                confirmed = bool(previous and result["supply"])
                selected = confirmed and decision - last_selection >= 30 * NS
                if selected:
                    last_selection = decision
                rows.append({"date": day, "offset_minutes": offset, "base": base, "bridge": bridge,
                             "direction": direction, "decision_ns": decision,
                             **result, "confirmed": confirmed, "selected": selected})
                previous = result["supply"]
    return rows, quotes, dict(counts), len(routes)
