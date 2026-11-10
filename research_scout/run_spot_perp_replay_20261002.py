"""Run the single selected event only after independently verified selection."""

import gzip
import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal as D

import pandas as pd

from research.spot_perp_response import parse, plan, replay
from research_scout.prepare_spot_perp_replay_20261002 import OUT, PARENT, ROOT, sha


def convert(value):
    if isinstance(value, D):
        return str(value)
    raise TypeError(type(value).__name__)


def dump(path, value):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, default=convert, indent=2, allow_nan=False) + "\n")


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    source = json.loads((OUT / "source_manifest.json").read_text())
    audit = json.loads((PARENT / "independent_verification.json").read_text())
    assert audit["verified"] and audit["selected_events_verified"] == 1
    assert sha(PARENT / "screen_results.json") == audit["results_sha256"] == spec["source_screen_results_sha256"]
    assert sha(ROOT / spec["events_path"]) == spec["events_sha256"]
    assert source["complete"] and sha(ROOT / source["path"]) == source["compressed_sha256"]
    output = OUT / "replay_v1"
    output.mkdir(exist_ok=True)
    code = ["research/spot_perp_response.py", "research/futures_response_hft.py", "research/spot_perp_supply.py",
            "tests/unit/test_spot_perp_response.py", "research_scout/run_spot_perp_replay_20261002.py"]
    dump(output / "implementation.json", {"frozen_at_utc": datetime.now(UTC).isoformat(),
         "specification_sha256": sha(OUT / "specification.json"), "source_manifest_sha256": sha(OUT / "source_manifest.json"),
         "source_screen_audit_sha256": sha(PARENT / "independent_verification.json"),
         "events_sha256": spec["events_sha256"], "code_sha256": {p: sha(ROOT / p) for p in code},
         "focused_tests_passed": 8, "economic_rules": 2, "scenarios": 12})
    event = pd.read_parquet(ROOT / spec["events_path"]).to_dict("records")[0]
    with gzip.open(ROOT / source["path"], "rt", encoding="utf-8") as stream:
        tape, counts = parse(stream, event["date"])
    intents = {rule: plan(tape, event, rule) for rule in spec["rules"]}
    dump(output / "intents.json", intents)
    # Verify the captured signal against the original all-symbol source rather
    # than trusting that a filtered re-download preserved its clock/order.
    original_sources = json.loads((PARENT / "source_manifest.json").read_text())["files"]
    original = next(r for r in original_sources if r["date"] == event["date"] and r["offset"] == int(event["offset_minutes"]) and r["venue"] == "perpetual")
    assert sha(ROOT / original["path"]) == original["compressed_sha256"]
    original_line = int(event["perpetual_source_line"])
    with gzip.open(ROOT / original["path"], "rt", encoding="utf-8") as stream:
        for index, line in enumerate(stream):
            if index == original_line:
                raw = json.loads(line.split(" ", 1)[1])["data"]
                break
        else:
            raise AssertionError("Original signal line absent")
    signal = next(r for r in tape.books if r["update_id"] == int(raw["u"]))
    assert signal["bid"] == D(event["entry_quote"]) == D(raw["b"])
    for intent in intents.values():
        if intent["eligible"]:
            assert intent["signal_book"]["update_id"] == int(raw["u"])
    scenarios = []
    for rule, intent in intents.items():
        for scenario in spec["scenarios"]:
            result = replay(tape, event, intent, scenario)
            complete = not result["status"].startswith("unknown")
            lower = result.get("lower", {}).get("net", D(0) if complete else None)
            upper = result.get("upper", {}).get("net", D(0) if complete else None)
            row = {"rule": rule, "scenario": scenario["name"], "complete": complete,
                   "net_lower": lower, "net_upper": upper, "outcome": result["status"],
                   "result": result, "actual_execution_verified": False}
            dump(output / f"{rule}_{scenario['name']}.json", row)
            scenarios.append(row)
            print(json.dumps({k: row[k] for k in ("rule", "scenario", "complete", "net_lower", "net_upper", "outcome")}, default=convert), flush=True)
    results = {"economic_configurations_run": 2, "scenario_cases": 12, "events": 1,
               "source_counts": counts, "scenarios": scenarios,
               "outcomes": dict(Counter(r["outcome"] for r in scenarios)),
               "complete_scenarios": sum(r["complete"] for r in scenarios),
               "positive_complete_scenarios": sum(r["complete"] and r["net_lower"] > 0 for r in scenarios),
               "independent_execution_audit_complete": False, "actual_execution_verified": False,
               "historical_lot_size_verified": False, "historical_permissions_verified": False,
               "selection_2025_opened": False, "candidates": [], "reliable_edge_established": False}
    dump(output / "results.json", results)


if __name__ == "__main__":
    main()
