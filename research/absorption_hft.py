"""Seconds-long displayed-price resilience and subsequent-break hypotheses.

This is a sampled-book observation, not identification of an iceberg, a trader,
or all market liquidity. Signal data use receipt time; fills use venue time.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from numba import njit

from research.cross_venue_dual_clock import physical_fill
from research.cross_venue_gate import STEP_US, freshness
from research.liquidation_event_replay import valid_snapshot

SCENARIOS = {
    "base": {"delay_us": 250000, "taker_bps": 6., "adverse_bps": 1.},
    "double_fees": {"delay_us": 250000, "taker_bps": 12., "adverse_bps": 1.},
    "latency_1s": {"delay_us": 1000000, "taker_bps": 6., "adverse_bps": 1.},
    "latency_3s": {"delay_us": 3000000, "taker_bps": 6., "adverse_bps": 1.},
    "extra_slippage": {"delay_us": 250000, "taker_bps": 6., "adverse_bps": 2.},
}
EVENT_FIELDS = ["received_us", "kind_code", "direction", "parent_us", "defended_price",
                "anchor_depth", "at_level_volume", "total_volume", "volume_multiple", "signed_share", "trade_count"]


@njit(cache=False)
def _events(bid, ask, bq, aq, known, local, exchange, price, amount, sell, tick):
    records = []
    watch_direction, watch_price, watch_parent, watch_until = 0, 0., 0, 0
    watch_depth, watch_volume, watch_total, watch_multiple, watch_share, watch_count = 0., 0., 0., 0., 0., 0
    next_support = 0
    for i in range(599, len(bid) - 600, 10):
        now = (i + 1) * 100000
        # Both mechanisms and all delays stay clear of every hourly boundary.
        in_window = (now - 60000000) // 3600000000 == (now + 115000000) // 3600000000
        if watch_direction and now > watch_until:
            watch_direction = 0
        if watch_direction and known[i]:
            broken = (bid[i] < watch_price - tick * .5 if watch_direction > 0
                      else ask[i] > watch_price + tick * .5)
            if broken and in_window:
                records.append((now, 1, -watch_direction, watch_parent, watch_price, watch_depth,
                                watch_volume, watch_total, watch_multiple, watch_share, watch_count))
                watch_direction = 0
        if now < next_support or not in_window or not known[i]:
            continue
        anchor = i - 20
        low_bid, high_ask, valid = bid[anchor], ask[anchor], True
        for j in range(anchor, i + 1):
            if not known[j]:
                valid = False
                break
            low_bid, high_ask = min(low_bid, bid[j]), max(high_ask, ask[j])
        if not valid:
            continue
        left = np.searchsorted(local, now - 2000000, side="left")
        right = np.searchsorted(local, now, side="left")
        total, at_bid, at_ask = 0., 0., 0.
        for j in range(left, right):
            if exchange[j] >= now or local[j] - exchange[j] > 1000000 or local[j] - exchange[j] < -1000:
                valid = False
                break
            total += amount[j]
            if sell[j] and abs(price[j] - bid[anchor]) <= tick * .4:
                at_bid += amount[j]
            elif not sell[j] and abs(price[j] - ask[anchor]) <= tick * .4:
                at_ask += amount[j]
        if not valid or total <= 0:
            continue
        direction, level, depth, volume = 0, 0., 0., 0.
        if (low_bid >= bid[anchor] - tick * .4 and at_bid >= 5 * bq[anchor]
                and at_bid / total >= .8 and at_bid * bid[anchor] >= 10000):
            direction, level, depth, volume = 1, bid[anchor], bq[anchor], at_bid
        elif (high_ask <= ask[anchor] + tick * .4 and at_ask >= 5 * aq[anchor]
              and at_ask / total >= .8 and at_ask * ask[anchor] >= 10000):
            direction, level, depth, volume = -1, ask[anchor], aq[anchor], at_ask
        if not direction:
            continue
        multiple, share = volume / depth, volume / total
        records.append((now, 0, direction, now, level, depth, volume, total, multiple, share, right - left))
        watch_direction, watch_price, watch_parent, watch_until = direction, level, now, now + 10000000
        watch_depth, watch_volume, watch_total = depth, volume, total
        watch_multiple, watch_share, watch_count = multiple, share, right - left
        next_support = now + 60000000
    return records


def detect_events(book, trades, tick):
    clock = np.arange(1, len(book["bid"]) + 1, dtype=np.int64) * STEP_US
    known = freshness(book, clock, 500000)
    records = _events(book["bid"], book["ask"], book["bid_qty"], book["ask_qty"], known,
                      trades["local_us"], trades["exchange_us"], trades["price"], trades["amount"], trades["sell"], tick)
    frame = pd.DataFrame(records, columns=EVENT_FIELDS)
    for field in ("received_us", "kind_code", "direction", "parent_us", "trade_count"):
        frame[field] = frame[field].astype(np.int64)
    frame["mechanism"] = np.where(frame.kind_code.eq(0), "hold_fade", "break_follow")
    frame["event_id"] = np.arange(len(frame))
    return frame


def targets(events):
    records = []
    for event in events.to_dict("records"):
        d, event_id = int(event["received_us"]), int(event["event_id"])
        records.append({"event_id": event_id, "label": "signal", "target_us": d})
        for delay in (250000, 1000000, 3000000):
            entry = d + 250000 + delay
            records.append({"event_id": event_id, "label": f"entry_{delay}", "target_us": entry})
            for hold in (15, 30):
                records.append({"event_id": event_id, "label": f"exit_{delay}_{hold}",
                                "target_us": entry + 2 * delay + hold * 1000000})
    return pd.DataFrame(records, columns=["event_id", "label", "target_us"])


def replay(events, quotes, mechanism, hold, scenario, tick, quantity_step):
    index = {(r["event_id"], r["label"]): r for r in quotes.to_dict("records")}
    rows, cash, halted, free_at = [], 10000., False, -1
    for event in events.loc[events.mechanism.eq(mechanism)].to_dict("records"):
        record = dict(event)
        if halted:
            rows.append({**record, "status": "skipped_unresolved_inventory", "complete": False, "pnl": None})
            continue
        delay = scenario["delay_us"]
        d, key, direction = int(event["received_us"]), int(event["event_id"]), int(event["direction"])
        send, entry_at = d + 250000, d + 250000 + delay
        exit_at = entry_at + (hold * 1000000) + 2 * delay
        record.update(send_us=send, entry_us=entry_at, entry_ack_us=entry_at + delay,
                      exit_us=exit_at, exit_ack_us=exit_at + delay)
        assert send > free_at, "Frozen 60s parent cooldown should prevent overlapping inventory"
        signal = index[key, "signal"]
        if not valid_snapshot(signal):
            rows.append({**record, "status": "predecision_unknown", "complete": True, "pnl": 0.})
            continue
        side = "asks" if direction > 0 else "bids"
        price, depth = signal[f"{side}[0].price"], signal[f"{side}[0].amount"]
        quantity = math.floor(min(1000 / price, .1 * depth) / quantity_step + 1e-10) * quantity_step
        raw_limit = price * (1 + direction * .0005)
        limit = (math.floor(raw_limit / tick) if direction > 0 else math.ceil(raw_limit / tick)) * tick
        record.update(quantity=quantity, signal_price=price, signal_depth=depth, limit=limit,
                      signal_local_us=signal["quote_local_us"], signal_exchange_us=signal["quote_exchange_us"])
        if quantity <= 0 or quantity * price < 100:
            rows.append({**record, "status": "predecision_size", "complete": True, "pnl": 0.})
            continue
        if cash < quantity * price * 1.02:
            rows.append({**record, "status": "predecision_capital", "complete": True, "pnl": 0.})
            continue
        entry_quote = index[key, f"entry_{delay}"]
        entry = physical_fill(entry_quote, direction, quantity, limit)
        free_at = entry_at + delay
        if entry["status"] == "rejected_fok":
            rows.append({**record, "status": "rejected_fok", "complete": True, "pnl": 0.})
            continue
        if entry["status"] != "filled":
            rows.append({**record, "status": "unresolved_entry", "reason": entry["status"],
                         "possible_open_quantity": quantity, "complete": False, "pnl": None})
            halted = True
            continue
        end_quote = index[key, f"exit_{delay}_{hold}"]
        end = physical_fill(end_quote, -direction, quantity)
        record.update(entry=entry["price"], entry_notional=entry["notional"], entry_levels=entry["levels"],
                      entry_source_us=entry_quote["quote_exchange_us"])
        if end["status"] != "filled":
            rows.append({**record, "status": "unresolved_exit", "reason": end["status"],
                         "open_quantity": quantity, "complete": False, "pnl": None})
            halted = True
            continue
        gross = direction * (end["notional"] - entry["notional"])
        fees = (entry["notional"] + end["notional"]) * scenario["taker_bps"] / 10000
        adverse = (entry["notional"] + end["notional"]) * scenario["adverse_bps"] / 10000
        pnl = gross - fees - adverse
        cash += pnl
        free_at = exit_at + delay
        rows.append({**record, "status": "priced", "complete": True, "exit": end["price"],
                     "exit_notional": end["notional"], "exit_levels": end["levels"],
                     "exit_source_us": end_quote["quote_exchange_us"], "closed_quantity": quantity,
                     "gross": gross, "fees": fees, "adverse": adverse, "pnl": pnl, "cash_after": cash})
    return rows
