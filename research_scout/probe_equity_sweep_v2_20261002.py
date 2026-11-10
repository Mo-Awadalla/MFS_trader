"""Frozen favorable-quote triage of audited sweep signals; not executable returns."""

import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import ROUND_FLOOR
from decimal import Decimal as D

import databento as db
import pandas as pd

from research.equity_resilience import arrays, causal_quantity, favorable_quotes, optimistic_cash
from research.exact_json import integer_default
from research_scout.prepare_equity_sweep_20261002 import OUT, ROOT, sha

PROBE = OUT / "optimistic_v2"


def dump(path, data):
    encoded = json.dumps(data, indent=2, allow_nan=False, default=integer_default) + "\n"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(encoded)


def session(job):
    source, events, scenarios = job
    assert sha(ROOT / source["path"]) == source["sha256"]
    store = db.read_dbn(ROOT / source["path"])
    raw = store.to_ndarray()
    tapes, rows = {}, []
    for symbol in sorted({e["symbol"] for e in events}):
        ids = [int(m["symbol"]) for m in store.metadata.mappings[symbol]
               if str(m["start_date"]) <= source["date"] < str(m["end_date"])]
        assert len(ids) == 1
        tapes[symbol] = arrays(raw[raw["instrument_id"] == ids[0]])
    for event in events:
        tape = tapes[event["symbol"]]
        index = event["signal_quote_index"]
        for field, position in (("signal_receive_ns", 0), ("signal_event_ns", 1), ("signal_bid_int", 2),
                                ("signal_ask_int", 3), ("signal_bid_quantity", 4), ("signal_ask_quantity", 5)):
            assert int(tape[position][index]) == event[field]
        quantity = causal_quantity(event["signal_ask_int"], event["signal_ask_quantity"])
        limit = (D(event["signal_ask_int"]) / 10**9 * D("1.001") * 100).to_integral_value(rounding=ROUND_FLOOR) / 100
        for scenario in scenarios:
            row = {"date": source["date"], "symbol": event["symbol"], "rule": event["rule"],
                   "decision_ns": event["decision_ns"], "scenario": scenario["name"], "quantity": quantity,
                   "signal_ask_int": event["signal_ask_int"], "signal_ask_quantity": event["signal_ask_quantity"],
                   "limit": str(limit)}
            if quantity < 1:
                rows.append({**row, "status": "no_causal_quantity", "net": "0"})
                continue
            delay, radius = scenario["delay_ms"] * 1_000_000, scenario["clock_ms"] * 1_000_000
            entry_at, exit_at = event["decision_ns"] + 50_000_000 + delay, event["decision_ns"] + 15_100_000_000 + 3 * delay
            assert exit_at - entry_at + radius * 2 < 30 * 10**9
            initial = favorable_quotes(tape, entry_at - radius, entry_at + radius, "buy")
            final = favorable_quotes(tape, exit_at - radius, exit_at + radius, "sell")
            row.update(entry_arrival_ns=entry_at, exit_arrival_ns=exit_at,
                       entry_reference=initial, exit_reference=final)
            if not initial["known"]:
                rows.append({**row, "status": "unknown_entry_reference", "net": None})
            elif D(initial["price_int"]) / 10**9 > limit:
                rows.append({**row, "status": "no_favorable_price_inside_collar", "net": "0"})
            elif not final["known"]:
                rows.append({**row, "status": "unknown_exit_reference", "net": None})
            else:
                rows.append({**row, "status": "optimistic_priced",
                             **optimistic_cash(initial["price_int"], final["price_int"], quantity,
                                               scenario["fee_multiple"], scenario["adverse_multiple"])})
    output = {"date": source["date"], "source_sha256": source["sha256"], "selected_events": len(events), "rows": rows}
    dump(PROBE / "sessions" / f"{source['date']}.json", output)
    return output


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    signal = json.loads((OUT / "screen_results.json").read_text())
    audit = json.loads((OUT / "candidate_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == sha(OUT / "screen_results.json")
    assert sha(OUT / "selected.parquet") == signal["selected_sha256"]
    events = pd.read_parquet(OUT / "selected.parquet").to_dict("records")
    assert len(events) == audit["selected_events_verified"] == 172
    PROBE.mkdir(exist_ok=True)
    (PROBE / "sessions").mkdir(exist_ok=True)
    paths = ["research/equity_resilience.py", "tests/unit/test_equity_resilience.py",
             "research_scout/probe_equity_sweep_v2_20261002.py", "research/exact_json.py", "tests/unit/test_exact_json.py"]
    dump(PROBE / "implementation.json", {"frozen_at_utc": datetime.now(UTC).isoformat(),
         "specification_sha256": sha(OUT / "specification.json"), "candidate_audit_sha256": sha(OUT / "candidate_verification.json"),
         "selected_sha256": signal["selected_sha256"], "code_sha256": {p: sha(ROOT / p) for p in paths},
         "reused_focused_tests_passed": 8, "new_focused_tests": 2, "superseded_implementation_sha256": sha(OUT / "optimistic_v1/implementation.json"),
         "repair": "V1 failed serializing a NumPy quote-index integer. Only add exact integer JSON encoding, and encode before opening output files. Source, signal, price, sizing, timing and cost mechanics are unchanged. Preserve v1 partial/empty files; no aggregate existed.", "economic_screen_rules": 2,
         "future_aware_price_proxy": True, "actual_execution_verified": False})
    jobs = [(source, [e for e in events if e["date"] == source["date"]], spec["scenarios"])
            for source in spec["sources"] if any(e["date"] == source["date"] for e in events)]
    results = []
    with ProcessPoolExecutor(max_workers=2) as pool:
        for n, future in enumerate(as_completed([pool.submit(session, job) for job in jobs]), 1):
            results.append(future.result())
            if n % 12 == 0 or n == len(jobs):
                print(json.dumps({"priced_source_sessions": n, "selected_source_sessions": len(jobs)}), flush=True)
    summaries = []
    for rule in spec["rules"]:
        for scenario in spec["scenarios"]:
            records = [r for result in results for r in result["rows"] if r["rule"] == rule and r["scenario"] == scenario["name"]]
            daily = {s["date"]: D(0) for s in spec["sources"]}
            for row in records:
                if row["net"] is not None:
                    daily[row["date"]] += D(row["net"])
            complete = not any(r["net"] is None for r in records)
            total = sum(daily.values(), D(0))
            summaries.append({"rule": rule, "scenario": scenario["name"], "observed_cohort_proxy_complete": complete,
                              "observed_cohort_optimistic_sum_usd": str(total) if complete else None,
                              "known_component_usd": str(total), "selected_events": len(records),
                              "priced_events": sum(r["status"] == "optimistic_priced" for r in records),
                              "outcomes": dict(Counter(r["status"] for r in records)),
                              "priced_dates": len({r["date"] for r in records if r["status"] == "optimistic_priced"}),
                              "drop_best_three_dates_usd": str(sum(sorted(daily.values())[:-3], D(0))) if complete else None,
                              "daily_known_component_usd": {k: str(v) for k, v in daily.items()},
                              "full_calendar_complete": complete and not signal["source_errors"],
                              "actual_portfolio_return": None, "actual_execution_verified": False})
    output = {"selected_events": len(events), "selected_source_dates": len(jobs), "scenario_cases": len(summaries),
              "economic_screen_configurations_executed": 2, "implementation_sha256": sha(PROBE / "implementation.json"),
              "source_error_symbol_sessions": signal["source_errors"], "scenarios": summaries,
              "session_files": [{"date": r["date"], "sha256": sha(PROBE / "sessions" / f"{r['date']}.json")}
                                for r in sorted(results, key=lambda r: r["date"])],
              "warning": "Future-aware favorable displayed quotes and unlimited execution depth; independent event budgets, not a capital-constrained portfolio. Known components exclude unknown references and unassessable symbol-sessions. No favorable result is an execution claim.",
              "independent_quote_and_cash_audit_complete": False, "realistic_execution_run": False,
              "actual_execution_verified": False, "reliable_edge_established": False}
    dump(PROBE / "results.json", output)
    for row in summaries:
        print(json.dumps({k: v for k, v in row.items() if k != "daily_known_component_usd"}), flush=True)


if __name__ == "__main__":
    main()
