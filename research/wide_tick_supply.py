"""Causal native spread/liquidity screening; no fill or return inference."""

import calendar
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal


def stamp_ns(stamp, midnight_ns):
    seconds = int(stamp[11:13])*3600 + int(stamp[14:16])*60 + int(stamp[17:19])
    fraction = stamp[19:].removesuffix("Z")
    return midnight_ns + seconds*1_000_000_000 + (int(fraction[1:].ljust(9, "0")) if fraction else 0)


def book_state(raw, received, line_index, sequence_ok):
    return {"receive_ns": received, "transaction_ns": int(raw["T"])*1_000_000,
            "publication_ns": int(raw["E"])*1_000_000, "source_line": line_index,
            "update_id": int(raw["u"]), "bid": raw["b"], "ask": raw["a"],
            "bid_quantity": raw["B"], "ask_quantity": raw["A"], "sequence_ok": sequence_ok}


def evaluate(state, decision):
    row = {"decision_ns": decision, "valid": False, "supply": False, "reason": "no_book_state"}
    if state is None:
        return row
    row.update(state)
    if not state["sequence_ok"]:
        row["reason"] = "non_monotone_or_conflicting_book_id"
        return row
    numbers = [float(state[key]) for key in ["bid", "ask", "bid_quantity", "ask_quantity"]]
    if not all(math.isfinite(x) and x > 0 for x in numbers) or numbers[0] >= numbers[1]:
        row["reason"] = "invalid_book_values"
        return row
    receipt, transaction, publication = state["receive_ns"], state["transaction_ns"], state["publication_ns"]
    if not (0 < decision-receipt <= 5_000_000_000 and 0 < decision-transaction <= 5_000_000_000
            and transaction <= receipt+1_000_000 and publication <= receipt+1_000_000
            and transaction <= publication+1_000_000):
        row["reason"] = "stale_or_inconsistent_book_clock"
        return row
    bid, ask, bq, aq = [Decimal(state[key]) for key in ["bid", "ask", "bid_quantity", "ask_quantity"]]
    spread = (ask-bid)*20000/(bid+ask)
    bid_value, ask_value = bid*bq, ask*aq
    supply = Decimal(12) <= spread <= Decimal(100) and min(bid_value, ask_value) >= Decimal(2000)
    row.update(valid=True, supply=supply, reason="supply" if supply else "spread_or_depth_below_gate",
               spread_bps=float(spread), bid_notional=float(bid_value), ask_notional=float(ask_value))
    return row


def summarize(rows, symbols, flows):
    by_symbol = defaultdict(list)
    for row in rows:
        by_symbol[row["symbol"]].append(row)
    output = []
    for symbol in sorted(symbols):
        states, flow = by_symbol[symbol], flows[symbol]
        valid = sum(r["valid"] for r in states)
        supply = sum(r["supply"] for r in states)
        enough_flow = flow["buy_count"] >= 10 and flow["sell_count"] >= 10 and min(flow["buy_notional"], flow["sell_notional"]) >= 5000
        qualified = valid >= 40 and supply >= 30 and enough_flow
        row = {"symbol": symbol, "grid_points": len(states), "valid_grid_points": valid, "supply_grid_points": supply,
               **dict(flow), "qualified": qualified, "selected": False,
               "minimum_side_flow": min(flow["buy_notional"], flow["sell_notional"])}
        row["reason"] = ("qualified" if qualified else "insufficient_valid_book_coverage" if valid < 40
                         else "insufficient_spread_and_depth_persistence" if supply < 30 else "insufficient_two_sided_executions")
        output.append(row)
    ranked = sorted([r for r in output if r["qualified"]], key=lambda r: (-r["minimum_side_flow"], r["symbol"]))
    for rank, row in enumerate(ranked, 1):
        row["selection_rank"] = rank
        row["selected"] = rank <= 4
    return output


