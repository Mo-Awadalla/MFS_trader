"""Conditional SPY FOK/taker replay with explicit unknown inventory."""

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR
from decimal import Decimal as D

import numpy as np

from research.same_index_supply import Quotes


@dataclass
class Account:
    lower: D = D(10000)
    upper: D = D(10000)
    halted: bool = False

    def book(self, result):
        if result["status"].startswith("unknown"):
            self.halted = True
        elif result["status"] == "conditional_complete":
            self.lower += result["lower"]["net"]
            self.upper += result["upper"]["net"]


class Tape:
    def __init__(self, frame):
        self.signal = Quotes(frame)
        self.times = self.signal.times
        self.fields = self.signal.fields
        self.valid = np.ones(len(frame), dtype=bool)
        for field in ("bid_price", "ask_price", "bid_size", "ask_size"):
            self.valid &= np.isfinite(self.fields[field]) & (self.fields[field] > 0)
        self.valid &= (self.fields["bid_price"] < self.fields["ask_price"]) & (self.fields["ask_price"] < 1e7)
        self.valid &= self.fields["conditions"] == '["R"]'
        self.valid &= (self.fields["bid_exchange"] != "") & (self.fields["ask_exchange"] != "")


def plan(tape, event, rule):
    cutoff = int(event["signal_cutoff_ns"])
    i = int(tape.signal.indices(cutoff))
    quote = tape.signal.row(i)
    result = {"eligible": False, "signal_index": i, "signal_cutoff_ns": cutoff}
    if quote is None:
        return {**result, "reason": "missing_invalid_or_tied_signal"}
    long = (event["return_bps"] > 0) == (rule == "follow_impulse")
    bid, ask = D(str(quote["bid_price"])), D(str(quote["ask_price"]))
    spread = (ask-bid)*20000/(bid+ask)
    entry = ask if long else bid
    depth = D(str(quote["ask_size" if long else "bid_size"]))
    quantity = int(min(D(10000)/(entry*D("1.01")), depth/10))
    limit = (entry*(D("1.001") if long else D("0.999"))/D("0.01")).to_integral_value(rounding=ROUND_FLOOR if long else ROUND_CEILING)*D("0.01")
    # Full notional plus both orders' maximum frozen fee, adverse and borrow
    # assumptions. The strategy never spends hypothetical short-sale proceeds.
    mark = max(ask, limit)
    reserve = quantity*mark + 4*max(D(1), quantity*D("0.0075")) + 2*(quantity*mark*D("0.00003")+quantity*D("0.0002")) + quantity*mark*D("0.0004")
    if not long:
        reserve += quantity*mark*D("0.1")/365
    result.update(long=long, quantity=quantity, limit=limit, capital_reserved=reserve,
                  signal_quote_ns=int(tape.times[i]), signal_bid=bid, signal_ask=ask,
                  signal_bid_size=quote["bid_size"], signal_ask_size=quote["ask_size"], spread_bps=spread)
    if spread > 20:
        return {**result, "reason": "spread_above_20bp"}
    if quantity*entry < 100:
        return {**result, "reason": "insufficient_known_entry_size"}
    return {**result, "eligible": True, "reason": "eligible"}


def compatible(tape, arrival, radius, long_side):
    left = int(np.searchsorted(tape.times, arrival-radius, side="left"))-1
    right = int(np.searchsorted(tape.times, arrival+radius, side="right"))
    result = {"known": False, "arrival_ns": arrival, "radius_ns": radius}
    if left < 0 or right >= len(tape.times):
        return {**result, "reason": "unbracketed_quote_window"}
    left = int(np.searchsorted(tape.times, tape.times[left], side="left"))
    if not tape.valid[left:right].all():
        return {**result, "reason": "invalid_quote_in_execution_interval", "first_index": left, "stop_index": right}
    side = "ask" if long_side else "bid"
    prices = [D(str(p)) for p in tape.fields[side+"_price"][left:right]]
    sizes = [D(str(q)) for q in tape.fields[side+"_size"][left:right]]
    return {**result, "known": True, "reason": "conditional_sip_envelope", "first_index": left, "stop_index": right,
            "successor_ns": int(tape.times[right]), "prices": prices, "sizes": sizes,
            "price_lower": min(prices), "price_upper": max(prices), "minimum_touch_shares": min(sizes)}


def fok(quotes, quantity, long, limit):
    if not quotes["known"]:
        return "unknown"
    crosses = [(p <= limit if long else p >= limit) for p in quotes["prices"]]
    if not any(crosses):
        return "no_fill"
    if all(crosses) and min(quotes["sizes"]) >= quantity:
        return "filled"
    return "unknown"


def cash(quantity, long, entry, exit_price, scenario):
    q, start, end = D(quantity), D(entry), D(exit_price)
    gross = q*(end-start)*(1 if long else -1)
    commission = 2*max(D(1), q*D("0.0075"))*scenario["fee_multiple"]
    sell_price = end if long else start
    sell = (q*sell_price*D("0.00003")+q*D("0.0002"))*scenario["fee_multiple"]
    adverse = q*(start+end)*D("0.0001")*scenario["adverse_multiple"]
    borrow = D(0) if long else q*max(start, end)*D("0.05")/365*scenario["fee_multiple"]
    return {"entry_price": start, "exit_price": end, "gross": gross, "commissions": commission,
            "sell_charges": sell, "adverse": adverse, "borrow": borrow, "net": gross-commission-sell-adverse-borrow}


def compact(quotes):
    return {k: v for k, v in quotes.items() if k not in ("prices", "sizes")}


def replay(tape, event, intent, scenario):
    effective = int(event["decision_ns"])+(scenario["feed_ms"]-100)*1_000_000
    entry = effective+50_000_000+scenario["outbound_ms"]*1_000_000
    exit_time = entry+scenario["ack_ms"]*1_000_000+15_000_000_000+50_000_000+scenario["outbound_ms"]*1_000_000
    radius = scenario["clock_ms"]*1_000_000
    result = {"submitted": True, "status": "unknown_entry", "quantity": intent["quantity"], "long": intent["long"],
              "entry_arrival_ns": entry, "exit_arrival_ns": exit_time, "inventory_schedule_upper_ns": exit_time-entry+2*radius,
              "potential_inventory_quantity": [0, intent["quantity"]]}
    assert result["inventory_schedule_upper_ns"] <= 30_000_000_000
    entry_quotes = compatible(tape, entry, radius, intent["long"])
    exit_quotes = compatible(tape, exit_time, radius, not intent["long"])
    result.update(entry_quotes=compact(entry_quotes), exit_quotes=compact(exit_quotes))
    outcome = fok(entry_quotes, intent["quantity"], intent["long"], intent["limit"])
    result["entry_outcome"] = outcome
    if outcome == "no_fill":
        return {**result, "status": "no_fill", "potential_inventory_quantity": [0, 0]}
    if outcome == "unknown":
        return result
    if not exit_quotes["known"] or exit_quotes["minimum_touch_shares"] < intent["quantity"]:
        return {**result, "status": "unknown_exit", "potential_inventory_quantity": [0, intent["quantity"]]}
    values = [cash(intent["quantity"], intent["long"], start, end, scenario)
              for start in (entry_quotes["price_lower"], entry_quotes["price_upper"])
              for end in (exit_quotes["price_lower"], exit_quotes["price_upper"])]
    return {**result, "status": "conditional_complete", "potential_inventory_quantity": [0, 0],
            "lower": min(values, key=lambda r: r["net"]), "upper": max(values, key=lambda r: r["net"])}
