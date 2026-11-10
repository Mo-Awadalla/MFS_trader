"""Conditional historical execution from sequenced Binance transaction-clock deltas.

The initial top five delimit known depth. This is a feed-state replay, not proof
of an order's live matching-engine priority or of unobserved states within batches.
"""

from __future__ import annotations

import math

from research.liquidation_event_replay import valid_snapshot


def initial_book(quote, tick):
    book = {side: {int(round(quote[f"{name}[{i}].price"] / tick)): float(quote[f"{name}[{i}].amount"])
                   for i in range(5)} for side, name in (("b", "bids"), ("a", "asks"))}
    assert all(len(book[s]) == 5 and all(math.isfinite(q) and q > 0 for q in book[s].values()) for s in book)
    assert max(book["b"]) < min(book["a"])
    return book


class TargetBook:
    def __init__(self, quote, raw, tick):
        self.target = int(quote["target_us"])
        self.tick = tick
        self.book = initial_book(quote, tick)
        self.boundary = {"b": min(self.book["b"]), "a": max(self.book["a"])}
        self.last = raw
        self.states = []
        self.result = {"target_us": self.target, "source_local_us": raw["local_us"],
                       "source_E_us": raw["E_us"], "source_T_us": raw["T_us"],
                       "source_u": raw["u"], "boundary": self.boundary, "tick": tick,
                       "updates_before_target": 0, "timestamp_ties": 0, "proof": [raw]}
        if raw["E_us"] != quote["quote_exchange_us"] or raw["T_us"] >= self.target:
            self.fail("invalid_source_clock")
            return
        for side in ("b", "a"):
            for p, q in raw[side]:
                p, q = int(round(float(p) / tick)), float(q)
                within = p >= self.boundary[side] if side == "b" else p <= self.boundary[side]
                if within and not math.isclose(self.book[side].get(p, 0.), q, rel_tol=1e-9, abs_tol=1e-9):
                    self.fail("source_snapshot_delta_disagreement")
                    return

    def fail(self, reason):
        self.result.update(complete=False, reason=reason)

    def snapshot(self):
        return {s: [[p, q] for p, q in sorted(self.book[s].items(), reverse=s == "b")] for s in ("b", "a")}

    def advance(self, raw):
        if "complete" in self.result:
            return
        self.result["proof"].append(raw)
        if raw.get("disconnect"):
            self.fail("disconnect_or_context_gap")
            return
        if raw["pu"] != self.last["u"] or raw["u"] <= self.last["u"] or raw["U"] > raw["u"]:
            self.fail("native_sequence_gap")
            return
        if raw["T_us"] < self.last["T_us"]:
            self.fail("transaction_clock_backtrack")
            return
        self.last = raw
        if raw["T_us"] > self.target:
            self.states.append(self.snapshot())
            # Retain before/after alternatives at each tied update, deduplicated.
            unique = []
            for state in self.states:
                if state not in unique:
                    unique.append(state)
            self.result.update(complete=True, reason="sequenced_native_transaction_clock",
                               states=unique, successor_T_us=raw["T_us"], successor_u=raw["u"])
            return
        if raw["T_us"] == self.target:
            self.result["timestamp_ties"] += 1
            self.states.append(self.snapshot())
        else:
            self.result["updates_before_target"] += 1
        for side in ("b", "a"):
            for p, q in raw[side]:
                p, q = int(round(float(p) / self.tick)), float(q)
                if not math.isfinite(q) or q < 0:
                    self.fail("invalid_native_quantity")
                    return
                within = p >= self.boundary[side] if side == "b" else p <= self.boundary[side]
                if within:
                    if q:
                        self.book[side][p] = q
                    else:
                        self.book[side].pop(p, None)
        if self.book["b"] and self.book["a"] and max(self.book["b"]) >= min(self.book["a"]):
            self.fail("crossed_native_state")


def walk(state, boundary, tick, direction, quantity, limit=None):
    side = "a" if direction > 0 else "b"
    remaining, notional = quantity, 0.
    for levels, (key, available) in enumerate(state[side], 1):
        price = key * tick
        if limit is not None and direction * (price - limit) > 1e-8:
            return {"status": "rejected_fok"}
        take = min(remaining, available)
        notional += take * price
        remaining -= take
        if remaining <= max(1e-10, quantity * 1e-10):
            return {"status": "filled", "notional": notional, "price": notional / quantity, "levels": levels}
    # An exhausted known range can establish a FOK rejection only if its
    # coverage includes the complete collar. Deeper unknown liquidity cannot
    # establish either a fill or a rejection when the collar extends past it.
    if limit is not None and direction * (boundary[side] * tick - limit) >= -1e-8:
        return {"status": "rejected_fok"}
    return {"status": "unknown_depth"}


