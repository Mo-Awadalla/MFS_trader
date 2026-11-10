"""Immediate, causal response to previously verified Databento multi-price sweeps."""

from decimal import Decimal

import numpy as np

from research.equity_resilience import optimistic_cash

NS = 1000000000
MS = 1000000


def admit(prepared, group, opening):
    qt, qe, bid, ask, bq, aq, valid, source = prepared[:8]
    # Information cutoff strictly exceeds the complete sweep's receive timestamp.
    decision = ((group["burst_receive_ns"] + MS) // MS + 1) * MS
    if not opening + 5 * NS <= decision <= opening + 570 * NS:
        return None, "outside_schedule"
    cutoff = decision - MS
    i = int(np.searchsorted(qt, cutoff, side="left")) - 1
    if i < 0 or not valid[i] or source[i] < group["burst_last_source"]:
        return None, "invalid_or_incomplete_signal_book"
    if not (0 < cutoff - int(qt[i]) <= 5 * MS and 0 <= cutoff - int(qe[i]) <= 5 * MS):
        return None, "signal_age_or_clock"
    bp, ap, bsize, asize = map(int, (bid[i], ask[i], bq[i], aq[i]))
    if bp % 10000000 or ap % 10000000:
        return None, "noncent_signal_price"
    if 20000 * (ap - bp) > 5 * (ap + bp):
        return None, "spread"
    sign = group["direction"]
    if min(sign * (bp - group["pre_bid_int"]), sign * (ap - group["pre_ask_int"])) <= 0:
        return None, "both_sides_not_displaced"
    limit = ((ap * 102 + NS - 1) // NS) * 10000000
    quantity = min(10000 * NS // limit, bsize // 10, asize // 10)
    if quantity <= 0:
        return None, "quantity"
    cost = -Decimal(optimistic_cash(ap, bp, quantity)["net"])
    cost_bp = cost * 10000 / (Decimal(ap * quantity) / NS)
    if cost_bp > 12:
        return None, "causal_cost"
    return {**group, "decision_ns": decision, "cutoff_ns": cutoff,
            "signal_quote_index": i, "signal_source_index": int(source[i]),
            "signal_receive_ns": int(qt[i]), "signal_event_ns": int(qe[i]),
            "signal_bid_int": bp, "signal_ask_int": ap,
            "signal_bid_quantity": bsize, "signal_ask_quantity": asize,
            "quantity": quantity, "entry_limit_int": limit,
            "causal_cost_usd": str(cost), "causal_cost_bp": str(cost_bp),
            "rule": "follow_buy_sweep" if sign > 0 else "fade_sell_sweep"}, None


def select(events):
    result = []
    for rule in ("follow_buy_sweep", "fade_sell_sweep"):
        ranked = sorted((r for r in events if r["rule"] == rule),
                        key=lambda r: (r["decision_ns"], -Decimal(r["burst_quantity"]) / r["burst_pre_quantity"],
                                       -r["burst_notional_int"], r["symbol"], r["burst_last_source"]))
        last, last_symbol = -10**30, {}
        for r in ranked:
            t = r["decision_ns"]
            if t - last < 6 * NS or t - last_symbol.get(r["symbol"], -10**30) < 60 * NS:
                continue
            result.append(r)
            last, last_symbol[r["symbol"]] = t, t
    return sorted(result, key=lambda r: (r["decision_ns"], r["rule"], r["symbol"]))


def quote(prepared, arrival):
    """Fixed receive-clock reference, not an invented consolidated exchange book."""
    qt, qe, bid, ask, bq, aq, valid, source = prepared[:8]
    nxt = int(np.searchsorted(qt, arrival, side="left"))
    if nxt == 0 or nxt == len(qt):
        return None, "unbracketed_arrival"
    if qt[nxt] == arrival:
        return None, "equal_capture_clock_boundary"
    i = nxt - 1
    if not valid[i] or qe[i] > arrival or arrival - qt[i] > 250 * MS or arrival - qe[i] > 250 * MS:
        return None, "invalid_stale_or_future_native_book"
    return {"quote_index": i, "source_index": int(source[i]), "receive_ns": int(qt[i]),
            "event_ns": int(qe[i]), "bid_int": int(bid[i]), "ask_int": int(ask[i]),
            "bid_size": int(bq[i]), "ask_size": int(aq[i])}, None


def replay(event, prepared, hold_ms, case):
    entry_time = event["decision_ns"] + 50000 + case["delay_ms"] * MS + case.get("clock_shift_ms", 0) * MS
    exit_time = entry_time + hold_ms * MS
    row = {"date": event["date"], "symbol": event["symbol"], "rule": event["rule"],
           "decision_ns": event["decision_ns"], "hold_ms": hold_ms, "case": case["name"],
           "entry_arrival_ns": entry_time, "exit_arrival_ns": exit_time,
           "requested_quantity": event["quantity"], "actual_execution_verified": False,
           "net_usd": None}
    entry, reason = quote(prepared, entry_time)
    if reason:
        return {**row, "outcome": "unknown_entry_" + reason}
    row["entry_quote"] = entry
    if entry["ask_int"] > event["entry_limit_int"]:
        return {**row, "outcome": "conditional_limit_no_entry", "filled_quantity": 0, "net_usd": "0"}
    filled = min(event["quantity"], entry["ask_size"])
    row["filled_quantity"] = filled
    exit_quote, reason = quote(prepared, exit_time)
    if reason:
        return {**row, "outcome": "unknown_exit_" + reason}
    row["exit_quote"] = exit_quote
    if exit_quote["bid_size"] < filled:
        return {**row, "outcome": "unknown_exit_depth_residual_inventory"}
    cash = optimistic_cash(entry["ask_int"], exit_quote["bid_int"], filled,
                           case["fee_multiple"], case["adverse_multiple"])
    return {**row, "outcome": "conditional_priced", "net_usd": cash["net"], "cash": cash,
            "holding_ns": exit_time - entry_time}
