"""Conditional displayed-queue replay, with explicit unresolved execution states."""

from dataclasses import dataclass
from decimal import Decimal as D
from itertools import groupby

from research.nasdaq_mbo_book import Book

NS = 1000000000
PROCESSING = 50000
USD = D(1000000000)


@dataclass(frozen=True)
class Case:
    name: str
    latency_ns: int
    clock_ns: int = 0
    fee_multiplier: int = 1
    adverse_multiplier: int = 1


CASES = (
    Case("base_1ms", 1000000), Case("delay_5ms", 5000000), Case("delay_25ms", 25000000),
    Case("delay_250ms", 250000000), Case("fees_2x", 1000000, fee_multiplier=2),
    Case("adverse_2x", 1000000, adverse_multiplier=2),
    Case("clock_minus_1ms", 1000000, clock_ns=-1000000), Case("clock_plus_1ms", 1000000, clock_ns=1000000),
)


class Unknown(Exception):
    pass


class Passive:
    def __init__(self, name, side, price, quantity, book, arrival_ns, ledger):
        bid, ask = book.bbo()
        if bid[0] is None or ask[0] is None or not 0 < bid[0] < ask[0]:
            raise Unknown("invalid_book_at_" + name)
        if (side == "B" and price >= ask[0]) or (side == "A" and price <= bid[0]):
            raise Unknown("marketable_passive_" + name)
        self.name, self.side, self.price, self.quantity = name, side, price, quantity
        self.remaining, self.active, self.fills = quantity, True, []
        self.ahead = {oid: order.size for oid, order in book.orders.items() if (order.side, order.price) == (side, price)}
        self.ledger = ledger
        ledger.append({"kind": "posted", "order": name, "arrival_ns": arrival_ns,
                       "side": side, "price_int": price, "requested_quantity": quantity,
                       "initial_ahead": dict(self.ahead), "bid": bid, "ask": ask})

    def reaches(self, price):
        return price <= self.price if self.side == "B" else price >= self.price

    def on_record(self, record, book):
        if not self.active or self.remaining == 0:
            return
        action, oid = record["action"], record["order_id"]
        if action == "R":
            raise Unknown("book_reset_while_" + self.name + "_active")
        if action == "F" and record["side"] == self.side:
            resting = book.orders[oid]
            assert 0 < record["size"] <= resting.size
            if not (self.reaches(resting.price) or self.reaches(record["price"])):
                return
            if record["price"] != resting.price:
                raise Unknown("off_display_execution_near_" + self.name)
            if not self.reaches(record["price"]):
                return
            if oid in self.ahead:
                self.ledger.append({"kind": "fill_ahead", "order": self.name, "source_row": record["source_row"],
                                    "order_id": oid, "quantity": record["size"], "ahead_before": sum(self.ahead.values())})
                return  # Its following Cancel changes displayed state exactly once.
            best = book.best(self.side)[0]
            if self.ahead or (best is not None and ((self.side == "B" and best > self.price) or (self.side == "A" and best < self.price))):
                raise Unknown("unresolved_priority_at_" + self.name)
            quantity = min(self.remaining, record["size"])
            fill = {"order": self.name, "side": self.side, "price_int": self.price, "quantity": quantity,
                    "event_ns": record["ts_event"], "source_row": record["source_row"],
                    "matched_historical_order_id": oid, "historical_fill_price_int": record["price"]}
            self.fills.append(fill)
            self.remaining -= quantity
            self.ledger.append({"kind": "conditional_fill", **fill})
        elif action == "C" and oid in self.ahead:
            before = self.ahead[oid]
            assert record["size"] <= before
            after = before - record["size"]
            if after:
                self.ahead[oid] = after
            else:
                del self.ahead[oid]
            self.ledger.append({"kind": "queue_cancel", "order": self.name, "source_row": record["source_row"],
                                "order_id": oid, "quantity": record["size"], "ahead_after": sum(self.ahead.values())})
        elif action == "M" and oid in self.ahead:
            before = book.orders[oid]
            if before.price != record["price"] or before.size < record["size"]:
                del self.ahead[oid]
            else:
                self.ahead[oid] = record["size"]


def schedule(decision_ns, case):
    delay, shift = case.latency_ns, case.clock_ns
    return [
        (decision_ns + PROCESSING + delay + shift, "post_bid"),
        (decision_ns + NS + PROCESSING + delay + shift, "cancel_bid"),
        (decision_ns + NS + 2 * PROCESSING + 3 * delay + shift, "post_ask"),
        (decision_ns + 5 * NS + PROCESSING + delay + shift, "cancel_ask"),
        (decision_ns + 5 * NS + 2 * PROCESSING + 3 * delay + shift, "force_exit"),
    ]


def cash(fills, case):
    orders = {}
    entry, sale, sold = D(0), D(0), 0
    for fill in fills:
        value = D(fill["quantity"]) * D(fill["price_int"]) / USD
        orders[fill["order"]] = orders.get(fill["order"], 0) + fill["quantity"]
        if fill["side"] == "B":
            entry += value
        else:
            sale += value
            sold += fill["quantity"]
    commissions = sum((max(D(1), D("0.005") * q) * case.fee_multiplier for q in orders.values()), D(0))
    adverse = (entry + sale) * D("0.0001") * case.adverse_multiplier
    sales_charges = sale * D("0.00003") + D(sold) * D("0.000166")
    return {"entry_notional": str(entry), "sale_notional": str(sale), "gross": str(sale - entry),
            "commissions": str(commissions), "adverse": str(adverse), "sales_charges": str(sales_charges),
            "net": str(sale - entry - commissions - adverse - sales_charges)}


