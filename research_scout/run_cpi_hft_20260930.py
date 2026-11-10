"""Replay both frozen CPI holding periods with unresolved paths retained."""

import json
from datetime import UTC, datetime

import exchange_calendars as xc
import numpy as np
import pandas as pd

from research.alpaca_quote_units import sip_sizes_in_shares
from research.cpi_quote_benchmark import SCENARIOS, replay
from research.crypto_symbol_cache import digest
from research_scout.prepare_cpi_hft_20260930 import OUT, ROOT


def exact_frame(rows):
    frame = pd.DataFrame(rows)
    for name in frame:
        if name.endswith("_ns") or name in {"quote_index", "first_index", "stop_index", "quantity"}:
            frame[name] = pd.array([r.get(name) for r in rows], dtype="Int64")
    return frame


def summarize(frame):
    complete = bool(frame.conditional_complete.all())
    priced = frame.loc[frame.status.eq("conditional_round_trip")]
    lower, upper = float(frame.net_lower.fillna(0).sum()), float(frame.net_upper.fillna(0).sum())
    days = frame.net_lower.fillna(0).to_numpy(float)
    rng = np.random.default_rng(20260930)
    boot = rng.choice(days, size=(20000, len(days)), replace=True).sum(axis=1)
    positive = sorted([v for v in days if v > 0], reverse=True)
    return {"conditional_complete": complete, "net_lower": lower if complete else None,
            "net_upper": upper if complete else None, "closed_lower": lower, "closed_upper": upper,
            "priced_trades": len(priced), "positive_dates": int((days > 0).sum()),
            "without_best_three": lower-sum(positive[:3]) if complete else None,
            "bootstrap_97_5_lower": float(np.quantile(boot, .025)) if complete else None,
            "priced_by_symbol": priced.groupby("symbol").net_lower.sum().to_dict(),
            "outcomes": frame.status.value_counts().to_dict(), "actual_execution_verified": False}


def main():
    dest = OUT/"conditional_benchmark"
    dest.mkdir(exist_ok=True)
    if (dest/"results.json").exists():
        raise RuntimeError("Preserve frozen economic results")
    spec = json.loads((OUT/"specification.json").read_text())
    manifest = json.loads((OUT/"quote_manifest.json").read_text())
    assert len(manifest["files"]) == manifest["expected_files"] == 33
    assert digest(OUT/"specification.json") == manifest["specification_sha256"]
    assert json.loads((OUT/"source_audit/bls_verification.json").read_text())["verified"]
    assert digest(OUT/"content_events.parquet") == json.loads((OUT/"content_results.json").read_text())["panel_sha256"]
    files = ["research/cpi_quote_benchmark.py", "research/halt_hft.py", "research/alpaca_quote_units.py",
             "research_scout/run_cpi_hft_20260930.py", "research_scout/verify_cpi_releases_20260930.py"]
    freeze = {"created_at_utc": datetime.now(UTC).isoformat(), "implementation_sha256": {p: digest(ROOT/p) for p in files},
              "protocol_sha256": digest(OUT/"specification.json"), "manifest_sha256": digest(OUT/"quote_manifest.json"),
              "calendar_elaboration": "CPI may be published on an exchange holiday. XNYS closed date means no venue session and no order; never move signal to next session. Such events remain in the84-release cohort. No alpha filter or return-dependent change.",
              "source_economic_limit": "Current official dated nowcasts and first releases reconciled; historical receipt time, exact venue state and premarket FOK routing remain conditional. No actual execution verified."}
    (dest/"specification.json").write_text(json.dumps(freeze, indent=2)+"\n")
    events = pd.read_parquet(OUT/"content_events.parquet")
    calendar = xc.get_calendar("XNYS", start="2017-01-01", end="2023-12-31")
    cached = {}
    source_records = {(r["date"], r["symbol"]): r for r in manifest["files"]}
    for r in manifest["files"]:
        if r["complete"]:
            p = ROOT/r["path"]
            assert digest(p) == r["sha256"]
            cached[(r["date"], r["symbol"])] = sip_sizes_in_shares(pd.read_parquet(p), legacy_round_lot_shares=100, feed="sip")
    results, traces, advance = {}, [], []
    for config in spec["configurations"]:
        hold = config["hold_seconds"]
        key = f"{hold}s"
        results[key] = {}
        for scenario, kwargs in SCENARIOS.items():
            rows = []
            for event in events.to_dict("records"):
                day, symbol = event["release_date"], event["symbol"]
                base = {"date": day, "symbol": symbol, "hold_seconds": hold, "scenario": scenario,
                        "conditional_complete": True, "net_lower": 0., "net_upper": 0., "actual_execution_verified": False}
                if not event["content_trigger"]:
                    row, trace = {**base, "status": "no_content_trigger"}, []
                elif not calendar.is_session(day):
                    row, trace = {**base, "status": "no_order_exchange_holiday"}, []
                elif not source_records[(day, symbol)]["complete"]:
                    row, trace = {**base, "status": "unknown_source", "conditional_complete": False,
                                  "net_lower": None, "net_upper": None}, []
                else:
                    release = pd.Timestamp(day+" 08:30", tz="America/New_York").tz_convert("UTC").value
                    output, trace = replay(cached[(day, symbol)], release, hold, **kwargs)
                    row = {**base, **output}
                rows.append(row)
                traces.extend({"date": day, "symbol": symbol, "hold_seconds": hold, "scenario": scenario, **r} for r in trace)
            frame = exact_frame(rows)
            frame.to_parquet(dest/f"ledger_{key}_{scenario}.parquet", index=False)
            results[key][scenario] = summarize(frame)
        b = results[key]["base"]
        if (all(r["conditional_complete"] and r["net_lower"] > 0 for r in results[key].values())
                and b["priced_trades"] >= 12 and b["without_best_three"] > 0 and b["bootstrap_97_5_lower"] > 0
                and all(b["priced_by_symbol"].get(s, 0) > 0 for s in ["SPY", "SH"])):
            advance.append(key)
    exact_frame(traces).to_parquet(dest/"quote_windows.parquet", index=False)
    report = {"results": results, "advance_to_selection": advance, "selection_opened": False,
              "actual_strategy_execution_verified": False, "reliable_edge_established": False}
    (dest/"results.json").write_text(json.dumps(report, indent=2)+"\n")
    for key, values in results.items():
        print(json.dumps({"configuration": key, "base": values["base"]}))
    print(json.dumps({"advance_to_selection": advance}))


if __name__ == "__main__":
    main()
