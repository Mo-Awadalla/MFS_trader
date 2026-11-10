"""Conditional short-hold price/print feasibility; not an execution backtest."""

from bisect import bisect_right
from collections import Counter
from decimal import Decimal

from research.iex_native_prefix import decode_message, inflate_prefix, packets, segment, udp_payload


def extract_symbol(path, symbol, endpoint_ns):
    data, complete = inflate_prefix(path)
    stats, streams, rows = Counter(), {}, []
    previous, covered = -1, False
    target = symbol.encode().ljust(8, b" ")
    total_messages = 0
    for capture, frame in packets(data, stats, allow_partial=not complete):
        if capture < previous:
            raise ValueError("Source capture reversal")
        previous = capture
        if capture >= endpoint_ns:
            covered = True
            break
        key, seq, offset, length, sent, messages = segment(udp_payload(frame))
        if (seq, offset) != streams.get(key, (1, 0)):
            raise ValueError("Source sequence/offset discontinuity")
        streams[key] = (seq + len(messages), offset + length)
        total_messages += len(messages)
        for i, message in enumerate(messages):
            if message[10:18] == target:
                row = decode_message(message)
                row.update(capture_ns=capture, send_ns=sent, sequence=seq + i)
                rows.append(row)
    return rows, {"covered": covered, "last_capture_ns": previous,
                  "endpoint_ns": endpoint_ns, "messages_checked": total_messages,
                  "full_gzip_checksum_verified": complete, "full_session": False}


class Tape:
    def __init__(self, rows):
        self.by_type = {}
        self.times = {}
        for name in ("Q", "T", "H", "O", "B"):
            values = [r for r in rows if r["type"] == name]
            times = [r["event_ns"] for r in values]
            if any(b < a for a, b in zip(times, times[1:], strict=False)):
                raise ValueError("Nonmonotonic native event clock for selected message type")
            self.by_type[name], self.times[name] = values, times

    def prior(self, name, time):
        index = bisect_right(self.times[name], time) - 1
        return self.by_type[name][index] if index >= 0 else None

    def book(self, time, *, require_successor=False, order_boundary=False):
        q, h, o = (self.prior(name, time) for name in ("Q", "H", "O"))
        if not q or not h or not o or h["flags"] != 84 or o["flags"] != 78:
            return None
        if order_boundary and any(row["event_ns"] == time for row in (q, h, o)):
            return None
        if q["flags"] or not 0 < q["bid_price"] < q["ask_price"] or min(q["bid_size"], q["ask_size"]) <= 0:
            return None
        if require_successor and (not self.times["Q"] or self.times["Q"][-1] <= time):
            return None
        return q

    def halt_between(self, start, end):
        return any(start < r["event_ns"] <= end and r["flags"] != active
                   for name, active in (("H", 84), ("O", 78)) for r in self.by_type[name])


def trade_allocations(tape, side, limit, quantity, start, stop, model):
    remaining, allocations = quantity, []
    for row in tape.by_type["T"]:
        t = row["event_ns"]
        if not start <= t <= stop or row["flags"] & 0x58 or min(row["price"], row["size"]) <= 0:
            continue
        eligible = row["price"] <= limit if side == "buy" else row["price"] >= limit
        if model == "strict_trade_through":
            eligible = row["price"] < limit if side == "buy" else row["price"] > limit
        if not eligible:
            continue
        if t in (start, stop):
            return [], "ambiguous_trade_at_order_boundary"
        if not tape.book(t):
            return [], "invalid_state_during_used_trade"
        if any(b["trade_id"] == row["trade_id"] for b in tape.by_type["B"]):
            return [], "used_trade_broken_in_source_prefix"
        qty = min(remaining, row["size"])
        allocations.append({"quantity": qty, "trade": row})
        remaining -= qty
        if remaining == 0:
            break
    return allocations, None


def cash(orders, fee_factor=1, adverse_factor=1):
    gross = commission = adverse = levy = Decimal(0)
    balance = 0
    for order in orders:
        quantity, side = order["quantity"], order["side"]
        if quantity <= 0:
            raise ValueError("Cash ledger contains empty order")
        value = Decimal(quantity * order["price"]) / 10000
        direction = 1 if side == "sell" else -1
        gross += direction * value
        balance -= direction * quantity
        commission += max(Decimal(1), Decimal(quantity) * Decimal("0.005")) * fee_factor
        adverse += value * Decimal("0.0001") * adverse_factor
        if side == "sell":
            levy += (value * Decimal("0.00003") + Decimal(quantity) * Decimal("0.000166")) * fee_factor
    if balance != 0:
        raise ValueError("Open inventory cannot be assigned a realized net")
    return {"gross_usd": str(gross), "commission_usd": str(commission),
            "adverse_usd": str(adverse), "sell_levy_usd": str(levy),
            "net_usd": str(gross - commission - adverse - levy)}


