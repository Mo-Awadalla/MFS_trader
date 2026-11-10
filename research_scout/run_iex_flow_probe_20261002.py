"""Evaluate newly selected activity-qualified events using already cached native DEEP."""

import gzip
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from research.iex_deep_probe_source import extract_symbol, quote_tape
from research.iex_spread_proxy import Tape, evaluate
from research_scout.prepare_iex_flow_20261002 import OUT, PARENT, ROOT, digest
from research_scout.run_iex_spread_probe_20261002 import aggregate, write

FOLDER = OUT / "price_probe_v1"


def records(path, rows):
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")


def one_event(candidate, spec, prior_results):
    day, symbol = candidate["date"], candidate["symbol"]
    flow = json.loads((OUT / "sessions" / (day + ".json")).read_text())
    assert candidate == {"date": day, **flow["selected"][0]}
    event = {**candidate, "decision_ns": flow["decision_ns"]}
    old_path = PARENT / "price_probe_v1/sessions" / (day + ".json")
    assert digest(old_path) == prior_results["session_hashes"][day]
    old = json.loads(old_path.read_text())
    result = {"event": event, "prior_event_session_path": str(old_path),
              "prior_event_session_sha256": digest(old_path),
              "specification_sha256": digest(FOLDER / "specification.json"),
              "actual_execution_verified": False, "fresh_source_messages_checked": 0}
    if event == old["event"]:
        result.update(reused_exact_audited_outcomes=True, outcomes=old["outcomes"])
    else:
        prefix = Path(old["prefix_path"])
        assert digest(prefix) == old["prefix_sha256"]
        day_source = json.loads((PARENT / "sessions" / (day + ".json")).read_text())
        assert old["source"] == day_source["source"]
        raw, coverage = extract_symbol(prefix, symbol, event["decision_ns"] + 35_000_000_000)
        assert coverage["covered"]
        venue = quote_tape(raw)
        folder = FOLDER / "sources" / day
        folder.mkdir(parents=True, exist_ok=True)
        native_path, venue_path = folder / "native_symbol.jsonl.gz", folder / "venue_tape.jsonl.gz"
        records(native_path, raw)
        records(venue_path, venue)
        tape = Tape(venue)
        outcomes = [evaluate(event, tape, c, model) for model in spec["fill_models"] for c in spec["cases"]]
        result.update(reused_exact_audited_outcomes=False, outcomes=outcomes, coverage=coverage,
                      prefix_path=str(prefix), prefix_sha256=digest(prefix),
                      native_path=str(native_path), native_sha256=digest(native_path),
                      venue_path=str(venue_path), venue_sha256=digest(venue_path),
                      native_symbol_messages=len(raw), derived_quote_count=sum(r["type"] == "Q" for r in venue),
                      fresh_source_messages_checked=coverage["messages_checked"])
    path = FOLDER / "sessions" / (day + ".json")
    assert not path.exists()
    write(path, result)
    print(json.dumps({"date": day, "symbol": symbol, "reused": result["reused_exact_audited_outcomes"],
                      "outcomes": dict(Counter(r["outcome"] for r in result["outcomes"]))}), flush=True)
    return result


def main():
    assert not (FOLDER / "results.json").exists()
    spec = json.loads((FOLDER / "specification.json").read_text())
    for relative, key in (("research_scout/run_iex_flow_probe_20261002.py", "implementation_sha256"),
                          ("research/iex_deep_probe_source.py", "source_implementation_sha256"),
                          ("research/iex_deep_supply.py", "deep_book_sha256"),
                          ("research/iex_native_prefix.py", "packet_decoder_sha256"),
                          ("research/iex_spread_proxy.py", "price_proxy_sha256"),
                          ("research_scout/run_iex_spread_probe_20261002.py", "aggregator_sha256")):
        assert digest(ROOT / relative) == spec[key]
    assert digest(OUT / "screen_results.json") == spec["parent_flow_sha256"]
    assert digest(OUT / "independent_verification.json") == spec["parent_flow_audit_sha256"]
    prior_folder = PARENT / "price_probe_v1"
    assert digest(prior_folder / "specification.json") == spec["prior_specification_sha256"]
    assert digest(prior_folder / "results.json") == spec["prior_results_sha256"]
    assert digest(prior_folder / "independent_verification.json") == spec["prior_audit_sha256"]
    prior = json.loads((prior_folder / "results.json").read_text())
    (FOLDER / "sessions").mkdir(exist_ok=True)
    sessions = [one_event(c, spec, prior) for c in spec["selected_events"]]
    by_date = {r["event"]["date"]: r for r in sessions}
    calendar, selected = [], []
    for day in spec["dates"]:
        if day in by_date:
            rows = by_date[day]["outcomes"]
            calendar.extend(rows)
            selected.extend(rows)
        else:
            unknown = day in spec["unknown_admission_dates"]
            for model in spec["fill_models"]:
                for case in spec["cases"]:
                    calendar.append({"date": day, "symbol": None, "case": case["name"], "fill_model": model,
                                     "outcome": "unknown_source_before_signal" if unknown else "conditional_no_selected_signal",
                                     "net_usd": None if unknown else "0", "actual_execution_verified": False})
    result = {"created_at_utc": datetime.now(UTC).isoformat(), "selected_events": len(sessions),
              "newly_replayed_events": sum(not r["reused_exact_audited_outcomes"] for r in sessions),
              "reused_audited_events": sum(r["reused_exact_audited_outcomes"] for r in sessions),
              "fresh_source_messages_checked": sum(r["fresh_source_messages_checked"] for r in sessions),
              "calendar_case_rows": calendar,
              "scenario_results": [aggregate(calendar, m, c["name"]) for m in spec["fill_models"] for c in spec["cases"]],
              "observed_selected_cohort_results": [aggregate(selected, m, c["name"]) for m in spec["fill_models"] for c in spec["cases"]],
              "unknown_admission_dates": spec["unknown_admission_dates"],
              "session_hashes": {d: digest(FOLDER / "sessions" / (d + ".json")) for d in by_date},
              "specification_sha256": digest(FOLDER / "specification.json"),
              "economic_configurations_executed": 1, "economic_implementation_versions": 1,
              "actual_execution_verified": False, "reliable_edge_established": False,
              "interpretation": "Selection variant only, conditional price/print assumptions. Reused results are not fresh validation; missing source admission remains unknown."}
    write(FOLDER / "results.json", result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("session_hashes", "calendar_case_rows")}), flush=True)


if __name__ == "__main__":
    main()
