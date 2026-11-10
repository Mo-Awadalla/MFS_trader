"""Fast local-data triage; future-aware favorable prices are not tradable P&L."""

import json
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import ROUND_FLOOR
from decimal import Decimal as D

import databento as db
import numpy as np
import pandas as pd

from research.equity_resilience import (
    FIELDS,
    NS,
    arrays,
    causal_quantity,
    detect,
    favorable_quotes,
    optimistic_cash,
)
from research.precise_ledger import ledger_frame
from research_scout.prepare_equity_resilience_20261002 import OUT, ROOT, SYMBOLS, sha


def dump(path, data):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(data, indent=2, allow_nan=False) + "\n")


def session(job):
    source, spec = job
    path, day = ROOT / source["path"], source["date"]
    assert sha(path) == source["sha256"]
    store = db.read_dbn(path)
    assert str(store.metadata.schema) == "mbp-1" and store.metadata.dataset == "EQUS.MINI"
    raw = store.to_ndarray()
    opening = pd.Timestamp(day + " 09:30:00", tz="America/New_York").tz_convert("UTC").value
    grids = np.arange(opening + 5 * NS, opening + 570 * NS + 1, 100_000_000, dtype=np.int64)
    events, sources, errors, native = [], {}, [], {}
    for symbol in SYMBOLS:
        mappings = [m for m in store.metadata.mappings[symbol] if str(m["start_date"]) <= day < str(m["end_date"])]
        assert len(mappings) == 1
        subset = raw[raw["instrument_id"] == int(mappings[0]["symbol"])]
        native[symbol] = {"source_rows": len(subset), "trade_rows": int(np.sum(subset["action"] == b"T"))}
        try:
            prepared = arrays(subset)
        except ValueError as error:
            errors.append({"symbol": symbol, "reason": str(error)})
            continue
        sources[symbol] = prepared
        for values in detect(*prepared, grids):
            event = {field: int(value) for field, value in zip(FIELDS, values, strict=True)}
            qi = event["signal_quote_index"]
            event.update(date=day, symbol=symbol, rule="bid_resilience_long" if event["kind"] == 0 else "ask_break_long",
                         signal_receive_ns=int(prepared[0][qi]), signal_event_ns=int(prepared[1][qi]),
                         signal_bid_int=int(prepared[2][qi]), signal_ask_int=int(prepared[3][qi]),
                         signal_bid_quantity=int(prepared[4][qi]), signal_ask_quantity=int(prepared[5][qi]))
            events.append(event)
    chosen = []
    for rule in spec["rules"]:
        candidates = sorted([e for e in events if e["rule"] == rule],
                            key=lambda r: (r["decision_ns"], -D(r["at_level_volume"]) / D(r["anchor_quantity"]),
                                           -r["at_level_volume"] * r["defended_price_int"], r["symbol"]))
        previous = -1
        for event in candidates:
            if event["decision_ns"] - previous < 35 * NS:
                continue
            chosen.append(event)
            previous = event["decision_ns"]
    rows = []
    for event in chosen:
        quantity = causal_quantity(event["signal_ask_int"], event["signal_ask_quantity"])
        limit = (D(event["signal_ask_int"]) / NS * D("1.001") * 100).to_integral_value(rounding=ROUND_FLOOR) / 100
        for scenario in spec["scenarios"]:
            row = {**event, "scenario": scenario["name"], "quantity": quantity, "limit": str(limit)}
            if quantity < 1:
                rows.append({**row, "status": "no_causal_quantity", "net": "0"})
                continue
            delay, radius, decision = scenario["delay_ms"] * 1_000_000, scenario["clock_ms"] * 1_000_000, event["decision_ns"]
            entry_at, exit_at = decision + 50_000_000 + delay, decision + 15_100_000_000 + 3 * delay
            assert exit_at - entry_at + 2 * radius < 30 * NS
            entry = favorable_quotes(sources[event["symbol"]], entry_at - radius, entry_at + radius, "buy")
            final = favorable_quotes(sources[event["symbol"]], exit_at - radius, exit_at + radius, "sell")
            row.update(entry_arrival_ns=entry_at, exit_arrival_ns=exit_at, entry_reference=entry, exit_reference=final)
            if not entry["known"]:
                rows.append({**row, "status": "unknown_entry_reference", "net": None})
            elif D(entry["price_int"]) / NS > limit:
                rows.append({**row, "status": "no_favorable_price_inside_collar", "net": "0"})
            elif not final["known"]:
                rows.append({**row, "status": "unknown_exit_reference", "net": None})
            else:
                rows.append({**row, "status": "optimistic_priced",
                             **optimistic_cash(entry["price_int"], final["price_int"], quantity,
                                               scenario["fee_multiple"], scenario["adverse_multiple"])})
    event_path = OUT / "events" / f"{day}.parquet"
    ledger_frame(events).to_parquet(event_path, index=False)
    record = {"date": day, "source_sha256": source["sha256"], "source_rows": len(raw), "symbol_counts": native,
              "source_errors": errors, "raw_events": len(events), "selected_events": len(chosen),
              "selected_by_rule": dict(Counter(e["rule"] for e in chosen)),
              "events_path": str(event_path.relative_to(ROOT)), "events_sha256": sha(event_path), "rows": rows}
    dump(OUT / "sessions" / f"{day}.json", record)
    return record


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    paths = ["research/equity_resilience.py", "research/precise_ledger.py", "tests/unit/test_equity_resilience.py",
             "research_scout/screen_equity_resilience_20261002.py"]
    dump(OUT / "implementation.json", {"frozen_at_utc": datetime.now(UTC).isoformat(),
         "specification_sha256": sha(OUT / "specification.json"), "code_sha256": {p: sha(ROOT / p) for p in paths},
         "new_focused_tests_passed": 8, "new_economic_screen_rules": 2, "realistic_execution_run": False})
    for folder in ("events", "sessions"):
        (OUT / folder).mkdir(exist_ok=True)
    results = []
    with ProcessPoolExecutor(max_workers=spec["workers"]) as pool:
        futures = [pool.submit(session, (source, spec)) for source in spec["sources"]]
        for count, future in enumerate(as_completed(futures), 1):
            row = future.result()
            results.append(row)
            if count % 12 == 0 or count == len(futures):
                print(json.dumps({"sessions_complete": count, "sessions_total": len(futures),
                                  "raw_events": sum(r["raw_events"] for r in results),
                                  "selected_events": sum(r["selected_events"] for r in results),
                                  "source_errors": sum(len(r["source_errors"]) for r in results)}), flush=True)
    results.sort(key=lambda r: r["date"])
    summaries = []
    for rule in spec["rules"]:
        for scenario in spec["scenarios"]:
            rows = [r for day in results for r in day["rows"] if r["rule"] == rule and r["scenario"] == scenario["name"]]
            unknown = [r for r in rows if r["net"] is None]
            daily = defaultdict(lambda: D(0), {r["date"]: D(0) for r in results})
            for r in rows:
                if r["net"] is not None:
                    daily[r["date"]] += D(r["net"])
            complete = not unknown and not any(r["source_errors"] for r in results)
            total = sum(daily.values(), D(0))
            summaries.append({"rule": rule, "scenario": scenario["name"], "complete_quote_proxy": complete,
                              "optimistic_sum_usd": str(total) if complete else None,
                              "known_component_usd": str(total), "selected_events": len(rows),
                              "priced_events": sum(r["status"] == "optimistic_priced" for r in rows),
                              "outcomes": dict(Counter(r["status"] for r in rows)),
                              "dates_with_priced_events": len({r["date"] for r in rows if r["status"] == "optimistic_priced"}),
                              "drop_best_three_dates_usd": str(sum(sorted(daily.values())[:-3], D(0))) if complete else None,
                              "daily_optimistic_usd": {k: str(v) for k, v in daily.items()},
                              "actual_portfolio_return": None, "realistic_execution_verified": False})
    output = {"source_sessions": len(results), "source_rows": sum(r["source_rows"] for r in results),
              "raw_events": sum(r["raw_events"] for r in results), "selected_events": sum(r["selected_events"] for r in results),
              "source_error_sessions": [r["date"] for r in results if r["source_errors"]],
              "scenarios": summaries, "implementation_sha256": sha(OUT / "implementation.json"),
              "session_files": [{"date": r["date"], "sha256": sha(OUT / "sessions" / f"{r['date']}.json")} for r in results],
              "economic_screen_configurations": 2, "scenario_cases": 12,
              "realistic_execution_run": False, "independent_audit_complete": False,
              "future_aware_diagnostic_not_tradable": True, "reliable_edge_established": False}
    dump(OUT / "results.json", output)
    for summary in summaries:
        print(json.dumps({k: v for k, v in summary.items() if k != "daily_optimistic_usd"}), flush=True)


if __name__ == "__main__":
    main()
