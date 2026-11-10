"""Frozen conditional source-clock halt signal and guarded quote execution."""

import json
import math

import numpy as np

NS = 1_000_000_000
PRIMARY = {"Nasdaq": "Q", "NYSE": "N", "NYSE American": "A"}


def quote_valid(r):
    values = [r[k] for k in ("bid_price", "ask_price", "bid_size", "ask_size")]
    return (np.isfinite(values).all() and min(values) > 0 and r["bid_price"] < r["ask_price"]
            and r["conditions"] == '["R"]' and bool(r["bid_exchange"]) and bool(r["ask_exchange"]))


def asof_quote(quotes, cutoff, maximum_age):
    times = quotes.timestamp.dt.as_unit("ns").astype("int64").to_numpy()
    i = int(np.searchsorted(times, cutoff, side="left"))-1
    if i < 0 or cutoff-int(times[i]) > maximum_age:
        return None
    r = quotes.iloc[i].to_dict()
    first = int(np.searchsorted(times, times[i], side="left"))
    fields = ["bid_price", "ask_price", "bid_size", "ask_size", "bid_exchange", "ask_exchange", "conditions"]
    if not quote_valid(r) or any(quotes.iloc[first:i+1][c].nunique(dropna=False) != 1 for c in fields):
        return None
    return {**r, "index": i, "source_ns": int(times[i])}


def signal(event, quotes, trades):
    result = {**event, "eligible": False}
    native = trades.timestamp.dt.as_unit("ns").astype("int64").to_numpy()
    archive = event["archive_resume_ns"]
    candidates = []
    for i in np.flatnonzero((native >= archive-5*NS) & (native <= archive+5*NS)):
        r = trades.iloc[int(i)].to_dict()
        flags = set(json.loads(r["conditions"]))
        if ("5" in flags and not flags.intersection({"Z", "L", "W", "P", "H", "U", "T"})
                and r["exchange"] == PRIMARY[event["exchange"]] and r["price"] > 0 and r["size"] > 0):
            candidates.append((int(i), r, int(native[i])))
    if not candidates:
        return {**result, "reason": "no_primary_reopening_print"}
    index, trade, reopen = candidates[0]
    if any(c[1]["price"] != trade["price"] for c in candidates if c[2] == reopen):
        return {**result, "reason": "ambiguous_reopening_print"}
    decision, cutoff = reopen+6*NS, reopen+5*NS
    result.update(reopen_ns=reopen, reopen_index=index, reopen_price=float(trade["price"]), decision_ns=decision)
    pre = asof_quote(quotes, event["halt_ns"]-NS, 5*NS)
    old = asof_quote(quotes, event["halt_ns"]-30*NS, 5*NS)
    now = asof_quote(quotes, cutoff, NS)
    if pre is None or old is None or now is None or now["source_ns"] < reopen:
        return {**result, "reason": "missing_stale_invalid_or_ambiguous_signal_quote"}
    mid, old_mid = (pre["bid_price"]+pre["ask_price"])/2, (old["bid_price"]+old["ask_price"])/2
    move = (mid/old_mid-1)*10000
    result.update(pre_move_bps=move, pre_mid=mid, old_mid=old_mid,
                  pre_index=pre["index"], old_index=old["index"], quote_index=now["index"],
                  quote_ns=now["source_ns"], bid=float(now["bid_price"]), ask=float(now["ask_price"]),
                  ask_depth=float(now["ask_size"]))
    if abs(move) < 100:
        return {**result, "reason": "prehalt_move_below_gate"}
    result["family"] = "up_continuation" if move >= 100 else "down_rebound"
    if trade["price"] < mid*1.005 or now["bid_price"] < trade["price"]:
        return {**result, "reason": "no_reopening_concession_and_support"}
    if not 2 <= now["ask_price"] <= 500 or (now["ask_price"]/now["bid_price"]-1)*10000 > 50:
        return {**result, "reason": "price_or_spread_gate"}
    quantity = int(math.floor(min(10000/(now["ask_price"]*1.01), 0.1*now["ask_size"])))
    if quantity*now["ask_price"] < 100:
        return {**result, "reason": "ticket_below_100"}
    limit = math.floor(now["ask_price"]*1.001*100+1e-9)/100
    return {**result, "eligible": True, "reason": "eligible", "quantity": quantity, "limit": limit}


def quote_window(quotes, target, radius):
    times = quotes.timestamp.dt.as_unit("ns").astype("int64").to_numpy()
    first = int(np.searchsorted(times, target-radius, side="left"))-1
    stop = int(np.searchsorted(times, target+radius, side="right"))
    if first < 0 or stop >= len(quotes):
        return None, {"first_index": first, "stop_index": stop, "reason": "unbracketed_quote_window"}
    records = quotes.iloc[first:stop].to_dict("records")
    return records, {"first_index": first, "stop_index": stop, "states": len(records),
                     "first_ns": int(times[first]), "last_ns": int(times[stop-1]),
                     "successor_ns": int(times[stop])}


def entry_state(records, quantity, limit):
    if records is None or not records or not all(quote_valid(r) for r in records):
        return "unknown_entry"
    fills = [r["ask_price"] <= limit+1e-9 and r["ask_size"] >= quantity for r in records]
    if all(fills):
        return "conditional_fill"
    if all(r["ask_price"] > limit+1e-9 for r in records):
        return "fok_price_reject"
    return "unknown_entry"


def cashflow(quantity, buy, sell, fee_multiplier=1, adverse_multiplier=1):
    gross = quantity*(sell-buy)
    fee = fee_multiplier*(2*max(1, quantity*.0075)+quantity*sell*.00003+quantity*.0002)
    adverse = adverse_multiplier*quantity*(buy+sell)*.0001
    return {"gross": gross, "fees": fee, "adverse": adverse, "net": gross-fee-adverse}


def halt_intersection(intervals, start, end):
    return any(a-NS <= end and b+NS >= start for a, b in intervals)
