"""Conditional quote-reference CPI HFT economics; actual routing unverified."""

import math

import numpy as np

from research.halt_hft import NS, cashflow, entry_state, quote_valid

SCENARIOS = {"base": {}, "double_fees": {"fee_multiplier": 2},
             "3s_outgoing_and_return": {"delay_seconds": 3},
             "double_adverse": {"adverse_multiplier": 2},
             "100ms_alignment": {"radius_ns": 100000000}, "10s_news_delay": {"news_seconds": 10}}


def quote_window(quotes, target, radius):
    """Retain all tied predecessor states as well as every in-window update."""
    times = quotes.timestamp.dt.as_unit("ns").astype("int64").to_numpy()
    predecessor = int(np.searchsorted(times, target-radius, side="left"))-1
    stop = int(np.searchsorted(times, target+radius, side="right"))
    if predecessor < 0 or stop >= len(quotes):
        return None, {"first_index": predecessor, "stop_index": stop, "reason": "unbracketed_quote_window"}
    first = int(np.searchsorted(times, times[predecessor], side="left"))
    records = quotes.iloc[first:stop].to_dict("records")
    return records, {"first_index": first, "stop_index": stop, "states": len(records),
                     "first_ns": int(times[first]), "last_ns": int(times[stop-1]),
                     "successor_ns": int(times[stop])}


def known_order(quotes, release_ns, news_seconds=2):
    decision = release_ns+news_seconds*NS
    cutoff = decision-NS
    result = {"decision_ns": decision, "source_cutoff_ns": cutoff}
    times = quotes.timestamp.dt.as_unit("ns").astype("int64").to_numpy()
    i = int(np.searchsorted(times, cutoff, side="left"))-1
    if i < 0 or times[i] < release_ns:
        return {**result, "status": "no_postrelease_decision_quote"}
    first = int(np.searchsorted(times, times[i], side="left"))
    tied = quotes.iloc[first:i+1]
    columns = ["bid_price", "ask_price", "bid_size", "ask_size", "conditions", "bid_exchange", "ask_exchange"]
    if tied[columns].nunique(dropna=False).gt(1).any():
        return {**result, "status": "unknown_tied_signal_state"}
    row = quotes.iloc[i].to_dict()
    result.update(quote_index=i, quote_ns=int(times[i]))
    if not quote_valid(row):
        return {**result, "status": "no_order_invalid_signal_quote"}
    if (row["ask_price"]/row["bid_price"]-1)*10000 > 20:
        return {**result, "status": "no_order_spread_gate"}
    quantity = int(math.floor(min(10000/(row["ask_price"]*1.01), .10*row["ask_size"])))
    if quantity*row["ask_price"] < 100:
        return {**result, "status": "no_order_ticket_below_100"}
    result.update(quantity=quantity, limit=math.floor(row["ask_price"]*1.001*100+1e-9)/100,
                  known_ask=float(row["ask_price"]), known_ask_depth=float(row["ask_size"]), status="order_planned")
    return result


def replay(quotes, release_ns, hold_seconds, *, delay_seconds=1, news_seconds=2,
           fee_multiplier=1, adverse_multiplier=1, radius_ns=1000000):
    order = known_order(quotes, release_ns, news_seconds)
    result = {**order, "conditional_complete": not order["status"].startswith("unknown"),
              "net_lower": 0., "net_upper": 0., "actual_execution_verified": False}
    if order["status"] != "order_planned":
        if not result["conditional_complete"]:
            result.update(net_lower=None, net_upper=None)
        return result, []
    quantity = order["quantity"]
    arrival = order["decision_ns"]+250000000+delay_seconds*NS
    ack = arrival+delay_seconds*NS
    exit_target = ack+hold_seconds*NS+250000000+delay_seconds*NS
    result.update(entry_ns=arrival, ack_ns=ack, exit_ns=exit_target, radius_ns=radius_ns)
    entries, entry_meta = quote_window(quotes, arrival, radius_ns)
    entry_status = entry_state(entries, quantity, order["limit"])
    traces = [{**entry_meta, "phase": "entry", "target_ns": arrival, "radius_ns": radius_ns, "quantity": quantity}]
    result["status"] = entry_status
    if entry_status == "fok_price_reject":
        return result, traces
    if entry_status != "conditional_fill":
        return {**result, "conditional_complete": False, "net_lower": None, "net_upper": None}, traces
    exits, exit_meta = quote_window(quotes, exit_target, radius_ns)
    traces.append({**exit_meta, "phase": "exit", "target_ns": exit_target, "radius_ns": radius_ns, "quantity": quantity})
    if exits is None or not all(quote_valid(r) and r["bid_size"] >= quantity for r in exits):
        return {**result, "status": "unknown_exit_state_or_depth", "conditional_complete": False,
                "net_lower": None, "net_upper": None}, traces
    buy_low, buy_high = min(r["ask_price"] for r in entries), max(r["ask_price"] for r in entries)
    sell_low, sell_high = min(r["bid_price"] for r in exits), max(r["bid_price"] for r in exits)
    lower = cashflow(quantity, buy_high, sell_low, fee_multiplier, adverse_multiplier)
    upper = cashflow(quantity, buy_low, sell_high, fee_multiplier, adverse_multiplier)
    result.update(status="conditional_round_trip", buy_lower=buy_low, buy_upper=buy_high,
                  sell_lower=sell_low, sell_upper=sell_high, net_lower=lower["net"], net_upper=upper["net"],
                  gross_lower=lower["gross"], gross_upper=upper["gross"],
                  fees_lower_path=lower["fees"], adverse_lower_path=lower["adverse"])
    return result, traces
