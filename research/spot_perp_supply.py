"""Causal native BBO sampling and a hypothetical spot/perpetual gap budget."""

import calendar
import json
import math
from collections import Counter
from datetime import datetime
from decimal import Decimal
from statistics import median

NS = 1_000_000_000
D = Decimal


def midnight_ns(day):
    return calendar.timegm(datetime.strptime(day, "%Y-%m-%d").timetuple()) * NS


def capture_ns(stamp, midnight):
    clock = int(stamp[11:13]) * 3600 + int(stamp[14:16]) * 60 + int(stamp[17:19])
    tail = stamp[19:].removesuffix("Z")
    fraction = int(tail[1:].ljust(9, "0")) if tail else 0
    return midnight + clock * NS + fraction


def update_book(raw, received, line_number, venue, states, ids, counts):
    symbol = raw["s"]
    uid = int(raw["u"])
    fingerprint = tuple(str(raw[k]) for k in ("b", "B", "a", "A"))
    if venue == "perpetual":
        fingerprint += (str(raw["T"]), str(raw["E"]))
    previous = ids.get(symbol)
    if previous and uid == previous[0] and fingerprint == previous[1]:
        counts["exact_duplicate_books"] += 1
        return
    good = previous is None or uid > previous[0]
    if not good:
        counts["conflicting_or_regressing_books"] += 1
    else:
        ids[symbol] = (uid, fingerprint)
    state = {"receive_ns": received, "source_line": line_number, "update_id": uid,
             "bid": str(raw["b"]), "ask": str(raw["a"]),
             "bid_quantity": str(raw["B"]), "ask_quantity": str(raw["A"]),
             "sequence_ok": good, "venue": venue}
    if venue == "perpetual":
        state.update(transaction_ns=int(raw["T"]) * 1_000_000,
                     publication_ns=int(raw["E"]) * 1_000_000)
    states[symbol] = state


def valid_book(state, decision):
    if state is None:
        return "missing_book"
    if not state["sequence_ok"]:
        return "conflicting_or_regressing_id"
    values = [float(state[k]) for k in ("bid", "ask", "bid_quantity", "ask_quantity")]
    if not all(math.isfinite(x) and x > 0 for x in values) or values[0] >= values[1]:
        return "invalid_values"
    received = state["receive_ns"]
    if not (received < decision - 250_000_000 and 0 < decision - received <= NS):
        return "capture_freshness_gate"
    if state["venue"] == "perpetual":
        transaction, publication = state["transaction_ns"], state["publication_ns"]
        if not (0 < decision - transaction <= NS and 0 < decision - publication <= NS
                and transaction <= publication + 1_000_000
                and max(transaction, publication) <= received + 1_000_000):
            return "perpetual_clock_gate"
    return None


def sample_native(lines, day, venue):
    midnight = midnight_ns(day)
    start = midnight + 9 * 3600 * NS
    grids = [start + i * NS for i in range(60)]
    states, ids, seen, samples = {}, {}, set(), []
    counts = Counter()
    previous, cursor = -1, 0
    for index, line in enumerate(lines):
        if not line.strip():
            counts["disconnects"] += 1
            states.clear()
            ids.clear()
            continue
        stamp, payload = line.rstrip("\r\n").split(" ", 1)
        assert stamp[:10] == day
        received = capture_ns(stamp, midnight)
        if received < previous or not start <= received < start + 60 * NS:
            raise ValueError("Capture order or frozen slice boundary violated")
        previous = received
        while cursor < len(grids) and grids[cursor] - 250_000_000 <= received:
            samples.append(dict(states))
            cursor += 1
        message = json.loads(payload)
        counts["native_messages"] += 1
        if not message.get("stream", "").endswith("@bookTicker"):
            continue
        raw = message["data"]
        symbol = raw["s"]
        counts["book_messages"] += 1
        if not symbol.endswith("USDT") or not symbol.isalnum():
            continue
        seen.add(symbol)
        update_book(raw, received, index, venue, states, ids, counts)
    while cursor < len(grids):
        samples.append(dict(states))
        cursor += 1
    return {"samples": samples, "symbols": seen, "grids": grids, "counts": dict(counts)}


