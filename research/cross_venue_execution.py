"""Non-atomic FOK entry and explicit failed-leg unwinds on native L2 captures.

This is a historical execution proxy. Unknown submitted-order outcomes stop the
day; they are not reclassified as harmless rejections or zero-profit trades.
"""

from __future__ import annotations

import math

import pandas as pd

from research.liquidation_event_replay import sweep, valid_snapshot

VENUES = ("binance", "bybit")
SCENARIOS = {
    "base": {"fee_bps": 6., "feed_us": 250_000, "binance_us": 1_000_000, "bybit_us": 1_000_000},
    "double_fees": {"fee_bps": 12., "feed_us": 250_000, "binance_us": 1_000_000, "bybit_us": 1_000_000},
    "latency_3s": {"fee_bps": 6., "feed_us": 250_000, "binance_us": 3_000_000, "bybit_us": 3_000_000},
    "binance_extra_500ms": {"fee_bps": 6., "feed_us": 250_000, "binance_us": 1_500_000, "bybit_us": 1_000_000},
    "bybit_extra_500ms": {"fee_bps": 6., "feed_us": 250_000, "binance_us": 1_000_000, "bybit_us": 1_500_000},
    "optimistic_200ms": {"fee_bps": 6., "feed_us": 0, "binance_us": 200_000, "bybit_us": 200_000},
}


def timing(event, scenario, horizon):
    send = int(event["clock_us"]) + scenario["feed_us"]
    arrivals = {venue: send + scenario[f"{venue}_us"] for venue in VENUES}
    # One outbound and one return trip before the two entry outcomes are known.
    acknowledged = max(arrivals[v] + scenario[f"{v}_us"] for v in VENUES)
    exit_send = acknowledged + horizon * 1_000_000
    return {"send": send, "arrivals": arrivals, "acknowledged": acknowledged,
            "exit_send": exit_send,
            "unwind": {v: acknowledged + scenario[f"{v}_us"] for v in VENUES},
            "exits": {v: exit_send + scenario[f"{v}_us"] for v in VENUES}}


def quote_targets(events, scenarios=SCENARIOS, horizons=(30, 120)):
    rows = []
    for event in events.to_dict("records"):
        for name, scenario in scenarios.items():
            for horizon in horizons:
                t = timing(event, scenario, horizon)
                for venue in VENUES:
                    targets = {"signal": int(event["clock_us"]), "entry": t["arrivals"][venue],
                               "unwind": t["unwind"][venue], "exit": t["exits"][venue]}
                    for label, target in targets.items():
                        rows.append({**event, "scenario": name, "horizon": horizon, "venue": venue,
                                     "label": label, "target_us": target})
    return pd.DataFrame(rows)


def strict_snapshot(row):
    return bool(valid_snapshot(row) and 0 <= row["quote_age_us"] <= 250_000
                and -1000 <= row["source_delay_us"] <= 1_000_000)


def bounded_fill(row, direction, quantity, limit=None):
    if not strict_snapshot(row):
        return {"status": "unknown_snapshot"}
    return sweep(row, direction, quantity, limit)


def collar(price, direction):
    desired = price * (1 + direction / 10000)
    return (math.floor(desired * 10) if direction > 0 else math.ceil(desired * 10)) / 10


def fill_record(event, venue, label, direction, quantity, clock, fill, fee_bps):
    return {"date": event["date"], "event_id": int(event["event_id"]), "venue": venue,
            "label": label, "direction": direction, "quantity": quantity, "clock_us": clock,
            "price": fill["price"], "levels": fill["levels"], "notional": fill["notional"],
            "fee": fill["notional"] * fee_bps / 10000,
            "adverse_cost": fill["notional"] / 10000}


