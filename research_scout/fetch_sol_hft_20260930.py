"""Calendar-selected public SOL replication data under a fixed byte ceiling."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from research_scout.fetch_liquidation_samples_20260930 import download_sample

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/sol_hft_replication_20260930"


def main():
    metadata = json.loads((OUT / "metadata.json").read_text())
    instrument = metadata["instrument"]
    assert len(instrument) == 1 and instrument[0]["type"] == "perpetual"
    assert {"liquidations", "trades", "book_snapshot_5"}.issubset(instrument[0]["dataTypes"])
    requested = [("liquidations", f"2024-{m:02d}-01") for m in range(1, 13)]
    requested += [(kind, f"2024-{m:02d}-01") for m in range(7, 13) for kind in ("book_snapshot_5", "trades")]
    session = requests.Session()
    session.trust_env = False
    estimates = []
    for kind, day in requested:
        url = f"https://datasets.tardis.dev/v1/binance-futures/{kind}/{day.replace('-', '/')}/SOLUSDT.csv.gz"
        with session.get(url, stream=True, timeout=(15, 30)) as response:
            response.raise_for_status()
            size = int(response.headers["Content-Length"])
        if size > 250_000_000:
            raise ValueError("Sample exceeds 250MB file cap")
        estimates.append({"kind": kind, "date": day, "bytes": size, "url": url})
    total = sum(x["bytes"] for x in estimates)
    if total > 1_000_000_000:
        raise ValueError("One-GB aggregate cap exceeded")
    plan = {"public_unauthenticated": True, "samples": estimates, "expected_bytes": total,
            "aggregate_cap": 1_000_000_000,
            "replication": "Fixed eight passive-liquidation variants already rejected on BTC. SOL is a preselected cross-asset replication, not a favorable-outcome selection. Same 8/16bp offsets, follow/reverse directions and 30/120s holds; same 3/6bp maker/taker fees plus 1bp market allowance and existing stresses.",
            "calibration": "Jan-Jun SOL reported-liquidation notional 99th percentile only, without future price outcomes.",
            "evaluation": "Six July-December 2024 monthly-first-day samples; no 2025 outcome data acquired.",
            "scope": "Strictly HFT; stocks, ETFs, crypto eligible; conservative fees. No slower intraday strategy.",
            "limits": "BTC outcomes and common market dates already exposed. SOL development is not genuine forward evidence; any positive needs distinct later dates and execution validation."}
    (OUT / "acquisition_plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    print(f"SOL samples total {total:,} compressed bytes", flush=True)
    manifests = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(download_sample, kind, day, symbol="SOLUSDT", cap_bytes=250_000_000, output_base=OUT)
                for kind, day in requested]
        for job in as_completed(jobs):
            _, manifest = job.result()
            manifests.append(manifest)
            print(f"{manifest['date']} {manifest['kind']}: {manifest['bytes']:,} bytes", flush=True)
    (OUT / "download_manifest.json").write_text(json.dumps(manifests, indent=2) + "\n")


if __name__ == "__main__":
    main()
