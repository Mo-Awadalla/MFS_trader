"""Freeze and evaluate both successful pairs and unhedged failed-leg attempts."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from research.cross_venue_execution import SCENARIOS, quote_targets, simulate, summarize
from research.crypto_symbol_cache import digest
from research.liquidation_event_replay import extract_quotes

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research_scout/cross_venue_20260930"
OUT = BASE / "execution"


def extract(day, venue, targets):
    base = ROOT / "research_scout/liquidation_event_20260930" if venue == "binance" else BASE / "bybit"
    path = base / "raw/book_snapshot_5" / day / "BTCUSDT.csv.gz"
    manifest = json.loads(path.with_suffix(path.suffix + ".json").read_text())
    if digest(path) != manifest["sha256"]:
        raise ValueError("Raw source changed")
    result, audit = extract_quotes(path, day, targets)
    audit.update({"venue": venue, "source_sha256": manifest["sha256"]})
    destination = OUT / f"{venue}_{day}_quotes.parquet"
    result.to_parquet(destination, index=False)
    audit["panel_sha256"] = digest(destination)
    return result, audit


def main():
    OUT.mkdir(exist_ok=True)
    spec_path = OUT / "specification.json"
    if spec_path.exists():
        raise FileExistsError("Execution batch already started; inspect existing outputs")
    events_path = BASE / "opening_opportunities.parquet"
    events = pd.read_parquet(events_path).sort_values(["date", "clock_us"]).reset_index(drop=True)
    events["event_id"] = events.index
    gate = json.loads((BASE / "gate_specification.json").read_text())
    code = [ROOT / p for p in ("research/cross_venue_execution.py", "research/liquidation_event_replay.py",
                               "research_scout/run_cross_venue_execution_20260930.py")]
    spec = {"created_at_utc": datetime.now(UTC).isoformat(), "dates": gate["dates"],
            "events_sha256": digest(events_path), "events": events.to_dict("records"),
            "horizons_seconds": [30, 120], "scenarios": SCENARIOS,
            "primary_scenario": "base", "fast_scenario_is_diagnostic_only": True,
            "prior_exposure": "Opening-gap screen and 200ms/1s/3s top-level diagnostics already inspected. These are development results, not an untouched validation sample.",
            "execution": "Send two independent FOK orders with 1bp causal collars and 0.1-USDT ticks. Equal BTC, predetermined quantity <=$1000 per leg and <=10% both touch sizes. No atomicity assumed.",
            "clocks": "Base uses 250ms extra feed/processing delay then 1s outbound per venue. Confirm both outcomes after another return delay; only then unwind a single filled leg or start the fixed hold. Closing orders incur outbound and acknowledgement delay.",
            "costs": "6bp fees and 1bp adverse cost on every fill, including failed-pair unwinds; fees doubled to 12bp in stress. Four pair fills cost roughly 28bp of mean one-leg notional.",
            "funding": "No funding earnings assumed; reject positions crossing any UTC hour plus a one-minute buffer, covering conventional hourly and coarser funding schedules.",
            "inventory": "$10000 notionally prefunded, $5000 per venue; max one active pair or unmatched leg; each completed attempt updates venue equity; isolated dates reset account. No transfers required or modeled.",
            "unknowns": "Latest native capture strictly before target, all five levels valid, <=250ms age and <=1s source delay. Unknown submitted entry/exit/deeper liquidity stops day and invalidates total, keeping known fills. They are not dropped.",
            "limits": "Only four screened episodes on two of six calendar-selected dates. Native capture-clock proxy is not venue-engine truth. Market-close proxy assumes enough shown depth and exchange acceptance; no queue, impact, disconnect, price-band or real-fill evidence. No competition execution specification known.",
            "progression": "Any putative survivor requires positive complete base and stresses, replication on later unopened dates, block-aware uncertainty and forward paper execution. No reliable-edge claim from these four episodes.",
            "sources": ["https://bybit-exchange.github.io/docs/v5/order/create-order", "https://docs.tardis.dev/downloadable-csv-files/data-types"],
            "code_sha256": {str(p.relative_to(ROOT)): digest(p) for p in code}}
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    targets = quote_targets(events)
    panels, audits = [], []
    with ProcessPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(extract, day, venue, group.copy())
                for (day, venue), group in targets.groupby(["date", "venue"])]
        for job in as_completed(jobs):
            panel, audit = job.result()
            panels.append(panel)
            audits.append(audit)
            print(f"Extracted exact {audit['venue']} {audit['date']}: {audit['rows']:,} raw rows", flush=True)
    quotes = pd.concat(panels, ignore_index=True)
    results = {}
    for horizon in spec["horizons_seconds"]:
        name = f"hold_{horizon}s"
        results[name] = {}
        for scenario in SCENARIOS:
            records, fills, daily = simulate(quotes, events, spec["dates"], horizon, scenario)
            stem = OUT / f"{name}_{scenario}"
            records.to_parquet(str(stem) + "_attempts.parquet", index=False)
            fills.to_parquet(str(stem) + "_fills.parquet", index=False)
            daily.to_parquet(str(stem) + "_daily.parquet", index=False)
            summary = summarize(records, fills, daily)
            results[name][scenario] = summary
            print(f"{name}/{scenario}: {summary['outcomes']}, net={summary['net_dollars']}, closed={summary['closed_subtotal']:+.4f}", flush=True)
    assert all(digest(ROOT / path) == expected for path, expected in spec["code_sha256"].items())
    (OUT / "results.json").write_text(json.dumps({"results": results, "source_audits": audits,
                                                 "edge_established": False}, indent=2) + "\n")


if __name__ == "__main__":
    main()