def evaluate(event, tape, case, model):
    d, latency = event["decision_ns"], case["latency_ns"]
    times = {"entry_arrival": d + 50_000_000 + latency,
             "entry_cancel_arrival": d + 5_000_000_000 + latency,
             "entry_cancel_ack": d + 5_000_000_000 + 2 * latency,
             "target_arrival": d + 5_050_000_000 + 3 * latency,
             "target_cancel_arrival": d + 15_000_000_000 + latency,
             "target_cancel_ack": d + 15_000_000_000 + 2 * latency,
             "forced_arrival": d + 15_050_000_000 + 3 * latency}
    result = {"date": event["date"], "symbol": event["symbol"], "case": case["name"],
              "fill_model": model, "times_ns": times, "intended_quantity": event["quantity"],
              "orders": [], "net_usd": None, "actual_execution_verified": False,
              "classification_is_conditional_on_proxy": True}
    bid, ask = event["quote"]["bid_price"], event["quote"]["ask_price"]
    entry_book = tape.book(times["entry_arrival"], order_boundary=True)
    if entry_book is None or tape.halt_between(times["entry_arrival"], times["entry_cancel_arrival"]):
        return {**result, "outcome": "unknown_entry_state"}
    if entry_book["ask_price"] <= bid:
        entry_fills = [{"quantity": event["quantity"], "assumed_aggressive": True,
                        "event_ns": times["entry_arrival"], "reference_quote": entry_book}]
    else:
        entry_fills, error = trade_allocations(tape, "buy", bid, event["quantity"],
                                               times["entry_arrival"], times["entry_cancel_arrival"], model)
        if error:
            return {**result, "outcome": "unknown_entry_" + error}
    bought = sum(f["quantity"] for f in entry_fills)
    result.update(bought_quantity=bought, entry_allocations=entry_fills)
    if not bought:
        return {**result, "outcome": "conditional_no_entry", "net_usd": "0"}
    first_fill = min(f.get("event_ns", f.get("trade", {}).get("event_ns")) for f in entry_fills)
    orders = [{"side": "buy", "quantity": bought, "price": bid, "role": "entry"}]
    result["orders"] = orders
    if tape.halt_between(first_fill, times["forced_arrival"]):
        return {**result, "outcome": "unknown_halt_with_inventory"}
    exit_book = tape.book(times["target_arrival"], order_boundary=True)
    if exit_book is None:
        return {**result, "outcome": "unknown_target_state_with_inventory"}
    if exit_book["bid_price"] >= ask:
        target_fills = [{"quantity": bought, "assumed_aggressive": True,
                         "event_ns": times["target_arrival"], "reference_quote": exit_book}]
    else:
        target_fills, error = trade_allocations(tape, "sell", ask, bought, times["target_arrival"],
                                                times["target_cancel_arrival"], model)
        if error:
            return {**result, "outcome": "unknown_target_" + error}
    sold = sum(f["quantity"] for f in target_fills)
    result.update(target_quantity=sold, target_allocations=target_fills)
    if sold:
        orders.append({"side": "sell", "quantity": sold, "price": ask, "role": "target"})
    residual = bought - sold
    if residual:
        forced_book = tape.book(times["forced_arrival"], require_successor=True, order_boundary=True)
        if forced_book is None:
            return {**result, "outcome": "unknown_forced_exit_with_inventory", "residual_quantity": residual}
        result["forced_reference_quote"] = forced_book
        orders.append({"side": "sell", "quantity": residual, "price": forced_book["bid_price"], "role": "forced"})
        final_fill = times["forced_arrival"]
    else:
        final_fill = max(f.get("event_ns", f.get("trade", {}).get("event_ns")) for f in target_fills)
    exposure = final_fill - first_fill
    if not 0 <= exposure < 30_000_000_000:
        raise ValueError("Inventory duration violates strict HFT policy")
    result.update(cash(orders, case["fee_factor"], case["adverse_factor"]))
    result.update(outcome="conditional_priced", forced_quantity=residual, exposure_ns=exposure)
    return result
