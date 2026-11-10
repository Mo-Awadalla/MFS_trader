"""Verify fresh activity-selected replay and exact reuse of previous audited outcomes."""

import json
from datetime import UTC, datetime
from pathlib import Path

from research_scout.audit_iex_deep_20261002 import native, sha
from research_scout.audit_iex_deep_probe_20261002 import aggregate_check, read_records, venue_quotes
from research_scout.audit_iex_spread_probe_20261002 import verify_case

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "research_scout/iex_deep_hft_20261002/price_probe_v1"
OUT = ROOT / "research_scout/iex_flow_hft_20261002/price_probe_v1"


def main():
    path = OUT / "results.json"
    results = json.loads(path.read_text())
    spec = json.loads((OUT / "specification.json").read_text())
    prior_spec = json.loads((PARENT / "specification.json").read_text())
    prior_audit = json.loads((PARENT / "independent_verification.json").read_text())
    prior_results = json.loads((PARENT / "results.json").read_text())
    assert prior_audit["verified"] and sha(PARENT / "results.json") == prior_audit["results_sha256"] == spec["prior_results_sha256"]
    assert sha(PARENT / "independent_verification.json") == spec["prior_audit_sha256"]
    for key in ("policy", "timing", "order_type", "entry_proxy", "exit_proxy", "cases", "costs", "fill_models", "quote_reference", "depth_limit"):
        assert spec[key] == prior_spec[key]
    cases = {c["name"]: c for c in spec["cases"]}
    calendar, events, sessions = [], [], {}
    fresh_messages = fresh_rows = fresh_quotes = fresh_cases = reused_cases = 0
    for event in spec["selected_events"]:
        day = event["date"]
        session_path = OUT / "sessions" / (day + ".json")
        assert sha(session_path) == results["session_hashes"][day]
        session = json.loads(session_path.read_text())
        old_path = Path(session["prior_event_session_path"])
        assert sha(old_path) == session["prior_event_session_sha256"] == prior_results["session_hashes"][day]
        old = json.loads(old_path.read_text())
        flow = json.loads((OUT.parent / "sessions" / (day + ".json")).read_text())
        assert session["event"] == {"date": day, **flow["selected"][0], "decision_ns": flow["decision_ns"]}
        assert event == {k: v for k, v in session["event"].items() if k != "decision_ns"}
        if session["reused_exact_audited_outcomes"]:
            assert session["event"] == old["event"] and session["outcomes"] == old["outcomes"]
            reused_cases += len(session["outcomes"])
        else:
            source = Path(session["prefix_path"])
            assert sha(source) == session["prefix_sha256"] == old["prefix_sha256"]
            native_path, venue_path = Path(session["native_path"]), Path(session["venue_path"])
            assert sha(native_path) == session["native_sha256"] and sha(venue_path) == session["venue_sha256"]
            rows, messages = [], 0
            for row in native(source, session["coverage"]["endpoint_ns"]):
                messages += 1
                if row.get("symbol") == event["symbol"]:
                    rows.append(row)
            assert messages == session["fresh_source_messages_checked"]
            assert rows == read_records(native_path) and len(rows) == session["native_symbol_messages"]
            quotes = venue_quotes(rows)
            assert quotes == read_records(venue_path)
            for row in session["outcomes"]:
                verify_case(session["event"], quotes, row, cases[row["case"]])
            fresh_messages += messages
            fresh_rows += len(rows)
            fresh_quotes += sum(r["type"] == "Q" for r in quotes)
            fresh_cases += len(session["outcomes"])
        sessions[day] = session
        events.extend(session["outcomes"])
    for day in spec["dates"]:
        if day in sessions:
            calendar.extend(sessions[day]["outcomes"])
        else:
            unknown = day in spec["unknown_admission_dates"]
            for model in spec["fill_models"]:
                for case in spec["cases"]:
                    calendar.append({"date": day, "symbol": None, "case": case["name"], "fill_model": model,
                                     "outcome": "unknown_source_before_signal" if unknown else "conditional_no_selected_signal",
                                     "net_usd": None if unknown else "0", "actual_execution_verified": False})
    assert calendar == results["calendar_case_rows"]
    assert fresh_messages == results["fresh_source_messages_checked"]
    for row in results["scenario_results"]:
        aggregate_check(row, calendar)
    for row in results["observed_selected_cohort_results"]:
        aggregate_check(row, events)
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
             "fresh_source_messages_verified": fresh_messages, "fresh_native_symbol_rows_verified": fresh_rows,
             "fresh_derived_quotes_verified": fresh_quotes, "fresh_event_cases_verified": fresh_cases,
             "prior_audited_event_cases_reused_exactly": reused_cases,
             "calendar_rows_verified": len(calendar), "aggregate_checks": 20,
             "results_sha256": sha(path), "auditor_sha256": sha(Path(__file__)),
             "independent_source_decoder_sha256": sha(ROOT / "research_scout/audit_iex_deep_20261002.py"),
             "independent_book_cash_auditor_sha256": sha(ROOT / "research_scout/audit_iex_deep_probe_20261002.py"),
             "independent_policy_auditor_sha256": sha(ROOT / "research_scout/audit_iex_spread_probe_20261002.py"),
             "scope": "Fresh native source, atomic venue-clock quotes and conditional allocations/cash for newly selected events; exact event/policy/outcome reuse for already audited events; full calendar unknown propagation. No actual execution claim.",
             "actual_execution_verified": False, "reliable_edge_established": False}
    (OUT / "independent_verification.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
