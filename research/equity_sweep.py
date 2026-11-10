"""Completed source sweeps and one fixed causal post-burst admission clock."""

from collections import Counter

import numpy as np

NS = 10**9


def sweep_groups(raw, prepared):
    qt, qe, bid, ask, bq, aq, valid, qsource = prepared[:8]
    ends = np.unique(np.searchsorted(qsource, np.flatnonzero(raw["action"] == b"T"), side="left"))
    groups, rejected, counters = [], [], Counter()
    for index in ends:
        counters["trade_bearing_groups"] += 1
        if index == len(qsource):
            rejected.append({"first_source": int(qsource[-1]) + 1 if len(qsource) else 0,
                             "last_source": len(raw) - 1, "reason": "incomplete_group"})
            counters["incomplete_group"] += 1
            continue
        first = int(qsource[index - 1]) + 1 if index else 0
        last = int(qsource[index])
        source = raw[first:last + 1]
        r, e = int(source["ts_recv"][-1]), int(source["ts_event"][-1])
        reason = None
        trades = source[source["action"] == b"T"]
        side = bytes(trades["side"][0])
        prices = trades["price"].astype(np.int64)
        sizes = trades["size"].astype(np.int64)
        direction = 1 if side == b"B" else -1 if side == b"A" else 0
        if not np.all(source["ts_recv"] == r) or not np.all(source["ts_event"] == e) or np.any(source["flags"] & 12):
            reason = "mixed_clocks_or_bad_group"
        elif (direction == 0 or not np.all(trades["side"] == side) or not np.all(sizes > 0)
              or not np.all((prices > 0) & (prices < 10**16))):
            reason = "unknown_mixed_side_or_invalid_trade"
        elif int(prices.max()) - int(prices.min()) < 10_000_000 or np.any(direction * np.diff(prices) < 0):
            reason = "not_monotonic_multiple_price_levels"
        elif index == 0 or not valid[index - 1]:
            reason = "invalid_immediate_prestate"
        elif not (0 < r - int(qt[index - 1]) <= 250_000_000 and 0 <= e - int(qe[index - 1]) <= 250_000_000
                  and -1_000_000 <= r - e <= NS):
            reason = "ambiguous_stale_or_inconsistent_prestate"
        else:
            pre_size = int(aq[index - 1] if direction > 0 else bq[index - 1])
            pre_price = int(ask[index - 1] if direction > 0 else bid[index - 1])
            quantity = sum(int(q) for q in sizes)
            notional = sum(int(p) * int(q) for p, q in zip(prices, sizes, strict=True))
            if np.any(direction * (prices - pre_price) < 0):
                reason = "print_inside_prestate_touch"
            elif quantity < pre_size or notional < 100_000 * NS:
                reason = "insufficient_burst_size_or_notional"
            else:
                groups.append({"burst_first_source": first, "burst_last_source": last,
                               "burst_receive_ns": r, "burst_event_ns": e, "burst_pre_quote_index": int(index) - 1,
                               "burst_quantity": quantity, "burst_notional_int": notional,
                               "burst_pre_quantity": pre_size, "direction": direction,
                               "trade_records": len(trades), "distinct_prices": len(np.unique(prices)),
                               "minimum_trade_price_int": int(prices.min()), "maximum_trade_price_int": int(prices.max()),
                               "pre_bid_int": int(bid[index - 1]), "pre_ask_int": int(ask[index - 1])})
        if reason:
            rejected.append({"first_source": first, "last_source": last, "reason": reason})
            counters[reason] += 1
    counters["prestate_qualified_sweeps"] = len(groups)
    return groups, rejected, dict(counters)


def admit(prepared, group, opening_ns):
    qt, qe, bid, ask, bq, aq, valid, qsource = prepared[:8]
    decision = opening_ns + ((group["burst_receive_ns"] + 500_000_000 - opening_ns) // 100_000_000 + 1) * 100_000_000
    if not opening_ns + 5 * NS <= decision <= opening_ns + 570 * NS:
        return None, "outside_fixed_decision_schedule"
    cutoff = decision - 250_000_000
    index = int(np.searchsorted(qt, cutoff, side="left")) - 1
    if index < 0 or not valid[index]:
        return None, "invalid_latest_signal_quote"
    if not (0 < cutoff - int(qt[index]) <= 250_000_000 and 0 < cutoff - int(qe[index]) <= 250_000_000):
        return None, "stale_signal_quote"
    if int(qt[index]) < group["burst_receive_ns"] + 250_000_000 or int(qe[index]) < group["burst_event_ns"] + 250_000_000:
        return None, "missing_postburst_quarter_second"
    if (int(ask[index]) - int(bid[index])) * 20000 > 5 * (int(ask[index]) + int(bid[index])):
        return None, "signal_spread"
    sign = group["direction"]
    if sign * (int(bid[index]) - group["pre_bid_int"]) <= 0 or sign * (int(ask[index]) - group["pre_ask_int"]) <= 0:
        return None, "both_sides_not_displaced"
    return {**group, "decision_ns": int(decision), "signal_cutoff_ns": int(cutoff),
            "signal_quote_index": index, "signal_source_index": int(qsource[index]),
            "signal_receive_ns": int(qt[index]), "signal_event_ns": int(qe[index]),
            "signal_bid_int": int(bid[index]), "signal_ask_int": int(ask[index]),
            "signal_bid_quantity": int(bq[index]), "signal_ask_quantity": int(aq[index]),
            "rule": "buy_sweep_continuation_long" if sign > 0 else "sell_sweep_reversal_long"}, None