def screen(lines, day):
    midnight = calendar.timegm(datetime.strptime(day, "%Y-%m-%d").timetuple())*1_000_000_000
    start = midnight+9*3600*1_000_000_000
    grid = [start+second*1_000_000_000 for second in range(10, 60)]
    end = start+60_000_000_000
    states, seen, ids, trades_seen = {}, set(), {}, defaultdict(dict)
    flows = defaultdict(lambda: {"buy_count": 0, "sell_count": 0, "buy_notional": 0.0, "sell_notional": 0.0})
    rows, cursor, previous = [], 0, -1
    diagnostics = Counter()

    def append_grid(decision):
        for symbol in sorted(seen):
            rows.append({"symbol": symbol, **evaluate(states.get(symbol), decision)})

    for line_index, line in enumerate(lines):
        if not line.strip():
            states.clear()
            ids.clear()
            diagnostics["disconnects"] += 1
            continue
        stamp, payload = line.rstrip("\n").split(" ", 1)
        assert stamp[:10] == day
        received = stamp_ns(stamp, midnight)
        if received < previous:
            raise ValueError("Native capture order regressed")
        previous = received
        if received < start or received >= end:
            raise ValueError("Source record outside frozen capture minute")
        while cursor < len(grid) and grid[cursor] <= received:
            append_grid(grid[cursor])
            cursor += 1
        event = json.loads(payload)["data"]
        kind, symbol = event["e"], event["s"]
        diagnostics["native_messages"] += 1
        if not symbol.endswith("USDT"):
            diagnostics["excluded_non_usdt"] += 1
            continue
        seen.add(symbol)
        if kind == "bookTicker":
            diagnostics["book_messages"] += 1
            identifier = int(event["u"])
            signature = tuple(event[k] for k in ["b", "B", "a", "A", "T"])
            old = ids.get(symbol)
            ok = old is None or identifier > old[0] or (identifier == old[0] and signature == old[1] and old[2])
            if old is None or identifier >= old[0]:
                ids[symbol] = (identifier, signature, ok)
            else:
                ids[symbol] = (old[0], old[1], False)
            if not ok:
                diagnostics["non_monotone_or_conflicting_book_id"] += 1
            states[symbol] = book_state(event, received, line_index, ok)
        elif kind == "trade":
            diagnostics["trade_messages"] += 1
            signature = tuple(event[k] for k in ["p", "q", "T", "m"]) + (event.get("X"),)
            identifier = int(event["t"])
            if identifier in trades_seen[symbol]:
                if trades_seen[symbol][identifier] != signature:
                    raise ValueError("Conflicting native trade ID")
                diagnostics["duplicate_trades"] += 1
                continue
            trades_seen[symbol][identifier] = signature
            if event.get("X") != "MARKET":
                diagnostics["excluded_off_book_or_unknown_type"] += 1
                continue
            price, quantity = float(event["p"]), float(event["q"])
            match, publication = int(event["T"])*1_000_000, int(event["E"])*1_000_000
            if not (math.isfinite(price) and math.isfinite(quantity) and price > 0 and quantity > 0
                    and isinstance(event["m"], bool) and -1_000_000 <= received-match <= 5_000_000_000
                    and -1_000_000 <= received-publication <= 5_000_000_000 and match <= publication+1_000_000):
                diagnostics["excluded_invalid_trade"] += 1
                continue
            if received >= grid[0]:
                side = "sell" if event["m"] else "buy"
                flows[symbol][side+"_count"] += 1
                flows[symbol][side+"_notional"] += price*quantity
        else:
            raise ValueError("Unexpected native event type")
    while cursor < len(grid):
        append_grid(grid[cursor])
        cursor += 1
    present = {(r["symbol"], r["decision_ns"]) for r in rows}
    for symbol in sorted(seen):
        for decision in grid:
            if (symbol, decision) not in present:
                rows.append({"symbol": symbol, **evaluate(None, decision)})
    rows.sort(key=lambda r: (r["decision_ns"], r["symbol"]))
    return rows, summarize(rows, seen, flows), dict(diagnostics)
