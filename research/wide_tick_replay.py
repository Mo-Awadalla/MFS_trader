"""Short two-sided quote cycles with native clocks and bounded partial inventory.

Bounds apply to the specified public-tape queue model, not private fills.
"""

import bisect
import gzip
import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from research.wide_tick_supply import evaluate, stamp_ns

NS = 1_000_000_000
SCENARIOS = {
    "base": {"delay_ns": NS, "maker_bps": 3., "taker_bps": 6., "adverse_bps": 1., "queue_factor": 1., "epsilon_ns": 1_000_000},
    "double_fees": {"delay_ns": NS, "maker_bps": 6., "taker_bps": 12., "adverse_bps": 1., "queue_factor": 1., "epsilon_ns": 1_000_000},
    "outbound_and_ack_3s": {"delay_ns": 3*NS, "maker_bps": 3., "taker_bps": 6., "adverse_bps": 1., "queue_factor": 1., "epsilon_ns": 1_000_000},
    "double_adverse": {"delay_ns": NS, "maker_bps": 3., "taker_bps": 6., "adverse_bps": 2., "queue_factor": 1., "epsilon_ns": 1_000_000},
    "queue_ahead_double": {"delay_ns": NS, "maker_bps": 3., "taker_bps": 6., "adverse_bps": 1., "queue_factor": 2., "epsilon_ns": 1_000_000},
    "clock_envelope_100ms": {"delay_ns": NS, "maker_bps": 3., "taker_bps": 6., "adverse_bps": 1., "queue_factor": 1., "epsilon_ns": 100_000_000},
}


@dataclass
class Tape:
    symbol: str
    book: list = field(default_factory=list)
    trades: list = field(default_factory=list)
    depth: list = field(default_factory=list)
    marks: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    resets: list = field(default_factory=list)
    diagnostics: Counter = field(default_factory=Counter)

    def index(self):
        self.capture = np.array([r["receive_ns"] for r in self.book], dtype=np.int64)
        self.physical = sorted(self.book, key=lambda r: (r["transaction_ns"], r["update_id"], r["source_index"]))
        self.physical_times = np.array([r["transaction_ns"] for r in self.physical], dtype=np.int64)
        self.trades.sort(key=lambda r: (r["transaction_ns"], r["id"]))
        self.trade_times = np.array([r["transaction_ns"] for r in self.trades], dtype=np.int64)
        self.depth.sort(key=lambda r: (r["transaction_ns"], r["u"]))
        self.depth_times = np.array([r["transaction_ns"] for r in self.depth], dtype=np.int64)
        self.mark_capture = np.array([r["receive_ns"] for r in self.marks], dtype=np.int64)
        self.problems.sort()
        self.resets.sort()
        self.reset_times = np.array([r[0] for r in self.resets], dtype=np.int64)

    def reset_since(self, source_index, cutoff):
        index = int(np.searchsorted(self.reset_times, cutoff, side="left"))-1
        return index >= 0 and self.resets[index][1] > source_index

    def signal(self, cutoff):
        index = int(np.searchsorted(self.capture, cutoff, side="left"))-1
        if index < 0 or self.reset_since(self.book[index]["source_index"], cutoff):
            return None
        return self.book[index]

    def envelope(self, clock, epsilon):
        left = int(np.searchsorted(self.physical_times, clock-epsilon, side="left"))-1
        if left < 0:
            return None
        predecessor_time = self.physical_times[left]
        left = int(np.searchsorted(self.physical_times, predecessor_time, side="left"))
        right = int(np.searchsorted(self.physical_times, clock+epsilon, side="right"))
        rows = self.physical[left:right]
        if not rows or clock-epsilon-int(predecessor_time) > 5*NS:
            return None
        for row in rows:
            values = [float(row[k]) for k in ["bid", "ask", "bid_quantity", "ask_quantity"]]
            if (not row["sequence_ok"] or not row["clock_ok"] or not all(math.isfinite(v) and v > 0 for v in values)
                    or values[0] >= values[1]):
                return None
        return rows

    def has_problem(self, start, end):
        i = bisect.bisect_left(self.problems, start)
        return i < len(self.problems) and self.problems[i] <= end


