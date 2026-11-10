"""Freeze and run the predeclared post-settlement price-only scenarios."""

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal as D

import pandas as pd

from research.post_funding_hft import entry_plan, load_window, replay
from research_scout.prepare_post_funding_20261002 import OUT, ROOT, SOURCE


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def convert(value):
    if isinstance(value, D):
        return str(value)
    raise TypeError(type(value).__name__)


def dump(path, value):
    with path.open("x") as stream:
        stream.write(json.dumps(value, default=convert, indent=2, allow_nan=False)+"\n")


def main():
    replay_out = OUT/"replay_v1"
    replay_out.mkdir(exist_ok=True)
    assert not (replay_out/"results.json").exists(), "Preserve frozen economic outcomes"
    spec = json.loads((OUT/"specification.json").read_text())
    assert sha(ROOT/spec["events_path"]) == spec["events_sha256"]
    events = pd.read_parquet(ROOT/spec["events_path"]).sort_values(["date", "hour", "symbol"]).to_dict("records")
    manifest = json.loads((SOURCE/"native_manifest.json").read_text())
    code = ["research_scout/run_post_funding_20261002.py", "research/post_funding_hft.py",
            "tests/unit/test_post_funding_hft.py", "research/external_quote_hft.py", "research/wide_tick_supply.py"]
    freeze = {"frozen_at_utc": datetime.now(UTC).isoformat(), "specification_sha256": sha(OUT/"specification.json"),
              "source_manifest_sha256": sha(SOURCE/"native_manifest.json"), "events_sha256": spec["events_sha256"],
              "code_sha256": {p: sha(ROOT/p) for p in code}, "focused_tests_passed": 11,
              "economic_rules": 2, "scenario_cases": 10, "actual_execution_verified": False}
    freeze_path = replay_out/"implementation.json"
    if freeze_path.exists():
        old = json.loads(freeze_path.read_text())
        for key in ("specification_sha256", "source_manifest_sha256", "events_sha256", "code_sha256"):
            assert old[key] == freeze[key]
    else:
        dump(freeze_path, freeze)
    source_map = {(r["date"], r["hour"]): r for r in manifest["files"]}
    books, tickers, diagnostics, plans = {}, {}, [], []
    reserved = Counter()
    for event in events:
        key = event["date"], event["hour"]
        if key not in books:
            source = source_map.get(key)
            if source is None or not source["complete"]:
                books[key], tickers[key] = None, None
            else:
                midnight = event["settlement_ns"]//(86400*1_000_000_000)*(86400*1_000_000_000)
                books[key], tickers[key], diag = load_window(ROOT, source, midnight)
                diagnostics.append({"date": key[0], "hour": key[1], **diag})
        row = {k: event[k] for k in ("date", "hour", "symbol", "settlement_ns", "bybit_funding_rate")}
        if books[key] is None:
            row.update(eligible=False, reason="unknown_native_source", source_known=False)
        else:
            row.update(entry_plan(books[key][event["symbol"]], tickers[key][event["symbol"]], event["settlement_ns"]), source_known=True)
            if row["eligible"]:
                reserve = D(str(row["quantity"]))*D(str(row["ask"]))*D("1.0014")
                if reserved[event["date"]]+reserve > 10000:
                    row.update(eligible=False, reason="insufficient_fully_collateralized_capital")
                else:
                    reserved[event["date"]] += reserve
                    row["capital_reserved"] = reserve
        plans.append(row)
    dump(replay_out/"plans.json", {"events": plans, "diagnostics": diagnostics, "capital_reserved_by_date": dict(reserved),
                                   "gate_outcomes": dict(Counter(r["reason"] for r in plans))})
    print(json.dumps({"events": len(plans), "admitted": sum(r["eligible"] for r in plans),
                      "gate_outcomes": dict(Counter(r["reason"] for r in plans))}), flush=True)
    summaries = []
    for rule in spec["rules"]:
        for scenario in spec["scenarios"]:
            ledger = []
            for event, plan in zip(events, plans, strict=True):
                result = {"date": event["date"], "hour": event["hour"], "symbol": event["symbol"], "rule": rule,
                          "scenario": scenario["name"], "submitted": False, "known": plan["source_known"], "reason": plan["reason"]}
                if plan["eligible"]:
                    key = event["date"], event["hour"]
                    result.update(replay(books[key][event["symbol"]], tickers[key][event["symbol"]], event, plan, rule, scenario))
                ledger.append(result)
            filename = f"{rule}_{scenario['name']}.json"
            dump(replay_out/filename, {"events": ledger})
            known = [r for r in ledger if r["submitted"] and r["known"]]
            unknown = [r for r in ledger if not r["known"]]
            dates = []
            for date in sorted({r["date"] for r in ledger}):
                day = [r for r in ledger if r["date"] == date]
                complete = all(r["known"] for r in day)
                lower = sum((r["lower"]["net"] for r in day if r["submitted"] and r["known"]), D(0))
                upper = sum((r["upper"]["net"] for r in day if r["submitted"] and r["known"]), D(0))
                dates.append({"date": date, "complete": complete, "net_lower": lower if complete else None,
                              "net_upper": upper if complete else None, "known_component_lower": lower,
                              "known_component_upper": upper, "submitted": sum(r["submitted"] for r in day),
                              "unknown": sum(not r["known"] for r in day)})
            lower = sum((r["lower"]["net"] for r in known), D(0))
            upper = sum((r["upper"]["net"] for r in known), D(0))
            summary = {"rule": rule, "scenario": scenario["name"], "complete": not unknown,
                       "events": len(ledger), "submitted": sum(r["submitted"] for r in ledger), "known_submitted": len(known),
                       "unknown_events": len(unknown), "net_lower": lower if not unknown else None,
                       "net_upper": upper if not unknown else None, "known_component_lower": lower, "known_component_upper": upper,
                       "positive_lower_events": sum(r["lower"]["net"] > 0 for r in known),
                       "negative_upper_events": sum(r["upper"]["net"] < 0 for r in known),
                       "gross_lower_components": sum((r["lower"]["gross"] for r in known), D(0)),
                       "fee_lower_components": sum((r["lower"]["fees"] for r in known), D(0)),
                       "adverse_lower_components": sum((r["lower"]["adverse"] for r in known), D(0)),
                       "outcomes": dict(Counter(r["reason"] for r in ledger)), "by_date": dates,
                       "ledger": filename, "ledger_sha256": sha(replay_out/filename)}
            summaries.append(summary)
            print(json.dumps({k: v for k, v in summary.items() if k not in ("by_date", "outcomes")}, default=convert), flush=True)
    result = {"family": spec["family"], "economic_configurations_run": 2, "scenario_cases": 10, "scenarios": summaries,
              "source_files": len(manifest["files"]), "native_messages": sum(r["native_messages"] for r in diagnostics),
              "source_decoded_bytes": manifest["decoded_bytes"], "source_complete": manifest["complete"],
              "plans_sha256": sha(replay_out/"plans.json"), "implementation_sha256": sha(freeze_path),
              "complete_scenarios": sum(r["complete"] for r in summaries),
              "positive_lower_complete_scenarios": sum(r["complete"] and r["net_lower"] > 0 for r in summaries),
              "independent_execution_audit_complete": False, "actual_execution_verified": False,
              "funding_payment_assumed": False, "selection_2025_opened": False, "reliable_edge_established": False}
    dump(replay_out/"results.json", result)


if __name__ == "__main__":
    main()
