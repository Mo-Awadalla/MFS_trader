"""Causal BTC-to-ETH information test with price/own-flow controls and IOC replay."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.crypto_passive_replay import DAY_MS, STEP_MS

LAGS = (1, 5, 30, 60)
PRICE = ["spread_bps", "ret_1", "ret_5", "ret_30", "ret_60", "rv_60"]
FLOW = PRICE + ["imbalance", "microprice_bps", "log_depth", "depth_change_5",
                "ofi_5", "ofi_30", "flow_5", "flow_30", "log_volume_30"]
FEATURES = {"price": ["ETH_" + name for name in PRICE],
            "own_flow": ["ETH_" + name for name in FLOW],
            "cross_flow": [prefix + name for prefix in ("ETH_", "BTC_") for name in FLOW]
                          + ["relative_ret_5", "relative_ret_30", "relative_ret_60", "relative_flow_30"]}


def states(book, targets):
    targets = np.asarray(targets, dtype=np.int64)
    if (targets % STEP_MS).any():
        raise ValueError("Off-grid target")
    idx = targets // STEP_MS - 1
    present = (idx >= 0) & (idx < len(book["bid"]))
    out = np.full((len(idx), 5), np.nan)
    for col, key in enumerate(("bid", "ask", "bid_qty", "ask_qty")):
        out[present, col] = book[key][idx[present]]
    out[present, 4] = targets[present] - book["event_ms"][idx[present]]
    invalid = (~np.isfinite(out).all(axis=1) | (out[:, :4] <= 0).any(axis=1)
               | (out[:, 0] >= out[:, 1]) | (out[:, 4] > 1000) | (out[:, 4] < 0))
    out[invalid] = np.nan
    return out


def roll_events(times, values, targets, lag_ms):
    cumulative = np.r_[0.0, np.cumsum(values, dtype=float)]
    # Both BBO and trade signals stop strictly before the feed-delayed clock.
    right = np.searchsorted(times, targets, side="left")
    left = np.searchsorted(times, targets - lag_ms, side="left")
    return cumulative[right] - cumulative[left]


def symbol_features(book, trades, targets):
    q = states(book, targets)
    bid, ask, bq, aq, _ = q.T
    mid, depth = (bid + ask) / 2, bq + aq
    with np.errstate(divide="ignore", invalid="ignore"):
        result = {"spread_bps": (ask - bid) / mid * 10000, "imbalance": (bq - aq) / depth,
                      "microprice_bps": ((ask * bq + bid * aq) / depth / mid - 1) * 10000,
                      "log_depth": np.log1p(depth)}
        for lag in LAGS:
            old = states(book, targets - lag * 1000)
            result[f"ret_{lag}"] = np.log(mid / ((old[:, 0] + old[:, 1]) / 2)) * 10000
            if lag == 5:
                result["depth_change_5"] = np.log(depth / (old[:, 2] + old[:, 3]))
        history = [np.log(np.mean(states(book, targets - lag * 1000)[:, :2], axis=1)) * 10000
                   for lag in range(0, 61, 5)]
        result["rv_60"] = np.sqrt(np.sum(np.diff(history, axis=0) ** 2, axis=0))
    # This is net top-of-book change at the sampled clock, not full-event OFI.
    grid = np.arange(1, len(book["bid"]) + 1) * STEP_MS
    sampled = states(book, grid)[:, :4]
    previous = np.vstack([np.full((1, 4), np.nan), sampled[:-1]])
    bid, ask, bq, aq = sampled.T
    pb, pa, pbq, paq = previous.T
    ofi = np.nan_to_num((bid >= pb) * bq - (bid <= pb) * pbq - (ask <= pa) * aq + (ask >= pa) * paq)
    notional = trades["price"] * trades["quantity"]
    signed = notional * np.where(trades["buyer_maker"], -1, 1)
    for lag in (5, 30):
        # <= current grid is causal because that grid contains only prior events.
        result[f"ofi_{lag}"] = np.arcsinh(roll_events(grid, ofi, targets + 1, lag * 1000) / depth)
        volume = roll_events(trades["time"], notional, targets, lag * 1000)
        flow = roll_events(trades["time"], signed, targets, lag * 1000)
        result[f"flow_{lag}"] = np.divide(flow, volume, out=np.zeros_like(flow), where=volume > 0)
        if lag == 30:
            result["log_volume_30"] = np.log1p(volume)
    return result, q


def make_panel(day, eth_book, eth_trades, btc_book, btc_trades):
    clock = np.arange(120_000, DAY_MS - 180_000, 10_000)
    features_time = clock - 250
    data = {"date": day, "decision_ms": clock}
    for symbol, book, trades in (("ETH", eth_book, eth_trades), ("BTC", btc_book, btc_trades)):
        features, quotes = symbol_features(book, trades, features_time)
        data.update({f"{symbol}_{key}": value for key, value in features.items()})
        if symbol == "ETH":
            for i, field in enumerate(("bid", "ask", "bid_qty", "ask_qty", "age")):
                data[field] = quotes[:, i]
    for lag in (5, 30, 60):
        data[f"relative_ret_{lag}"] = data[f"ETH_ret_{lag}"] - data[f"BTC_ret_{lag}"]
    data["relative_flow_30"] = data["ETH_flow_30"] - data["BTC_flow_30"]
    for delay in (1000, 3000):
        entry = states(eth_book, clock + delay)
        for i, field in enumerate(("bid", "ask", "bid_qty", "ask_qty", "age")):
            data[f"entry_{delay}_{field}"] = entry[:, i]
        for hold in (30, 120):
            end = states(eth_book, clock + delay + hold * 1000)
            for i, field in enumerate(("bid", "ask", "bid_qty", "ask_qty", "age")):
                data[f"exit_{delay}_{hold}_{field}"] = end[:, i]
            with np.errstate(invalid="ignore", divide="ignore"):
                data[f"target_{delay}_{hold}"] = np.log((end[:, 0] + end[:, 1]) / (entry[:, 0] + entry[:, 1])) * 10000
    panel = pd.DataFrame(data)
    panel["eligible"] = np.isfinite(panel[["bid", "ask", *FEATURES["price"]]]).all(axis=1)
    return panel


def replay(panel, prediction, horizon, *, fee_bps=5.0, delay_ms=1000, slippage_bps=1.0):
    work = panel.copy()
    work["prediction"] = prediction
    # The decision threshold is frozen at base costs even when stress fees rise.
    threshold = 12 + work.ETH_spread_bps + 1
    candidates = work.loc[work.eligible & (work.prediction.abs() > threshold)]
    ledger, daily = [], []
    for day in sorted(work.date.unique()):
        cash, free_at, unresolved, rejections = 10000.0, 0, 0, 0
        for row in candidates.loc[candidates.date.eq(day)].sort_values("decision_ms").to_dict("records"):
            decision = row["decision_ms"]
            if decision <= free_at:
                continue
            entry_time, exit_time = decision + delay_ms, decision + delay_ms + horizon * 1000
            if any(decision < boundary <= exit_time + delay_ms for boundary in (28_800_000, 57_600_000, DAY_MS)):
                continue
            direction = 1 if row["prediction"] > 0 else -1
            side, size = ("ask", "ask_qty") if direction > 0 else ("bid", "bid_qty")
            opposite, opposite_size = ("bid", "bid_qty") if direction > 0 else ("ask", "ask_qty")
            intended = np.floor(min(1000 / row[side], cash * .1 / row[side], row[size] * .1) * 1000) / 1000
            if intended <= 0 or intended * row[side] < 100:
                rejections += 1
                continue
            record = {"date": day, "decision_ms": decision, "direction": direction, "intended_quantity": float(intended), "prediction_bps": row["prediction"]}
            entry, available = row[f"entry_{delay_ms}_{side}"], row[f"entry_{delay_ms}_{size}"]
            if not np.isfinite([entry, available]).all():
                ledger.append(dict(record, status="unresolved_entry"))
                unresolved += 1
                break
            # A submitted IOC has a causal 5bp price collar. Available top size
            # controls its actual partial fill, not whether we chose to submit.
            price_limit = row[side] * (1 + direction * 5 / 10000)
            if direction * (entry - price_limit) > 0:
                rejections += 1
                continue
            quantity = np.floor(min(intended, available) * 1000 + 1e-10) / 1000
            if quantity <= 0:
                rejections += 1
                continue
            exit_price = row[f"exit_{delay_ms}_{horizon}_{opposite}"]
            exit_size = row[f"exit_{delay_ms}_{horizon}_{opposite_size}"]
            if not np.isfinite([exit_price, exit_size]).all() or quantity > exit_size:
                ledger.append(dict(record, quantity=float(quantity), entry=entry, status="unresolved_exit"))
                unresolved += 1
                break
            fees = quantity * (entry + exit_price) * fee_bps / 10000
            slippage = quantity * (entry + exit_price) * slippage_bps / 10000
            gross = direction * quantity * (exit_price - entry)
            pnl = gross - fees - slippage
            cash += pnl
            free_at = exit_time + delay_ms
            ledger.append(dict(record, quantity=float(quantity), entry=entry, exit=exit_price,
                               entry_ms=entry_time, exit_ms=exit_time, gross_dollars=gross,
                               fees=fees, slippage_dollars=slippage, pnl=pnl,
                               net_bps=pnl / (quantity * entry) * 10000, status="priced"))
        daily.append({"date": day, "closed_trade_pnl": cash - 10000, "complete": unresolved == 0,
                          "unresolved": unresolved, "rejected_entries": rejections})
    return pd.DataFrame(ledger), pd.DataFrame(daily)
