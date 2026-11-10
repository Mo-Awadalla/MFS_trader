"""Acquire every causally prescreened counterpart and compare quoted funding."""

import gzip
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import requests

from research.crypto_symbol_cache import digest
from research_scout.prepare_funding_universe_20260930 import OUT, ROOT

COLUMNS = ["exchange", "symbol", "timestamp", "local_timestamp", "funding_timestamp", "funding_rate", "mark_price"]


def download(job, maximum):
    path = OUT/"counterparts"/f"{job['date']}_{job['symbol']}.csv.gz"
    sidecar = path.with_suffix(path.suffix+".json")
    if sidecar.exists():
        old = json.loads(sidecar.read_text())
        if old["complete"]:
            assert digest(path) == old["sha256"]
        return old
    url = f"https://datasets.tardis.dev/v1/bybit/derivative_ticker/{job['date'].replace('-', '/')}/{job['symbol']}.csv.gz"
    record = {**job, "url": url, "path": str(path.relative_to(ROOT)), "complete": False, "authenticated": False}
    session = requests.Session()
    session.trust_env = False
    start = time.monotonic()
    try:
        with session.get(url, stream=True, timeout=(15, 60), allow_redirects=False) as response:
            record["http_status"] = response.status_code
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError("Unexpected counterpart response")
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > maximum or time.monotonic()-start > 180:
                    raise ValueError("Bounded counterpart acquisition limit")
                chunks.append(chunk)
            payload = b"".join(chunks)
        path.write_bytes(payload)
        with gzip.open(path, "rt") as stream:
            assert set(COLUMNS).issubset(stream.readline().strip().split(","))
        record.update(complete=True, compressed_bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    except Exception as error:
        record.update(error_type=type(error).__name__, error=str(error))
    sidecar.write_text(json.dumps(record, indent=2)+"\n")
    return record


def asof_states(item, events):
    path = ROOT/item["path"]
    assert digest(path) == item["sha256"]
    selected, offset, last = {}, 0, None
    for frame in pd.read_csv(path, usecols=COLUMNS, chunksize=200_000):
        times = frame.local_timestamp.to_numpy(np.int64)
        assert not (np.diff(times) < 0).any() and (last is None or times[0] >= last)
        assert frame.exchange.eq("bybit").all() and frame.symbol.eq(item["symbol"]).all()
        last = int(times[-1])
        for event in events:
            cutoff = event["decision_ns"]//1000
            i = int(np.searchsorted(times, cutoff, side="left"))-1
            if i >= 0:
                r = frame.iloc[i]
                selected[event["hour"]] = {"source_position": offset+i, "receive_us": int(r.local_timestamp),
                                            "event_us": int(r.timestamp),
                                            "funding_time_us": None if pd.isna(r.funding_timestamp) else int(r.funding_timestamp),
                                            "funding_rate": float(r.funding_rate), "mark_price": float(r.mark_price)}
        offset += len(frame)
    return selected, offset


def main():
    if (OUT/"stage_b_results.json").exists():
        raise RuntimeError("Preserve counterpart screen")
    spec = json.loads((OUT/"specification.json").read_text())
    stage_a = json.loads((OUT/"stage_a_results.json").read_text())
    assert digest(OUT/"large_binance_rates.parquet") == stage_a["large_rates_sha256"]
    events = pd.read_parquet(OUT/"large_binance_rates.parquet")
    jobs = events[["date", "symbol"]].drop_duplicates().sort_values(["date", "symbol"]).to_dict("records")
    maximum = spec["download"]["counterpart_per_file_compressed_cap"]
    assert len(jobs)*maximum <= spec["download"]["counterpart_total_compressed_cap"]
    (OUT/"counterparts").mkdir(exist_ok=True)
    freeze_path = OUT/"stage_b_implementation.json"
    if freeze_path.exists():
        freeze = json.loads(freeze_path.read_text())
        assert freeze["code_sha256"] == digest(ROOT/"research_scout/funding_counterparts_20260930.py")
    else:
        freeze = {"created_at_utc": datetime.now(UTC).isoformat(), "jobs": jobs,
                  "code_sha256": digest(ROOT/"research_scout/funding_counterparts_20260930.py"),
                  "stage_a_sha256": digest(OUT/"stage_a_results.json"),
                  "funding_rate_threshold_bps": 28, "strategy_pnl_tested": False}
        freeze_path.write_text(json.dumps(freeze, indent=2)+"\n")
    records = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = [pool.submit(download, job, maximum) for job in jobs]
        for task in as_completed(pending):
            record = task.result()
            records.append(record)
            (OUT/"counterpart_manifest.json").write_text(json.dumps({"files": records, "expected_files": len(jobs),
                    "complete": len(records) == len(jobs) and all(r["complete"] for r in records)}, indent=2)+"\n")
            print(json.dumps({"date": record["date"], "symbol": record["symbol"], "complete": record["complete"],
                              "files": len(records), "compressed_bytes": record.get("compressed_bytes"), "http_status": record.get("http_status")}), flush=True)
    sources = {(r["date"], r["symbol"]): r for r in records}
    rows, raw_count = [], 0
    for job in jobs:
        cohort = events.loc[(events.date == job["date"]) & (events.symbol == job["symbol"])].to_dict("records")
        item = sources[(job["date"], job["symbol"])]
        states = {}
        if item["complete"]:
            states, count = asof_states(item, cohort)
            raw_count += count
        for event in cohort:
            row = {"date": event["date"], "symbol": event["symbol"], "hour": event["hour"],
                   "settlement_ns": event["settlement_ns"], "decision_ns": event["decision_ns"],
                   "binance_rate": event["funding_rate"], "binance_mark": event["mark_price"],
                   "usable": False, "eligible": False, "reason": "unknown_counterpart_source"}
            state = states.get(event["hour"])
            if state:
                row.update({"bybit_"+k: v for k, v in state.items()})
                cutoff = event["decision_ns"]//1000
                good = (0 < cutoff-state["receive_us"] <= 5_000_000
                        and 0 < cutoff-state["event_us"] <= 5_000_000
                        and state["funding_time_us"] == event["settlement_ns"]//1000
                        and np.isfinite([state["funding_rate"], state["mark_price"]]).all() and state["mark_price"] > 0)
                if good:
                    difference = event["funding_rate"]*event["mark_price"]-state["funding_rate"]*state["mark_price"]
                    bps = abs(difference)/max(event["mark_price"], state["mark_price"])*10000
                    row.update(usable=True, quoted_payment_difference_bps=bps, eligible=bps > 28,
                               sell_exchange="binance-futures" if difference > 0 else "bybit",
                               reason="eligible" if bps > 28 else "payment_difference_below_cost_hurdle")
                else:
                    row["reason"] = "stale_invalid_or_wrong_funding_time_counterpart"
            rows.append(row)
    frame = pd.DataFrame(rows)
    for name in frame:
        if name.endswith("_ns") or name.endswith("_us") or name.endswith("_position"):
            frame[name] = pd.array([r.get(name) for r in rows], dtype="Int64")
    frame.to_parquet(OUT/"funding_pairs.parquet", index=False)
    result = {"events": len(frame), "counterpart_files": len(records), "successful_counterpart_files": sum(r["complete"] for r in records),
              "counterpart_native_normalized_rows": raw_count, "compressed_bytes": sum(r.get("compressed_bytes", 0) for r in records),
              "usable_pairs": int(frame.usable.sum()), "eligible_pairs": int(frame.eligible.sum()),
              "outcomes": frame.reason.value_counts().to_dict(),
              "maximum_quoted_payment_difference_bps": float(frame.quoted_payment_difference_bps.max()) if frame.usable.any() else None,
              "pairs_sha256": digest(OUT/"funding_pairs.parquet"), "native_counterpart_verified": False,
              "contract_equivalence_verified": False, "strategy_pnl_tested": False, "reliable_edge_established": False}
    (OUT/"stage_b_results.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result), flush=True)
    print(frame[["date", "hour", "symbol", "binance_rate", "bybit_funding_rate", "quoted_payment_difference_bps", "reason"]].to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
