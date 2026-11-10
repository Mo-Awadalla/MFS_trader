"""Small public raw-field admission probe; no return or direction optimization."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/force_order_fields_20260930"


def fetch(target):
    day, minute = target["date"], target["minute_offset"]
    path = OUT / "raw" / f"{day}_{minute:04d}.ndjson"
    if path.exists():
        payload = path.read_bytes()
    else:
        session = requests.Session()
        session.trust_env = False
        params = {"from": day, "offset": minute, "filters": json.dumps([{"channel": "forceOrder"}])}
        with session.get("https://api.tardis.dev/v1/data-feeds/binance-futures", params=params,
                         headers={"Accept-Encoding": "gzip"}, stream=True, timeout=(15, 45)) as response:
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 1_000_000:
                    raise ValueError("Raw minute exceeds fixed one-MB decoded cap")
                chunks.append(chunk)
        payload = b"".join(chunks)
        path.write_bytes(payload)
    orders, disconnects = [], 0
    for line in payload.decode("utf-8").splitlines():
        if not line.strip():
            disconnects += 1
            continue
        stamp, encoded = line.split(" ", 1)
        wrapper = json.loads(encoded)
        message = wrapper.get("data", wrapper)
        if message.get("e") != "forceOrder":
            continue
        order = message["o"]
        if order.get("s") not in {"BTCUSDT", "SOLUSDT"}:
            continue
        local_us = pd.Timestamp(stamp).value // 1000
        original, filled = float(order["q"]), float(order["z"])
        orders.append({"date": day, "minute_offset": minute, "local_timestamp": int(local_us),
                       "symbol": order["s"], "status": order.get("X"), "time_in_force": order.get("f"),
                       "side": order.get("S"), "original_quantity": original, "filled_quantity": filled,
                       "unfilled_order_quantity": max(0., original - filled), "last_fill_quantity": float(order["l"]),
                       "limit_price": float(order["p"]), "average_price": float(order["ap"]),
                       "order_time_ms": order.get("T"), "event_time_ms": message.get("E"),
                       "raw_order_fields": sorted(order)})
    manifest = {**target, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
                "public_unauthenticated": True, "path": str(path.relative_to(ROOT)),
                "disconnect_markers": disconnects, "retained_orders": len(orders)}
    return manifest, orders


def main():
    (OUT / "raw").mkdir(parents=True, exist_ok=True)
    requests_by_minute = {}
    for symbol, folder in (("BTCUSDT", "liquidation_event_20260930"), ("SOLUSDT", "sol_hft_replication_20260930")):
        for month in range(7, 13):
            day = f"2024-{month:02d}-01"
            events = pd.read_parquet(ROOT / "research_scout" / folder / "panels" / f"{day}_events.parquet")
            event = events.sort_values("received_us").iloc[0]
            minute = int(event.received_us // 60_000_000)
            target = requests_by_minute.setdefault((day, minute), {"date": day, "minute_offset": minute, "chosen_events": []})
            target["chosen_events"].append({"symbol": symbol, "event_id": int(event.event_id), "received_us": int(event.received_us)})
    targets = list(requests_by_minute.values())
    spec = {"created_at_utc": datetime.now(UTC).isoformat(), "selection": "Earliest frozen large-liquidation event per symbol/date. No P&L selection. Raw-field supply admission only, not a candidate strategy.",
            "targets": targets, "maximum_decoded_bytes": len(targets) * 1_000_000,
            "authentication": "None; only documented free first-of-month API samples. No paid or authenticated fallback.",
            "economic_boundary": "Unfilled quantity of an IOC is not an observed resting order or proof of remaining account liquidation. Status and quantity availability are assessed without asserting that mechanism.",
            "sources": ["https://docs.tardis.dev/api/http-api-reference.md", "https://docs.tardis.dev/historical-data-details/binance-futures"]}
    (OUT / "probe_specification.json").write_text(json.dumps(spec, indent=2) + "\n")
    manifests, orders = [], []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for job in as_completed([pool.submit(fetch, target) for target in targets]):
            manifest, rows = job.result()
            manifests.append(manifest)
            orders.extend(rows)
            print(f"{manifest['date']} minute {manifest['minute_offset']}: {manifest['retained_orders']} BTC/SOL reports, {manifest['bytes']} bytes", flush=True)
    frame = pd.DataFrame(orders)
    frame.to_parquet(OUT / "orders.parquet", index=False)
    result = {"manifests": manifests, "orders": len(frame), "status_counts": frame.status.value_counts().to_dict(),
              "time_in_force_counts": frame.time_in_force.value_counts().to_dict(),
              "positive_unfilled_order_quantity": int(frame.unfilled_order_quantity.gt(1e-10).sum()),
              "strategy_returns_computed": False}
    (OUT / "probe_results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "manifests"}, indent=2))


if __name__ == "__main__":
    main()
