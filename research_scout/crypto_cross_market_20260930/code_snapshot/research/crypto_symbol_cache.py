"""Audited local Binance BBO/trade archives; no network or paid API calls."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.crypto_passive_replay import DAY_MS, STEP_MS

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "research_scout/navier_stokes_liquidity_v2/free_data/binance-public/futures-um"
CACHE = ROOT / "research_scout/crypto_cross_market_20260930/cache"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_symbol_day(symbol, day):
    # Reuse the audited BTC cache without rewriting its original files.
    base = (ROOT / "research_scout/crypto_passive_20260930/cache" if symbol == "BTCUSDT" else CACHE / symbol)
    base.mkdir(parents=True, exist_ok=True)
    target, audit_path = base / f"{day}.npz", base / f"{day}.json"
    if target.exists() and audit_path.exists():
        audit = json.loads(audit_path.read_text())
        return str(target), dict(audit, symbol=symbol, cache_sha256=digest(target))
    start = pd.Timestamp(day, tz="UTC").value // 1_000_000
    paths = {kind: RAW / symbol / day / f"{symbol}-{kind}-{day}.zip" for kind in ("bookTicker", "aggTrades")}
    hashes = {path.name: digest(path) for path in paths.values()}
    for path in paths.values():
        if hashes[path.name] != Path(str(path) + ".CHECKSUM").read_text().split()[0]:
            raise ValueError(f"Archive checksum mismatch: {path}")
    n = DAY_MS // STEP_MS
    field_map = {"bid": "best_bid_price", "ask": "best_ask_price", "bid_qty": "best_bid_qty", "ask_qty": "best_ask_qty"}
    arrays = {name: np.full(n, np.nan) for name in field_map}
    event = np.full(n, -1, dtype=np.int64)
    previous_time = previous_id = None
    rows = invalid_book_rows = 0
    for chunk in pd.read_csv(paths["bookTicker"], compression="zip", chunksize=500_000,
                             usecols=["update_id", "event_time", *field_map.values()]):
        ts = chunk.event_time.to_numpy(np.int64) - start
        ids = chunk.update_id.to_numpy(np.int64)
        if (np.any(np.diff(ts) < 0) or (previous_time is not None and ts[0] < previous_time)
                or np.any(np.diff(ids) <= 0) or (previous_id is not None and ids[0] <= previous_id)):
            raise ValueError(f"Raw BBO ordering failure: {symbol} {day}")
        previous_time, previous_id = int(ts[-1]), int(ids[-1])
        rows += len(chunk)
        values = chunk[list(field_map.values())].to_numpy(float)
        invalid_book_rows += int((~np.isfinite(values).all(axis=1) | (values <= 0).any(axis=1)
                                  | (values[:, 0] >= values[:, 1])).sum())
        bins = ts // STEP_MS
        last = np.r_[np.flatnonzero(bins[1:] != bins[:-1]), len(bins) - 1]
        last = last[(bins[last] >= 0) & (bins[last] < n)]
        for col, name in enumerate(field_map):
            arrays[name][bins[last]] = values[last, col]
        event[bins[last]] = ts[last]
    latest = np.maximum.accumulate(np.where(event >= 0, np.arange(n), -1))
    present = latest >= 0
    for name, values in arrays.items():
        expanded = np.full(n, np.nan)
        expanded[present] = values[latest[present]]
        arrays[name] = expanded
    expanded = np.full(n, -1, np.int64)
    expanded[present] = event[latest[present]]
    arrays["event_ms"] = expanded
    trades = pd.read_csv(paths["aggTrades"], compression="zip",
                         usecols=["agg_trade_id", "price", "quantity", "transact_time", "is_buyer_maker"])
    ts, ids = trades.transact_time.to_numpy(np.int64) - start, trades.agg_trade_id.to_numpy(np.int64)
    if np.any(np.diff(ts) < 0) or np.any(np.diff(ids) <= 0):
        raise ValueError(f"Raw trade ordering failure: {symbol} {day}")
    for key in ("price", "quantity"):
        if not np.isfinite(trades[key]).all() or (trades[key] <= 0).any():
            raise ValueError(f"Invalid raw trade {key}: {symbol} {day}")
    good = (ts >= 0) & (ts < DAY_MS)
    arrays.update(trade_time=ts[good], trade_price=trades.price.to_numpy(float)[good],
                  trade_quantity=trades.quantity.to_numpy(float)[good],
                  trade_buyer_maker=trades.is_buyer_maker.to_numpy(bool)[good])
    np.savez_compressed(target, **arrays)
    audit = {"symbol": symbol, "date": day, "bbo_rows": rows, "trade_rows": int(good.sum()),
                 "invalid_book_rows": invalid_book_rows, "source_sha256": hashes, "cache_grid_ms": STEP_MS,
                 "source_order_preserved": True, "cache_sha256": digest(target)}
    audit_path.write_text(json.dumps(audit, indent=2) + "\n")
    return str(target), audit


def load_cache(path):
    with np.load(path) as archive:
        book = {key: archive[key] for key in ("bid", "ask", "bid_qty", "ask_qty", "event_ms")}
        trades = {key: archive["trade_" + key] for key in ("time", "price", "quantity", "buyer_maker")}
    if not np.isfinite(trades["price"]).all() or not np.isfinite(trades["quantity"]).all():
        raise ValueError("Nonfinite cached trade")
    if (trades["price"] <= 0).any() or (trades["quantity"] <= 0).any() or (np.diff(trades["time"]) < 0).any():
        raise ValueError("Invalid cached trade")
    return book, trades
