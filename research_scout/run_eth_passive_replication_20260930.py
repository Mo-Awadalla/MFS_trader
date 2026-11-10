"""Fixed six-rule passive BTC-family replication on cached ETH data."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from research.crypto_passive_multisymbol import PartialRule, replay_partial_day
from research.crypto_symbol_cache import build_symbol_day, digest, load_cache

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout/eth_passive_replication_20260930"
DEVELOPMENT = ["2023-08-15", "2023-09-15", "2023-10-15", "2023-11-15", "2023-12-15"]
SELECTION = ["2024-01-15", "2024-01-21", "2024-01-28", "2024-01-31"]
TRIALS = 48


def run_day(day, scenarios):
    path, audit = build_symbol_day("ETHUSDT", day)
    book, trades = load_cache(path)
    for values, units in ((book["bid"], 100), (book["ask"], 100), (trades["price"], 100), (trades["quantity"], 1000)):
        finite = values[np.isfinite(values)] * units
        if not np.all(np.abs(finite - np.round(finite)) < 1e-6):
            raise ValueError(f"Price/size increments incompatible with frozen ETH contract: {day}")
    results = {name: replay_partial_day(book, trades, PartialRule(**rule), day) for name, rule in scenarios.items()}
    return day, audit, results


def summarize(records, name, split):
    records.sort(key=lambda x: x["date"])
    ledger = [trade for day in records for trade in day.pop("trades")]
    pd.DataFrame(ledger).to_parquet(OUTPUT / f"{split}_{name}_trades.parquet", index=False)
    complete = all(day["complete"] for day in records)
    pnl = np.array([day["closed_trade_pnl"] for day in records])
    priced = [row for row in ledger if row["status"] == "priced"]
    rng = np.random.default_rng(93026)
    boot = pnl[rng.integers(0, len(pnl), (20000, len(pnl)))].mean(axis=1)
    return {"daily": records, "complete": complete, "closed_trade_subtotal": float(pnl.sum()),
            "net_dollars": float(pnl.sum()) if complete else None, "trades": len(priced),
            "positive_days": int((pnl > 0).sum()) if complete else None,
            "mean_net_bps": float(np.mean([row["net_bps"] for row in priced])) if priced else None,
            "daily_mean_ci95": np.quantile(boot, [.025, .975]).tolist() if complete else None,
            "adjusted_daily_mean_lower": float(np.quantile(boot, .05 / TRIALS)) if complete else None,
            "net_excluding_best_day": float(pnl.sum() - pnl.max()) if complete else None}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if (OUTPUT / "specification.json").exists():
        raise FileExistsError("Replication already started")
    scenarios, names = {}, []
    for direction in ("imbalance", "follow", "fade"):
        for offset in (8., 16.):
            name = f"{direction}_{int(offset)}bps"
            names.append(name)
            rule = PartialRule(direction, offset, tick_size=.01, quantity_step=.001)
            scenarios[name + "_base"] = asdict(rule)
            scenarios[name + "_double_fees"] = asdict(replace(rule, maker_fee_bps=4, taker_fee_bps=10))
            scenarios[name + "_latency_1s"] = asdict(replace(rule, order_delay_ms=1000))
            scenarios[name + "_full_first_print"] = asdict(replace(rule, full_on_first_through=True))
    sources = [ROOT / relative for relative in ("research/crypto_passive_multisymbol.py", "research/crypto_symbol_cache.py",
                                                "research_scout/run_eth_passive_replication_20260930.py")]
    spec = {"created_at_utc": datetime.now(UTC).isoformat(), "development": DEVELOPMENT, "selection": SELECTION,
            "symbol": "ETHUSDT", "scenarios": scenarios, "configuration_count": 6, "current_version_correction": TRIALS,
            "hypothesis": "The same fixed passive rules may have different spread-capture versus adverse-selection economics in ETH than BTC.",
            "protocol": "All six frozen rules are evaluated in both chronological sections; no fitting or choosing parameters from ETH outcomes. ETH prices use 0.01 quote increments, quantities 0.001 ETH; verify these increments against source values.",
            "costs": "2bp maker, 5bp taker per side, 1bp extra cost on taker exits; stress doubles fees. $10000 daily account, max $1000 ticket, <=10% decision-time touch size.",
            "gate": "Both periods separately: all scenarios complete and net positive, >=100 base trades, >=75% positive days, 48-version-adjusted date-bootstrap lower>0, profit without best day>0. No declaration of production reliability from nine previously exposed dates.",
            "limits": "Counterfactual tape, not queue or impact simulation. Trade-through prints do not resolve at-price fills. Same dates have historical research exposure and are correlated with BTC. Only exact ETH tick/quantity increments differ from the BTC rules.",
            "code_sha256": {str(path.relative_to(ROOT)): digest(path) for path in sources}}
    (OUTPUT / "specification.json").write_text(json.dumps(spec, indent=2) + "\n")
    combined = {name: [] for name in scenarios}
    audits = []
    with ProcessPoolExecutor(max_workers=2) as pool:
        for job in as_completed([pool.submit(run_day, day, scenarios) for day in DEVELOPMENT + SELECTION]):
            day, audit, results = job.result()
            audits.append(audit)
            for name, result in results.items():
                combined[name].append(result)
            print(f"ETH passive replay finished {day}", flush=True)
    split_results = {}
    for split, days in (("development", DEVELOPMENT), ("selection", SELECTION)):
        split_results[split] = {name: summarize([dict(day) for day in records if day["date"] in days], name, split)
                                for name, records in combined.items()}
    survivors = []
    for name in names:
        passed = True
        for split, days in (("development", DEVELOPMENT), ("selection", SELECTION)):
            family = {key: value for key, value in split_results[split].items() if key.startswith(name + "_")}
            base = family[name + "_base"]
            passed &= (all(value["complete"] and value["net_dollars"] > 0 for value in family.values())
                       and base["trades"] >= 100 and base["positive_days"] >= np.ceil(len(days) * .75)
                       and base["adjusted_daily_mean_lower"] > 0 and base["net_excluding_best_day"] > 0)
        if passed:
            survivors.append(name)
        dev, later = split_results["development"][name + "_base"], split_results["selection"][name + "_base"]
        print(f"{name}: development {dev['net_dollars']}, later {later['net_dollars']}, later trades {later['trades']}, pass={passed}", flush=True)
    assert all(digest(path) == spec["code_sha256"][str(path.relative_to(ROOT))] for path in sources)
    results = {"verdict": "CANDIDATES_REQUIRE_MORE_EVIDENCE" if survivors else "NO_REPLICATION_SURVIVOR",
               "survivors": survivors, "results": split_results, "audits": audits}
    (OUTPUT / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print(results["verdict"], flush=True)


if __name__ == "__main__":
    main()
