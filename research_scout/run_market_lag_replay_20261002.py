"""Run the frozen controls after both independent selection audits pass."""

import gzip
import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal as D

import pandas as pd

from research.perp_shock_response import episode, parse, plan
from research.spot_perp_response import before
from research_scout.prepare_market_lag_replay_20261002 import FLOW, OUT, ROOT, TARGET, sha


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
    assert source["complete"] and source["specification_sha256"] == sha(OUT / "specification.json")
    assert source["acquisition_sha256"] == sha(ROOT / "research_scout/fetch_market_lag_replay_20261002.py")
    for parent, field, count_field in ((TARGET, "target_results_sha256", "selected_target_events_verified"),
                                       (FLOW, "flow_results_sha256", "selected_events_verified")):
        audit = json.loads((parent / "independent_verification.json").read_text())
        assert audit["verified"] and audit[count_field] == 1
        assert sha(parent / "screen_results.json") == audit["results_sha256"] == spec[field]
    assert sha(ROOT / spec["events_path"]) == spec["events_sha256"]
    events = pd.read_parquet(ROOT / spec["events_path"]).to_dict("records")
    output = OUT / "replay_v1"
    output.mkdir(exist_ok=True)
    code = ["research/perp_shock_response.py", "research/spot_perp_response.py", "research/futures_response_hft.py",
            "research/spot_perp_supply.py", "tests/unit/test_perp_shock_response.py",
            "research_scout/run_market_lag_replay_20261002.py"]
    dump(output / "implementation.json", {"frozen_at_utc": datetime.now(UTC).isoformat(),
         "specification_sha256": sha(OUT / "specification.json"), "source_manifest_sha256": sha(OUT / "source_manifest.json"),
         "quote_audit_sha256": sha(TARGET / "independent_verification.json"),
         "flow_audit_sha256": sha(FLOW / "independent_verification.json"),
         "events_sha256": spec["events_sha256"], "code_sha256": {p: sha(ROOT / p) for p in code},
         "reused_focused_tests_passed": 14, "new_focused_tests": 0, "economic_rules": 2, "scenario_cases": 12})
    sources = {(r["date"], r["offset"], r["symbol"]): r for r in source["files"]}
    original = json.loads((TARGET / "screen_results.json").read_text())
    windows = {(r["date"], r["offset"]): r for r in original["windows"]}
    tapes, intents, intent_rows, counts, source_rows = {}, {}, [], Counter(), []
    for event in events:
        key = (event["date"], event["symbol"], int(event["decision_ns"]))
        row = sources[(event["date"], int(event["offset_minutes"]), event["symbol"])]
        assert row["complete"] and sha(ROOT / row["path"]) == row["compressed_sha256"]
        with gzip.open(ROOT / row["path"], "rt", encoding="utf-8") as stream:
            tape, native_counts = parse(stream, event["date"], event["offset_minutes"], event["symbol"], D(spec["grids"][event["symbol"]]))
        counts.update(native_counts)
        window = windows[(event["date"], int(event["offset_minutes"]))]
        assert sha(ROOT / window["quotes_path"]) == window["quotes_sha256"]
        ledger = pd.read_parquet(ROOT / window["quotes_path"])
        signal = ledger[(ledger.symbol == event["symbol"]) & (ledger.decision_ns == event["decision_ns"])].to_dict("records")
        assert len(signal) == 1 and signal[0]["sequence_ok"] and signal[0]["transaction_order_ok"]
        quote = before(tape.books, int(event["decision_ns"]) - 250_000_000)
        for field in ("receive_ns", "transaction_ns", "publication_ns", "update_id"):
            assert quote[field] == int(signal[0][field]), (key, field)
        for field in ("bid", "ask", "bid_quantity", "ask_quantity"):
            assert quote[field] == D(signal[0][field]), (key, field)
        tapes[key] = tape
        intents[key] = {rule: plan(tape, event, spec["engine_rule_mapping"][rule], D(spec["grids"][event["symbol"]])) for rule in spec["rules"]}
        intent_rows.append({"date": event["date"], "symbol": event["symbol"], "decision_ns": int(event["decision_ns"]),
                            "original_signal_verified": True, "intents": intents[key]})
        source_rows.append({"date": row["date"], "offset": row["offset"], "symbol": row["symbol"],
                            "counts": native_counts, "physical_ordered": tape.physical_ordered,
                            "book_rows": len(tape.books), "mark_rows": len(tape.marks)})
    dump(output / "intents.json", intent_rows)
    dump(output / "native_summary.json", source_rows)
    scenarios = []
    for rule in spec["rules"]:
        for scenario in spec["scenarios"]:
            row = episode(events, tapes, intents, rule, scenario)
            dump(output / f"{rule}_{scenario['name']}.json", row)
            scenarios.append(row)
            print(json.dumps({k: row[k] for k in ("rule", "scenario", "complete", "net_lower", "net_upper",
                                                 "completed_round_trips", "outcomes")}, default=convert), flush=True)
    result = {"economic_configurations_run": 2, "scenario_cases": 12, "events": len(events),
              "dates": len({r["date"] for r in events}), "source_counts": dict(counts), "scenarios": scenarios,
              "eligible_intents": sum(p["eligible"] for rows in intents.values() for p in rows.values()),
              "complete_scenarios": sum(r["complete"] for r in scenarios),
              "positive_complete_scenarios": sum(r["complete"] and r["net_lower"] > 0 for r in scenarios),
              "independent_execution_audit_complete": False, "actual_execution_verified": False,
              "historical_price_grid_verified": False, "historical_lot_size_verified": False,
              "historical_permissions_verified": False, "selection_2025_opened": False,
              "candidates": [], "reliable_edge_established": False}
    dump(output / "results.json", result)


if __name__ == "__main__":
    main()
