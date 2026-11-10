"""Completed same-clock trade bursts with causal pre/post displayed-price proof.

A source burst is not an identified aggressor or a claim about hidden orders.
Only signal data are evaluated here; no future return is calculated.
"""

from collections import Counter

import numpy as np

NS = 10**9


def completed_bursts(raw, prepared):
    qt, qe, bid, ask, bq, aq, valid, qsource = prepared[:8]
    end_positions = np.searchsorted(qsource, np.flatnonzero(raw["action"] == b"T"), side="left")
    groups, counts = [], Counter()
    for qi in np.unique(end_positions):
        counts["trade_bearing_source_groups"] += 1
        if qi >= len(qsource):
            counts["unterminated_source_group"] += 1
            continue
        end = int(qsource[qi])
        first = int(qsource[qi - 1]) + 1 if qi else 0
        group = raw[first:end + 1]
        r, e = int(group["ts_recv"][-1]), int(group["ts_event"][-1])
        if (not np.all(group["ts_recv"] == r) or not np.all(group["ts_event"] == e)
                or np.any(group["flags"] & 12)):
            counts["mixed_clocks_or_bad_group"] += 1
            continue
        trades = group[group["action"] == b"T"]
        side = trades["side"][0]
        price = int(trades["price"][0])
        if (side not in (b"A", b"B") or not np.all(trades["side"] == side)
                or not np.all(trades["price"] == price) or price <= 0 or price >= 10**16
                or not np.all(trades["size"] > 0)):
            counts["unknown_or_mixed_trade_side_price"] += 1
            continue
        if qi == 0 or not valid[qi - 1] or not valid[qi]:
            counts["invalid_pre_or_completion_book"] += 1
            continue
        pre = int(qi) - 1
        # Use the immediately prior completed state, never an older smaller quote.
        if not (0 < r - int(qt[pre]) <= 250_000_000 and 0 <= e - int(qe[pre]) <= 250_000_000
                and -1_000_000 <= r - e <= NS):
            counts["ambiguous_stale_or_inconsistent_prestate"] += 1
            continue
        pre_price = int(bid[pre] if side == b"A" else ask[pre])
        pre_qty = int(bq[pre] if side == b"A" else aq[pre])
        quantity = sum(int(v) for v in trades["size"])
        if price != pre_price:
            counts["trade_price_not_preburst_touch"] += 1
            continue
        if quantity < 5 * pre_qty or quantity * price < 10_000_000_000_000:
            counts["burst_below_size_or_notional"] += 1
            continue
        groups.append({"burst_first_source": first, "burst_last_source": end, "burst_quote_index": int(qi),
                       "burst_receive_ns": r, "burst_event_ns": e, "burst_pre_quote_index": pre,
                       "burst_pre_quantity": pre_qty, "burst_quantity": quantity,
                       "burst_trade_records": len(trades), "defended_price_int": price,
                       "kind": 0 if side == b"A" else 1})
    counts["prestate_qualified_bursts"] = len(groups)
    return groups, dict(counts)


