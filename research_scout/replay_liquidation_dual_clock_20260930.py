"""Exchange-time correction of the frozen liquidation screen; no signal tuning."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from research.cross_venue_dual_clock import extract_dual_clock
from research.crypto_symbol_cache import digest
from research.liquidation_event_replay import quote_targets, simulate
from research_scout.run_liquidation_event_20260930 import summary

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research_scout/liquidation_event_20260930"
OUT = BASE / "dual_clock"


def extract(day):
    events_path = BASE / "panels" / f"{day}_events.parquet"
    events = pd.read_parquet(events_path)
    targets = quote_targets(events)
    original_labels = targets.label.copy()
    # Both decision inputs are receive-clock information, including the lagged
    # price control. Renaming only for the extractor prevents future capture leak.
    targets.loc[targets.label.eq("prior30"), "label"] = "signal"
    raw = BASE / "raw/book_snapshot_5" / day / "BTCUSDT.csv.gz"
    manifest = json.loads(raw.with_suffix(raw.suffix + ".json").read_text())
    assert digest(raw) == manifest["sha256"]
    quotes, audit = extract_dual_clock(raw, day, targets)
    quotes["label"] = original_labels
    path = OUT / f"{day}_quotes.parquet"
    quotes.to_parquet(path, index=False)
    audit.update({"events_sha256": digest(events_path), "panel_sha256": digest(path),
                  "source_sha256": manifest["sha256"], "events": len(events)})
    return quotes, audit


def evaluation_view(quotes):
    view = quotes.copy()
    physical = ~view.label.isin(["signal", "prior30"])
    # The immutable original simulator's depth walker uses source_delay only as
    # a receive-clock quality guard. Historical physical-book execution does not
    # depend on later capture latency; retain it separately for the audit.
    view["original_capture_delay_us"] = view.source_delay_us
    view.loc[physical, "source_delay_us"] = 0
    bad = physical & (view.exchange_clock_ambiguous | view.original_capture_delay_us.lt(-1000))
    view.loc[bad, "quote_age_us"] = 1_000_001
    return view


def main():
    OUT.mkdir(exist_ok=True)
    spec_path = OUT / "specification.json"
    if spec_path.exists():
        raise FileExistsError("Corrected liquidation batch already started")
    old = json.loads((BASE / "strategy_specification.json").read_text())
    for name, sha in old["code_sha256"].items():
        assert digest(ROOT / name) == sha
    code = [ROOT / p for p in ("research/cross_venue_dual_clock.py", "research/liquidation_event_replay.py",
                               "research_scout/run_liquidation_event_20260930.py",
                               "research_scout/replay_liquidation_dual_clock_20260930.py")]
    spec = {"created_at_utc": datetime.now(UTC).isoformat(), "original_spec_sha256": digest(BASE / "strategy_specification.json"),
            "evaluation": old["evaluation"], "directions": old["directions"], "modes": old["modes"],
            "horizons_seconds": old["horizons_seconds"], "configs": old["configs"],
            "correction": "All original signals, costs, quantities, collars, holding periods and delays preserved. Decisions and prior30 controls use capture time; submitted-order fills use strictly-prior exchange-time states. No re-fitting or new dates.",
            "freshness": "Original one-second quote-age threshold remains, now measured against exchange timestamps for fills. Capture skew below -1ms or a locally ambiguous exchange timestamp invalidates the submitted outcome. Raw actual capture delay is retained.",
            "prior_exposure": "All original 16 liquidation/control outcomes have been seen; this is an implementation correction, not new untouched validation.",
            "reliability": "No confidence improvement is inferred from the replay. Six dependent-date samples, historical tuning and prior failed rules remain. Original 64-version intervals are reproduced as diagnostics only; any new promotion requires a full current-exposure correction and independent data.",
            "code_sha256": {str(p.relative_to(ROOT)): digest(p) for p in code}}
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    panels, audits = [], []
    with ProcessPoolExecutor(max_workers=2) as pool:
        for job in as_completed([pool.submit(extract, day) for day in old["evaluation"]]):
            panel, audit = job.result()
            panels.append(panel)
            audits.append(audit)
            print(f"{audit['date']}: {audit['events']} frozen events, {audit['exchange_backtracks']} clock backtracks", flush=True)
    quotes = evaluation_view(pd.concat(panels, ignore_index=True))
    results, positive_complete = {}, []
    for direction in old["directions"]:
        for mode in old["modes"]:
            for horizon in old["horizons_seconds"]:
                name = f"{direction}_{mode}_{horizon}s"
                scenarios = {}
                for scenario, kwargs in {"base": {}, "double_fees": {"fee_bps": 10}, "latency_3s": {"delay_ms": 3000}}.items():
                    trades, daily = simulate(quotes, direction, mode, horizon, **kwargs)
                    trades.to_parquet(OUT / f"{name}_{scenario}_trades.parquet", index=False)
                    daily.to_parquet(OUT / f"{name}_{scenario}_daily.parquet", index=False)
                    scenarios[scenario] = summary(trades, daily)
                results[name] = {"scenarios": scenarios, "is_price_control": direction.startswith("price_")}
                if all(x["complete"] and x["net_dollars"] > 0 for x in scenarios.values()):
                    positive_complete.append(name)
                print(f"{name}: net={scenarios['base']['net_dollars']}, gross={scenarios['base']['gross_dollars']:+.4f}, trades={scenarios['base']['trades']}", flush=True)
    assert all(digest(ROOT / p) == expected for p, expected in spec["code_sha256"].items())
    (OUT / "results.json").write_text(json.dumps({"results": results, "source_audits": audits,
        "complete_and_positive_all_scenarios": positive_complete, "reliable_edge_established": False}, indent=2) + "\n")


if __name__ == "__main__":
    main()