def outcomes(panel, direction, quantity, limit=None):
    if not panel["complete"]:
        return [{"status": panel["reason"]}]
    return [walk(s, panel["boundary"], panel["tick"], direction, quantity, limit) for s in panel["states"]]


def replay(events, quotes, panels, mechanism, hold, scenario, tick, quantity_step):
    index = {(r["event_id"], r["label"]): r for r in quotes.to_dict("records")}
    rows, cash_lo, cash_hi, halted, free_at = [], 10000., 10000., False, -1
    rate = (scenario["taker_bps"] + scenario["adverse_bps"]) / 10000
    for event in events.loc[events.mechanism.eq(mechanism)].to_dict("records"):
        rec = dict(event)
        if halted:
            rows.append({**rec, "status": "skipped_unresolved_inventory", "complete": False})
            continue
        d, key, direction = int(event["received_us"]), int(event["event_id"]), int(event["direction"])
        delay = scenario["delay_us"]
        entry_at = d + 250000 + delay
        exit_at = entry_at + hold * 1000000 + 2 * delay
        rec.update(send_us=d + 250000, entry_us=entry_at, entry_ack_us=entry_at + delay,
                   exit_us=exit_at, exit_ack_us=exit_at + delay)
        assert d + 250000 > free_at
        signal = index[key, "signal"]
        status = None
        if not valid_snapshot(signal):
            status = "predecision_unknown"
        else:
            side = "asks" if direction > 0 else "bids"
            price, depth = signal[f"{side}[0].price"], signal[f"{side}[0].amount"]
            quantity = math.floor(min(1000 / price, .1 * depth) / quantity_step + 1e-10) * quantity_step
            raw_limit = price * (1 + direction * .0005)
            limit = (math.floor(raw_limit / tick) if direction > 0 else math.ceil(raw_limit / tick)) * tick
            rec.update(quantity=quantity, limit=limit, signal_price=price, signal_depth=depth,
                       signal_local_us=int(signal["quote_local_us"]), signal_exchange_us=int(signal["quote_exchange_us"]))
            if quantity <= 0 or quantity * price < 100:
                status = "predecision_size"
            elif cash_hi < quantity * price * 1.02:
                status = "predecision_capital"
            elif cash_lo < quantity * price * 1.02:
                rows.append({**rec, "status": "unresolved_capital_branch", "complete": False})
                halted = True
                continue
        if status:
            rows.append({**rec, "status": status, "complete": True, "pnl_lower": 0., "pnl_upper": 0.})
            continue
        ent = outcomes(panels[entry_at], direction, quantity, limit)
        rec.update(entry_state_count=len(ent), entry_ties=panels[entry_at].get("timestamp_ties", 0))
        free_at = entry_at + delay
        if any(x["status"] not in ("filled", "rejected_fok") for x in ent):
            rows.append({**rec, "status": "unresolved_entry", "reason": ",".join(sorted({x["status"] for x in ent})),
                         "possible_open_quantity": quantity, "complete": False})
            halted = True
            continue
        filled = [x for x in ent if x["status"] == "filled"]
        if not filled:
            rows.append({**rec, "status": "rejected_fok", "complete": True, "pnl_lower": 0., "pnl_upper": 0.})
            continue
        optional = len(filled) != len(ent)
        end = outcomes(panels[exit_at], -direction, quantity)
        rec.update(entry_notional_lower=min(x["notional"] for x in filled),
                   entry_notional_upper=max(x["notional"] for x in filled), entry_optional=optional,
                   exit_state_count=len(end), exit_ties=panels[exit_at].get("timestamp_ties", 0))
        if any(x["status"] != "filled" for x in end):
            rows.append({**rec, "status": "unresolved_exit", "reason": ",".join(sorted({x["status"] for x in end})),
                         "open_quantity": 0. if optional else quantity, "possible_open_quantity": quantity,
                         "complete": False})
            halted = True
            continue
        amounts = [direction * (x["notional"] - e["notional"]) - rate * (x["notional"] + e["notional"])
                   for e in filled for x in end]
        gross = [direction * (x["notional"] - e["notional"]) for e in filled for x in end]
        costs = [rate * (x["notional"] + e["notional"]) for e in filled for x in end]
        if optional:
            amounts.append(0.)
            gross.append(0.)
            costs.append(0.)
        lo, hi = min(amounts), max(amounts)
        cash_lo += lo
        cash_hi += hi
        free_at = exit_at + delay
        rows.append({**rec, "status": "bounded", "complete": True,
                     "exit_notional_lower": min(x["notional"] for x in end),
                     "exit_notional_upper": max(x["notional"] for x in end), "closed_quantity": quantity,
                     "gross_lower": min(gross), "gross_upper": max(gross),
                     "cost_lower": min(costs), "cost_upper": max(costs), "pnl_lower": lo, "pnl_upper": hi,
                     "cash_lower": cash_lo, "cash_upper": cash_hi})
    return rows