def ratio(spot, perpetual):
    return (D(perpetual["bid"]) + D(perpetual["ask"])) / (D(spot["bid"]) + D(spot["ask"]))


def gap_budget(spot, perpetual, reference):
    spot_mid = (D(spot["bid"]) + D(spot["ask"])) / 2
    bid, ask = D(perpetual["bid"]), D(perpetual["ask"])
    mid = (bid + ask) / 2
    projected_mid = spot_mid * reference
    gap = (mid / projected_mid - 1) * 10_000
    direction = -1 if gap > 0 else 1
    entry = bid if direction < 0 else ask
    projected_exit = projected_mid + (ask - bid) / 2 * (-direction)
    gross = direction * (projected_exit - entry)
    cost = D("0.0007") * (entry + projected_exit)
    return {"gap_bps": str(gap), "direction": direction,
            "entry_quote": str(entry), "projected_exit_quote": str(projected_exit),
            "projected_budget_bps": str((gross - cost) / entry * 10_000)}


def evaluate_grid(spot_data, perpetual_data, symbol, second):
    decision = perpetual_data["grids"][second]
    spot = spot_data["samples"][second].get(symbol)
    perpetual = perpetual_data["samples"][second].get(symbol)
    row = {"symbol": symbol, "second": second, "decision_ns": decision,
           "raw_eligible": False, "selected": False, "reason": "missing_spot_symbol"}
    if symbol not in spot_data["symbols"]:
        return row
    for name, state in (("spot", spot), ("perpetual", perpetual)):
        reason = valid_book(state, decision)
        if reason:
            row["reason"] = f"{name}_{reason}"
            return row
    row.update(spot_source_line=spot["source_line"], perpetual_source_line=perpetual["source_line"])
    history = []
    for old_second in range(second - 10, second):
        old_spot = spot_data["samples"][old_second].get(symbol)
        old_perpetual = perpetual_data["samples"][old_second].get(symbol)
        old_decision = perpetual_data["grids"][old_second]
        if valid_book(old_spot, old_decision) is None and valid_book(old_perpetual, old_decision) is None:
            history.append(ratio(old_spot, old_perpetual))
    row["anchor_observations"] = len(history)
    if len(history) < 8:
        row["reason"] = "insufficient_fresh_anchor"
        return row
    reference = median(history)
    mad = median([abs(x / reference - 1) * 10_000 for x in history])
    row.update(reference_ratio=str(reference), anchor_mad_bps=str(mad),
               **gap_budget(spot, perpetual, reference))
    if mad > 10:
        row["reason"] = "unstable_anchor"
        return row
    if abs(D(row["gap_bps"])) < 25:
        row["reason"] = "gap_below_25bp"
        return row
    notionals = [D(state[side]) * D(state[side + "_quantity"])
                 for state in (spot, perpetual) for side in ("bid", "ask")]
    row["minimum_touch_notional"] = str(min(notionals))
    if min(notionals) < 2000:
        row["reason"] = "insufficient_displayed_depth"
        return row
    if D(row["projected_budget_bps"]) <= 5:
        row["reason"] = "convergence_budget_below_buffer"
        return row
    row.update(raw_eligible=True, reason="requires_consecutive_confirmation")
    return row


def screen_pair(spot_data, perpetual_data, day):
    rows = []
    for symbol in sorted(perpetual_data["symbols"]):
        prior, selected = None, False
        for second in range(10, 60):
            row = {"date": day, **evaluate_grid(spot_data, perpetual_data, symbol, second)}
            if row["raw_eligible"] and prior and prior["raw_eligible"] and row["direction"] == prior["direction"]:
                row["selected"] = not selected
                row["reason"] = "selected_for_native_execution_review" if not selected else "one_event_per_symbol_date"
                selected = True
            rows.append(row)
            prior = row
    return rows
