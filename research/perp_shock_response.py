"""Fixed causal shock orders and conditional native-clock execution episodes."""

import json
from collections import Counter, defaultdict
from decimal import ROUND_CEILING, ROUND_FLOOR
from decimal import Decimal as D

from research.spot_perp_response import Tape, before, replay
from research.spot_perp_supply import capture_ns, midnight_ns

NS = 1_000_000_000


def parse(lines, day, offset, symbol, tick):
    books, marks, disconnects, counts = [], [], [], Counter()
    midnight = midnight_ns(day)
    start = midnight + int(offset) * 60 * NS
    end = start + 120 * NS
    previous_capture, previous_uid, previous_t = -1, -1, -1
    fingerprint = None
    physical_ordered, pending_disconnect = True, None
    for line_number, line in enumerate(lines):
        if not line.strip():
            counts["disconnects"] += 1
            pending_disconnect = previous_t if previous_t >= 0 else start
            marks.append({"receive_ns": previous_capture + 1, "valid": False, "source_line": line_number})
            previous_uid, fingerprint = -1, None
            continue
        stamp, payload = line.rstrip("\r\n").split(" ", 1)
        received = capture_ns(stamp, midnight)
        assert stamp[:10] == day and start <= received < end and received >= previous_capture
        previous_capture = received
        message = json.loads(payload)
        raw, stream = message["data"], message["stream"]
        assert raw["s"] == symbol and stream.startswith(symbol.lower() + "@")
        channel = stream.split("@", 1)[1]
        counts["native_messages"] += 1
        if channel.startswith("markPrice"):
            counts["mark_messages"] += 1
            assert type(raw["E"]) is int and type(raw["T"]) is int
            event, price = raw["E"] * 1_000_000, D(raw["p"])
            marks.append({"receive_ns": received, "publication_ns": event,
                          "next_funding_ns": raw["T"] * 1_000_000, "mark_price": price,
                          "source_line": line_number,
                          "valid": event <= received + 1_000_000 and price.is_finite() and price > 0})
            continue
        assert channel == "bookTicker" and all(type(raw[k]) is int for k in ("u", "T", "E"))
        counts["book_messages"] += 1
        uid, t, e = raw["u"], raw["T"] * 1_000_000, raw["E"] * 1_000_000
        mark = tuple(str(raw[k]) for k in ("b", "B", "a", "A", "T", "E"))
        if uid == previous_uid and mark == fingerprint:
            counts["exact_duplicate_books"] += 1
            continue
        sequence_ok = uid > previous_uid
        if sequence_ok:
            previous_uid, fingerprint = uid, mark
        else:
            counts["conflicting_or_regressing_ids"] += 1
            physical_ordered = False
        if t < previous_t:
            counts["transaction_clock_regressions"] += 1
            physical_ordered = False
        if pending_disconnect is not None:
            disconnects.append((pending_disconnect, t))
            pending_disconnect = None
        previous_t = t
        bid, ask, bq, aq = [D(raw[k]) for k in ("b", "a", "B", "A")]
        valid = (sequence_ok and all(p.is_finite() and p > 0 for p in (bid, ask, bq, aq))
                 and bid < ask and bid % tick == 0 and ask % tick == 0
                 and t <= e + 1_000_000 and max(t, e) <= received + 1_000_000)
        books.append({"receive_ns": received, "transaction_ns": t, "publication_ns": e,
                      "update_id": uid, "source_line": line_number, "valid": valid,
                      "bid": bid, "ask": ask, "bid_quantity": bq, "ask_quantity": aq})
    if pending_disconnect is not None:
        disconnects.append((pending_disconnect, end))
    return Tape(books, marks, disconnects, physical_ordered), dict(counts)


