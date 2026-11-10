"""Bounded, unauthenticated public Tardis first-of-month sample acquisition.

Only small liquidation files are fetched by default. No API key is read, no paid
endpoint is used, and HTTP/authentication failures do not trigger a paid fallback.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout/liquidation_event_20260930"
DATES = [f"2024-{month:02d}-01" for month in range(1, 13)]


def download_sample(kind, day, symbol="BTCUSDT", cap_bytes=20_000_000, *,
                    exchange="binance-futures", output_base=None):
    if not day.endswith("-01"):
        raise ValueError("Only documented public first-of-month samples are allowed")
    if kind not in {"liquidations", "book_snapshot_5", "trades"}:
        raise ValueError("Unapproved sample type")
    if exchange not in {"binance-futures", "bybit"} or symbol not in {"BTCUSDT", "ETHUSDT", "SOLUSDT"}:
        raise ValueError("Unapproved public instrument")
    base = OUTPUT if output_base is None else Path(output_base)
    if not base.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("Downloads must remain inside the research workspace")
    target = base / "raw" / kind / day / f"{symbol}.csv.gz"
    manifest_path = target.with_suffix(target.suffix + ".json")
    if target.exists() and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if hashlib.sha256(target.read_bytes()).hexdigest() != manifest["sha256"]:
            raise ValueError("Cached sample checksum changed")
        return target, manifest
    url = f"https://datasets.tardis.dev/v1/{exchange}/{kind}/{day.replace('-', '/')}/{symbol}.csv.gz"
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    session = requests.Session()
    session.trust_env = False  # No netrc credentials or ambient authenticated session.
    with session.get(url, stream=True, timeout=(15, 45)) as response:
        response.raise_for_status()
        length = response.headers.get("Content-Length")
        if length and int(length) > cap_bytes:
            raise ValueError(f"Public sample exceeds its frozen size cap: {length}")
        digest, received = hashlib.sha256(), 0
        with partial.open("wb") as sink:
            for chunk in response.iter_content(1024 * 1024):
                received += len(chunk)
                if received > cap_bytes:
                    raise ValueError("Public sample exceeded its frozen size cap")
                digest.update(chunk)
                sink.write(chunk)
        with gzip.open(partial, "rt", encoding="utf-8") as source:
            columns = source.readline().strip().split(",")
        if not {"exchange", "symbol", "timestamp", "local_timestamp"}.issubset(columns):
            raise ValueError("Unexpected public sample schema")
        manifest = {"retrieved_at_utc": datetime.now(UTC).isoformat(), "url": url,
                    "date": day, "symbol": symbol, "kind": kind, "bytes": received,
                    "sha256": digest.hexdigest(), "columns": columns,
                    "http_status": response.status_code, "authenticated": False}
    partial.replace(target)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return target, manifest


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    spec_path = OUTPUT / "acquisition_specification.json"
    if not spec_path.exists():
        spec_path.write_text(json.dumps({"created_at_utc": datetime.now(UTC).isoformat(),
            "dates": DATES, "symbol": "BTCUSDT", "stage": "liquidation supply audit, no future-price outcomes",
            "first_stage_bytes_cap": 240_000_000,
            "sources": ["https://docs.tardis.dev/downloadable-csv-files/overview", "https://docs.tardis.dev/faq/data"],
            "limits": "First day of each month is a calendar-selected sample, not continuous coverage. Binance publishes throttled snapshots; reported notional is not total forced volume."}, indent=2) + "\n")
    audit, failures = [], []
    for day in DATES:
        try:
            path, manifest = download_sample("liquidations", day)
            data = pd.read_csv(path)
            local = data.local_timestamp.to_numpy()
            notional = data.price * data.amount
            record = {**manifest, "records": len(data),
                      "capture_time_backtracks": int((pd.Series(local).diff() < 0).sum()),
                      "invalid_values": int((~(data.price > 0) | ~(data.amount > 0)).sum()),
                      "sides": data.side.value_counts().to_dict(),
                      "reported_notional_quantiles": notional.quantile([.5, .9, .99, 1.]).to_dict()}
            audit.append(record)
            print(f"{day}: {len(data)} liquidation reports; {manifest['bytes']:,} compressed bytes", flush=True)
        except Exception as error:
            failures.append({"date": day, "error": str(error)})
            print(f"Sample unavailable {day}: {error}", flush=True)
    (OUTPUT / "liquidation_supply_audit.json").write_text(json.dumps({"sources": audit, "failures": failures, "future_prices_inspected": False}, indent=2) + "\n")


if __name__ == "__main__":
    main()
