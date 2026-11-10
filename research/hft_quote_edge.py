"""Causal, small-order quote replay for an explicitly exploratory HFT screen.

EQUS.MINI is an anonymized aggregate BBO, not an executable NBBO or queue feed.
This module never assumes passive fills and keeps missing exits as blockers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SYMBOLS = ("SPY", "SSO", "UPRO", "SH", "SDS", "SPXU")
LEVERAGE = {"SPY": 1, "SSO": 2, "UPRO": 3, "SH": -1, "SDS": -2, "SPXU": -3}
HORIZONS = (5, 30, 120)
DELAYS_MS = (250, 1000, 3000)
PRICE_FEATURES = [
    "leverage", "clock", "spread_bps", "ret_1", "ret_5", "ret_30", "rv_30"
]
BOOK_FEATURES = PRICE_FEATURES + [
    "imbalance", "microprice_bps", "log_depth", "depth_change_5",
    "ofi_1", "ofi_5", "ofi_30", "trade_flow_5", "trade_flow_30",
    "log_trade_volume_30", "log_events_5", "quote_age_s",
]


def prior_indices(times: np.ndarray, targets: np.ndarray) -> np.ndarray:
    """Use the last completed message strictly BEFORE each clock boundary."""
    if np.any(np.diff(times) < 0):
        raise ValueError("nonmonotonic receive timestamps")
    return np.searchsorted(times, targets, side="left") - 1


def asof_state(times: np.ndarray, values: np.ndarray, targets: np.ndarray) -> np.ndarray:
    idx = prior_indices(times, targets)
    output = np.full((len(targets), values.shape[1] + 1), np.nan)
    valid = idx >= 0
    output[valid, :-1] = values[idx[valid]]
    output[valid, -1] = (targets[valid] - times[idx[valid]]) / 1e9
    return output


def rolling_sum(times: np.ndarray, values: np.ndarray, targets: np.ndarray, seconds: int):
    total = np.r_[0.0, np.cumsum(values, dtype=float)]
    right = np.searchsorted(times, targets, side="left")
    left = np.searchsorted(times, targets - seconds * 1_000_000_000, side="left")
    return total[right] - total[left]


def symbol_panel(frame: pd.DataFrame, day: str, symbol: str) -> pd.DataFrame:
    """Sample decision features and delayed marketable execution references."""
    source = frame.loc[frame.symbol.astype(str).eq(symbol)].copy()
    if source.empty:
        return pd.DataFrame()
    source = source.loc[source["flags"].astype(int) & 8 == 0]
    # F_LAST=128 marks a completed event; BAD_TS_RECV=8 invalidates the clock.
    raw = source.loc[source["flags"].astype(int) & 128 != 0]
    times = raw.ts_recv.dt.as_unit("ns").astype("int64").to_numpy()
    if np.any(np.diff(times) < 0):
        raise ValueError(f"receive clock backtrack {day} {symbol}")
    values = raw[["bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00"]].to_numpy(float)
    # Keep invalid states in the stream: dropping them would resurrect an old quote.
    bad = (~np.isfinite(values).all(axis=1) | (values <= 0).any(axis=1)
           | (values[:, 0] >= values[:, 1]) | (values[:, :2] > 1e7).any(axis=1)
           | (raw["flags"].to_numpy(int) & 4 != 0))
    values[bad] = np.nan
    start = pd.Timestamp(day + " 09:30:00", tz="America/New_York").tz_convert("UTC").value
    seconds = np.arange(30, 451, 5, dtype=np.int64)
    decision = start + seconds * 1_000_000_000
    state = asof_state(times, values, decision)
    bid, ask, bq, aq, age = state.T
    mid, depth = (bid + ask) / 2, bq + aq
    with np.errstate(divide="ignore", invalid="ignore"):
        data = {
            "date": day, "symbol": symbol, "second": seconds,
            "leverage": LEVERAGE[symbol], "clock": seconds / 600,
            "bid": bid, "ask": ask, "bid_qty": bq, "ask_qty": aq,
            "quote_age_s": age, "spread_bps": (ask - bid) / mid * 1e4,
            "imbalance": (bq - aq) / depth, "log_depth": np.log1p(depth),
            "microprice_bps": ((ask * bq + bid * aq) / depth / mid - 1) * 1e4,
        }
        for lag in (1, 5, 30):
            old = asof_state(times, values, decision - lag * 1_000_000_000)
            old_mid = (old[:, 0] + old[:, 1]) / 2
            data[f"ret_{lag}"] = np.where(old[:, -1] <= 1, np.log(mid / old_mid) * 1e4, np.nan)
            if lag == 5:
                data["depth_change_5"] = np.log(depth / (old[:, 2] + old[:, 3]))
        rv_samples = []
        for lag in range(0, 31, 5):
            old = asof_state(times, values, decision - lag * 1_000_000_000)
            rv_samples.append(np.log((old[:, 0] + old[:, 1]) / 2) * 1e4)
        data["rv_30"] = np.sqrt(np.sum(np.diff(np.array(rv_samples), axis=0) ** 2, axis=0))
    # Top-of-book order-flow imbalance, not identified cancellations or institutions.
    prev = np.vstack([np.full((1, 4), np.nan), values[:-1]])
    ofi = ((values[:, 0] >= prev[:, 0]) * values[:, 2]
           - (values[:, 0] <= prev[:, 0]) * prev[:, 2]
           - (values[:, 1] <= prev[:, 1]) * values[:, 3]
           + (values[:, 1] >= prev[:, 1]) * prev[:, 3])
    ofi = np.nan_to_num(ofi)
    for lag in (1, 5, 30):
        data[f"ofi_{lag}"] = np.arcsinh(rolling_sum(times, ofi, decision, lag) / depth)
    # Trades can precede their event's final book message; retain every trade.
    trade_rows = source.loc[source.action.astype(str).eq("T")]
    trade_times = trade_rows.ts_recv.dt.as_unit("ns").astype("int64").to_numpy()
    qty = trade_rows["size"].to_numpy(float)
    side = trade_rows.side.astype(str).to_numpy()
    signed = qty * np.where(side == "B", 1, np.where(side == "A", -1, 0))
    for lag in (5, 30):
        volume = rolling_sum(trade_times, qty, decision, lag)
        flow = rolling_sum(trade_times, signed, decision, lag)
        data[f"trade_flow_{lag}"] = np.divide(flow, volume, out=np.zeros_like(flow), where=volume > 0)
        if lag == 30:
            data["log_trade_volume_30"] = np.log1p(volume)
    data["log_events_5"] = np.log1p(rolling_sum(times, np.ones(len(times)), decision, 5))
    for delay in DELAYS_MS:
        entry = asof_state(times, values, decision + delay * 1_000_000)
        for j, name in enumerate(("bid", "ask", "bid_qty", "ask_qty", "age")):
            data[f"entry_{delay}_{name}"] = entry[:, j]
        for horizon in HORIZONS:
            end = asof_state(times, values, decision + delay * 1_000_000 + horizon * 1_000_000_000)
            for j, name in enumerate(("bid", "ask", "bid_qty", "ask_qty", "age")):
                data[f"exit_{delay}_{horizon}_{name}"] = end[:, j]
            valid = (entry[:, -1] <= 1) & (end[:, -1] <= 1)
            data[f"target_{delay}_{horizon}"] = np.where(valid, (end[:, 0] / entry[:, 1] - 1) * 1e4, np.nan)
    result = pd.DataFrame(data)
    result["eligible"] = ((result.quote_age_s <= 1) & (result.ask_qty >= 10)
                          & np.isfinite(result[PRICE_FEATURES]).all(axis=1))
    return result


def cost_bps(price: np.ndarray | float, slippage_bps: float = 1.0):
    """Per-share round trip fees plus sell levies and slippage; spread is in fills."""
    return 2 * slippage_bps + (0.01 + 0.000119) / np.asarray(price) * 1e4 + 0.051


def replay(panel: pd.DataFrame, predictions: np.ndarray, horizon: int, *,
           delay: int = 250, slippage_bps: float = 1.0,
           initial_cash: float = 10_000.0, buffer_bps: float = 1.0,
           spread_stress_bps: float = 0.0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One long position at a time, integer shares, no future-conditioned selection.

    A stale/missing exit or insufficient displayed exit size blocks the path.
    Rejected entries earn zero with their own counts. No position is silently erased.
    """
    work = panel.copy()
    work["prediction"] = predictions
    work["expected_net"] = predictions - cost_bps(work.ask.to_numpy())
    dates = sorted(work.date.unique())
    candidates = work.loc[work.eligible & (work.expected_net > buffer_bps)].sort_values(
        ["date", "second", "expected_net", "symbol"], ascending=[True, True, False, True]
    ).drop_duplicates(["date", "second"])
    records = {day: rows.to_dict("records") for day, rows in candidates.groupby("date", sort=True)}
    cash = initial_cash
    ledger, daily = [], []
    for day in dates:
        start_cash = cash
        available_at = -np.inf
        unresolved = rejected = 0
        for row in records.get(day, []):
            second = row["second"]
            if second <= available_at:
                continue
            prefix = f"entry_{delay}"
            entry, entry_qty, entry_age = (row[f"{prefix}_{x}"] for x in ("ask", "ask_qty", "age"))
            intended = min(int(cash / (row["ask"] * 1.001)), int(row["ask_qty"] * 0.1))
            if not np.isfinite([entry, entry_qty, entry_age]).all() or entry_age > 1 or entry <= 0:
                rejected += 1
                continue
            fill_price = entry * (1 + (slippage_bps + spread_stress_bps / 2) / 1e4)
            quantity = min(intended, int(entry_qty * 0.1), int(cash / (fill_price + 0.005)))
            if quantity < 1:
                rejected += 1
                continue
            available_at = second + delay / 1000 + horizon
            prefix = f"exit_{delay}_{horizon}"
            exit_price, exit_qty, exit_age = (row[f"{prefix}_{x}"] for x in ("bid", "bid_qty", "age"))
            if (not np.isfinite([exit_price, exit_qty, exit_age]).all()
                    or exit_age > 1 or exit_price <= 0 or quantity > exit_qty):
                ledger.append({"date": day, "second": second, "symbol": row["symbol"],
                               "quantity": quantity, "entry": entry, "status": "unresolved_exit"})
                unresolved += 1
                break
            sell_fill = exit_price * (1 - (slippage_bps + spread_stress_bps / 2) / 1e4)
            fees = quantity * (0.01 + 0.000119) + quantity * sell_fill * 0.0000051
            pnl = quantity * (sell_fill - fill_price) - fees
            cash += pnl
            ledger.append({"date": day, "second": second, "symbol": row["symbol"],
                           "quantity": quantity, "entry": entry, "exit": exit_price,
                           "entry_second": second + delay / 1000, "exit_second": available_at,
                           "prediction_bps": row["prediction"],
                           "net_bps": pnl / (quantity * entry) * 1e4,
                           "pnl": pnl, "fees": fees, "status": "priced"})
        daily.append({"date": day, "pnl": cash - start_cash,
                      "return": cash / start_cash - 1, "cash": cash,
                      "unresolved": unresolved, "rejected_entries": rejected})
        if unresolved:
            # An unknown position invalidates subsequent portfolio accounting.
            break
    return pd.DataFrame(ledger), pd.DataFrame(daily)


