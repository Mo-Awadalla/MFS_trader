"""Conditional single-perpetual FOK replay on native matching timestamps."""

import bisect
import json
from collections import Counter
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR
from decimal import Decimal as D

from research.futures_response_hft import fok
from research.spot_perp_supply import capture_ns, midnight_ns

NS = 1_000_000_000
TICK = D("0.0001")


@dataclass
class Tape:
    books: list
    marks: list
    disconnects: list
    physical_ordered: bool = True


def parse(lines, day):
    books, marks, disconnects, counts = [], [], [], Counter()
    previous_capture = -1
    previous_uid, previous_fingerprint = -1, None
    previous_t = -1
    physical_ordered, pending_disconnect = True, None
    midnight = midnight_ns(day)
    for line_number, line in enumerate(lines):
        if not line.strip():
            counts["disconnects"] += 1
            pending_disconnect = previous_t
            marks.append({"receive_ns": previous_capture + 1, "valid": False, "source_line": line_number})
            previous_uid, previous_fingerprint = -1, None
            continue
        stamp, payload = line.rstrip("\r\n").split(" ", 1)
        received = capture_ns(stamp, midnight)
        assert stamp[:10] == day and midnight <= received < midnight + 60 * NS
        assert received >= previous_capture
        previous_capture = received
        message = json.loads(payload)
        data, stream = message["data"], message["stream"].split("@", 1)[1]
        assert data["s"] == "ENAUSDT"
        counts["native_messages"] += 1
        if stream.startswith("markPrice"):
            counts["mark_messages"] += 1
            event = int(data["E"]) * 1_000_000
            marks.append({"receive_ns": received, "publication_ns": event,
                          "next_funding_ns": int(data["T"]) * 1_000_000,
                          "mark_price": D(data["p"]), "source_line": line_number,
                          "valid": event <= received + 1_000_000 and D(data["p"]).is_finite() and D(data["p"]) > 0})
            continue
        assert stream == "bookTicker"
        counts["book_messages"] += 1
        uid, t, e = int(data["u"]), int(data["T"]) * 1_000_000, int(data["E"]) * 1_000_000
        fingerprint = tuple(str(data[k]) for k in ("b", "B", "a", "A", "T", "E"))
        if uid == previous_uid and fingerprint == previous_fingerprint:
            counts["exact_duplicate_books"] += 1
            continue
        sequence_ok = uid > previous_uid
        if sequence_ok:
            previous_uid, previous_fingerprint = uid, fingerprint
        else:
            counts["conflicting_or_regressing_ids"] += 1
            physical_ordered = False
        if t < previous_t:
            physical_ordered = False
            counts["transaction_clock_regressions"] += 1
        if pending_disconnect is not None:
            disconnects.append((pending_disconnect, t))
            pending_disconnect = None
        previous_t = t
        bid, ask, bq, aq = [D(data[k]) for k in ("b", "a", "B", "A")]
        valid = (sequence_ok and all(x.is_finite() and x > 0 for x in (bid, ask, bq, aq))
                 and bid < ask and bid % TICK == 0 and ask % TICK == 0
                 and t <= e + 1_000_000 and max(t, e) <= received + 1_000_000)
        books.append({"receive_ns": received, "transaction_ns": t, "publication_ns": e,
                      "update_id": uid, "source_line": line_number, "valid": valid,
                      "bid": bid, "ask": ask, "bid_quantity": bq, "ask_quantity": aq})
    if pending_disconnect is not None:
        disconnects.append((pending_disconnect, midnight + 60 * NS))
    return Tape(books, marks, disconnects, physical_ordered), dict(counts)


def before(rows, cutoff):
    i = bisect.bisect_left([r["receive_ns"] for r in rows], cutoff) - 1
    return rows[i] if i >= 0 else None


def plan(tape, event, rule):
    decision = int(event["decision_ns"])
    cutoff = decision - 250_000_000
    quote, mark = before(tape.books, cutoff), before(tape.marks, cutoff)
    result = {"eligible": False, "signal_cutoff_ns": cutoff}
    if quote is None or not quote["valid"] or not all(0 < decision - quote[k] <= NS for k in ("receive_ns", "transaction_ns", "publication_ns")):
        return {**result, "reason": "invalid_or_stale_causal_quote"}
    latest_exit = decision + 24_100_000_000 + 100_000_000
    if (mark is None or not mark["valid"]
            or not 0 < decision - mark["receive_ns"] <= 5 * NS
            or not 0 < decision - mark["publication_ns"] <= 5 * NS
            or mark["next_funding_ns"] <= latest_exit + NS):
        return {**result, "reason": "funding_cycle_not_proven_clear", "mark": mark}
    long = (int(event["direction"]) > 0) == (rule == "fade_basis")
    price = quote["ask" if long else "bid"]
    size = quote["ask_quantity" if long else "bid_quantity"]
    quantity = int(min(D(200) / (price * D("1.01")), size / 10) / 100) * 100
    limit = (price * (D("1.001") if long else D("0.999")) / TICK).to_integral_value(
        rounding=ROUND_FLOOR if long else ROUND_CEILING) * TICK
    reserve = quantity * max(limit, quote["ask"]) * D("1.02")
    result.update(long=long, quantity=quantity, limit=limit, capital_reserved=reserve,
                  signal_book=quote, signal_mark=mark)
    if quantity * price < 100 or reserve > 10000:
        return {**result, "reason": "size_or_capital_gate"}
    return {**result, "eligible": True, "reason": "conditional_plan"}


