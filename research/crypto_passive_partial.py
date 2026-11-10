"""Versioned BTC trade-through replay with partial inventory and cancel clocks.

This is a counterfactual tape model, not a queue simulation or a P&L lower bound.
Every qualifying print contributes inventory; missing execution states stop a day.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from research.crypto_passive_replay import DAY_MS, STEP_MS, ceil_grid, quote_at, valid_quote


@dataclass(frozen=True)
class PartialRule:
    direction: str
    offset_bps: float
    hold_ms: int = 120_000
    quote_lifetime_ms: int = 5_000
    feed_delay_ms: int = 250
    order_delay_ms: int = 250
    maker_fee_bps: float = 2.0
    taker_fee_bps: float = 5.0
    taker_slippage_bps: float = 1.0
    ticket_dollars: float = 1000.0
    full_on_first_through: bool = False


def through_fills(trades: dict[str, np.ndarray], start: int, end: int,
                  direction: int, limit: float, quantity: float, *,
                  full_on_first_through: bool = False) -> list[dict]:
    """Consume strictly through-price, correctly signed volume in source order.

    Boundary-time prints are excluded. Full-first-print is a separate fill-model
    sensitivity test; neither version claims to bound real fills or real P&L.
    """
    left = np.searchsorted(trades["time"], start, side="right")
    right = np.searchsorted(trades["time"], end, side="left")
    price = trades["price"][left:right]
    maker = trades["buyer_maker"][left:right]
    hit = ((price < limit) & maker) if direction > 0 else ((price > limit) & ~maker)
    indices = np.flatnonzero(hit) + left
    remaining, fills = quantity, []
    for idx in indices:
        available = float(trades["quantity"][idx])
        if not np.isfinite(available) or available <= 0:
            raise ValueError("Invalid trade quantity")
        filled = remaining if full_on_first_through else min(remaining, available)
        fills.append({"time": int(trades["time"][idx]), "quantity": filled,
                      "price": float(limit), "kind": "maker", "source_index": int(idx)})
        remaining -= filled
        if remaining <= 1e-12:
            break
    return fills


def replay_partial_day(book: dict[str, np.ndarray], trades: dict[str, np.ndarray],
                       rule: PartialRule, day: str) -> dict:
    if rule.direction not in {"imbalance", "follow", "fade"}:
        raise ValueError(rule.direction)
    if rule.order_delay_ms % STEP_MS or rule.feed_delay_ms % STEP_MS:
        raise ValueError("Latency must align with the causal BBO cache")
    if rule.quote_lifetime_ms + 2 * rule.order_delay_ms >= 10_000:
        raise ValueError("Entry cancellation acknowledgement must precede next decision")
    if rule.hold_ms <= rule.quote_lifetime_ms + 3 * rule.order_delay_ms:
        raise ValueError("Hold must leave time to acknowledge entry cancellation")
    counts = {"decisions": 0, "posted": 0, "entry_rejected": 0, "entry_no_fill": 0,
              "partial_entries": 0, "mixed_exits": 0, "maker_only_exits": 0,
              "taker_only_exits": 0, "unresolved_exits": 0, "funding_exclusions": 0}
    ledger, free_at, cash = [], 0, 10000.0
    for decision in range(120_000, DAY_MS - 180_000, 10_000):
        if decision <= free_at:
            continue
        maximum_end = (decision + rule.quote_lifetime_ms + rule.hold_ms
                       + 5 * rule.order_delay_ms + STEP_MS)
        if any(decision < boundary <= maximum_end for boundary in (28_800_000, 57_600_000, DAY_MS)):
            counts["funding_exclusions"] += 1
            continue
        counts["decisions"] += 1
        state = quote_at(book, decision - rule.feed_delay_ms)
        if not valid_quote(state):
            counts["entry_rejected"] += 1
            continue
        bid, ask, bq, aq, _ = state
        mid = (bid + ask) / 2
        if rule.direction == "imbalance":
            direction = 1 if bq >= aq else -1
        else:
            old = quote_at(book, decision - rule.feed_delay_ms - 30_000)
            if not valid_quote(old):
                counts["entry_rejected"] += 1
                continue
            old_mid = (old[0] + old[1]) / 2
            if mid == old_mid:
                continue
            direction = (1 if mid > old_mid else -1) * (-1 if rule.direction == "fade" else 1)
        raw_limit = mid * (1 - direction * rule.offset_bps / 10000)
        limit = (np.floor(raw_limit * 10) if direction > 0 else np.ceil(raw_limit * 10)) / 10
        # All sizing information is visible before submission, never arrival depth.
        visible_size = bq if direction > 0 else aq
        intended = min(cash * 0.1 / limit, rule.ticket_dollars / limit, visible_size * 0.1)
        intended = np.floor(intended * 1000 + 1e-10) / 1000
        if intended <= 0 or intended * limit < 100:
            counts["entry_rejected"] += 1
            continue
        activation = decision + rule.order_delay_ms
        expiration = activation + rule.quote_lifetime_ms
        arrival = quote_at(book, activation)
        if not valid_quote(arrival):
            # A submitted order could fill even when our archived arrival book is
            # invalid. Only a no-fill tape can safely let this decision pass.
            possible = through_fills(trades, activation, expiration, direction, limit, intended,
                                     full_on_first_through=rule.full_on_first_through)
            if possible:
                counts["unresolved_exits"] += 1
                ledger.append({"date": day, "decision_ms": decision, "status": "unknown_post_only_acceptance",
                               "quantity": intended, "direction": direction, "entry": limit})
                break
            counts["entry_rejected"] += 1
            continue
        if (direction > 0 and limit >= arrival[1]) or (direction < 0 and limit <= arrival[0]):
            counts["entry_rejected"] += 1
            continue  # Exchange rejects the post-only order at its arrival.
        counts["posted"] += 1
        entry_fills = through_fills(trades, activation, expiration, direction, limit, intended,
                                    full_on_first_through=rule.full_on_first_through)
        if not entry_fills:
            counts["entry_no_fill"] += 1
            continue
        quantity = sum(f["quantity"] for f in entry_fills)
        partial_entry = quantity < intended - 1e-12
        counts["partial_entries"] += int(partial_entry)
        first_entry, last_entry = entry_fills[0]["time"], entry_fills[-1]["time"]
        # A partial entry must cancel its remainder before its exit can be sent.
        entry_finished = expiration if partial_entry else last_entry
        exit_activation = ceil_grid(entry_finished + 2 * rule.order_delay_ms)
        cancel_arrival = ceil_grid(first_entry + rule.hold_ms + rule.order_delay_ms)
        forced_arrival = cancel_arrival + 2 * rule.order_delay_ms
        target = (np.ceil(mid * 10) if direction > 0 else np.floor(mid * 10)) / 10
        arrival_exit = quote_at(book, exit_activation)
        record = {"date": day, "decision_ms": decision, "activation_ms": activation,
                  "entry_expiration_ms": expiration, "entry_ms": first_entry,
                  "last_entry_ms": last_entry, "exit_activation_ms": exit_activation,
                  "cancel_arrival_ms": cancel_arrival, "forced_arrival_ms": forced_arrival,
                  "direction": direction, "intended_quantity": float(intended),
                  "quantity": float(quantity), "entry": float(limit), "target": float(target),
                  "partial_entry": partial_entry, "entry_fills": entry_fills,
                  "arrival_depth_fraction": float(intended / (arrival[2] if direction > 0 else arrival[3]))}
        exits, failure = [], ""
        if not valid_quote(arrival_exit):
            failure = "unknown_exit_limit_arrival"
        elif (direction > 0 and arrival_exit[0] >= target) or (direction < 0 and arrival_exit[1] <= target):
            size = arrival_exit[2] if direction > 0 else arrival_exit[3]
            if quantity > size + 1e-12:
                failure = "insufficient_marketable_limit_depth"
            else:
                price = arrival_exit[0] if direction > 0 else arrival_exit[1]
                exits = [{"time": exit_activation, "quantity": quantity, "price": price,
                          "kind": "taker_target", "source_index": -1}]
        else:
            exits = through_fills(trades, exit_activation, cancel_arrival, -direction, target,
                                   quantity, full_on_first_through=rule.full_on_first_through)
            remaining = max(0.0, quantity - sum(f["quantity"] for f in exits))
            if remaining > 1e-12:
                # The old limit is canceled; wait for its acknowledgement and a
                # second outbound journey before flattening the exact remainder.
                timeout_state = quote_at(book, forced_arrival)
                if not valid_quote(timeout_state):
                    failure = "unknown_forced_exit_quote"
                elif remaining > (timeout_state[2] if direction > 0 else timeout_state[3]) + 1e-12:
                    failure = "insufficient_forced_exit_depth"
                else:
                    price = timeout_state[0] if direction > 0 else timeout_state[1]
                    exits.append({"time": forced_arrival, "quantity": remaining, "price": price,
                                  "kind": "taker_timeout", "source_index": -1})
        record["exit_fills"] = exits
        if failure:
            counts["unresolved_exits"] += 1
            record.update(status="unresolved_exit", failure=failure,
                          remaining_quantity=float(quantity - sum(f["quantity"] for f in exits)))
            ledger.append(record)
            break
        maker_qty = sum(f["quantity"] for f in exits if f["kind"] == "maker")
        taker_qty = quantity - maker_qty
        if maker_qty > 1e-12 and taker_qty > 1e-12:
            counts["mixed_exits"] += 1
        elif taker_qty > 1e-12:
            counts["taker_only_exits"] += 1
        else:
            counts["maker_only_exits"] += 1
        entry_value = quantity * limit
        exit_value = sum(f["quantity"] * f["price"] for f in exits)
        fees = entry_value * rule.maker_fee_bps / 10000
        fees += sum(f["quantity"] * f["price"] * (rule.maker_fee_bps if f["kind"] == "maker"
                    else rule.taker_fee_bps) / 10000 for f in exits)
        # Explicit extra execution-cost allowance preserves the limit-price record.
        slippage = sum(f["quantity"] * f["price"] * rule.taker_slippage_bps / 10000
                       for f in exits if f["kind"] != "maker")
        gross = direction * (exit_value - entry_value)
        pnl = gross - fees - slippage
        cash += pnl
        free_at = exits[-1]["time"] + rule.order_delay_ms
        record.update(status="priced", exit_ms=exits[-1]["time"], exit=exit_value / quantity,
                      closed_quantity=sum(f["quantity"] for f in exits), maker_exit_quantity=maker_qty,
                      taker_exit_quantity=taker_qty, gross_dollars=gross, fees=fees,
                      slippage_dollars=slippage, pnl=pnl, net_bps=pnl / entry_value * 10000)
        ledger.append(record)
    return {"date": day, "cash": cash if not counts["unresolved_exits"] else None,
            "closed_trade_pnl": cash - 10000, "complete": counts["unresolved_exits"] == 0,
            "counts": counts, "trades": ledger}