def native_clocks(event, received):
    transaction, publication = int(event["T"])*1_000_000, int(event["E"])*1_000_000
    valid = (-1_000_000 <= received-transaction <= 5*NS
             and -1_000_000 <= received-publication <= 5*NS and transaction <= publication+1_000_000)
    return transaction, publication, valid


def load_day(root, sources, day, midnight_ns, symbols):
    tapes = {symbol: Tape(symbol) for symbol in symbols}
    last_book, last_depth, seen_trades = {}, {}, {symbol: {} for symbol in symbols}
    last_trade = {}
    prior, source_index = -1, 0
    source_counts = Counter()
    for source in sorted(sources, key=lambda r: r["offset"]):
        assert source["complete"]
        path = root/source["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source["compressed_sha256"]
        digest = hashlib.sha256()
        with gzip.open(path, "rb") as handle:
            for raw_line in handle:
                digest.update(raw_line)
                source_index += 1
                if not raw_line.strip():
                    source_counts["disconnects"] += 1
                    for tape in tapes.values():
                        tape.problems.append(prior)
                        tape.resets.append((prior, source_index))
                    last_book.clear()
                    last_depth.clear()
                    continue
                stamp, payload = raw_line.decode().split(" ", 1)
                assert stamp[:10] == day
                received = stamp_ns(stamp, midnight_ns)
                assert prior <= received
                assert midnight_ns+source["offset"]*60*NS <= received < midnight_ns+(source["offset"]+10)*60*NS
                prior = received
                event = json.loads(payload)["data"]
                symbol, kind = event["s"], event["e"]
                assert symbol in tapes
                tape = tapes[symbol]
                tape.diagnostics[kind] += 1
                source_counts["native_messages"] += 1
                if kind == "markPriceUpdate":
                    publication = int(event["E"])*1_000_000
                    mark, rate = float(event["p"]), float(event["r"])
                    valid = math.isfinite(mark) and math.isfinite(rate) and mark > 0 and -1_000_000 <= received-publication <= 5*NS
                    tape.marks.append({"receive_ns": received, "publication_ns": publication,
                                       "funding_ns": int(event["T"])*1_000_000, "valid": valid,
                                       "source_index": source_index})
                    continue
                transaction, publication, clock_ok = native_clocks(event, received)
                if not clock_ok:
                    tape.problems.append(transaction)
                    tape.diagnostics["invalid_clocks"] += 1
                if kind == "bookTicker":
                    identifier = int(event["u"])
                    signature = tuple(event[k] for k in ["b", "B", "a", "A", "T"])
                    old = last_book.get(symbol)
                    ok = old is None or identifier > old[0] or (identifier == old[0] and signature == old[1] and old[2])
                    if old is None or identifier >= old[0]:
                        last_book[symbol] = (identifier, signature, ok)
                    else:
                        last_book[symbol] = (old[0], old[1], False)
                    if not ok:
                        tape.problems.append(transaction)
                    if old is not None and identifier > old[0] and int(event["T"]) < old[1][-1]:
                        tape.problems.extend([transaction, int(old[1][-1])*1_000_000])
                        tape.diagnostics["book_transaction_clock_regressions"] += 1
                    tape.book.append({"receive_ns": received, "transaction_ns": transaction, "publication_ns": publication,
                                      "source_line": source_index, "source_index": source_index, "update_id": identifier,
                                      "bid": event["b"], "ask": event["a"], "bid_quantity": event["B"], "ask_quantity": event["A"],
                                      "sequence_ok": ok, "clock_ok": clock_ok})
                elif kind == "depthUpdate":
                    u, pu = int(event["u"]), int(event["pu"])
                    old = last_depth.get(symbol)
                    if old is not None and (u <= old[0] or pu != old[0]):
                        tape.problems.append(transaction)
                        tape.diagnostics["depth_sequence_breaks"] += 1
                    if old is not None and transaction < old[1]:
                        tape.problems.extend([transaction, old[1]])
                        tape.diagnostics["depth_transaction_clock_regressions"] += 1
                    last_depth[symbol] = (u, transaction)
                    tape.depth.append({"transaction_ns": transaction, "receive_ns": received, "u": u, "pu": pu,
                                       "b": {float(p): float(q) for p, q in event["b"]},
                                       "a": {float(p): float(q) for p, q in event["a"]}, "source_index": source_index})
                elif kind == "trade":
                    identifier = int(event["t"])
                    signature = tuple(event[k] for k in ["p", "q", "T", "m"]) + (event.get("X"),)
                    if identifier in seen_trades[symbol]:
                        if seen_trades[symbol][identifier] != signature:
                            tape.problems.append(transaction)
                            tape.diagnostics["conflicting_trade_id"] += 1
                        else:
                            tape.diagnostics["duplicate_trade_id"] += 1
                        continue
                    seen_trades[symbol][identifier] = signature
                    if event.get("X") in {"INSURANCE_FUND", "ADL", "NA"}:
                        tape.diagnostics["off_book_trades"] += 1
                        continue
                    old = last_trade.get(symbol)
                    if old is not None and (identifier <= old[0] or transaction < old[1]):
                        tape.problems.extend([transaction, old[1]])
                        tape.diagnostics["trade_id_or_transaction_clock_regressions"] += 1
                    last_trade[symbol] = (identifier, transaction)
                    p, q = float(event["p"]), float(event["q"])
                    if event.get("X") != "MARKET" or not isinstance(event["m"], bool) or not all(math.isfinite(v) and v > 0 for v in [p, q]):
                        tape.problems.append(transaction)
                        tape.diagnostics["invalid_regular_trade"] += 1
                        continue
                    tape.trades.append({"transaction_ns": transaction, "receive_ns": received, "id": identifier,
                                        "price": p, "quantity": q, "sell": event["m"], "source_index": source_index})
                else:
                    raise ValueError(f"Unexpected native event {kind}")
        assert digest.hexdigest() == source["decoded_sha256"]
    for tape in tapes.values():
        tape.index()
    return tapes, {"date": day, **dict(source_counts), "symbols": {s: dict(t.diagnostics) for s, t in tapes.items()}}


def queue_ahead(tape, signal, envelope, arrival, epsilon, direction, price):
    quantity_key, price_key, side = ("bid_quantity", "bid", "b") if direction > 0 else ("ask_quantity", "ask", "a")
    maximum = float(signal[quantity_key])
    for row in envelope:
        if float(row[price_key]) == price:
            maximum = max(maximum, float(row[quantity_key]))
    lo = int(np.searchsorted(tape.depth_times, signal["transaction_ns"]-epsilon, side="left"))
    hi = int(np.searchsorted(tape.depth_times, arrival+epsilon, side="right"))
    covering = False
    evidence = []
    for row in tape.depth[lo:hi]:
        if row["pu"] <= signal["update_id"] <= row["u"]:
            covering = True
        if row["u"] > signal["update_id"] and price in row[side]:
            value = row[side][price]
            if not math.isfinite(value) or value < 0:
                return None, evidence
            maximum = max(maximum, value)
            evidence.append(row["source_index"])
    # If no depth interval spans the signal, a directly observed arrival best
    # at that exact own price supplies a fresh full quantity seed instead.
    directly_observed = all(float(row[price_key]) == price for row in envelope)
    if not covering and not directly_observed:
        return None, evidence
    return maximum, evidence


def filled_quantity(tape, direction, price, intended, ahead, start, end, outer=False):
    if end < start:
        return 0.0, []
    left = int(np.searchsorted(tape.trade_times, start, side="left" if outer else "right"))
    right = int(np.searchsorted(tape.trade_times, end, side="right" if outer else "left"))
    filled, proof = 0.0, []
    for trade in tape.trades[left:right]:
        if trade["sell"] != (direction > 0):
            continue
        delta = direction*(trade["price"]-price)
        if delta > 0:
            continue
        available = trade["quantity"]
        if delta < 0:
            ahead = 0.0
        else:
            consumed = min(ahead, available)
            ahead -= consumed
            available -= consumed
        execution = min(intended-filled, available)
        if execution > 1e-12:
            filled += execution
            proof.append({"id": trade["id"], "transaction_ns": trade["transaction_ns"], "source_index": trade["source_index"],
                          "source_price": trade["price"], "source_quantity": trade["quantity"], "filled_quantity": execution})
        if filled >= intended-1e-12:
            break
    return min(filled, intended), proof


def cash_at(buy_quantity, sell_quantity, bid_limit, ask_limit, exit_bid, exit_ask, maker_bps, taker_bps, adverse_bps):
    maker_notional = buy_quantity*bid_limit+sell_quantity*ask_limit
    gross = sell_quantity*ask_limit-buy_quantity*bid_limit
    residual = buy_quantity-sell_quantity
    exit_price = exit_bid if residual >= 0 else exit_ask
    gross += residual*exit_price
    taker_notional = abs(residual)*exit_price
    fees = maker_notional*maker_bps/10000+taker_notional*taker_bps/10000
    adverse = (maker_notional+taker_notional)*adverse_bps/10000
    return {"net": gross-fees-adverse, "gross": gross, "fees": fees, "adverse": adverse,
            "maker_notional": maker_notional, "taker_notional": taker_notional,
            "buy_quantity": buy_quantity, "sell_quantity": sell_quantity, "residual": residual,
            "exit_price": exit_price}


def cash_bounds(buy_bounds, sell_bounds, bid_limit, ask_limit, exit_prices, scenario):
    points = {(x, y) for x in buy_bounds for y in sell_bounds}
    low, high = max(buy_bounds[0], sell_bounds[0]), min(buy_bounds[1], sell_bounds[1])
    if low <= high:
        points.update([(low, low), (high, high)])
    cases = []
    for x, y in sorted(points):
        for exit_bid, exit_ask in exit_prices:
            cases.append(cash_at(x, y, bid_limit, ask_limit, exit_bid, exit_ask,
                                 scenario["maker_bps"], scenario["taker_bps"], scenario["adverse_bps"]))
    return min(cases, key=lambda r: r["net"]), max(cases, key=lambda r: r["net"])


def replay_cycle(tape, decision, rest_seconds, scenario, available_cash):
    delay, epsilon = scenario["delay_ns"], scenario["epsilon_ns"]
    arrival = decision+delay
    cancel = arrival+rest_seconds*NS
    flatten = cancel+2*delay
    row = {"symbol": tape.symbol, "decision_ns": decision, "arrival_ns": arrival, "cancel_ns": cancel,
           "flatten_ns": flatten, "status": "predecision_no_order", "net_low": 0.0, "net_high": 0.0}
    signal = tape.signal(decision-250_000_000)
    if signal is None:
        row["reason"] = "no_causal_book"
        return row
    checked = evaluate(signal, decision-250_000_000)
    if not checked["supply"] or not signal["clock_ok"]:
        row["reason"] = "signal_"+checked["reason"]
        return row
    bid, ask = float(signal["bid"]), float(signal["ask"])
    q = math.floor(min(200/ask, .1*float(signal["bid_quantity"]), .1*float(signal["ask_quantity"]))/10)*10
    if q*bid < 100 or available_cash < q*ask*1.01:
        row["reason"] = "size_or_capital_gate"
        return row
    mindex = int(np.searchsorted(tape.mark_capture, decision-250_000_000, side="left"))-1
    if mindex < 0:
        row["reason"] = "missing_funding_state"
        return row
    mark = tape.marks[mindex]
    cutoff = decision-250_000_000
    if (not mark["valid"] or not 0 < cutoff-mark["receive_ns"] <= 5*NS
            or not 0 < cutoff-mark["publication_ns"] <= 5*NS
            or tape.reset_since(mark["source_index"], cutoff) or mark["funding_ns"] <= flatten+epsilon):
        row["reason"] = "unknown_or_overlapping_funding"
        return row
    row.update(signal_source_index=signal["source_index"], signal_receive_ns=signal["receive_ns"],
               signal_transaction_ns=signal["transaction_ns"], bid_limit=bid, ask_limit=ask, intended_quantity=q,
               status="unknown", net_low=None, net_high=None)
    if tape.has_problem(signal["transaction_ns"]-epsilon, flatten+epsilon):
        row["reason"] = "source_clock_or_sequence_problem_during_possible_exposure"
        return row
    envelope = tape.envelope(arrival, epsilon)
    if envelope is None:
        row["reason"] = "unknown_arrival_book"
        return row
    row["arrival_sources"] = [r["source_index"] for r in envelope]
    for direction, name, price in [(1, "buy", bid), (-1, "sell", ask)]:
        accepted = [price < float(r["ask"]) if direction > 0 else price > float(r["bid"]) for r in envelope]
        if not any(accepted):
            row[name+"_quantity_bounds"] = [0.0, 0.0]
            row[name+"_acceptance"] = "rejected"
            continue
        ahead, sources = queue_ahead(tape, signal, envelope, arrival, epsilon, direction, price)
        if ahead is None:
            row["reason"] = "unknown_"+name+"_arrival_queue"
            return row
        ahead *= scenario["queue_factor"]
        lower, lower_proof = filled_quantity(tape, direction, price, q, ahead, arrival+epsilon, cancel-epsilon)
        upper, upper_proof = filled_quantity(tape, direction, price, q, ahead, arrival-epsilon, cancel+epsilon, outer=True)
        assert -1e-10 <= lower <= upper+1e-9 <= q+1e-8
        if not all(accepted):
            lower, lower_proof = 0.0, []
        row.update({name+"_quantity_bounds": [lower, upper], name+"_queue_ahead": ahead,
                    name+"_queue_sources": sources, name+"_lower_fills": lower_proof, name+"_upper_fills": upper_proof,
                    name+"_acceptance": "accepted" if all(accepted) else "bounded_acceptance"})
    buy, sell = row["buy_quantity_bounds"], row["sell_quantity_bounds"]
    maximum_long, maximum_short = max(0., buy[1]-sell[0]), max(0., sell[1]-buy[0])
    row.update(maximum_long_residual=maximum_long, maximum_short_residual=maximum_short)
    prices = [(0.0, 0.0)]
    if max(maximum_long, maximum_short) > 1e-10:
        exit_envelope = tape.envelope(flatten, epsilon)
        if exit_envelope is None:
            row["reason"] = "unknown_forced_exit_book"
            return row
        if (maximum_long > min(float(r["bid_quantity"]) for r in exit_envelope)+1e-10
                or maximum_short > min(float(r["ask_quantity"]) for r in exit_envelope)+1e-10):
            row["reason"] = "insufficient_forced_exit_depth"
            return row
        row["exit_sources"] = [r["source_index"] for r in exit_envelope]
        prices = [(float(r["bid"]), float(r["ask"])) for r in exit_envelope]
    # A changing funding schedule during an already submitted cycle cannot
    # retroactively turn it into a harmless excluded opportunity.
    active_marks = [r for r in tape.marks if signal["receive_ns"] <= r["receive_ns"] <= flatten+epsilon]
    if any(not r["valid"] for r in active_marks):
        row["reason"] = "invalid_funding_source_during_possible_exposure"
        return row
    if any(arrival-epsilon <= r["funding_ns"] <= flatten+epsilon for r in active_marks):
        row["reason"] = "unexpected_funding_requires_actual_cashflow"
        return row
    worst, best = cash_bounds(buy, sell, bid, ask, prices, scenario)
    row.update(status="bounded_complete", reason="both_orders_resolved_and_all_inventory_flattened",
               net_low=worst["net"], net_high=best["net"], worst_cash=worst, best_cash=best,
               exit_price_pairs=prices)
    return row


def replay_portfolio(tapes, midnight_ns, rest_seconds, scenario):
    records, cash_low, cash_high, stopped = [], 10000., 10000., False
    for minute in range(2, 30):
        decision = midnight_ns+(9*3600+minute*60)*NS
        batch, reserved = [], 0.0
        for symbol in sorted(tapes):
            if stopped:
                records.append({"symbol": symbol, "decision_ns": decision, "status": "halted_after_unknown_inventory",
                                "net_low": None, "net_high": None})
                continue
            record = replay_cycle(tapes[symbol], decision, rest_seconds, scenario, cash_low-reserved)
            if "intended_quantity" in record:
                reserved += record["intended_quantity"]*record["ask_limit"]*1.01
            batch.append(record)
        for record in batch:
            if record["status"] == "unknown":
                stopped = True
            else:
                cash_low += record["net_low"]
                cash_high += record["net_high"]
            records.append(record)
    return records, {"complete": not stopped, "net_low": None if stopped else cash_low-10000,
                     "net_high": None if stopped else cash_high-10000,
                     "closed_portion_net_low": cash_low-10000, "closed_portion_net_high": cash_high-10000,
                     "statuses": dict(Counter(r["status"] for r in records))}
