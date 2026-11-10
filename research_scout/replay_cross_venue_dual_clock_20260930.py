"""Correct delayed-recording execution while preserving all frozen signals."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from research.cross_venue_dual_clock import extract_dual_clock, physical_fill
from research.cross_venue_execution import SCENARIOS, quote_targets, simulate, summarize
from research.crypto_symbol_cache import digest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research_scout/cross_venue_20260930"
OUT = BASE / "dual_clock"


def extract(day, venue, targets):
    base = ROOT / "research_scout/liquidation_event_20260930" if venue == "binance" else BASE / "bybit"
    path = base / "raw/book_snapshot_5" / day / "BTCUSDT.csv.gz"
    manifest = json.loads(path.with_suffix(path.suffix + ".json").read_text())
    if digest(path) != manifest["sha256"]:
        raise ValueError("Source hash changed")
    result, audit = extract_dual_clock(path, day, targets)
    destination = OUT / f"{venue}_{day}_quotes.parquet"
    result.to_parquet(destination, index=False)
    audit.update({"venue": venue, "source_sha256": manifest["sha256"], "panel_sha256": digest(destination)})
    return result, audit


def main():
    OUT.mkdir(exist_ok=True)
    path = OUT / "specification.json"
    if path.exists():
        raise FileExistsError("Dual-clock batch already started")
    old = json.loads((BASE / "execution/specification.json").read_text())
    events = pd.DataFrame(old["events"])
    code = [ROOT / p for p in ("research/cross_venue_dual_clock.py", "research/cross_venue_execution.py",
                               "research/liquidation_event_replay.py", "research_scout/replay_cross_venue_dual_clock_20260930.py")]
    spec = {**old, "created_at_utc": datetime.now(UTC).isoformat(),
            "correction": "Keep every frozen opportunity, size, collar, cost and delay. Signals use strictly prior capture timestamps. Fill states instead use strictly prior exchange timestamps, including later-collected observations, and never feed those observations into decisions. Receipt-time execution was not a valid way to establish the apparent fast-fill profit.",
            "fill_quality": "Exchange snapshot age <=250ms. Do not exclude a physical state merely because collection was delayed. Negative capture delay below -1ms or target within a 250ms-padded exchange-clock backtrack interval is unknown. Source order breaks equal exchange-timestamp ties.",
            "limits": "Exchange-published book timestamps are not private matching-engine execution logs. Clock synchronization, unseen queue, impact, market-close acceptance, book reconstructions and price bands remain limitations. A positive output is not proof of executable profit.",
            "code_sha256": {str(p.relative_to(ROOT)): digest(p) for p in code}}
    path.write_text(json.dumps(spec, indent=2) + "\n")
    panels, audits = [], []
    targets = quote_targets(events)
    with ProcessPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(extract, day, venue, group.copy())
                for (day, venue), group in targets.groupby(["date", "venue"])]
        for job in as_completed(jobs):
            panel, audit = job.result()
            panels.append(panel)
            audits.append(audit)
            print(f"Dual-clock {audit['venue']} {audit['date']}: {audit['exchange_backtracks']} backtracks, {audit['ambiguous_target_count']} ambiguous targets", flush=True)
    quotes = pd.concat(panels, ignore_index=True)
    results = {}
    for horizon in spec["horizons_seconds"]:
        name = f"hold_{horizon}s"
        results[name] = {}
        for scenario in SCENARIOS:
            records, fills, daily = simulate(quotes, events, spec["dates"], horizon, scenario, fill_function=physical_fill)
            stem = OUT / f"{name}_{scenario}"
            records.to_parquet(str(stem) + "_attempts.parquet", index=False)
            fills.to_parquet(str(stem) + "_fills.parquet", index=False)
            daily.to_parquet(str(stem) + "_daily.parquet", index=False)
            summary = summarize(records, fills, daily)
            results[name][scenario] = summary
            print(f"{name}/{scenario}: {summary['outcomes']}, net={summary['net_dollars']}, closed={summary['closed_subtotal']:+.4f}", flush=True)
    assert all(digest(ROOT / p) == expected for p, expected in spec["code_sha256"].items())
    (OUT / "results.json").write_text(json.dumps({"results": results, "source_audits": audits,
                                                 "edge_established": False}, indent=2) + "\n")


if __name__ == "__main__":
    main()