def simulate(records, event, case):
    """No fill from quote touches, cancellations or anonymous/non-displayed trades."""
    book, ledger, orders, fills = Book(), [], {}, []
    actions = schedule(event["decision_ns"], case)
    action_index, previous_source, previous_event = 0, None, None
    bought, sold, unknown, context = 0, 0, None, None

    def fire(time, kind, next_record, equal_clock):
        nonlocal bought, sold, context
        context = {"scheduled_action": kind, "event_ns": time, "next_source_row": next_record["source_row"]}
        bought = sum(f["quantity"] for f in fills if f["side"] == "B")
        sold = sum(f["quantity"] for f in fills if f["side"] == "A")
        relevant = kind == "post_bid" or (kind == "cancel_bid" and "bid" in orders and orders["bid"].remaining > 0)
        relevant |= (kind in ("post_ask", "cancel_ask", "force_exit") and bought > sold)
        ledger.append({"kind": "scheduled_action", "action": kind, "event_ns": time,
                       "source_before": previous_source, "source_after": next_record["source_row"],
                       "native_before": previous_event, "native_after": next_record["ts_event"], "relevant": relevant})
        if equal_clock and relevant:
            raise Unknown("equal_native_clock_at_" + kind)
        if kind == "post_bid":
            orders["bid"] = Passive("bid", "B", event["bid_price_int"], event["quantity"], book, time, ledger)
        elif kind == "cancel_bid":
            orders["bid"].active = False
        elif kind == "post_ask" and bought > sold:
            orders["ask"] = Passive("ask", "A", event["ask_price_int"], bought - sold, book, time, ledger)
        elif kind == "cancel_ask" and "ask" in orders:
            orders["ask"].active = False
        elif kind == "force_exit" and bought > sold:
            bid, ask = book.bbo()
            if bid[0] is None or ask[0] is None or not 0 < bid[0] < ask[0]:
                raise Unknown("invalid_forced_exit_book")
            floor = event["bid_price_int"] // 10000000 * 98 // 100 * 10000000
            needed = bought - sold
            levels = sorted(((p, q, n) for p, (q, n) in book.levels["B"].items() if p >= floor), reverse=True)
            ledger.append({"kind": "forced_exit_depth", "event_ns": time, "floor_int": floor, "levels": levels})
            for price, available, _ in levels:
                quantity = min(needed, available)
                fill = {"order": "force", "side": "A", "price_int": price, "quantity": quantity,
                        "event_ns": time, "source_row": previous_source}
                fills.append(fill)
                ledger.append({"kind": "conditional_ioc_fill", **fill})
                needed -= quantity
                if needed == 0:
                    break
            if needed:
                raise Unknown("insufficient_forced_exit_depth_inside_collar")

    try:
        for time, group in groupby(records, key=lambda r: r["ts_event"]):
            group = list(group)
            while action_index < len(actions) and actions[action_index][0] <= time:
                action_time, kind = actions[action_index]
                fire(action_time, kind, group[0], action_time == time)
                action_index += 1
            if action_index == len(actions):
                break
            for record in group:
                context = {key: record[key] for key in ("source_row", "ts_event", "action", "side", "order_id", "price", "size")}
                for order in orders.values():
                    old_count = len(order.fills)
                    order.on_record(record, book)
                    fills.extend(order.fills[old_count:])
                book.apply(record["action"], record["side"], record["order_id"], record["price"], record["size"], record["source_row"])
                previous_source, previous_event = record["source_row"], record["ts_event"]
        if action_index != len(actions):
            raise Unknown("source_ended_before_order_lifecycle")
    except Unknown as exc:
        unknown = str(exc)
        ledger.append({"kind": "unknown", "reason": unknown, "context": context})
    bought = sum(f["quantity"] for f in fills if f["side"] == "B")
    sold = sum(f["quantity"] for f in fills if f["side"] == "A")
    if not unknown and bought != sold:
        unknown = "unflattened_inventory"
    status = "unknown" if unknown else ("no_entry_fill" if bought == 0 else "flat")
    known_cash = cash(fills, case)
    holding = None
    if bought and sold and not unknown:
        holding = max(f["event_ns"] for f in fills if f["side"] == "A") - min(f["event_ns"] for f in fills if f["side"] == "B")
        assert 0 <= holding < 30 * NS
    return {"case": case.name, "status": status, "unknown_reason": unknown, "requested_quantity": event["quantity"],
            "bought": bought, "sold": sold, "residual_known_inventory": bought - sold,
            "max_inventory_holding_ns": holding, "fills": fills, "cash": known_cash if not unknown else None,
            "known_cash_component": known_cash, "ledger": ledger,
            "conditional_on_unchanged_historical_flow_and_posting": True, "actual_execution_verified": False}
