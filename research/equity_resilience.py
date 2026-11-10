"""Causal L1 price-resilience observations and explicitly optimistic quote screens.

All prices remain integer billionths of a dollar until Decimal cash arithmetic.
EQUS.MINI does not identify a venue or prove a private execution.
"""

from decimal import ROUND_FLOOR
from decimal import Decimal as D

import numpy as np
from numba import njit

NS = 10**9
FIELDS = ("decision_ns", "kind", "parent_decision_ns", "defended_price_int", "anchor_quantity",
          "at_level_volume", "total_volume", "distinct_trade_clocks", "signal_quote_index")


@njit(cache=False)
def detect(qt, qe, bid, ask, bq, aq, valid, qsource, tt, te, price, size, side, tvalid, tsource, grids):
    records = []
    bid_free, ask_free = -1, -1
    watch_until, watch_price, watch_parent, watch_index = -1, 0, 0, -1
    watch_qty, watch_volume, watch_total, watch_clocks = 0, 0, 0, 0
    for decision in grids:
        cutoff = decision - 250_000_000
        right = np.searchsorted(qt, cutoff, side="left") - 1
        if right < 0 or not valid[right]:
            watch_until = -1
            continue
        if not (0 < cutoff - qt[right] <= 250_000_000 and 0 < cutoff - qe[right] <= 250_000_000):
            watch_until = -1
            continue
        if (ask[right] - bid[right]) / (ask[right] + bid[right]) * 20000 > 5:
            continue
        if decision <= watch_until:
            chain_ok = True
            for j in range(watch_index, right + 1):
                if not valid[j]:
                    chain_ok = False
                    break
            if not chain_ok:
                watch_until = -1
            elif ask[right] > watch_price:
                records.append((decision, 1, watch_parent, watch_price, watch_qty,
                                watch_volume, watch_total, watch_clocks, right))
                watch_until = -1
        start = cutoff - 2_000_000_000
        left = np.searchsorted(qt, start, side="left") - 1
        if left < 0 or not valid[left]:
            continue
        if not (0 < start - qt[left] <= 250_000_000 and 0 < start - qe[left] <= 250_000_000):
            continue
        held_bid, held_ask, clean = True, True, True
        for j in range(left, right + 1):
            if not valid[j] or (j > left and qt[j] - qt[j - 1] > 250_000_000):
                clean = False
                break
            if bid[j] != bid[left]:
                held_bid = False
            if ask[j] != ask[left]:
                held_ask = False
        if not clean or not (held_bid or held_ask):
            continue
        lo, hi = np.searchsorted(tt, start, side="left"), np.searchsorted(tt, cutoff, side="left")
        total, at_bid, at_ask, bid_clocks, ask_clocks = 0, 0, 0, 0, 0
        last_bid_clock, last_ask_clock = -1, -1
        for j in range(lo, hi):
            # A final book message must have completed this trade's event by cutoff.
            if tsource[j] > qsource[right]:
                continue
            if not tvalid[j] or te[j] >= cutoff or te[j] < start:
                clean = False
                break
            total += size[j]  # Unknown-side volume remains in the denominator.
            if side[j] == -1 and price[j] == bid[left]:
                at_bid += size[j]
                if tt[j] != last_bid_clock:
                    bid_clocks += 1
                    last_bid_clock = tt[j]
            elif side[j] == 1 and price[j] == ask[left]:
                at_ask += size[j]
                if tt[j] != last_ask_clock:
                    ask_clocks += 1
                    last_ask_clock = tt[j]
        if not clean or total <= 0:
            continue
        if (held_bid and decision >= bid_free and at_bid >= 5 * bq[left]
                and 5 * at_bid >= 4 * total and bid_clocks >= 5
                and at_bid >= (10_000_000_000_000 + bid[left] - 1) // bid[left]):
            records.append((decision, 0, decision, bid[left], bq[left], at_bid, total, bid_clocks, right))
            bid_free = decision + 60_000_000_000
        if (held_ask and decision >= ask_free and at_ask >= 5 * aq[left]
                and 5 * at_ask >= 4 * total and ask_clocks >= 5
                and at_ask >= (10_000_000_000_000 + ask[left] - 1) // ask[left]):
            watch_until, watch_parent, watch_index = decision + 10_000_000_000, decision, right
            watch_price, watch_qty = ask[left], aq[left]
            watch_volume, watch_total, watch_clocks = at_ask, total, ask_clocks
            ask_free = decision + 60_000_000_000
    return records


def arrays(raw):
    qt = raw["ts_recv"].astype(np.int64)
    qe = raw["ts_event"].astype(np.int64)
    if np.any(qt < 0) or np.any(np.diff(qt) < 0):
        raise ValueError("Unusable capture clock")
    if np.any(raw["flags"] & 8):
        raise ValueError("BAD_TS_RECV record: no removal or timestamp repair")
    final = raw["flags"] & 128 != 0
    books = raw[final]
    br, be = qt[final], qe[final]
    bid, ask = books["bid_px_00"], books["ask_px_00"]
    bq, aq = books["bid_sz_00"].astype(np.int64), books["ask_sz_00"].astype(np.int64)
    valid = ((bid > 0) & (ask > bid) & (ask < 10**16) & (bq > 0) & (aq > 0)
             & (books["flags"] & 4 == 0) & (be <= br + 1_000_000) & (be >= br - NS))
    trade = raw["action"] == b"T"
    tr, te = qt[trade], qe[trade]
    price, size = raw["price"][trade], raw["size"][trade].astype(np.int64)
    side = np.where(raw["side"][trade] == b"B", 1, np.where(raw["side"][trade] == b"A", -1, 0)).astype(np.int64)
    good_trade = ((price > 0) & (price < 10**16) & (size > 0) & (raw["flags"][trade] & 4 == 0)
                  & (te <= tr + 1_000_000) & (te >= tr - NS))
    return (br, be, bid, ask, bq, aq, valid, np.flatnonzero(final),
            tr, te, price, size, side, good_trade, np.flatnonzero(trade))


def causal_quantity(ask_int, ask_quantity):
    price = D(int(ask_int)) / NS
    return min(int((D(10000) / (price * D("1.02"))).to_integral_value(rounding=ROUND_FLOOR)), int(ask_quantity) // 10)


def optimistic_cash(entry_int, exit_int, quantity, fee_multiple=1, adverse_multiple=1):
    entry, exit_price, q = D(int(entry_int)) / NS, D(int(exit_int)) / NS, D(quantity)
    gross = q * (exit_price - entry)
    commission = max(D(1), q * D("0.005")) * 2 * fee_multiple
    sell_levies = (q * exit_price * D("0.00003") + q * D("0.000166")) * fee_multiple
    adverse = q * (entry + exit_price) * D("0.0001") * adverse_multiple
    return {"gross": str(gross), "commissions": str(commission), "sell_levies": str(sell_levies),
            "adverse": str(adverse), "net": str(gross - commission - sell_levies - adverse)}


def favorable_quotes(book_arrays, lower, upper, side):
    """Future-aware diagnostic price, never an implementable timing rule."""
    times, _, bids, asks, _, _, valid, _ = book_arrays[:8]
    start = np.searchsorted(times, lower, side="left") - 1
    stop = np.searchsorted(times, upper, side="right")
    if start < 0 or stop >= len(times) or times[start] < lower - 250_000_000:
        return {"known": False, "reason": "unbracketed_or_stale_reference"}
    if not np.all(valid[start:stop]):
        return {"known": False, "reason": "invalid_book_in_reference_window"}
    values = asks[start:stop] if side == "buy" else bids[start:stop]
    if not len(values):
        return {"known": False, "reason": "empty_reference_window"}
    position = int(np.argmin(values) if side == "buy" else np.argmax(values)) + start
    return {"known": True, "price_int": int((asks if side == "buy" else bids)[position]),
            "source_quote_index": position, "source_receive_ns": int(times[position]),
            "window_lower_ns": int(lower), "window_upper_ns": int(upper)}
