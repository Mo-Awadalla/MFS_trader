"""Independent exact cash/intent/aggregation checks, without claiming quote provenance."""

import json
from collections import Counter
from datetime import UTC, datetime
from decimal import ROUND_FLOOR
from decimal import Decimal as D
from pathlib import Path

import pandas as pd

from research_scout.prepare_equity_sweep_20261002 import OUT, ROOT, sha

PROBE = OUT / "optimistic_v2"


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    signal = json.loads((OUT / "screen_results.json").read_text())
    result = json.loads((PROBE / "results.json").read_text())
    impl = json.loads((PROBE / "implementation.json").read_text())
    assert sha(PROBE / "implementation.json") == result["implementation_sha256"]
    assert sha(OUT / "specification.json") == impl["specification_sha256"]
    assert sha(OUT / "candidate_verification.json") == impl["candidate_audit_sha256"]
    assert sha(OUT / "selected.parquet") == impl["selected_sha256"]
    for path, digest in impl["code_sha256"].items():
        assert sha(ROOT / path) == digest
    events = {(r["date"], r["symbol"], r["rule"], r["decision_ns"]): r
              for r in pd.read_parquet(OUT / "selected.parquet").to_dict("records")}
    settings = {r["name"]: r for r in spec["scenarios"]}
    rows, seen, cash_count = [], set(), 0
    for file in result["session_files"]:
        path = PROBE / "sessions" / f"{file['date']}.json"
        assert sha(path) == file["sha256"]
        for row in json.loads(path.read_text())["rows"]:
            key = row["date"], row["symbol"], row["rule"], row["decision_ns"]
            unique = *key, row["scenario"]
            assert unique not in seen
            seen.add(unique)
            event, scenario = events[key], settings[row["scenario"]]
            price = D(event["signal_ask_int"]) / 10**9
            q = min(int((D(10000) / (price * D("1.02"))).to_integral_value(rounding=ROUND_FLOOR)), event["signal_ask_quantity"] // 10)
            limit = (price * D("1.001") * 100).to_integral_value(rounding=ROUND_FLOOR) / 100
            assert row["quantity"] == q and D(row["limit"]) == limit
            if not q:
                assert row["status"] == "no_causal_quantity" and row["net"] == "0"
                rows.append(row)
                continue
            entry_time = event["decision_ns"] + 50_000_000 + scenario["delay_ms"] * 10**6
            exit_time = event["decision_ns"] + 15_100_000_000 + scenario["delay_ms"] * 3 * 10**6
            assert row["entry_arrival_ns"] == entry_time and row["exit_arrival_ns"] == exit_time
            assert exit_time - entry_time + scenario["clock_ms"] * 2 * 10**6 < 30 * 10**9
            entry, final = row["entry_reference"], row["exit_reference"]
            for point, clock in ((entry, entry_time), (final, exit_time)):
                if point["known"]:
                    assert point["window_lower_ns"] == clock - scenario["clock_ms"] * 10**6
                    assert point["window_upper_ns"] == clock + scenario["clock_ms"] * 10**6
            if not entry["known"]:
                status, net = "unknown_entry_reference", None
            elif D(entry["price_int"]) / 10**9 > limit:
                status, net = "no_favorable_price_inside_collar", D(0)
            elif not final["known"]:
                status, net = "unknown_exit_reference", None
            else:
                initial, terminal = D(entry["price_int"]) / 10**9, D(final["price_int"]) / 10**9
                entry_notional, exit_notional = q * initial, q * terminal
                gross = exit_notional - entry_notional
                commission = 2 * max(D(1), D(q) / 200) * scenario["fee_multiple"]
                levies = (exit_notional * D(3) / 100000 + D(q) * D(166) / 1000000) * scenario["fee_multiple"]
                adverse = (entry_notional + exit_notional) / 10000 * scenario["adverse_multiple"]
                net = gross - commission - levies - adverse
                for field, value in (("gross", gross), ("commissions", commission), ("sell_levies", levies), ("adverse", adverse)):
                    assert D(row[field]) == value
                status, cash_count = "optimistic_priced", cash_count + 1
            assert row["status"] == status and ((row["net"] is None and net is None) or (row["net"] is not None and D(row["net"]) == net))
            rows.append(row)
    assert len(rows) == len(events) * len(settings)
    complete_count = 0
    for summary in result["scenarios"]:
        subset = [r for r in rows if (r["rule"], r["scenario"]) == (summary["rule"], summary["scenario"])]
        daily = {s["date"]: D(0) for s in spec["sources"]}
        for row in subset:
            if row["net"] is not None:
                daily[row["date"]] += D(row["net"])
        total, complete = sum(daily.values(), D(0)), all(r["net"] is not None for r in subset)
        assert summary["observed_cohort_proxy_complete"] == complete
        assert summary["observed_cohort_optimistic_sum_usd"] == (str(total) if complete else None)
        assert D(summary["known_component_usd"]) == total
        assert summary["outcomes"] == dict(Counter(r["status"] for r in subset))
        assert summary["selected_events"] == len(subset)
        assert summary["priced_events"] == sum(r["status"] == "optimistic_priced" for r in subset)
        assert summary["priced_dates"] == len({r["date"] for r in subset if r["status"] == "optimistic_priced"})
        assert {k: D(v) for k, v in summary["daily_known_component_usd"].items()} == daily
        assert summary["drop_best_three_dates_usd"] == (str(sum(sorted(daily.values())[:-3], D(0))) if complete else None)
        assert summary["full_calendar_complete"] == (complete and not signal["source_errors"])
        assert summary["actual_portfolio_return"] is None and not summary["actual_execution_verified"]
        complete_count += int(complete)
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(), "event_case_rows_verified": len(rows),
             "priced_cash_rows_verified": cash_count, "aggregates_verified": len(result["scenarios"]),
             "complete_observed_cohort_cases": complete_count, "maximum_cash_difference": "0",
             "results_sha256": sha(PROBE / "results.json"), "auditor_sha256": sha(Path(__file__)),
             "scope": "Exact intended quantity, fixed timing/collar, saved-reference outcome logic, all stated costs and all daily/case aggregates independently recomputed. No production sizing, fee or aggregation helper called.",
             "forward_quote_provenance_independently_verified": False,
             "scope_limit": "Future favorable-quote extrema and their validity were not reconstructed independently from raw sources in this accounting check. Candidate admission audit is separate. No profitable survivor, realistic execution or full-calendar return is claimed.",
             "actual_execution_verified": False, "reliable_edge_established": False}
    with (PROBE / "independent_accounting.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