def compatible(tape, arrival, radius, long):
    result = {"known": False, "arrival_ns": arrival, "radius_ns": radius}
    if not tape.physical_ordered:
        return {**result, "reason": "source_sequence_or_matching_clock_regression"}
    times = [r["transaction_ns"] for r in tape.books]
    left = bisect.bisect_left(times, arrival - radius) - 1
    stop = bisect.bisect_right(times, arrival + radius)
    if left < 0 or stop >= len(times):
        return {**result, "reason": "unbracketed_matching_clock"}
    left = bisect.bisect_left(times, times[left])
    if any(a <= arrival + radius and b >= arrival - radius for a, b in tape.disconnects):
        return {**result, "reason": "source_disconnect_spans_arrival"}
    rows = tape.books[left:stop]
    if not all(r["valid"] for r in rows):
        return {**result, "reason": "invalid_compatible_book"}
    prices = [r["ask" if long else "bid"] for r in rows]
    sizes = [r["ask_quantity" if long else "bid_quantity"] for r in rows]
    return {**result, "known": True, "reason": "conditional_native_matching_clock",
            "first_index": left, "stop_index": stop, "successor_ns": times[stop],
            "source_lines": [r["source_line"] for r in rows], "prices": prices, "sizes": sizes,
            "price_lower": min(prices), "price_upper": max(prices), "minimum_touch_quantity": min(sizes)}


def cash(quantity, long, entry, exit_price, scenario):
    q = D(quantity)
    gross = q * (exit_price - entry) * (1 if long else -1)
    turnover = q * (entry + exit_price)
    fees = turnover * D("0.0006") * scenario["fee_multiple"]
    adverse = turnover * D("0.0001") * scenario["adverse_multiple"]
    return {"entry_price": entry, "exit_price": exit_price, "gross": gross,
            "fees": fees, "adverse": adverse, "net": gross - fees - adverse}


def replay(tape, event, intent, scenario):
    if not intent["eligible"]:
        return {"submitted": False, "status": "predecision_no_order", "reason": intent["reason"]}
    entry = int(event["decision_ns"]) + 50_000_000 + scenario["delay_ms"] * 1_000_000
    exit_time = entry + 15 * NS + 50_000_000 + 2 * scenario["delay_ms"] * 1_000_000
    radius = scenario["clock_ms"] * 1_000_000
    long, quantity = intent["long"], intent["quantity"]
    entry_quotes = compatible(tape, entry, radius, long)
    exit_quotes = compatible(tape, exit_time, radius, not long)
    inventory_upper = exit_time - entry + 2 * radius
    assert inventory_upper <= 30 * NS
    result = {"submitted": True, "status": "unknown_entry", "quantity": quantity, "long": long,
              "entry_arrival_ns": entry, "exit_arrival_ns": exit_time,
              "inventory_schedule_upper_ns": inventory_upper,
              "entry_quotes": entry_quotes, "exit_quotes": exit_quotes,
              "potential_inventory_quantity": [0, quantity]}
    outcome = fok(entry_quotes, quantity, long, intent["limit"])
    result["entry_outcome"] = outcome
    if outcome == "no_fill":
        return {**result, "status": "no_fill", "potential_inventory_quantity": [0, 0]}
    if outcome != "filled":
        return result
    if not exit_quotes["known"] or exit_quotes["minimum_touch_quantity"] < quantity:
        return {**result, "status": "unknown_exit"}
    possibilities = [cash(quantity, long, start, end, scenario)
                     for start in (entry_quotes["price_lower"], entry_quotes["price_upper"])
                     for end in (exit_quotes["price_lower"], exit_quotes["price_upper"])]
    return {**result, "status": "conditional_complete", "potential_inventory_quantity": [0, 0],
            "lower": min(possibilities, key=lambda r: r["net"]),
            "upper": max(possibilities, key=lambda r: r["net"])}
