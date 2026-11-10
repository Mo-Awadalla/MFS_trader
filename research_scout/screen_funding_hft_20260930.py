"""Cheap causal funding-payment screen before buying time on an execution study."""

from __future__ import annotations

import gzip
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from research.crypto_symbol_cache import digest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/funding_hft_screen_20260930"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT")
DATES = tuple(f"2024-{month:02d}-01" for month in range(1, 13))
EXCHANGES = ("binance-futures", "bybit")
PER_FILE_CAP, TOTAL_CAP = 32_000_000, 600_000_000
COLUMNS = ["exchange", "symbol", "timestamp", "local_timestamp", "funding_timestamp", "funding_rate", "mark_price"]


def session():
    result = requests.Session()
    result.trust_env = False
    return result


def probe(item):
    url = f"https://datasets.tardis.dev/v1/{item['exchange']}/derivative_ticker/{item['date'].replace('-', '/')}/{item['symbol']}.csv.gz"
    with session().get(url, stream=True, timeout=(15, 45)) as response:
        if response.status_code == 404:
            return {**item, "url": url, "available": False, "http_status": 404}
        response.raise_for_status()
        size = int(response.headers["Content-Length"])
        if size > PER_FILE_CAP:
            raise ValueError("File exceeds frozen public-download cap")
        return {**item, "url": url, "available": True, "bytes": size}


def download(item):
    target = OUT / "raw" / item["exchange"] / item["date"] / f"{item['symbol']}.csv.gz"
    manifest = target.with_suffix(target.suffix + ".json")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and manifest.exists():
        previous = json.loads(manifest.read_text())
        assert digest(target) == previous["sha256"] and target.stat().st_size == item["bytes"]
        return previous
    partial = target.with_suffix(target.suffix + ".part")
    h, received = hashlib.sha256(), 0
    with session().get(item["url"], stream=True, timeout=(15, 60)) as response:
        response.raise_for_status()
        with partial.open("wb") as sink:
            for chunk in response.iter_content(1024 * 1024):
                received += len(chunk)
                if received > item["bytes"] or received > PER_FILE_CAP:
                    raise ValueError("Download exceeded preflight byte reservation")
                h.update(chunk)
                sink.write(chunk)
    if received != item["bytes"]:
        raise ValueError("Truncated public sample")
    with gzip.open(partial, "rt") as stream:
        assert set(COLUMNS).issubset(stream.readline().strip().split(","))
    partial.replace(target)
    record = {**item, "path": str(target.relative_to(ROOT)), "sha256": h.hexdigest(), "authenticated": False}
    manifest.write_text(json.dumps(record, indent=2) + "\n")
    return record


