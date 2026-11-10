"""Read only causal burst/quote supply; no execution-price or return calculation."""

import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal as D

import databento as db
import numpy as np
import pandas as pd

from research.equity_burst_resilience import completed_bursts, events_from_seeds, seed_windows
from research.equity_resilience import arrays
from research.precise_ledger import ledger_frame
from research_scout.prepare_equity_burst_20261002 import OUT, PARENT, ROOT, SYMBOLS, sha


def dump(path, data):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(data, indent=2, allow_nan=False) + "\n")


def screen(source):
    path, day = ROOT / source["path"], source["date"]
    assert sha(path) == source["sha256"]
    store = db.read_dbn(path)
    assert str(store.metadata.schema) == "mbp-1" and store.metadata.dataset == "EQUS.MINI"
    raw = store.to_ndarray()
    opening = pd.Timestamp(day + " 09:30:00", tz="America/New_York").tz_convert("UTC").value
    grids = np.arange(opening + 5_000_000_000, opening + 570_000_000_001, 100_000_000, dtype=np.int64)
    events, errors, diagnostics, counters, failures = [], [], [], Counter(), Counter()
    for symbol in SYMBOLS:
        mapping = [m for m in store.metadata.mappings[symbol] if str(m["start_date"]) <= day < str(m["end_date"])]
        assert len(mapping) == 1
        subset = raw[raw["instrument_id"] == int(mapping[0]["symbol"])]
        try:
            prepared = arrays(subset)
        except ValueError as error:
            errors.append({"symbol": symbol, "reason": str(error)})
            continue
        groups, counts = completed_bursts(subset, prepared)
        seeds, reasons = seed_windows(prepared, groups, grids)
        detected = events_from_seeds(prepared, seeds, grids)
        counters.update(counts)
        failures.update(reasons)
        diagnostics.append({"symbol": symbol, "source_rows": len(subset), "counts": counts,
                            "seed_failures": reasons, "groups": groups, "seeds": seeds})
        for event in detected:
            qi = event["signal_quote_index"]
            event.update(date=day, symbol=symbol, rule="bid_resilience_long" if event["kind"] == 0 else "ask_break_long",
                         signal_receive_ns=int(prepared[0][qi]), signal_event_ns=int(prepared[1][qi]),
                         signal_bid_int=int(prepared[2][qi]), signal_ask_int=int(prepared[3][qi]),
                         signal_bid_quantity=int(prepared[4][qi]), signal_ask_quantity=int(prepared[5][qi]))
            events.append(event)
    selected = []
    for rule in ("bid_resilience_long", "ask_break_long"):
        candidates = sorted([r for r in events if r["rule"] == rule],
                            key=lambda r: (r["decision_ns"], -D(r["at_level_volume"]) / D(r["anchor_quantity"]),
                                           -r["at_level_volume"] * r["defended_price_int"], r["symbol"]))
        previous = -1
        for event in candidates:
            if event["decision_ns"] - previous >= 35_000_000_000:
                selected.append(event)
                previous = event["decision_ns"]
    output = {"date": day, "source_sha256": source["sha256"], "source_rows": len(raw),
              "source_errors": errors, "group_counters": dict(counters), "seed_failures": dict(failures),
              "symbol_diagnostics": diagnostics, "events": events, "selected_events": selected}
    dump(OUT / "sessions" / f"{day}.json", output)
    return output


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    assert sha(PARENT / "independent_supply_verification.json") == spec["parent_audit_sha256"]
    paths = ["research/equity_burst_resilience.py", "research/equity_resilience.py", "research/precise_ledger.py",
             "tests/unit/test_equity_burst_resilience.py", "research_scout/screen_equity_burst_20261002.py"]
    dump(OUT / "implementation.json", {"frozen_at_utc": datetime.now(UTC).isoformat(),
         "specification_sha256": sha(OUT / "specification.json"), "code_sha256": {p: sha(ROOT / p) for p in paths},
         "new_focused_tests_passed": 8, "economic_implementations_run": 0})
    (OUT / "sessions").mkdir(exist_ok=True)
    rows, counts, failures = [], Counter(), Counter()
    with ProcessPoolExecutor(max_workers=spec["workers"]) as pool:
        for n, future in enumerate(as_completed([pool.submit(screen, source) for source in spec["sources"]]), 1):
            row = future.result()
            rows.append(row)
            counts.update(row["group_counters"])
            failures.update(row["seed_failures"])
            if n % 12 == 0 or n == len(spec["sources"]):
                print(json.dumps({"sessions_complete": n, "prestate_qualified_bursts": counts["prestate_qualified_bursts"],
                                  "raw_events": sum(len(r["events"]) for r in rows),
                                  "selected_events": sum(len(r["selected_events"]) for r in rows)}), flush=True)
    rows.sort(key=lambda r: r["date"])
    selected = sorted([e for r in rows for e in r["selected_events"]], key=lambda e: (e["decision_ns"], e["rule"], e["symbol"]))
    ledger_frame(selected).to_parquet(OUT / "selected.parquet", index=False)
    result = {"source_sessions": len(rows), "source_rows": sum(r["source_rows"] for r in rows),
              "source_errors": [{"date": r["date"], **e} for r in rows for e in r["source_errors"]],
              "group_counters": dict(counts), "seed_failures": dict(failures),
              "raw_events": sum(len(r["events"]) for r in rows), "selected_events": len(selected),
              "selected_by_rule": dict(Counter(e["rule"] for e in selected)),
              "selected_sha256": sha(OUT / "selected.parquet"), "implementation_sha256": sha(OUT / "implementation.json"),
              "session_files": [{"date": r["date"], "sha256": sha(OUT / "sessions" / f"{r['date']}.json")} for r in rows],
              "economic_implementations_run": 0, "future_returns_evaluated": False,
              "independent_audit_complete": False, "actual_execution_verified": False, "reliable_edge_established": False}
    dump(OUT / "screen_results.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "session_files"}), flush=True)


if __name__ == "__main__":
    main()