def plan(tape, event, rule, tick):
    assert rule in ("follow_shock", "fade_shock") and int(event["direction"]) in (-1, 1)
    decision = int(event["decision_ns"])
    cutoff = decision - 250_000_000
    quote, mark = before(tape.books, cutoff), before(tape.marks, cutoff)
    result = {"eligible": False, "signal_cutoff_ns": cutoff}
    if quote is None or not quote["valid"] or not all(
            0 < cutoff - quote[k] <= 250_000_000 for k in ("receive_ns", "transaction_ns", "publication_ns")):
        return {**result, "reason": "invalid_or_stale_causal_quote"}
    latest_exit = decision + 24_200_000_000
    if (mark is None or not mark["valid"]
            or not 0 < decision - mark["receive_ns"] <= 5 * NS
            or not 0 < decision - mark["publication_ns"] <= 5 * NS
            or mark["next_funding_ns"] <= latest_exit + NS):
        return {**result, "reason": "funding_cycle_not_proven_clear", "signal_book": quote, "signal_mark": mark}
    long = (int(event["direction"]) > 0) == (rule == "follow_shock")
    price = quote["ask" if long else "bid"]
    size = quote["ask_quantity" if long else "bid_quantity"]
    quantity = int(min(D(200) / (price * D("1.01")), size / 10) / 10) * 10
    limit = (price * (D("1.001") if long else D("0.999")) / tick).to_integral_value(
        rounding=ROUND_FLOOR if long else ROUND_CEILING) * tick
    reserve = quantity * max(limit, quote["ask"]) * D("1.02")
    result.update(long=long, quantity=quantity, limit=limit, capital_reserved=reserve,
                  signal_book=quote, signal_mark=mark)
    if quantity * price < 100 or reserve > 10000:
        return {**result, "reason": "size_or_capital_gate"}
    return {**result, "eligible": True, "reason": "conditional_plan"}


def episode(events, tapes, intents, rule, scenario):
    halted, busy_until, rows = set(), {}, []
    for event in sorted(events, key=lambda x: (int(x["decision_ns"]), x["symbol"])):
        key = (event["date"], event["symbol"], int(event["decision_ns"]))
        day = event["date"]
        if day in halted:
            result = {"submitted": False, "status": "halted_after_unknown_inventory"}
        elif int(event["decision_ns"]) <= busy_until.get(day, -1):
            result = {"submitted": False, "status": "busy_with_prior_order"}
        else:
            result = replay(tapes[key], event, intents[key][rule], scenario)
            if result["status"].startswith("unknown"):
                halted.add(day)
            elif result["status"] == "conditional_complete":
                busy_until[day] = result["exit_arrival_ns"] + (scenario["delay_ms"] + scenario["clock_ms"]) * 1_000_000
            elif result["status"] == "no_fill":
                busy_until[day] = result["entry_arrival_ns"] + (scenario["delay_ms"] + scenario["clock_ms"]) * 1_000_000
        rows.append({"date": day, "symbol": event["symbol"], "decision_ns": int(event["decision_ns"]), "result": result})
    complete = not halted
    known = [r for r in rows if r["result"]["status"] == "conditional_complete"]
    lower = sum((r["result"]["lower"]["net"] for r in known), D(0))
    upper = sum((r["result"]["upper"]["net"] for r in known), D(0))
    daily = defaultdict(lambda: D(0))
    for row in known:
        daily[row["date"]] += row["result"]["lower"]["net"]
    for event in events:
        daily[event["date"]] += D(0)
    return {"rule": rule, "scenario": scenario["name"], "complete": complete,
            "net_lower": lower if complete else None, "net_upper": upper if complete else None,
            "known_component_lower": lower, "known_component_upper": upper,
            "completed_round_trips": len(known), "outcomes": dict(Counter(r["result"]["status"] for r in rows)),
            "daily_lower": dict(daily) if complete else None,
            "drop_best_three_dates_lower": sum(sorted(daily.values())[:-3], D(0)) if complete else None,
            "unknown_dates": sorted(halted), "rows": rows, "actual_execution_verified": False}
