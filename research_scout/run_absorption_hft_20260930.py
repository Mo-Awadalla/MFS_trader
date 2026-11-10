"""New, frozen price-resilience/break experiment on existing BTC and SOL tapes."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from research.absorption_hft import SCENARIOS, detect_events, replay, targets
from research.cross_venue_dual_clock import extract_dual_clock
from research.cross_venue_gate import sampled_book
from research.crypto_symbol_cache import digest
from research_scout.audit_force_order_full_20260930 import ASSETS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/absorption_hft_20260930"
DATES = [f"2024-{month:02d}-01" for month in range(7, 13)]


def source_path(symbol, day, kind):
    folder = ASSETS[symbol]["source" if kind == "book_snapshot_5" else "trades"]
    return ROOT / "research_scout" / folder / "raw" / kind / day / f"{symbol}.csv.gz"


def trade_cache(symbol, day):
    path = source_path(symbol, day, "trades")
    manifest = json.loads(path.with_suffix(path.suffix + ".json").read_text())
    assert digest(path) == manifest["sha256"]
    frame = pd.read_csv(path, usecols=["local_timestamp", "timestamp", "id", "side", "price", "amount"])
    start = pd.Timestamp(day, tz="UTC").value // 1000
    values = {"local_us": frame.local_timestamp.to_numpy(np.int64) - start,
              "exchange_us": frame.timestamp.to_numpy(np.int64) - start,
              "id": frame.id.to_numpy(np.int64), "price": frame.price.to_numpy(float),
              "amount": frame.amount.to_numpy(float), "sell": frame.side.eq("sell").to_numpy()}
    assert frame.side.isin(["buy", "sell"]).all()
    assert not (np.diff(values["local_us"]) < 0).any() and not (np.diff(values["exchange_us"]) < 0).any()
    assert not (np.diff(values["id"]) <= 0).any()
    assert np.isfinite(values["price"]).all() and (values["price"] > 0).all()
    assert np.isfinite(values["amount"]).all() and (values["amount"] > 0).all()
    cache = OUT / symbol / "cache" / f"{day}_trades.npz"
    np.savez_compressed(cache, **values)
    return values, {"source_path": str(path.relative_to(ROOT)), "source_sha256": manifest["sha256"],
                    "rows": len(frame), "cache_path": str(cache.relative_to(ROOT)), "cache_sha256": digest(cache),
                    "capture_and_exchange_ordered": True, "trade_ids_strictly_increasing": True}


def process_day(symbol, day):
    folder = OUT / symbol
    source = source_path(symbol, day, "book_snapshot_5")
    cache = (ROOT / "research_scout/cross_venue_20260930/cache/binance" / f"{day}.npz"
             if symbol == "BTCUSDT" else folder / "cache" / f"{day}_book.npz")
    book_audit = sampled_book(source, day, cache)
    with np.load(cache) as arrays:
        book = {key: arrays[key] for key in arrays.files}
    trades, trade_audit = trade_cache(symbol, day)
    events = detect_events(book, trades, ASSETS[symbol]["tick_size"])
    events.insert(0, "date", day)
    events.insert(1, "symbol", symbol)
    event_path = folder / "panels" / f"{day}_events.parquet"
    events.to_parquet(event_path, index=False)
    print(f"{symbol} {day}: {events.mechanism.value_counts().to_dict()} causal events; extracting execution states", flush=True)
    requests = targets(events)
    quotes, execution_audit = extract_dual_clock(source, day, requests) if len(requests) else (requests, {"raw_rows": 0, "no_events": True})
    quote_path = folder / "panels" / f"{day}_quotes.parquet"
    quotes.to_parquet(quote_path, index=False)
    records = {}
    for mechanism in ("hold_fade", "break_follow"):
        for hold in (15, 30):
            name = f"{mechanism}_{hold}s"
            records[name] = {name: replay(events, quotes, mechanism, hold, scenario,
                                          ASSETS[symbol]["tick_size"], ASSETS[symbol]["quantity_step"])
                             for name, scenario in SCENARIOS.items()}
    audit = {"symbol": symbol, "date": day, "book_source_path": str(source.relative_to(ROOT)),
             "book_cache_path": str(cache.relative_to(ROOT)), "book": book_audit, "trades": trade_audit,
             "events_sha256": digest(event_path), "quotes_sha256": digest(quote_path),
             "events": events.mechanism.value_counts().to_dict(), "execution": execution_audit}
    return symbol, day, records, audit


def summarize(frame, days):
    daily = []
    for day in days:
        group = frame.loc[frame.date.eq(day)]
        complete = bool(group.complete.all())
        daily.append({"date": day, "complete": complete, "closed_subtotal": float(group.pnl.sum()),
                      "net_dollars": float(group.pnl.sum()) if complete else None,
                      "trades": int(group.status.eq("priced").sum())})
    complete = all(d["complete"] for d in daily)
    subtotal = sum(d["closed_subtotal"] for d in daily)
    return {"complete": complete, "net_dollars": subtotal if complete else None,
            "closed_subtotal": subtotal, "trades": sum(d["trades"] for d in daily),
            "positive_dates": sum(d["closed_subtotal"] > 0 for d in daily) if complete else None,
            "without_best_date": subtotal - max(d["closed_subtotal"] for d in daily) if complete else None,
            "outcomes": frame.status.value_counts().to_dict(), "daily": daily}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "specification.json").exists():
        raise FileExistsError("Absorption mechanism already frozen")
    for symbol in ASSETS:
        (OUT / symbol / "cache").mkdir(parents=True, exist_ok=True)
        (OUT / symbol / "panels").mkdir(parents=True, exist_ok=True)
    code = ["research/absorption_hft.py", "research/cross_venue_gate.py", "research/cross_venue_dual_clock.py",
            "research/liquidation_event_replay.py", "research_scout/run_absorption_hft_20260930.py"]
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(), "configurations": 8, "instruments": list(ASSETS),
        "development_dates": DATES[:3], "selection_dates": DATES[3:], "holds_seconds": [15, 30],
        "mechanisms": ["hold_fade", "break_follow"], "scenarios": SCENARIOS,
        "novelty": "Explicit defended-price/volume event followed by an observed level break. Separate from prior liquidation triggers and unconditioned imbalance/return models. Related flow and passive-control ideas already tested; no claim of pristine discovery.",
        "data": "Existing native Binance BTC/SOL top-five books and signed trades, six first-of-month Jul-Dec 2024 dates. All globally exposed discovery. No later data unless the frozen rule passes. Calendar samples, not continuous-year returns.",
        "signal_clock": "Every whole receipt-clock second. Use only capture times strictly earlier. Book sampled at last receipt before each 100ms endpoint. Over the prior 2s, all 21 sampled states from anchor through decision must be valid and <=500ms old with source lag -1ms..1s. This does not assert the price never changed between samples.",
        "absorption": "Sell trades exactly at anchor bid within 0.4 tick must total >=5x anchor displayed bid quantity, >=80% of ALL same-window base-coin volume, and >=$10000 at defended price; sampled bid never below anchor beyond 0.4 tick. Mirror aggressive buys against ask. Trade capture/event order must be preserved; no future exchange timestamp or trade source lag outside -1ms..1s. This is a price-resilience proxy, not proof of hidden orders or an institution.",
        "hold_fade": "Immediately trade with the defending side: buy defended bid after selling is absorbed; sell defended ask after buying is absorbed.",
        "break_follow": "After the same parent event watch for at most 10s; first fresh sampled bid below defended bid by >0.5 tick triggers short, or ask above defended ask triggers long. No retrospective choice of the eventual break time. A break is optional; parents without breaks stay in the record.",
        "cooldown": "60s from each parent event, independent of prices, profits, fill outcomes or strategy. At most one watched level. Both rules remain flat around every hourly boundary (60s before, 115s after decision safety margin), so no funding cashflow is assumed away while exposed.",
        "orders": "250ms processing plus 250ms outbound/return in base; 1s and 3s delay stresses. Hold15/30s only after entry ACK. Five-bp causal FOK entry collar rounded conservatively to tick; market exit sweeps at most five recorded levels. Single-venue native-time as-of quotes <=250ms old, no capture-clock prices for fills. Unknown depth/clock after submission halts further orders that day and retains possible/known inventory.",
        "capital": "$10000 reset independently per date. Fixed <=$1000 ticket and <=10% predecision opposite touch quantity, >=$100 minimum, native quantity grid. No future resizing or compounded scaling; capital shortage is an explicit causal no-order. Each candidate is standalone, not summed into a portfolio.",
        "fees": "6bp taker commission each side plus separate 1bp adverse allowance each side. Double fees and independently double adverse allowance; no VIP discount, rebate or funding credit. Conservative research assumptions, not exact unknown competition terms.",
        "progression": "Both discovery periods separately: every scenario complete and positive; baseline >=50 completed trades, >=2 positive dates, positive without best date. Even a pass only justifies a separately frozen larger/later test, date-blocked uncertainty and forward measured execution. No win or reliability claim from these six exposed days.",
        "multiplicity": "8 new configurations: session totals116 configurations/156 implementations, plus separate funding-only supply screens and repository-wide history. All five stresses per candidate are dependent replays.",
        "code_sha256": {name: digest(ROOT / name) for name in code},
    }
    (OUT / "specification.json").write_text(json.dumps(spec, indent=2) + "\n")
    print("Frozen 8 BTC/SOL price-resilience/break HFT rules; no new downloads", flush=True)
    batches, audits = {}, []
    with ProcessPoolExecutor(max_workers=2) as pool:
        for job in as_completed([pool.submit(process_day, symbol, day) for symbol in ASSETS for day in DATES]):
            symbol, day, records, audit = job.result()
            batches[symbol, day] = records
            audits.append(audit)
            print(f"Finished {symbol} {day} ({len(audits)}/12)", flush=True)
    results, advance = {}, []
    for symbol in ASSETS:
        results[symbol] = {}
        for mechanism in spec["mechanisms"]:
            for hold in spec["holds_seconds"]:
                name = f"{mechanism}_{hold}s"
                scenarios = {}
                for scenario in SCENARIOS:
                    rows = [dict(row, date=day, symbol=symbol) for day in DATES for row in batches[symbol, day][name][scenario]]
                    frame = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["date", "symbol", "event_id", "status", "complete", "pnl"])
                    frame.to_parquet(OUT / symbol / f"{name}_{scenario}_attempts.parquet", index=False)
                    scenarios[scenario] = {"all": summarize(frame, DATES),
                        "development": summarize(frame.loc[frame.date.isin(DATES[:3])], DATES[:3]),
                        "selection": summarize(frame.loc[frame.date.isin(DATES[3:])], DATES[3:])}
                passed = True
                for period in ("development", "selection"):
                    base = scenarios["base"][period]
                    passed &= (all(s[period]["complete"] and s[period]["net_dollars"] > 0 for s in scenarios.values())
                               and base["trades"] >= 50 and base["positive_dates"] >= 2 and base["without_best_date"] > 0)
                if passed:
                    advance.append(f"{symbol}/{name}")
                results[symbol][name] = {"scenarios": scenarios, "needs_additional_evidence": bool(passed)}
                base = scenarios["base"]["all"]
                print(f"{symbol} {name}: net={base['net_dollars']}, closed={base['closed_subtotal']:.4f}, trades={base['trades']}, pass={passed}", flush=True)
    assert all(digest(ROOT / name) == sha for name, sha in spec["code_sha256"].items())
    (OUT / "results.json").write_text(json.dumps({"results": results, "source_audits": audits,
        "candidates_for_additional_evidence": advance, "reliable_edge_established": False}, indent=2) + "\n")


if __name__ == "__main__":
    main()