def simulate(quotes, events, dates, horizon, scenario_name, scenarios=SCENARIOS, fill_function=bounded_fill):
    scenario = scenarios[scenario_name]
    panel = quotes.loc[quotes.scenario.eq(scenario_name) & quotes.horizon.eq(horizon)]
    lookup = {(r["date"], int(r["event_id"]), r["venue"], r["label"]): r for r in panel.to_dict("records")}
    records, fills, daily = [], [], []
    for day in dates:
        equity = dict.fromkeys(VENUES, 5000.0)
        free_at, complete, subtotal = -1, True, 0.
        for event in events.loc[events.date.eq(day)].sort_values("clock_us").to_dict("records"):
            t = timing(event, scenario, horizon)
            record = {**event, "send_us": t["send"], "entry_ack_us": t["acknowledged"]}
            if t["send"] <= free_at:
                records.append({**record, "status": "skipped_busy"})
                continue
            # Exclude every UTC hour with a one-minute buffer, covering ordinary
            # one/two/four/eight-hour funding schedules without earning funding.
            end = max(t["exits"][v] + scenario[f"{v}_us"] for v in VENUES)
            first = (t["send"] - 60_000_000) // 3_600_000_000
            last = (end + 60_000_000) // 3_600_000_000
            if first != last:
                records.append({**record, "status": "skipped_hour_boundary"})
                continue
            long_venue = "binance" if event["direction"] == "buy_binance_sell_bybit" else "bybit"
            directions = {v: (1 if v == long_venue else -1) for v in VENUES}
            states = {v: {label: lookup[(day, int(event["event_id"]), v, label)]
                          for label in ("signal", "entry", "unwind", "exit")} for v in VENUES}
            if not all(strict_snapshot(states[v]["signal"]) for v in VENUES):
                records.append({**record, "status": "predecision_invalid_book"})
                continue  # No orders were sent and no future data were consulted.
            quantity = float(event["intended_btc"])
            for v in VENUES:
                side = "asks" if directions[v] > 0 else "bids"
                price = states[v]["signal"][f"{side}[0].price"]
                quantity = min(quantity, math.floor(.2 * equity[v] / price * 1000) / 1000)
            if quantity <= 0 or any(quantity * states[v]["signal"]["bids[0].price"] < 100 for v in VENUES):
                records.append({**record, "status": "predecision_insufficient_capital"})
                continue
            record["quantity"] = quantity
            entries, event_fills = {}, []
            for v in VENUES:
                side = "asks" if directions[v] > 0 else "bids"
                price = states[v]["signal"][f"{side}[0].price"]
                limit = collar(price, directions[v])
                entries[v] = fill_function(states[v]["entry"], directions[v], quantity, limit)
                record[f"{v}_entry_status"] = entries[v]["status"]
                record[f"{v}_limit"] = limit
                record[f"{v}_entry_quote_age_us"] = int(states[v]["entry"]["quote_age_us"])
                if entries[v]["status"] == "filled":
                    event_fills.append(fill_record(event, v, "entry", directions[v], quantity,
                                                   t["arrivals"][v], entries[v], scenario["fee_bps"]))
            unknown = [v for v in VENUES if entries[v]["status"] not in ("filled", "rejected_fok")]
            if unknown:
                # Keep every known fill and its exposure; do not report flat or
                # zero P&L just because the other venue cannot be reconstructed.
                records.append({**record, "status": "unresolved_entry", "unknown_venues": ",".join(unknown)})
                fills.extend(event_fills)
                complete = False
                break
            filled = [v for v in VENUES if entries[v]["status"] == "filled"]
            if not filled:
                free_at = t["acknowledged"]
                records.append({**record, "status": "both_rejected", "free_at_us": free_at, "pnl": 0.})
                continue
            label, clocks = ("exit", t["exits"]) if len(filled) == 2 else ("unwind", t["unwind"])
            unresolved = []
            for v in filled:
                close = fill_function(states[v][label], -directions[v], quantity)
                record[f"{v}_{label}_status"] = close["status"]
                if close["status"] != "filled":
                    unresolved.append(v)
                    continue
                event_fills.append(fill_record(event, v, label, -directions[v], quantity,
                                               clocks[v], close, scenario["fee_bps"]))
            fills.extend(event_fills)
            if unresolved:
                records.append({**record, "status": f"unresolved_{label}", "unknown_venues": ",".join(unresolved)})
                complete = False
                break
            gross = sum(-f["direction"] * f["notional"] for f in event_fills)
            fees = sum(f["fee"] for f in event_fills)
            adverse = sum(f["adverse_cost"] for f in event_fills)
            pnl = gross - fees - adverse
            subtotal += pnl
            for v in filled:
                equity[v] += sum(-f["direction"] * f["notional"] - f["fee"] - f["adverse_cost"]
                                 for f in event_fills if f["venue"] == v)
            free_at = max(clocks[v] + scenario[f"{v}_us"] for v in filled)
            records.append({**record, "status": "closed_pair" if len(filled) == 2 else "closed_single_leg",
                            "free_at_us": free_at, "gross": gross, "fees": fees, "adverse_cost": adverse, "pnl": pnl})
        daily.append({"date": day, "complete": complete, "closed_subtotal": subtotal,
                      "net_dollars": subtotal if complete else None})
    return pd.DataFrame(records), pd.DataFrame(fills), pd.DataFrame(daily)


def summarize(records, fills, daily):
    closed = records.loc[records.status.isin(["closed_pair", "closed_single_leg"])]
    complete = bool(daily.complete.all())
    gross = float(closed.gross.sum()) if len(closed) else 0.
    return {"complete": complete, "net_dollars": float(daily.closed_subtotal.sum()) if complete else None,
            "closed_subtotal": float(daily.closed_subtotal.sum()), "gross_closed_subtotal": gross,
            "closed_pairs": int((records.status == "closed_pair").sum()),
            "closed_single_legs": int((records.status == "closed_single_leg").sum()),
            "known_fill_count": len(fills), "outcomes": records.status.value_counts().to_dict(),
            "daily": daily.to_dict("records"), "edge_established": False}