def summarize(ledger: pd.DataFrame, daily: pd.DataFrame, *, trials: int = 9) -> dict:
    values = daily.pnl.to_numpy(float)
    rng = np.random.default_rng(93026)
    n = len(values)
    starts = rng.integers(0, n, (5000, (n + 4) // 5))
    idx = ((starts[:, :, None] + np.arange(5)) % n).reshape(5000, -1)[:, :n]
    bootstrap = values[idx].mean(axis=1)
    priced = ledger.loc[ledger.status.eq("priced")] if len(ledger) else ledger
    positives = np.maximum(values, 0)
    complete = int(daily.unresolved.sum()) == 0
    net = float(values.sum())
    equity = np.r_[10_000.0, daily.cash.to_numpy()]
    return {
        "complete": complete, "days": n, "trades": len(priced),
        "trade_days": int((daily.pnl != 0).sum()), "net_dollars": net,
        "total_return_pct": net / 100,
        "mean_trade_net_bps": float(priced.net_bps.mean()) if len(priced) else None,
        "positive_days": int((values > 0).sum()),
        "max_drawdown_pct": float(np.min(equity / np.maximum.accumulate(equity) - 1) * 100),
        "mean_daily_pnl_ci95": np.quantile(bootstrap, [0.025, 0.975]).tolist(),
        "mean_daily_pnl_familywise_lower": float(np.quantile(bootstrap, 0.05 / trials)),
        "best_day_share_positive_pnl": float(positives.max() / positives.sum()) if positives.sum() else None,
        "net_without_best_five_days": float(net - np.sort(values)[-5:].sum()),
        "unresolved_exits": int(daily.unresolved.sum()),
        "rejected_entries": int(daily.rejected_entries.sum()),
    }
