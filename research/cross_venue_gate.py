"""Fee/capacity admission for a two-venue BTCUSDT basis-convergence hypothesis.

An opening price gap is not riskless profit: separate venues, asynchronous fills,
funding, exit basis and counterparty exposures remain. This module claims no P&L.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from research.crypto_symbol_cache import digest

STEP_US = 100_000
DAY_US = 86_400_000_000
MAP = {"bid": "bids[0].price", "ask": "asks[0].price",
       "bid_qty": "bids[0].amount", "ask_qty": "asks[0].amount"}


def sampled_book(path, day, cache):
    manifest = json.loads(path.with_suffix(path.suffix + ".json").read_text())
    if digest(path) != manifest["sha256"]:
        raise ValueError("Source file hash changed")
    cache.parent.mkdir(parents=True, exist_ok=True)
    audit_path = cache.with_suffix(".json")
    if cache.exists() and audit_path.exists():
        audit = json.loads(audit_path.read_text())
        if audit["source_sha256"] != manifest["sha256"] or digest(cache) != audit["cache_sha256"]:
            raise ValueError("Cached source/hash mismatch")
        return audit
    start = pd.Timestamp(day, tz="UTC").value // 1000
    n = DAY_US // STEP_US
    arrays = {key: np.full(n, np.nan) for key in MAP}
    local_grid, exchange_grid = np.full(n, -1, np.int64), np.full(n, -1, np.int64)
    previous_local, rows = None, 0
    columns = ["local_timestamp", "timestamp", *MAP.values()]
    for chunk in pd.read_csv(path, usecols=columns, chunksize=200_000):
        local = chunk.local_timestamp.to_numpy(np.int64) - start
        exchange = chunk.timestamp.to_numpy(np.int64) - start
        if (np.diff(local) < 0).any() or (previous_local is not None and local[0] < previous_local):
            raise ValueError("Capture ordering failure")
        previous_local, rows = int(local[-1]), rows + len(chunk)
        bins = local // STEP_US
        last = np.r_[np.flatnonzero(bins[1:] != bins[:-1]), len(bins) - 1]
        last = last[(bins[last] >= 0) & (bins[last] < n)]
        destinations = bins[last]
        for key, field in MAP.items():
            arrays[key][destinations] = chunk[field].to_numpy(float)[last]
        local_grid[destinations], exchange_grid[destinations] = local[last], exchange[last]
    latest = np.maximum.accumulate(np.where(local_grid >= 0, np.arange(n), -1))
    present = latest >= 0
    for key, values in arrays.items():
        expanded = np.full(n, np.nan)
        expanded[present] = values[latest[present]]
        arrays[key] = expanded
    for key, values in (("local_us", local_grid), ("exchange_us", exchange_grid)):
        expanded = np.full(n, -1, np.int64)
        expanded[present] = values[latest[present]]
        arrays[key] = expanded
    np.savez_compressed(cache, **arrays)
    audit = {"date": day, "source_sha256": manifest["sha256"], "rows": rows,
             "cache_sha256": digest(cache), "capture_order_preserved": True,
             "grid_us": STEP_US, "boundary_policy": "Last raw message strictly before each grid endpoint; invalid final states remain invalid"}
    audit_path.write_text(json.dumps(audit, indent=2) + "\n")
    return audit


def freshness(book, clock, maximum_age_us):
    finite = np.isfinite(np.column_stack([book[key] for key in MAP])).all(axis=1)
    valid = finite & (book["bid"] > 0) & (book["ask"] > book["bid"])
    valid &= (book["bid_qty"] > 0) & (book["ask_qty"] > 0)
    valid &= (clock - book["local_us"] >= 0) & (clock - book["local_us"] <= maximum_age_us)
    source_delay = book["local_us"] - book["exchange_us"]
    valid &= (source_delay >= -1000) & (source_delay <= 1_000_000)
    return valid


def basis_gap(long_ask, short_bid):
    """Gap in bp of the mean leg price; four 7bp fills cost roughly 28bp here."""
    with np.errstate(invalid="ignore", divide="ignore"):
        return 2 * (short_bid - long_ask) / (short_bid + long_ask) * 10000


def visible_quantity(long_book, short_book):
    with np.errstate(invalid="ignore", divide="ignore"):
        maximum_price = np.maximum(long_book["ask"], short_book["bid"])
        quantity = np.minimum.reduce([1000 / maximum_price, .1 * long_book["ask_qty"], .1 * short_book["bid_qty"]])
    return np.floor(quantity * 1000) / 1000


def screen_day(a, b, day, cutoff=33.):
    if len(a["bid"]) != len(b["bid"]):
        raise ValueError("Venue cache clocks do not align")
    clock = np.arange(1, len(a["bid"]) + 1, dtype=np.int64) * STEP_US
    gaps = {"buy_binance_sell_bybit": basis_gap(a["ask"], b["bid"]),
            "buy_bybit_sell_binance": basis_gap(b["ask"], a["bid"])}
    quantities = {"buy_binance_sell_bybit": visible_quantity(a, b),
                  "buy_bybit_sell_binance": visible_quantity(b, a)}
    summary, opportunities = {}, []
    for max_age in (100_000, 250_000, 1_000_000):
        known = freshness(a, clock, max_age) & freshness(b, clock, max_age)
        window = (clock >= 60_000_000) & (clock < DAY_US - 360_000_000)
        eligible = known & window
        by_direction = {}
        for direction, gap in gaps.items():
            quantity = quantities[direction]
            long, short = (a, b) if direction == "buy_binance_sell_bybit" else (b, a)
            sized = eligible & np.isfinite(quantity) & (quantity > 0)
            sized &= quantity * np.minimum(long["ask"], short["bid"]) >= 100
            selected = gap[sized]
            gate = sized & (gap >= cutoff)
            starts = np.flatnonzero(gate & ~np.r_[False, gate[:-1]])
            by_direction[direction] = {"sized_clocks": int(sized.sum()),
                "max_opening_gap_bps": float(selected.max()) if len(selected) else None,
                "gap_quantiles_50_95_99_999": np.quantile(selected, [.5, .95, .99, .999]).tolist() if len(selected) else None,
                "clocks_above_28bp_cost_floor": int((selected >= 28).sum()),
                "clocks_above_33bp_gate": int(gate.sum()), "contiguous_gate_intervals": len(starts)}
            if max_age == 250_000:
                for idx in starts:
                    item = {"date": day, "clock_us": int(clock[idx]), "direction": direction,
                            "opening_gap_bps": float(gap[idx]), "intended_btc": float(quantity[idx]),
                            "long_ask": float(long["ask"][idx]), "short_bid": float(short["bid"][idx])}
                    # Future snapshots are diagnostic only. They never filter
                    # whether an initial opportunity is counted or an order sent.
                    for delay_ms in (200, 1000, 3000):
                        later = idx + delay_ms * 1000 // STEP_US
                        key = f"diagnostic_after_{delay_ms}ms"
                        if later >= len(clock) or not known[later]:
                            item[key] = "unknown_arrival"
                            continue
                        buy_ok = (long["ask"][later] <= long["ask"][idx] * 1.0001
                                  and long["ask_qty"][later] >= quantity[idx])
                        sell_ok = (short["bid"][later] >= short["bid"][idx] * .9999
                                   and short["bid_qty"][later] >= quantity[idx])
                        item[key] = "both_top_levels_inside_collars" if buy_ok and sell_ok else "one_or_both_legs_need_full_depth_replay"
                        item[f"gap_after_{delay_ms}ms_bps"] = float(gap[later])
                    opportunities.append(item)
        summary[str(max_age // 1000) + "ms"] = {"joint_fresh_clocks": int(eligible.sum()),
                                                   "fraction_joint_fresh": float(eligible.mean()), "directions": by_direction}
    return {"date": day, "quality_sensitivities": summary, "opportunities": opportunities}
