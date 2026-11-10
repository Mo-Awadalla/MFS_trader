"""Event-conditioned passive fills with capture/venue clocks and exact inventory."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from research.cross_venue_dual_clock import physical_fill
from research.liquidation_event_replay import FIELDS, valid_snapshot

SCENARIOS = {
    "base": {"delay_us": 1_000_000, "maker_bps": 3., "taker_bps": 6., "fill_mode": "through_partial"},
    "double_fees": {"delay_us": 1_000_000, "maker_bps": 6., "taker_bps": 12., "fill_mode": "through_partial"},
    "latency_3s": {"delay_us": 3_000_000, "maker_bps": 3., "taker_bps": 6., "fill_mode": "through_partial"},
    "first_through_full": {"delay_us": 1_000_000, "maker_bps": 3., "taker_bps": 6., "fill_mode": "through_full"},
    "touch_partial": {"delay_us": 1_000_000, "maker_bps": 3., "taker_bps": 6., "fill_mode": "touch_partial"},
}


def window_mask(times, event_times):
    lower, upper = event_times - 35_000_000, event_times + 170_000_000
    positions = np.searchsorted(lower, times, side="right") - 1
    valid = positions >= 0
    valid[valid] &= times[valid] <= upper[positions[valid]]
    return valid


def load_event_tape(path, day, events, kind):
    start = pd.Timestamp(day, tz="UTC").value // 1000
    event_times = events.received_us.to_numpy(np.int64)
    columns = ["local_timestamp", "timestamp", *FIELDS] if kind == "book" else ["local_timestamp", "timestamp", "id", "side", "price", "amount"]
    previous_local = previous_exchange = previous_id = None
    retained, rows = [], 0
    for chunk in pd.read_csv(path, usecols=columns, chunksize=200_000):
        local = chunk.local_timestamp.to_numpy(np.int64) - start
        exchange = chunk.timestamp.to_numpy(np.int64) - start
        if (np.diff(local) < 0).any() or (previous_local is not None and local[0] < previous_local):
            raise ValueError(f"Unordered capture stream: {kind} {day}")
        if (np.diff(exchange) < 0).any() or (previous_exchange is not None and exchange[0] < previous_exchange):
            raise ValueError(f"Unordered exchange stream: {kind} {day}")
        previous_local, previous_exchange = int(local[-1]), int(exchange[-1])
        rows += len(chunk)
        if kind == "trades":
            ids = chunk.id.to_numpy(np.int64)
            if (np.diff(ids) <= 0).any() or (previous_id is not None and ids[0] <= previous_id):
                raise ValueError(f"Trade sequence is not strictly increasing: {day}")
            previous_id = int(ids[-1])
            values = chunk[["price", "amount"]].to_numpy(float)
            if not np.isfinite(values).all() or (values <= 0).any() or not chunk.side.isin(["buy", "sell"]).all():
                raise ValueError("Malformed raw trade")
        keep = window_mask(local, event_times) | window_mask(exchange, event_times)
        selected = chunk.loc[keep].copy()
        selected["local_us"], selected["exchange_us"] = local[keep], exchange[keep]
        retained.append(selected)
    result = pd.concat(retained, ignore_index=True)
    return result, {"date": day, "kind": kind, "raw_rows": rows, "retained_rows": len(result),
                    "capture_and_exchange_order_verified": True,
                    "windows": "Fixed -35s/+170s around every frozen event, selected without future price or fill conditions"}


class EventBook:
    def __init__(self, frame):
        self.local = frame.local_us.to_numpy(np.int64)
        self.exchange = frame.exchange_us.to_numpy(np.int64)
        if (np.diff(self.local) < 0).any() or (np.diff(self.exchange) < 0).any():
            raise ValueError("Unordered cached book")
        self.values = frame[FIELDS].to_numpy(float)

    def at(self, clock, role):
        axis = self.local if role == "capture" else self.exchange
        index = np.searchsorted(axis, clock, side="left") - 1
        if index < 0:
            return None
        local, exchange = int(self.local[index]), int(self.exchange[index])
        return {**dict(zip(FIELDS, self.values[index], strict=True)),
                "clock_kind": role, "quote_local_us": local, "quote_exchange_us": exchange,
                "source_delay_us": local - exchange, "quote_age_us": clock - (local if role == "capture" else exchange),
                "exchange_age_us": clock - exchange, "exchange_clock_ambiguous": False}


def entry_fills(trades, activation, cancellation, direction, limit, intended, mode):
    times = trades["exchange_us"]
    left = np.searchsorted(times, activation, side="right")
    right = np.searchsorted(times, cancellation, side="left")
    price, sell = trades["price"][left:right], trades["sell"][left:right]
    if mode == "touch_partial":
        cross = price <= limit if direction > 0 else price >= limit
    else:
        cross = price < limit if direction > 0 else price > limit
    eligible = cross & (sell if direction > 0 else ~sell)
    remaining, fills = intended, []
    for index in np.flatnonzero(eligible) + left:
        volume = float(trades["amount"][index])
        quantity = remaining if mode == "through_full" else min(remaining, volume)
        fills.append({"time_us": int(times[index]), "source_id": int(trades["id"][index]),
                      "source_price": float(trades["price"][index]), "source_amount": volume,
                      "quantity": quantity, "price": limit})
        remaining -= quantity
        if remaining <= 1e-12:
            break
    return fills


def replay(day, book, trades, events, direction_rule, offset_bps, hold_s, scenario):
    if direction_rule not in ("follow", "reverse"):
        raise ValueError("Unknown event direction")
    delay = scenario["delay_us"]
    cash, free_at, complete = 10000., -1, True
    ledger = []
    for event in events.to_dict("records"):
        received = int(event["received_us"])
        send = received + 250_000
        activation = send + delay
        cancellation = activation + 5_000_000
        acknowledged = cancellation + delay
        exit_send = acknowledged + hold_s * 1_000_000
        exit_clock = exit_send + delay
        record = {**event, "send_us": send, "activation_us": activation, "cancel_arrival_us": cancellation,
                  "cancel_ack_us": acknowledged, "exit_send_us": exit_send, "exit_us": exit_clock}
        if send <= free_at:
            ledger.append({**record, "status": "skipped_busy"})
            continue
        if (send - 60_000_000) // 3_600_000_000 != (exit_clock + delay + 60_000_000) // 3_600_000_000:
            ledger.append({**record, "status": "skipped_hour_boundary"})
            continue
        signal = book.at(received, "capture")
        if signal is None or not valid_snapshot(signal):
            ledger.append({**record, "status": "predecision_unknown"})
            continue
        direction = int(event["forced_side"]) * (1 if direction_rule == "follow" else -1)
        mid = (signal["bids[0].price"] + signal["asks[0].price"]) / 2
        raw_limit = mid * (1 - direction * offset_bps / 10000)
        limit = (math.floor(raw_limit * 10) if direction > 0 else math.ceil(raw_limit * 10)) / 10
        side = "bids" if direction > 0 else "asks"
        intended = math.floor(min(1000. / limit, cash * .1 / limit, .1 * signal[f"{side}[0].amount"]) * 1000 + 1e-10) / 1000
        record.update(direction=direction, entry=limit, intended_quantity=intended,
                      signal_local_us=signal["quote_local_us"], signal_exchange_us=signal["quote_exchange_us"],
                      signal_mid=mid, signal_depth=signal[f"{side}[0].amount"])
        if intended <= 0 or intended * limit < 100:
            ledger.append({**record, "status": "predecision_size"})
            continue
        arrival = book.at(activation, "exchange")
        # Validate the actual physical book even if the fill proxy would show no
        # trade-through. An unknown submitted order is never a harmless no-fill.
        if arrival is None or physical_fill(arrival, direction, 1e-12)["status"] != "filled":
            ledger.append({**record, "status": "unresolved_post_only"})
            complete = False
            break
        if (direction > 0 and limit >= arrival["asks[0].price"]) or (direction < 0 and limit <= arrival["bids[0].price"]):
            free_at = activation + delay
            ledger.append({**record, "status": "post_only_rejected", "free_at_us": free_at})
            continue
        fills = entry_fills(trades, activation, cancellation, direction, limit, intended, scenario["fill_mode"])
        free_at = acknowledged
        if not fills:
            ledger.append({**record, "status": "no_proxy_fill", "free_at_us": free_at})
            continue
        quantity = sum(f["quantity"] for f in fills)
        record.update(entry_fills=fills, quantity=quantity, partial_entry=quantity < intended - 1e-12)
        ending = book.at(exit_clock, "exchange")
        exit_fill = {"status": "missing_snapshot"} if ending is None else physical_fill(ending, -direction, quantity)
        if exit_fill["status"] != "filled":
            ledger.append({**record, "status": "unresolved_exit", "reason": exit_fill["status"], "open_quantity": quantity})
            complete = False
            break
        entry_value, exit_value = quantity * limit, exit_fill["notional"]
        gross = direction * (exit_value - entry_value)
        maker_fee = entry_value * scenario["maker_bps"] / 10000
        taker_fee = exit_value * scenario["taker_bps"] / 10000
        adverse = exit_value / 10000
        pnl = gross - maker_fee - taker_fee - adverse
        cash += pnl
        free_at = exit_clock + delay
        ledger.append({**record, "status": "priced", "exit": exit_fill["price"], "exit_levels": exit_fill["levels"],
                       "exit_quote_exchange_us": ending["quote_exchange_us"], "exit_quote_local_us": ending["quote_local_us"],
                       "closed_quantity": quantity, "gross": gross, "maker_fee": maker_fee, "taker_fee": taker_fee,
                       "adverse_cost": adverse, "pnl": pnl, "net_bps": pnl / entry_value * 10000, "free_at_us": free_at})
    return {"date": day, "complete": complete, "net_dollars": cash - 10000 if complete else None,
            "closed_subtotal": cash - 10000, "attempts": ledger}