def prove_seed(prepared, burst, decision):
    qt, qe, bid, ask, bq, aq, valid, qsource, tt, te, price, size, side, tvalid, tsource = prepared
    cutoff, start = int(decision) - 250_000_000, int(decision) - 2_250_000_000
    received = burst["burst_receive_ns"]
    if not (start <= received and received + 250_000_000 < cutoff
            and start <= burst["burst_event_ns"] < cutoff):
        return None, "burst_outside_causal_window"
    left = int(np.searchsorted(qt, start, side="left")) - 1
    right = int(np.searchsorted(qt, cutoff, side="left")) - 1
    if left < 0 or right < 0:
        return None, "missing_endpoint"
    for idx, boundary in ((left, start), (right, cutoff)):
        if not (valid[idx] and 0 < boundary - int(qt[idx]) <= 250_000_000
                and 0 < boundary - int(qe[idx]) <= 250_000_000):
            return None, "invalid_or_stale_endpoint"
    if int(qt[right]) < received + 250_000_000 or int(qe[right]) < burst["burst_event_ns"] + 250_000_000:
        return None, "missing_quarter_second_postburst_proof"
    if burst["burst_last_source"] > int(qsource[right]):
        return None, "burst_not_yet_complete"
    if not np.all(valid[left:right + 1]) or np.any(np.diff(qt[left:right + 1]) > 250_000_000):
        return None, "intervening_invalid_or_stale_book"
    if (int(ask[right]) - int(bid[right])) * 20000 > 5 * (int(ask[right]) + int(bid[right])):
        return None, "current_spread"
    prices = bid if burst["kind"] == 0 else ask
    if not np.all(prices[left:right + 1] == burst["defended_price_int"]):
        return None, "defended_price_did_not_hold"
    anchor_size = int(bq[left] if burst["kind"] == 0 else aq[left])
    if burst["burst_quantity"] < 5 * anchor_size:
        return None, "insufficient_volume_vs_anchor"
    lo, hi = np.searchsorted(tt, start, side="left"), np.searchsorted(tt, cutoff, side="left")
    indices = np.arange(lo, hi)
    indices = indices[tsource[indices] <= qsource[right]]
    if not np.all(tvalid[indices]) or np.any(te[indices] < start) or np.any(te[indices] >= cutoff):
        return None, "invalid_or_delayed_window_trade"
    total = sum(int(v) for v in size[indices])
    if 5 * burst["burst_quantity"] < 4 * total:
        return None, "burst_not_dominant_in_full_window"
    return {**burst, "decision_ns": int(decision), "parent_decision_ns": int(decision),
            "anchor_quantity": anchor_size, "at_level_volume": burst["burst_quantity"],
            "total_volume": total, "distinct_trade_clocks": 1, "signal_quote_index": right}, None


def seed_windows(prepared, groups, grids):
    seeds, reasons = [], Counter()
    for burst in groups:
        # This is only an algebraic prefilter over the frozen decision schedule.
        eligible = grids[(grids > burst["burst_receive_ns"] + 500_000_000)
                         & (grids <= burst["burst_receive_ns"] + 2_250_000_000)]
        for decision in eligible:
            row, reason = prove_seed(prepared, burst, int(decision))
            if row is None:
                reasons[reason] += 1
            else:
                seeds.append(row)
    seeds.sort(key=lambda r: (r["decision_ns"], r["kind"], -r["burst_quantity"], r["burst_last_source"]))
    return seeds, dict(reasons)


def events_from_seeds(prepared, seeds, grids):
    qt, qe, bid, ask, bq, aq, valid, qsource = prepared[:8]
    output, next_bid, next_ask = [], -1, -1
    for seed in seeds:
        decision = seed["decision_ns"]
        if seed["kind"] == 0:
            if decision >= next_bid:
                output.append(dict(seed))
                next_bid = decision + 60 * NS
            continue
        if decision < next_ask:
            continue
        next_ask = decision + 60 * NS
        for later in grids[(grids > decision) & (grids <= decision + 10 * NS)]:
            cutoff = int(later) - 250_000_000
            right = int(np.searchsorted(qt, cutoff, side="left")) - 1
            if (right < 0 or not valid[right] or not 0 < cutoff - int(qt[right]) <= 250_000_000
                    or not 0 < cutoff - int(qe[right]) <= 250_000_000):
                break
            if not np.all(valid[seed["signal_quote_index"]:right + 1]):
                break
            if (int(ask[right]) - int(bid[right])) * 20000 > 5 * (int(ask[right]) + int(bid[right])):
                continue
            if int(ask[right]) > seed["defended_price_int"]:
                output.append({**seed, "decision_ns": int(later), "signal_quote_index": right})
                break
    return sorted(output, key=lambda r: (r["decision_ns"], r["kind"]))
