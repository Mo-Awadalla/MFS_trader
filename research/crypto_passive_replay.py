"""Small-order, strict trade-through BTC passive execution feasibility replay.

There are no touch fills, queue-position guesses, or free inventory disposal.
Prices remain historical replay proxies: our orders cannot change the tape.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

STEP_MS = 250
DAY_MS = 86_400_000


@dataclass(frozen=True)
class PassiveRule:
    direction: str
    offset_bps: float
    hold_ms: int = 120_000
    quote_lifetime_ms: int = 5_000
    feed_delay_ms: int = 250
    order_delay_ms: int = 250
    maker_fee_bps: float = 2.0
    taker_fee_bps: float = 5.0
    taker_slippage_bps: float = 1.0
    required_print_multiple: float = 2.0


def quote_at(book: dict[str, np.ndarray], stamp_ms: int) -> tuple[float, ...]:
    if stamp_ms % STEP_MS:
        raise ValueError("Quote clocks must be aligned to the causal cache grid")
    idx = stamp_ms // STEP_MS - 1
    if idx < 0 or idx >= len(book["bid"]):
        return (np.nan,) * 5
    return (float(book["bid"][idx]), float(book["ask"][idx]),
            float(book["bid_qty"][idx]), float(book["ask_qty"][idx]),
            float(stamp_ms - book["event_ms"][idx]))


def valid_quote(quote: tuple[float, ...]) -> bool:
    bid, ask, bq, aq, age = quote
    return bool(np.isfinite(quote).all() and 0 < bid < ask and bq > 0 and aq > 0 and 0 <= age <= 1000)


def ceil_grid(stamp_ms: int) -> int:
    return ((int(stamp_ms) + STEP_MS - 1) // STEP_MS) * STEP_MS


def first_trade_through(trades: dict[str, np.ndarray], start: int, end: int,
                        direction: int, limit: float, quantity: float,
                        required_multiple: float) -> int:
    """A buy needs an aggressive sell strictly below its limit (and vice versa)."""
    left = np.searchsorted(trades["time"], start, side="right")
    right = np.searchsorted(trades["time"], end, side="left")
    price = trades["price"][left:right]
    maker = trades["buyer_maker"][left:right]
    qualifies = ((price < limit) & maker) if direction > 0 else ((price > limit) & ~maker)
    qualifies &= trades["quantity"][left:right] >= quantity * required_multiple
    where = np.flatnonzero(qualifies)
    return int(left + where[0]) if len(where) else -1


def simulate_day(book: dict[str, np.ndarray], trades: dict[str, np.ndarray],
                 rule: PassiveRule, day: str) -> dict:
    """One $1,000 ticket maximum, no overlapping orders/positions, flat before funding.

    Entry quotes expire before the next decision, avoiding a cancel/replace fill
    race. Exit acknowledgement also must precede the next entry decision.
    An unobservable market exit invalidates the remainder; never drop that trade.
    """
    ledger = []
    free_at = 0
    counters = {"decisions": 0, "posted": 0, "entry_rejected": 0,
                "entry_no_fill": 0, "maker_exits": 0, "taker_exits": 0,
                "unresolved_exits": 0, "funding_exclusions": 0}
    cash = 10000.0
    for decision in range(120_000, DAY_MS - 180_000, 10_000):
        if decision <= free_at:
            continue
        maximum_end = decision + rule.order_delay_ms + rule.quote_lifetime_ms + rule.hold_ms + 4 * rule.order_delay_ms
        if any(decision < boundary <= maximum_end for boundary in (28_800_000, 57_600_000, DAY_MS)):
            counters["funding_exclusions"] += 1
            continue
        counters["decisions"] += 1
        q = quote_at(book, decision - rule.feed_delay_ms)
        if not valid_quote(q):
            counters["entry_rejected"] += 1
            continue
        bid, ask, bq, aq, _ = q
        mid = (bid + ask) / 2
        if rule.direction == "imbalance":
            direction = 1 if bq >= aq else -1
        else:
            old = quote_at(book, decision - rule.feed_delay_ms - 30_000)
            if not valid_quote(old):
                counters["entry_rejected"] += 1
                continue
            old_mid = (old[0] + old[1]) / 2
            if mid == old_mid:
                continue
            direction = 1 if mid > old_mid else -1
            if rule.direction == "fade":
                direction *= -1
            elif rule.direction != "follow":
                raise ValueError(rule.direction)
        raw_limit = mid * (1 - direction * rule.offset_bps / 10000)
        limit = np.floor(raw_limit * 10) / 10 if direction > 0 else np.ceil(raw_limit * 10) / 10
        quantity = np.floor(min(cash * 0.1, 1000.0) / limit * 1000) / 1000
        if quantity <= 0 or quantity * limit < 100:
            counters["entry_rejected"] += 1
            continue
        activation = decision + rule.order_delay_ms
        expiration = activation + rule.quote_lifetime_ms
        if expiration + rule.order_delay_ms >= decision + 10_000:
            raise ValueError("Pending entry may race the next decision")
        arrival = quote_at(book, activation)
        if not valid_quote(arrival):
            counters["entry_rejected"] += 1
            continue
        if ((direction > 0 and limit >= arrival[1]) or (direction < 0 and limit <= arrival[0])
                or quantity > 0.1 * (arrival[2] if direction > 0 else arrival[3])):
            counters["entry_rejected"] += 1
            continue
        counters["posted"] += 1
        index = first_trade_through(trades, activation, expiration, direction, limit,
                                    quantity, rule.required_print_multiple)
        if index < 0:
            counters["entry_no_fill"] += 1
            continue
        entry_time = int(trades["time"][index])
        entry_fee = quantity * limit * rule.maker_fee_bps / 10000
        # Returning to the old fair price is the target; no forward price selects it.
        target = np.ceil(mid * 10) / 10 if direction > 0 else np.floor(mid * 10) / 10
        exit_activation = ceil_grid(entry_time + 2 * rule.order_delay_ms)
        timeout = ceil_grid(entry_time + rule.hold_ms + rule.order_delay_ms)
        exit_arrival = quote_at(book, exit_activation)
        exit_time, exit_price, exit_kind = -1, np.nan, ""
        if not valid_quote(exit_arrival):
            counters["unresolved_exits"] += 1
            ledger.append({"date": day, "decision_ms": decision, "entry_ms": entry_time,
                           "direction": direction, "quantity": quantity, "entry": limit,
                           "status": "unresolved_exit"})
            break
        # A plain limit may be immediately marketable when it reaches the venue.
        if ((direction > 0 and exit_arrival[0] >= target)
                or (direction < 0 and exit_arrival[1] <= target)):
            if quantity <= (exit_arrival[2] if direction > 0 else exit_arrival[3]):
                exit_time = exit_activation
                exit_price = exit_arrival[0] if direction > 0 else exit_arrival[1]
                exit_kind = "taker_target"
        else:
            index_exit = first_trade_through(trades, exit_activation, timeout, -direction,
                                             target, quantity, rule.required_print_multiple)
            if index_exit >= 0:
                exit_time = int(trades["time"][index_exit])
                exit_price = target
                exit_kind = "maker_target"
            else:
                timeout_quote = quote_at(book, timeout)
                if valid_quote(timeout_quote) and quantity <= (timeout_quote[2] if direction > 0 else timeout_quote[3]):
                    exit_time = timeout
                    exit_price = timeout_quote[0] if direction > 0 else timeout_quote[1]
                    exit_kind = "taker_timeout"
        if exit_time < 0:
            counters["unresolved_exits"] += 1
            ledger.append({"date": day, "decision_ms": decision, "entry_ms": entry_time,
                           "direction": direction, "quantity": quantity, "entry": limit,
                           "status": "unresolved_exit"})
            break
        taker = exit_kind != "maker_target"
        if taker:
            exit_price *= 1 - direction * rule.taker_slippage_bps / 10000
            counters["taker_exits"] += 1
        else:
            counters["maker_exits"] += 1
        exit_fee = quantity * exit_price * (rule.taker_fee_bps if taker else rule.maker_fee_bps) / 10000
        pnl = direction * quantity * (exit_price - limit) - entry_fee - exit_fee
        cash += pnl
        free_at = exit_time + rule.order_delay_ms
        ledger.append({"date": day, "decision_ms": decision, "activation_ms": activation,
                       "entry_ms": entry_time, "exit_activation_ms": exit_activation,
                       "exit_ms": exit_time, "direction": direction, "quantity": quantity,
                       "entry": limit, "exit": exit_price, "exit_kind": exit_kind,
                       "gross_bps": direction * (exit_price / limit - 1) * 10000,
                       "pnl": pnl, "fees": entry_fee + exit_fee,
                       "net_bps": pnl / (quantity * limit) * 10000, "status": "priced"})
    return {"date": day, "cash": cash, "net_dollars": cash - 10000,
            "complete": counters["unresolved_exits"] == 0, "counts": counters, "trades": ledger}
