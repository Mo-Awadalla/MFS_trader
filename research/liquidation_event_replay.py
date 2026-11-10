"""Receive-clock liquidation events, exact as-of L2 snapshots and bounded fills."""

from __future__ import annotations

import numpy as np
import pandas as pd

DAY_US = 86_400_000_000
FIELDS = [f"{side}s[{level}].{field}" for level in range(5)
          for side in ("ask", "bid") for field in ("price", "amount")]


def events_for_day(liquidations, day, threshold):
    start = pd.Timestamp(day, tz="UTC").value // 1000
    local = liquidations.local_timestamp.to_numpy(np.int64) - start
    if (np.diff(local) < 0).any():
        raise ValueError("Liquidation capture clock backtracks")
    notional = (liquidations.price * liquidations.amount).to_numpy()
    if not np.isfinite(notional).all() or (notional <= 0).any():
        raise ValueError("Invalid reported liquidation notional")
    if not liquidations.side.isin(["buy", "sell"]).all():
        raise ValueError("Unknown liquidation side")
    events, refractory_end = [], -1
    for idx in np.flatnonzero(notional >= threshold):
        received = int(local[idx])
        if received < 60_000_000 or received > DAY_US - 180_000_000 or received <= refractory_end:
            continue
        refractory_end = received + 300_000_000
        # Only the first large report in a five-minute refractory window counts.
        # This does not retrospectively select the largest/last report in a burst.
        quiet_clock = received + 2_000_000
        next_index = np.searchsorted(local, quiet_clock, side="left")
        quiet = next_index == idx + 1
        events.append({"date": day, "event_id": int(idx), "received_us": received,
                       "reported_notional": float(notional[idx]),
                       "forced_side": 1 if liquidations.iloc[idx].side == "buy" else -1,
                       "quiet_2s": bool(quiet)})
    return pd.DataFrame(events, columns=["date", "event_id", "received_us", "reported_notional", "forced_side", "quiet_2s"])


def quote_targets(events):
    rows = []
    for event in events.to_dict("records"):
        for mode, wait in (("immediate", 0), ("quiet", 2_000_000)):
            decision = event["received_us"] + wait + 250_000
            targets = {"signal": decision - 250_000, "prior30": decision - 30_250_000}
            for delay in (1000, 3000):
                targets[f"entry_{delay}"] = decision + delay * 1000
                for horizon in (30, 120):
                    targets[f"exit_{delay}_{horizon}"] = decision + delay * 1000 + horizon * 1_000_000
            for label, target in targets.items():
                rows.append({**event, "mode": mode, "decision_us": decision, "label": label, "target_us": target})
    return pd.DataFrame(rows)


def extract_quotes(path, day, targets):
    """Scan the entire capture stream, retaining exact prior snapshots at targets.

    Invalid final states are retained as invalid; they never resurrect earlier books.
    Duplicate capture times preserve source order; equal-time messages are excluded.
    """
    start = pd.Timestamp(day, tz="UTC").value // 1000
    requested = targets.target_us.to_numpy(np.int64)
    values = np.full((len(targets), len(FIELDS)), np.nan)
    selected_local = np.full(len(targets), -1, dtype=np.int64)
    selected_exchange = np.full(len(targets), -1, dtype=np.int64)
    previous = None
    rows = exchange_backtracks = 0
    usecols = ["timestamp", "local_timestamp", *FIELDS]
    for chunk in pd.read_csv(path, usecols=usecols, chunksize=200_000):
        local = chunk.local_timestamp.to_numpy(np.int64) - start
        exchange = chunk.timestamp.to_numpy(np.int64) - start
        if (np.diff(local) < 0).any() or (previous is not None and local[0] < previous):
            raise ValueError(f"Book capture clock backtracks: {day}")
        previous = int(local[-1])
        rows += len(chunk)
        exchange_backtracks += int((np.diff(exchange) < 0).sum())
        indices = np.searchsorted(local, requested, side="left") - 1
        valid = indices >= 0
        # Later chunks replace only with later source observations strictly before
        # the target. A target earlier than this chunk keeps its previous state.
        values[valid] = chunk[FIELDS].to_numpy(float)[indices[valid]]
        selected_local[valid] = local[indices[valid]]
        selected_exchange[valid] = exchange[indices[valid]]
    result = targets.copy()
    result[FIELDS] = values
    result["quote_local_us"] = selected_local
    result["quote_exchange_us"] = selected_exchange
    result["quote_age_us"] = requested - selected_local
    result["source_delay_us"] = selected_local - selected_exchange
    return result, {"date": day, "rows": rows, "capture_order_preserved": True,
                    "exchange_clock_backtracks_within_chunks": exchange_backtracks,
                    "requested_snapshots": len(targets)}


def valid_snapshot(row):
    if not (0 <= row["quote_age_us"] <= 1_000_000 and -1000 <= row["source_delay_us"] <= 2_000_000):
        return False
    bids = np.array([row[f"bids[{i}].price"] for i in range(5)])
    asks = np.array([row[f"asks[{i}].price"] for i in range(5)])
    sizes = np.array([row[f"{side}s[{i}].amount"] for i in range(5) for side in ("bid", "ask")])
    return bool(np.isfinite(np.r_[bids, asks, sizes]).all() and (bids > 0).all()
                and (asks > 0).all() and (sizes > 0).all() and bids[0] < asks[0]
                and (np.diff(bids) < 0).all() and (np.diff(asks) > 0).all())


