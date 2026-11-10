"""Causal external-price protection for the frozen short passive-quote model."""

import bisect
import gzip
import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass, field

from research.wide_tick_replay import NS, cash_bounds, filled_quantity, queue_ahead
from research.wide_tick_supply import evaluate, stamp_ns

SOURCE_DELAY = 250_000_000
MAX_AGE = 5*NS


@dataclass
class ExternalTape:
    rows: list = field(default_factory=list)

    def index(self):
        self.captures = [r["receive_ns"] for r in self.rows]


def apply_external(event, received, source, previous):
    """Depth-one deltas identify the sole positive best level on each side."""
    data = event["data"]
    publication = int(event["ts"])*1_000_000
    transaction = int(event["cts"])*1_000_000 if "cts" in event else None
    update, sequence = int(data["u"]), int(data["seq"])
    snapshot = event["type"] == "snapshot"
    state = dict(previous)
    invalid = None
    clock_ok = -1_000_000 <= received-publication <= MAX_AGE
    if transaction is not None:
        clock_ok &= -1_000_000 <= received-transaction <= MAX_AGE and transaction <= publication+1_000_000
    old_update = previous.get("update")
    reset = snapshot and update == 1
    if old_update is not None and not reset:
        if sequence < previous["sequence"] or update < old_update or (not snapshot and update != old_update+1):
            invalid = "sequence_break"
    if not clock_ok:
        invalid = "inconsistent_source_clock"
    if snapshot or invalid:
        state = {}
    for side in ("b", "a"):
        pairs = [(float(p), float(q)) for p, q in data[side]]
        if any(not math.isfinite(p) or not math.isfinite(q) or p <= 0 or q < 0 for p, q in pairs):
            invalid = "invalid_level"
            state.pop(side, None)
            continue
        positive = [(p, q) for p, q in pairs if q > 0]
        if len(positive) > 1:
            invalid = "multiple_positive_levels_in_depth_one"
            state.pop(side, None)
            continue
        if positive:
            state[side] = (*positive[0], source)
        elif side in state and any(p == state[side][0] and q == 0 for p, q in pairs):
            state.pop(side)
    if old_update == update and snapshot and not reset and all(k in previous for k in ("b", "a")):
        if any(state.get(k, ())[:2] != previous.get(k, ())[:2] for k in ("b", "a")):
            invalid = "conflicting_repeated_snapshot"
    if event["type"] not in {"snapshot", "delta"}:
        invalid = "unexpected_message_type"
    valid = invalid is None and all(k in state for k in ("b", "a"))
    if valid and state["b"][0] >= state["a"][0]:
        valid, invalid = False, "crossed_external_book"
    state.update(update=update, sequence=sequence)
    row = {"receive_ns": received, "publication_ns": publication, "transaction_ns": transaction,
           "source_index": source, "valid": valid, "reason": invalid or ("complete_depth_one" if valid else "incomplete_depth_one"),
           "update": update, "sequence": sequence, "native_type": event["type"]}
    for side, name in (("b", "bid"), ("a", "ask")):
        if side in state:
            row[name], row[name+"_quantity"], row[name+"_seed_source"] = state[side]
    # Invalid observations never carry their known level state forward. Later
    # messages must establish both current depth-one levels again.
    if invalid:
        state = {"update": update, "sequence": sequence}
    return row, state


