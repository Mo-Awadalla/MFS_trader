"""Execution-corrected rerun of the same six frozen passive BTC hypotheses."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from research.crypto_passive_partial import PartialRule, replay_partial_day
from research_scout.run_crypto_passive_20260930 import CACHE, build_day, digest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout/crypto_passive_partial_20260930"
DEVELOPMENT = ["2023-08-15", "2023-09-15", "2023-10-15", "2023-11-15", "2023-12-15"]
SELECTION = ["2024-01-15", "2024-01-21", "2024-01-28", "2024-01-31"]
TRIALS = 36  # Includes both execution versions, despite dependent configurations.


def run_day(day, scenarios):
    audit = build_day(day)
    with np.load(CACHE / f"{day}.npz") as archive:
        book = {k: archive[k] for k in ["bid", "ask", "bid_qty", "ask_qty", "event_ms"]}
        trades = {k: archive["trade_" + k] for k in ["time", "price", "quantity", "buyer_maker"]}
    if (not np.isfinite(trades["price"]).all() or not np.isfinite(trades["quantity"]).all()
            or (trades["price"] <= 0).any() or (trades["quantity"] <= 0).any()
            or (np.diff(trades["time"]) < 0).any()):
        raise ValueError(f"Invalid cached trades: {day}")
    audit = dict(audit, cache_sha256=digest(CACHE / f"{day}.npz"))
    results = {name: replay_partial_day(book, trades, PartialRule(**config), day)
               for name, config in scenarios.items()}
    return day, audit, results


def run_section(days, scenarios, section):
    combined, audits = {name: [] for name in scenarios}, []
    with ProcessPoolExecutor(max_workers=2) as pool:
        for job in as_completed([pool.submit(run_day, day, scenarios) for day in days]):
            day, audit, results = job.result()
            audits.append(audit)
            for name, result in results.items():
                combined[name].append(result)
            print(f"Partial-inventory replay finished {day}", flush=True)
    summaries = {}
    for name, records in combined.items():
        records.sort(key=lambda x: x["date"])
        ledger = [trade for record in records for trade in record.pop("trades")]
        pd.DataFrame(ledger).to_parquet(OUTPUT / f"{section}_{name}_trades.parquet", index=False)
        complete = all(record["complete"] for record in records)
        pnl = np.array([record["closed_trade_pnl"] for record in records])
        priced = [trade for trade in ledger if trade["status"] == "priced"]
        rng = np.random.default_rng(93026)
        boot = pnl[rng.integers(0, len(pnl), (20000, len(pnl)))].mean(axis=1)
        summaries[name] = {"daily": records, "complete": complete,
                           "closed_trade_pnl": float(pnl.sum()),
                           "net_dollars": float(pnl.sum()) if complete else None,
                           "trades": len(priced), "positive_days": int((pnl > 0).sum()) if complete else None,
                           "mean_net_bps": float(np.mean([t["net_bps"] for t in priced])) if priced else None,
                           "daily_mean_ci95": np.quantile(boot, [.025, .975]).tolist() if complete else None,
                           "adjusted_daily_mean_lower": float(np.quantile(boot, .05 / TRIALS)) if complete else None,
                           "net_excluding_best_day": float(pnl.sum() - pnl.max()) if complete else None,
                           "partial_entries": sum(r["counts"]["partial_entries"] for r in records),
                           "mixed_exits": sum(r["counts"]["mixed_exits"] for r in records)}
    (OUTPUT / f"{section}_results.json").write_text(json.dumps(summaries, indent=2) + "\n")
    (OUTPUT / f"{section}_audits.json").write_text(json.dumps(audits, indent=2) + "\n")
    return summaries


def passes_gate(family, minimum_days):
    base = family["base"]
    return (all(value["complete"] and value["net_dollars"] > 0 for value in family.values())
            and base["trades"] >= 100 and base["positive_days"] >= minimum_days
            and base["adjusted_daily_mean_lower"] > 0 and base["net_excluding_best_day"] > 0)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if (OUTPUT / "results.json").exists() or (OUTPUT / "specification.json").exists():
        raise FileExistsError("Versioned batch already started; preserve its frozen artifacts")
    code = [ROOT / "research/crypto_passive_partial.py", ROOT / "research/crypto_passive_replay.py",
            ROOT / "research_scout/run_crypto_passive_partial_20260930.py"]
    scenarios, names = {}, []
    for direction in ("imbalance", "follow", "fade"):
        for offset in (8.0, 16.0):
            name = f"{direction}_{int(offset)}bps"
            names.append(name)
            rule = PartialRule(direction, offset)
            scenarios[name + "_base"] = asdict(rule)
            scenarios[name + "_double_fees"] = asdict(replace(rule, maker_fee_bps=4, taker_fee_bps=10))
            scenarios[name + "_latency_1s"] = asdict(replace(rule, order_delay_ms=1000))
            scenarios[name + "_full_first_print"] = asdict(replace(rule, full_on_first_through=True))
    spec = {"created_at_utc": datetime.now(UTC).isoformat(), "development": DEVELOPMENT,
            "selection": SELECTION, "scenarios": scenarios,
            "changes": ["All qualifying through-price volume causes partial fills; no ignored small fills or leftover inventory",
                        "Partial entry waits for remainder cancellation acknowledgement before exit submission",
                        "Partial exit remainder crosses only after old limit cancellation acknowledgement and outbound latency",
                        "Quantity uses only delayed pre-decision depth; no arrival-depth-based selection",
                        "Full-first-print is a distinct fill-model sensitivity, not a conservative claim"],
            "fees": "2bp maker, 5bp taker per side; 1bp additional execution-cost allowance on taker exit notional",
            "capital": "Each date starts $10000; one maximum $1000 ticket; not compounded across isolated dates",
            "gate": "Complete and profitable under every scenario; >=100 base fills; >=75% positive days; date bootstrap lower>0 after 36-version correction; profitable excluding best day",
            "limits": "Neither print-volume nor full-first-print replay is a real-fill or P&L bound. At-price fills and impact remain unknown. Same six hypotheses, repaired implementation; all history has prior research exposure. Bootstrap on five isolated dates cannot establish production reliability.",
            "code_sha256": {str(path.relative_to(ROOT)): digest(path) for path in code}}
    (OUTPUT / "specification.json").write_text(json.dumps(spec, indent=2) + "\n")
    development = run_section(DEVELOPMENT, scenarios, "development")
    survivors = []
    for name in names:
        family = {key.removeprefix(name + "_"): value for key, value in development.items() if key.startswith(name + "_")}
        passed = passes_gate(family, 4)
        base = family["base"]
        print(f"{name}: net={base['net_dollars']}, {base['trades']} trades, partial entries={base['partial_entries']}, passed={passed}", flush=True)
        if passed:
            survivors.append(name)
    result = {"development_survivors": survivors, "selection_opened": False,
              "verdict": "NO_DEVELOPMENT_SURVIVOR"}
    if survivors:
        selected = {key: value for key, value in scenarios.items() if any(key.startswith(name + "_") for name in survivors)}
        (OUTPUT / "frozen_selection.json").write_text(json.dumps({"survivors": survivors, "created_at_utc": datetime.now(UTC).isoformat()}, indent=2))
        selection = run_section(SELECTION, selected, "selection")
        result.update(selection_opened=True, selection_results=selection,
                      verdict="SELECTION_REQUIRES_REVIEW_BEFORE_FURTHER_HISTORY")
    assert all(digest(path) == spec["code_sha256"][str(path.relative_to(ROOT))] for path in code)
    (OUTPUT / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result["verdict"], flush=True)


if __name__ == "__main__":
    main()
