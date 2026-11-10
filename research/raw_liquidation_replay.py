"""Exchange-native liquidation fields and a bounded two-clock taker replay."""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd

from research.cross_venue_dual_clock import physical_fill
from research.liquidation_event_replay import valid_snapshot

TAKER_SCENARIOS = {
    "base": {"delay_us": 1_000_000, "taker_bps": 6.},
    "double_fees": {"delay_us": 1_000_000, "taker_bps": 12.},
    "latency_3s": {"delay_us": 3_000_000, "taker_bps": 6.},
}


def parse_slice(payload, day, minute):
    start = pd.Timestamp(day, tz="UTC").value // 1000
    low, high = start + minute * 60_000_000, start + (minute + 10) * 60_000_000
    rows, disconnects, previous = [], 0, -1
    for sequence, line in enumerate(payload.decode("utf-8").splitlines()):
        if not line.strip():
            disconnects += 1
            continue
        stamp, encoded = line.split(" ", 1)
        local = pd.Timestamp(stamp).value // 1000
        if local < previous or not low <= local < high:
            raise ValueError("Unordered or out-of-slice capture timestamp")
        previous = local
        wrapper = json.loads(encoded)
        message = wrapper.get("data", wrapper)
        if message.get("e") != "forceOrder":
            raise ValueError("Unexpected event in filtered liquidation stream")
        order = message["o"]
        if order["s"] not in {"BTCUSDT", "SOLUSDT"} or order["S"] not in {"BUY", "SELL"}:
            raise ValueError("Unexpected instrument or side")
        original, filled, last = (float(order[key]) for key in ("q", "z", "l"))
        limit, average = float(order["p"]), float(order["ap"])
        numbers = np.array([original, filled, last, limit, average])
        if not np.isfinite(numbers).all() or (numbers < 0).any() or original <= 0 or limit <= 0:
            raise ValueError("Invalid raw order fields")
        if last > filled + 1e-9 or filled > original + 1e-9 or (filled > 0 and average <= 0):
            raise ValueError("Inconsistent executed quantity or average price")
        rows.append({"date": day, "minute_offset": minute, "source_line": sequence,
            "local_timestamp": int(local), "timestamp": int(order["T"]) * 1000,
            "event_time_us": int(message["E"]) * 1000,
            "symbol": order["s"], "side": order["S"].lower(),
            "status": order["X"], "time_in_force": order["f"],
            "original_quantity": original, "filled_quantity": filled,
            "last_fill_quantity": last, "limit_price": limit, "average_price": average,
            "executed_notional": filled * average, "legacy_proxy": last * limit})
    return rows, disconnects


def taker_replay(day, book, events, direction_rule, hold_s, scenario, *, tick_size, quantity_step):
    if direction_rule not in {"follow", "reverse"} or tick_size <= 0 or quantity_step <= 0:
        raise ValueError("Invalid direction or instrument increments")
    delay = int(scenario["delay_us"])
    cash, free_at, complete, attempts = 10000., -1, True, []
    for event in events.to_dict("records"):
        received = int(event["received_us"])
        send = received + 250_000
        entry_at = send + delay
        entry_ack = entry_at + delay
        exit_send = entry_ack + hold_s * 1_000_000
        exit_at, exit_ack = exit_send + delay, exit_send + 2 * delay
        record = {**event, "send_us": send, "entry_us": entry_at,
                  "entry_ack_us": entry_ack, "exit_send_us": exit_send,
                  "exit_us": exit_at, "exit_ack_us": exit_ack}
        if send <= free_at:
            attempts.append({**record, "status": "skipped_busy"})
            continue
        if (send - 60_000_000) // 3_600_000_000 != (exit_ack + 60_000_000) // 3_600_000_000:
            attempts.append({**record, "status": "skipped_hour_boundary"})
            continue
        signal = book.at(received, "capture")
        if signal is None or not valid_snapshot(signal):
            attempts.append({**record, "status": "predecision_unknown"})
            continue
        direction = int(event["forced_side"]) * (1 if direction_rule == "follow" else -1)
        side = "asks" if direction > 0 else "bids"
        price, depth = signal[f"{side}[0].price"], signal[f"{side}[0].amount"]
        quantity = math.floor(min(1000. / price, cash * .1 / price, .1 * depth) / quantity_step + 1e-10) * quantity_step
        raw_limit = price * (1 + direction * 5 / 10000)
        limit = (math.floor(raw_limit / tick_size) if direction > 0 else math.ceil(raw_limit / tick_size)) * tick_size
        record.update(direction=direction, intended_quantity=quantity, quantity=quantity,
            limit=limit, signal_price=price, signal_depth=depth,
            signal_local_us=signal["quote_local_us"], signal_exchange_us=signal["quote_exchange_us"])
        if quantity <= 0 or quantity * price < 100:
            attempts.append({**record, "status": "predecision_size"})
            continue
        arrival = book.at(entry_at, "exchange")
        entry = {"status": "unknown_snapshot"} if arrival is None else physical_fill(arrival, direction, quantity, limit)
        free_at = entry_ack
        if entry["status"] == "rejected_fok":
            attempts.append({**record, "status": "rejected_fok"})
            continue
        if entry["status"] != "filled":
            attempts.append({**record, "status": "unresolved_entry", "reason": entry["status"]})
            complete = False
            break
        end = book.at(exit_at, "exchange")
        exit_fill = {"status": "unknown_snapshot"} if end is None else physical_fill(end, -direction, quantity)
        if exit_fill["status"] != "filled":
            attempts.append({**record, "status": "unresolved_exit", "entry": entry["price"],
                             "open_quantity": quantity, "reason": exit_fill["status"]})
            complete = False
            break
        gross = direction * (exit_fill["notional"] - entry["notional"])
        fees = (entry["notional"] + exit_fill["notional"]) * scenario["taker_bps"] / 10000
        adverse = (entry["notional"] + exit_fill["notional"]) / 10000
        pnl = gross - fees - adverse
        cash += pnl
        free_at = exit_ack
        attempts.append({**record, "status": "priced", "entry": entry["price"], "exit": exit_fill["price"],
            "entry_levels": entry["levels"], "exit_levels": exit_fill["levels"],
            "closed_quantity": quantity, "gross": gross, "fees": fees, "adverse": adverse,
            "pnl": pnl, "net_bps": pnl / entry["notional"] * 10000,
            "entry_exchange_us": arrival["quote_exchange_us"], "exit_exchange_us": end["quote_exchange_us"]})
    return {"date": day, "complete": complete, "closed_subtotal": cash - 10000.,
            "net_dollars": cash - 10000. if complete else None, "attempts": attempts}