def causal_snapshots(item):
    path = ROOT / item["path"]
    assert digest(path) == item["sha256"]
    frame = pd.read_csv(path, usecols=COLUMNS)
    local = frame.local_timestamp.to_numpy(np.int64)
    assert not (np.diff(local) < 0).any()
    assert frame.exchange.eq(item["exchange"]).all() and frame.symbol.eq(item["symbol"]).all()
    records = []
    for hour in (8, 16):
        funding = pd.Timestamp(f"{item['date']} {hour:02d}:00", tz="UTC").value // 1000
        decision = funding - 30_000_000
        pos = np.searchsorted(local, decision, side="left") - 1
        row = {"date": item["date"], "exchange": item["exchange"], "symbol": item["symbol"],
               "settlement_us": int(funding), "decision_us": int(decision), "usable": False}
        if pos >= 0:
            state = frame.iloc[pos]
            row.update(source_position=int(pos), receive_us=int(local[pos]), event_us=int(state.timestamp),
                       funding_time_us=None if pd.isna(state.funding_timestamp) else int(state.funding_timestamp),
                       funding_rate=float(state.funding_rate), mark_price=float(state.mark_price))
            row["usable"] = bool(0 < decision - local[pos] <= 5_000_000
                                 and 0 < decision - state.timestamp <= 5_000_000
                                 and state.funding_timestamp == funding
                                 and np.isfinite([state.funding_rate, state.mark_price]).all()
                                 and state.mark_price > 0)
        records.append(row)
    return records, len(frame)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    spec_path = OUT / "specification.json"
    if not spec_path.exists():
        spec_path.write_text(json.dumps({
            "created_at_utc": datetime.now(UTC).isoformat(), "symbols": SYMBOLS, "dates": DATES,
            "exchanges": EXCHANGES, "per_file_compressed_cap": PER_FILE_CAP, "total_compressed_cap": TOTAL_CAP,
            "selection": "Six fixed common USDT perpetuals, twelve calendar first-of-month 2024 dates. Convenience/existing-instrument universe, not a point-in-time broad-market selection or independent holdout.",
            "scope": "Strict HFT feasibility only: hypothetical paired entry at settlement minus 30s, exit plus 30s, with delayed order/ACK handling required in any later replay. No multiday carry and no price-return or realized-profit backtest here.",
            "signal": "Last received ticker strictly before T-30s, receive/event age <=5s, both next-funding timestamps equal T, finite funding rate and positive mark. Use funding_rate for the immediately upcoming event, never predicted_funding_rate for the following one.",
            "gate": "Equal coin quantities, buy lower funding payment/coin and sell higher. Predecision quoted funding difference = abs(rate_A*mark_A-rate_B*mark_B)/max(mark_A,mark_B)*10000; require >28bp, the approximate four executions at 6bp fee plus 1bp adverse allowance per execution, before spread or basis risk. This is a predeclared economic trigger, not a bound proving impossibility of strategies with additional price alpha.",
            "next_stage": "Only eligible events justify a separately frozen full-book paired replay including actual settled rates/mark cashflows, price-basis repricing, funding uncertainty, missed leg/unwind, conservative fees, latency and no lookahead. Funding field normalization must be checked against native messages before any P&L claim.",
            "funding_timing": "Bybit warns that inclusion is uncertain within five seconds of settlement. A later model must keep confirmed inventory well outside this interval and stress inclusion; current documentation is not automatically proof of unchanged historical rules.",
            "sources": ["https://docs.tardis.dev/downloadable-csv-files/data-types",
                        "https://www.bybit.com/en/help-center/article/Funding-fee-calculation"],
            "authentication": "None; public first-of-month samples. No paid fallback or credentials.",
            "code_sha256": digest(Path(__file__)),
        }, indent=2) + "\n")
    spec = json.loads(spec_path.read_text())
    assert digest(Path(__file__)) == spec["code_sha256"]
    items = [{"exchange": exchange, "date": day, "symbol": symbol}
             for exchange in EXCHANGES for day in DATES for symbol in SYMBOLS]
    plan_path = OUT / "download_plan.json"
    if plan_path.exists():
        plan = json.loads(plan_path.read_text())
    else:
        with ThreadPoolExecutor(max_workers=6) as pool:
            plan = list(pool.map(probe, items))
        plan_path.write_text(json.dumps(plan, indent=2) + "\n")
    available = [item for item in plan if item["available"]]
    total = sum(item["bytes"] for item in available)
    if total > TOTAL_CAP:
        raise ValueError(f"Public files total {total:,} bytes, exceeding predeclared cap")
    print(f"Preflight: {len(available)}/{len(items)} samples, {total:,} compressed bytes", flush=True)
    manifests = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for job in as_completed([pool.submit(download, item) for item in available]):
            manifests.append(job.result())
            if len(manifests) % 12 == 0 or len(manifests) == len(available):
                print(f"Downloaded {len(manifests)}/{len(available)} public funding files", flush=True)
    (OUT / "manifest.json").write_text(json.dumps(manifests, indent=2) + "\n")
    rows, raw_rows = [], 0
    for item in manifests:
        snapshots, count = causal_snapshots(item)
        rows.extend(snapshots)
        raw_rows += count
    snapshots = pd.DataFrame(rows)
    snapshots.to_parquet(OUT / "snapshots.parquet", index=False)
    index = {(r["exchange"], r["symbol"], r["settlement_us"]): r for r in rows}
    pairs = []
    for day in DATES:
        for symbol in SYMBOLS:
            for hour in (8, 16):
                funding = pd.Timestamp(f"{day} {hour:02d}:00", tz="UTC").value // 1000
                a, b = (index.get((exchange, symbol, funding)) for exchange in EXCHANGES)
                row = {"date": day, "symbol": symbol, "hour_utc": hour, "settlement_us": int(funding),
                       "usable": bool(a and b and a["usable"] and b["usable"]), "eligible": False}
                if row["usable"]:
                    difference = (a["funding_rate"] * a["mark_price"] - b["funding_rate"] * b["mark_price"])
                    bps = abs(difference) / max(a["mark_price"], b["mark_price"]) * 10000
                    row.update(quoted_funding_difference_bps=bps, eligible=bps > 28,
                               sell_exchange=EXCHANGES[0] if difference > 0 else EXCHANGES[1])
                pairs.append(row)
    pairs = pd.DataFrame(pairs)
    pairs.to_parquet(OUT / "pairs.parquet", index=False)
    result = {"files": len(manifests), "compressed_bytes": total, "raw_ticker_rows": raw_rows,
              "funding_pairs": len(pairs), "usable_pairs": int(pairs.usable.sum()),
              "eligible_pairs": int(pairs.eligible.sum()),
              "maximum_quoted_funding_difference_bps": float(pairs.quoted_funding_difference_bps.max()) if pairs.usable.any() else None,
              "by_symbol": {s: {"usable_pairs": int(g.usable.sum()), "eligible_pairs": int(g.eligible.sum()),
                               "maximum_quoted_funding_difference_bps": float(g.quoted_funding_difference_bps.max()) if g.usable.any() else None}
                            for s, g in pairs.groupby("symbol")},
              "missing_files": [item for item in plan if not item["available"]],
              "strategy_pnl_tested": False, "edge_established": False}
    (OUT / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
