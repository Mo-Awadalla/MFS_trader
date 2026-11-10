"""Frozen strict-through passive BTC screen, with a reusable causal BBO cache."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from research.crypto_passive_replay import DAY_MS, STEP_MS, PassiveRule, simulate_day

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "research_scout/navier_stokes_liquidity_v2/free_data/binance-public/futures-um/BTCUSDT"
OUTPUT = ROOT / "research_scout/crypto_passive_20260930"
CACHE = OUTPUT / "cache"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_day(day):
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / f"{day}.npz"
    audit_path = CACHE / f"{day}.json"
    if target.exists() and audit_path.exists():
        return json.loads(audit_path.read_text())
    start = pd.Timestamp(day, tz="UTC").value // 1_000_000
    n = DAY_MS // STEP_MS
    fields = ["best_bid_price", "best_ask_price", "best_bid_qty", "best_ask_qty"]
    arrays = {name: np.full(n, np.nan) for name in ["bid", "ask", "bid_qty", "ask_qty"]}
    event = np.full(n, -1, dtype=np.int64)
    book_path = RAW / day / f"BTCUSDT-bookTicker-{day}.zip"
    trade_path = RAW / day / f"BTCUSDT-aggTrades-{day}.zip"
    source_hashes = {p.name: digest(p) for p in [book_path, trade_path]}
    for p in [book_path, trade_path]:
        expected = Path(str(p) + ".CHECKSUM").read_text().split()[0]
        if source_hashes[p.name] != expected:
            raise ValueError(f"Archive checksum mismatch {day}")
    previous_time = previous_id = None
    rows = 0
    for chunk in pd.read_csv(book_path, compression="zip", chunksize=500_000,
                             usecols=["update_id", "event_time", *fields]):
        ts = chunk.event_time.to_numpy(np.int64) - start
        ids = chunk.update_id.to_numpy(np.int64)
        if (np.any(np.diff(ts) < 0) or (previous_time is not None and ts[0] < previous_time)
                or np.any(np.diff(ids) <= 0) or (previous_id is not None and ids[0] <= previous_id)):
            raise ValueError(f"Raw BBO ordering failure {day}")
        previous_time, previous_id = int(ts[-1]), int(ids[-1])
        rows += len(chunk)
        bins = ts // STEP_MS
        # Last event in each bin (still strictly before the next grid boundary).
        last = np.r_[np.flatnonzero(bins[1:] != bins[:-1]), len(bins) - 1]
        last = last[(bins[last] >= 0) & (bins[last] < n)]
        dest = bins[last]
        for name, field in zip(arrays, fields, strict=True):
            arrays[name][dest] = chunk[field].to_numpy(float)[last]
        event[dest] = ts[last]
    latest = np.maximum.accumulate(np.where(event >= 0, np.arange(n), -1))
    valid = latest >= 0
    for name, values in arrays.items():
        expanded = np.full(n, np.nan)
        expanded[valid] = values[latest[valid]]
        arrays[name] = expanded
    expanded_event = np.full(n, -1, np.int64)
    expanded_event[valid] = event[latest[valid]]
    arrays["event_ms"] = expanded_event
    trades = pd.read_csv(trade_path, compression="zip", usecols=["agg_trade_id", "price", "quantity", "transact_time", "is_buyer_maker"])
    ts = trades.transact_time.to_numpy(np.int64) - start
    ids = trades.agg_trade_id.to_numpy(np.int64)
    if np.any(np.diff(ts) < 0) or np.any(np.diff(ids) <= 0):
        raise ValueError(f"Trade ordering failure {day}")
    good = (ts >= 0) & (ts < DAY_MS)
    arrays.update(trade_time=ts[good], trade_price=trades.price.to_numpy(float)[good],
                  trade_quantity=trades.quantity.to_numpy(float)[good],
                  trade_buyer_maker=trades.is_buyer_maker.to_numpy(bool)[good])
    audit = {"date": day, "bbo_rows": rows, "trade_rows": int(good.sum()),
             "source_sha256": source_hashes, "cache_grid_ms": STEP_MS,
             "source_order_preserved": True, "fresh_bins": int(np.sum((np.arange(1, n + 1) * STEP_MS - expanded_event) <= 1000))}
    np.savez_compressed(target, **arrays)
    audit_path.write_text(json.dumps(audit, indent=2) + "\n")
    return audit


def run_day(day, scenarios):
    archive = np.load(CACHE / f"{day}.npz")
    book = {k: archive[k] for k in ["bid", "ask", "bid_qty", "ask_qty", "event_ms"]}
    trades = {k: archive["trade_" + k] for k in ["time", "price", "quantity", "buyer_maker"]}
    results = {}
    for name, config in scenarios.items():
        results[name] = simulate_day(book, trades, PassiveRule(**config), day)
    return day, results


def section(days, scenarios, name):
    audits = []
    with ProcessPoolExecutor(max_workers=2) as pool:
        for job in as_completed([pool.submit(build_day, day) for day in days]):
            a = job.result()
            audits.append(a)
            print(f"cached {a['date']}: {a['bbo_rows']:,} BBO / {a['trade_rows']:,} trades", flush=True)
    combined = {key: [] for key in scenarios}
    with ProcessPoolExecutor(max_workers=2) as pool:
        for job in as_completed([pool.submit(run_day, day, scenarios) for day in days]):
            day, results = job.result()
            for key, value in results.items():
                combined[key].append(value)
            print(f"replayed {day}", flush=True)
    summary = {}
    for key, data in combined.items():
        data.sort(key=lambda d: d["date"])
        ledger = [trade for record in data for trade in record.pop("trades")]
        pd.DataFrame(ledger).to_parquet(OUTPUT / f"{name}_{key}_trades.parquet", index=False)
        pnl = np.array([d["net_dollars"] for d in data])
        rng = np.random.default_rng(93026)
        boot = pnl[rng.integers(0, len(pnl), (20000, len(pnl)))].mean(axis=1)
        priced = [x for x in ledger if x["status"] == "priced"]
        summary[key] = {"daily": data, "net_dollars": float(pnl.sum()),
                        "trades": len(priced), "positive_days": int((pnl > 0).sum()),
                        "complete": all(d["complete"] for d in data),
                        "mean_net_bps": float(np.mean([x["net_bps"] for x in priced])) if priced else None,
                        "daily_mean_ci95": np.quantile(boot, [0.025, 0.975]).tolist(),
                        "thirty_trial_adjusted_daily_mean_lower": float(np.quantile(boot, 0.05 / 30)),
                        "net_excluding_best_day": float(pnl.sum() - pnl.max())}
    (OUTPUT / f"{name}_results.json").write_text(json.dumps(summary, indent=2) + "\n")
    (OUTPUT / f"{name}_audit.json").write_text(json.dumps(audits, indent=2) + "\n")
    return summary


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    spec_path = OUTPUT / "specification.json"
    if spec_path.exists():
        spec = json.loads(spec_path.read_text())
    else:
        spec = {"created_at_utc": datetime.now(UTC).isoformat(),
                "mechanism": "Passive spread capture with strict trade-through fills; imbalance, momentum-pullback and transient-impact-fade direction controls",
                "development": ["2023-08-15", "2023-09-15", "2023-10-15", "2023-11-15", "2023-12-15"],
                "selection": ["2024-01-15", "2024-01-21", "2024-01-28", "2024-01-31"],
                "historical_test": ["2024-03-03", "2024-03-06", "2024-03-10", "2024-03-15", "2024-03-17", "2024-03-20", "2024-03-24", "2024-03-27"],
                "new_configurations": 6, "session_configurations": 30,
                "fees": "2bps maker and 5bps taker per side; 1bp extra adverse slippage on taker exits; stress doubles fees",
                "cash": "Each date starts with $10,000, maximum $1,000 ticket; fixed initial-capital dollar P&L, not compounded portfolio wealth",
                "entry": "One-sided post-only quote 8 or 16bps from causal midpoint, every 10 seconds; 250ms feed and order latency, five-second lifetime",
                "fills": "Strictly through price and correctly signed single aggregate print at least twice own quantity, ignoring price improvement; never touch fills",
                "exit": "Old midpoint limit sent after fill acknowledgement and outbound latency, 120s timeout then bid/ask crossing. Missing exits invalidate day. Orders finished before next entry; no funding-boundary exposure",
                "sizing": "0.001BTC quantity grid; at most 10% of arrival touch depth, at least $100 notional",
                "stresses": ["double_fees", "1s_order_latency", "5x_required_print_volume"],
                "gate": "Development and selection separately: complete every scenario, >=100 base fills, >=75% positive base days, 30-trial-adjusted date-bootstrap lower>0, net excluding best day>0, all stresses net>0",
                "limits": "Historical tape is unaffected by simulated orders; BBO is not queue-level data. Selected historical days were already exposed. A survivor would need larger untouched data and measured fills.",
                "reference": "https://hftbacktest.readthedocs.io/en/latest/tutorials/Accelerated%20Backtesting.html"}
        spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    if (OUTPUT / "results.json").exists():
        raise FileExistsError("Frozen batch already completed")
    scenarios = {}
    for direction in ["imbalance", "follow", "fade"]:
        for offset in [8.0, 16.0]:
            name = f"{direction}_{int(offset)}bps"
            rule = PassiveRule(direction, offset)
            scenarios[name + "_base"] = asdict(rule)
            scenarios[name + "_double_fees"] = asdict(replace(rule, maker_fee_bps=4, taker_fee_bps=10))
            scenarios[name + "_latency_1s"] = asdict(replace(rule, order_delay_ms=1000))
            scenarios[name + "_volume_5x"] = asdict(replace(rule, required_print_multiple=5))
    development = section(spec["development"], scenarios, "development")
    survivors = []
    for name in [k.removesuffix("_base") for k in scenarios if k.endswith("_base")]:
        family = {k:v for k,v in development.items() if k.startswith(name + "_")}
        b = development[name + "_base"]
        passes = (all(v["complete"] and v["net_dollars"] > 0 for v in family.values())
                  and b["trades"] >= 100 and b["positive_days"] >= 4
                  and b["thirty_trial_adjusted_daily_mean_lower"] > 0 and b["net_excluding_best_day"] > 0)
        print(f"{name}: ${b['net_dollars']:.2f}; {b['trades']} fills; complete={b['complete']}; passes={passes}", flush=True)
        if passes:
            survivors.append(name)
    result = {"development_survivors": survivors, "selection_opened": False,
              "code_sha256": digest(ROOT / "research/crypto_passive_replay.py"),
              "verdict": "NO_DEVELOPMENT_SURVIVOR"}
    if survivors:
        selected = {k:v for k,v in scenarios.items() if any(k.startswith(name + "_") for name in survivors)}
        (OUTPUT / "frozen_selection.json").write_text(json.dumps({"survivors":survivors,"created_at_utc":datetime.now(UTC).isoformat()},indent=2))
        selection = section(spec["selection"], selected, "selection")
        result["selection_opened"] = True
        result["selection_results"] = selection
        result["verdict"] = "SELECTION_EVIDENCE_REQUIRES_REVIEW_BEFORE_FURTHER_HISTORY"
    (OUTPUT / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result["verdict"], flush=True)


if __name__ == "__main__":
    main()