def load_external(root, files, day, midnight, symbols):
    tapes = {s: ExternalTape() for s in symbols}
    states = {s: {} for s in symbols}
    counts = Counter()
    prior, source = -1, 0
    for item in sorted(files, key=lambda x: x["offset"]):
        assert item["complete"]
        path = root/item["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["compressed_sha256"]
        digest = hashlib.sha256()
        with gzip.open(path, "rb") as stream:
            for line in stream:
                digest.update(line)
                source += 1
                if not line.strip():
                    counts["disconnects"] += 1
                    for symbol, tape in tapes.items():
                        tape.rows.append({"receive_ns": prior, "source_index": source, "valid": False, "reason": "disconnect"})
                        states[symbol] = {}
                    continue
                stamp, raw = line.decode().split(" ", 1)
                received = stamp_ns(stamp, midnight)
                assert stamp.startswith(day) and prior <= received
                assert midnight+item["offset"]*60*NS <= received < midnight+(item["offset"]+10)*60*NS
                prior = received
                event = json.loads(raw)
                symbol = event["data"]["s"]
                assert symbol in tapes and event["topic"] == f"orderbook.1.{symbol}"
                row, state = apply_external(event, received, source, states[symbol])
                if row["native_type"] == "snapshot" and states[symbol].get("update") == row["update"] and row["valid"]:
                    counts["repeated_snapshots_reconciled"] += 1
                states[symbol] = state
                tapes[symbol].rows.append(row)
                counts["native_messages"] += 1
                counts[row["reason"]] += 1
                counts["matching_clock_present" if row["transaction_ns"] is not None else "matching_clock_absent"] += 1
        assert digest.hexdigest() == item["decoded_sha256"]
    for tape in tapes.values():
        tape.index()
    return tapes, {"date": day, **dict(counts)}


def fresh(row, cutoff):
    if not row["valid"]:
        return False
    clocks = [row["receive_ns"], row["publication_ns"]]
    if row["transaction_ns"] is not None:
        clocks.append(row["transaction_ns"])
    return all(0 < cutoff-t <= MAX_AGE for t in clocks)


def expiry(row):
    clocks = [row["receive_ns"], row["publication_ns"]]
    if row["transaction_ns"] is not None:
        clocks.append(row["transaction_ns"])
    return min(clocks)+MAX_AGE+SOURCE_DELAY+1


def cushion(row, price, buy):
    # This fixed decision rule does not change when stress-test fees change.
    external = row["bid"] if buy else row["ask"]
    return (external-price if buy else price-external)-price*.0004-external*.0007


def cancellation(tape, initial_index, decision, scheduled, delay, price, buy):
    current = tape.rows[initial_index]
    for index in range(initial_index+1, len(tape.rows)+1):
        available = tape.rows[index]["receive_ns"]+SOURCE_DELAY+1 if index < len(tape.rows) else scheduled+NS
        stale = expiry(current)
        if stale <= available and stale+delay <= scheduled:
            assert stale > decision
            return {"cancel_ns": stale+delay, "trigger_ns": stale, "reason": "external_freshness_expired", "source_index": current["source_index"]}
        if available+delay > scheduled:
            break
        current = tape.rows[index]
        assert available > decision
        valid = fresh(current, available-SOURCE_DELAY)
        if not valid or cushion(current, price, buy) <= 0:
            return {"cancel_ns": available+delay, "trigger_ns": available,
                    "reason": "external_state_invalid" if not valid else "external_cushion_exhausted", "source_index": current["source_index"]}
    return {"cancel_ns": scheduled, "trigger_ns": scheduled-delay, "reason": "scheduled", "source_index": None}


def quote_plan(tape, decision, rest, delay, bid, ask):
    cutoff = decision-SOURCE_DELAY
    index = bisect.bisect_left(tape.captures, cutoff)-1
    plan = {"eligible": False, "reason": "external_state_missing_or_stale"}
    if index < 0 or not fresh(tape.rows[index], cutoff):
        return plan
    row = tape.rows[index]
    plan.update(source_index=row["source_index"], receive_ns=row["receive_ns"], publication_ns=row["publication_ns"],
                transaction_ns=row["transaction_ns"], bid=row["bid"], ask=row["ask"],
                bid_seed_source=row["bid_seed_source"], ask_seed_source=row["ask_seed_source"])
    for buy, name, price in ((True, "buy", bid), (False, "sell", ask)):
        budget = cushion(row, price, buy)
        plan[name] = {"admitted": budget > 0, "cushion_per_unit": budget}
        if budget > 0:
            plan["eligible"] = True
            plan[name].update(cancellation(tape, index, decision, decision+delay+rest*NS, delay, price, buy))
    plan["reason"] = "external_price_cushion" if plan["eligible"] else "external_cushion_below_cost"
    return plan


def replay_cycle(tape, external, decision, rest, scenario, cash):
    delay, epsilon = scenario["delay_ns"], scenario["epsilon_ns"]
    arrival = decision+delay
    scheduled_cancel = arrival+rest*NS
    scheduled_flatten = scheduled_cancel+2*delay
    cutoff = decision-SOURCE_DELAY
    row = {"symbol": tape.symbol, "decision_ns": decision, "arrival_ns": arrival,
           "scheduled_cancel_ns": scheduled_cancel, "status": "predecision_no_order", "net_low": 0., "net_high": 0.}
    signal = tape.signal(cutoff)
    if signal is None:
        row["reason"] = "no_causal_book"
        return row
    checked = evaluate(signal, cutoff)
    if not checked["supply"] or not signal["clock_ok"]:
        row["reason"] = "signal_"+checked["reason"]
        return row
    bid, ask = float(signal["bid"]), float(signal["ask"])
    quantity = math.floor(min(200/ask, .1*float(signal["bid_quantity"]), .1*float(signal["ask_quantity"]))/10)*10
    if quantity*bid < 100 or cash < quantity*ask*1.01:
        row["reason"] = "size_or_capital_gate"
        return row
    mindex = bisect.bisect_left(tape.mark_capture, cutoff)-1
    if mindex < 0:
        row["reason"] = "missing_funding_state"
        return row
    mark = tape.marks[mindex]
    if (not mark["valid"] or not 0 < cutoff-mark["receive_ns"] <= 5*NS
            or not 0 < cutoff-mark["publication_ns"] <= 5*NS
            or tape.reset_since(mark["source_index"], cutoff) or mark["funding_ns"] <= scheduled_flatten+epsilon):
        row["reason"] = "unknown_or_overlapping_funding"
        return row
    plan = quote_plan(external, decision, rest, delay, bid, ask)
    row["external_plan"] = plan
    if not plan["eligible"]:
        row["reason"] = plan["reason"]
        return row
    flatten = max(plan[name]["cancel_ns"] for name in ("buy", "sell") if plan[name]["admitted"])+2*delay
    row.update(signal_source_index=signal["source_index"], signal_receive_ns=signal["receive_ns"],
               signal_transaction_ns=signal["transaction_ns"], bid_limit=bid, ask_limit=ask, intended_quantity=quantity,
               flatten_ns=flatten, status="unknown", net_low=None, net_high=None)
    if tape.has_problem(signal["transaction_ns"]-epsilon, flatten+epsilon):
        row["reason"] = "source_clock_or_sequence_problem_during_possible_exposure"
        return row
    arrived = tape.envelope(arrival, epsilon)
    if arrived is None:
        row["reason"] = "unknown_arrival_book"
        return row
    row["arrival_sources"] = [x["source_index"] for x in arrived]
    for direction, name, price in ((1, "buy", bid), (-1, "sell", ask)):
        if not plan[name]["admitted"]:
            row[name+"_quantity_bounds"] = [0., 0.]
            row[name+"_acceptance"] = "not_submitted"
            continue
        accepted = [price < float(x["ask"]) if direction > 0 else price > float(x["bid"]) for x in arrived]
        if not any(accepted):
            row[name+"_quantity_bounds"] = [0., 0.]
            row[name+"_acceptance"] = "rejected"
            continue
        ahead, sources = queue_ahead(tape, signal, arrived, arrival, epsilon, direction, price)
        if ahead is None:
            row["reason"] = "unknown_"+name+"_arrival_queue"
            return row
        ahead *= scenario["queue_factor"]
        cancel = plan[name]["cancel_ns"]
        low, low_proof = filled_quantity(tape, direction, price, quantity, ahead, arrival+epsilon, cancel-epsilon)
        high, high_proof = filled_quantity(tape, direction, price, quantity, ahead, arrival-epsilon, cancel+epsilon, outer=True)
        assert -1e-10 <= low <= high+1e-9 <= quantity+1e-8
        if not all(accepted):
            low, low_proof = 0., []
        row.update({name+"_quantity_bounds": [low, high], name+"_queue_ahead": ahead,
                    name+"_queue_sources": sources, name+"_lower_fills": low_proof, name+"_upper_fills": high_proof,
                    name+"_acceptance": "accepted" if all(accepted) else "bounded_acceptance"})
    buy, sell = row["buy_quantity_bounds"], row["sell_quantity_bounds"]
    long, short = max(0., buy[1]-sell[0]), max(0., sell[1]-buy[0])
    row.update(maximum_long_residual=long, maximum_short_residual=short)
    prices = [(0., 0.)]
    if max(long, short) > 1e-10:
        exits = tape.envelope(flatten, epsilon)
        if exits is None:
            row["reason"] = "unknown_forced_exit_book"
            return row
        if long > min(float(x["bid_quantity"]) for x in exits)+1e-10 or short > min(float(x["ask_quantity"]) for x in exits)+1e-10:
            row["reason"] = "insufficient_forced_exit_depth"
            return row
        row["exit_sources"] = [x["source_index"] for x in exits]
        prices = [(float(x["bid"]), float(x["ask"])) for x in exits]
    active_marks = [x for x in tape.marks if signal["receive_ns"] <= x["receive_ns"] <= flatten+epsilon]
    if any(not x["valid"] for x in active_marks):
        row["reason"] = "invalid_funding_source_during_possible_exposure"
        return row
    if any(arrival-epsilon <= x["funding_ns"] <= flatten+epsilon for x in active_marks):
        row["reason"] = "unexpected_funding_requires_actual_cashflow"
        return row
    worst, best = cash_bounds(buy, sell, bid, ask, prices, scenario)
    row.update(status="bounded_complete", reason="both_orders_resolved_and_all_inventory_flattened",
               net_low=worst["net"], net_high=best["net"], worst_cash=worst, best_cash=best, exit_price_pairs=prices)
    return row


def replay_portfolio(tapes, externals, midnight, rest, scenario):
    records, low, high, stopped = [], 10000., 10000., False
    for minute in range(2, 30):
        decision = midnight+(9*3600+minute*60)*NS
        batch, reserved = [], 0.
        for symbol in sorted(tapes):
            if stopped:
                records.append({"symbol": symbol, "decision_ns": decision, "status": "halted_after_unknown_inventory", "net_low": None, "net_high": None})
                continue
            row = replay_cycle(tapes[symbol], externals[symbol], decision, rest, scenario, low-reserved)
            if "intended_quantity" in row:
                reserved += row["intended_quantity"]*row["ask_limit"]*1.01
            batch.append(row)
        for row in batch:
            if row["status"] == "unknown":
                stopped = True
            else:
                low += row["net_low"]
                high += row["net_high"]
            records.append(row)
    return records, {"complete": not stopped, "net_low": None if stopped else low-10000, "net_high": None if stopped else high-10000,
                     "closed_portion_net_low": low-10000, "closed_portion_net_high": high-10000,
                     "statuses": dict(Counter(r["status"] for r in records))}