def sweep(row, direction, quantity, limit=None):
    """Known five-level FOK entry / market exit proxy. Never invent deeper fills.

    FOK returns no fill when a known next level exceeds the limit. If every shown
    level is inside the limit but insufficient, unseen deeper liquidity is unknown.
    """
    if not valid_snapshot(row):
        return {"status": "unknown_snapshot"}
    side = "asks" if direction > 0 else "bids"
    remaining, value = quantity, 0.0
    for level in range(5):
        price, amount = row[f"{side}[{level}].price"], row[f"{side}[{level}].amount"]
        if limit is not None and direction * (price - limit) > 1e-10:
            return {"status": "rejected_fok"}
        take = min(remaining, amount)
        value += take * price
        remaining -= take
        if remaining <= 1e-12:
            return {"status": "filled", "price": value / quantity, "quantity": quantity,
                    "notional": value, "levels": level + 1}
    return {"status": "unknown_deeper_liquidity", "known_quantity": quantity - remaining}


def simulate(quotes, direction_rule, mode, horizon, *, fee_bps=5.0, delay_ms=1000, slippage_bps=1.0):
    if direction_rule not in {"follow", "reverse", "price_follow", "price_reverse"} or mode not in {"immediate", "quiet"}:
        raise ValueError("Unknown event rule")
    ledger, daily = [], []
    for day, day_quotes in quotes.groupby("date", sort=True):
        cash, free_at, unresolved, rejects = 10000.0, 0, 0, 0
        for _, event in day_quotes.loc[day_quotes["mode"].eq(mode)].groupby("event_id", sort=False):
            states = {row["label"]: row for row in event.to_dict("records")}
            signal = states["signal"]
            decision = signal["decision_us"]
            if decision <= free_at or (mode == "quiet" and not signal["quiet_2s"]):
                continue
            exit_clock = decision + delay_ms * 1000 + horizon * 1_000_000
            if any(decision < boundary <= exit_clock + delay_ms * 1000 for boundary in (28_800_000_000, 57_600_000_000, DAY_US)):
                continue
            if not valid_snapshot(signal):
                rejects += 1
                continue  # No order has yet been submitted.
            if direction_rule.startswith("price_"):
                old = states["prior30"]
                if not valid_snapshot(old):
                    rejects += 1
                    continue
                now_mid = (signal["asks[0].price"] + signal["bids[0].price"]) / 2
                old_mid = (old["asks[0].price"] + old["bids[0].price"]) / 2
                if now_mid == old_mid:
                    continue
                direction = (1 if now_mid > old_mid else -1) * (-1 if direction_rule == "price_reverse" else 1)
            else:
                direction = signal["forced_side"] * (-1 if direction_rule == "reverse" else 1)
            side = "asks" if direction > 0 else "bids"
            visible_price, visible_size = signal[f"{side}[0].price"], signal[f"{side}[0].amount"]
            quantity = np.floor(min(1000 / visible_price, cash * .1 / visible_price, visible_size * .1) * 1000) / 1000
            if quantity <= 0 or quantity * visible_price < 100:
                rejects += 1
                continue
            record = {"date": day, "event_id": signal["event_id"], "decision_us": decision,
                      "reported_notional": signal["reported_notional"], "direction": direction, "quantity": float(quantity)}
            # Round the causal price collar away from our desired marketability.
            limit = visible_price * (1 + direction * 5 / 10000)
            limit = (np.floor(limit * 10) if direction > 0 else np.ceil(limit * 10)) / 10
            entry = sweep(states[f"entry_{delay_ms}"], direction, quantity, limit)
            if entry["status"] == "rejected_fok":
                rejects += 1
                continue
            if entry["status"] != "filled":
                ledger.append({**record, "status": "unresolved_entry", "reason": entry["status"]})
                unresolved += 1
                break
            end = sweep(states[f"exit_{delay_ms}_{horizon}"], -direction, quantity)
            if end["status"] != "filled":
                ledger.append({**record, "status": "unresolved_exit", "entry": entry["price"], "reason": end["status"]})
                unresolved += 1
                break
            gross = direction * (end["notional"] - entry["notional"])
            fees = (end["notional"] + entry["notional"]) * fee_bps / 10000
            slippage = (end["notional"] + entry["notional"]) * slippage_bps / 10000
            pnl = gross - fees - slippage
            cash += pnl
            free_at = exit_clock + delay_ms * 1000
            ledger.append({**record, "status": "priced", "entry": entry["price"], "exit": end["price"],
                           "entry_us": decision + delay_ms * 1000, "exit_us": exit_clock,
                           "entry_levels": entry["levels"], "exit_levels": end["levels"], "gross_dollars": gross,
                           "fees": fees, "slippage_dollars": slippage, "pnl": pnl,
                           "gross_bps": gross / entry["notional"] * 10000, "net_bps": pnl / entry["notional"] * 10000})
        daily.append({"date": day, "closed_trade_subtotal": cash - 10000, "complete": unresolved == 0,
                      "unresolved": unresolved, "rejected_or_ineligible": rejects})
    return pd.DataFrame(ledger), pd.DataFrame(daily)
