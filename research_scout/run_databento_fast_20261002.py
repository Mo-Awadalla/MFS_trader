"""Local DBN screen and deterministic conditional replay; never calls an API."""

import argparse
import json
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal

import databento as db
import pandas as pd

from research.equity_resilience import arrays
from research.equity_sweep_fast import admit, replay, select
from research_scout.prepare_databento_fast_20261002 import OUT, PARENT, ROOT, sha, write


def verify(spec):
    for relative, expected in spec["code_sha256"].items():
        assert sha(ROOT / relative) == expected


def source_arrays(source, symbols):
    path, day = ROOT / source["path"], source["date"]
    assert sha(path) == source["sha256"]
    store = db.read_dbn(path)
    assert store.metadata.dataset == "EQUS.MINI" and str(store.metadata.schema) == "mbp-1"
    raw = store.to_ndarray()
    ready, errors = {}, []
    for symbol in symbols:
        ids = [int(m["symbol"]) for m in store.metadata.mappings[symbol]
               if str(m["start_date"]) <= day < str(m["end_date"])]
        assert len(ids) == 1
        try:
            ready[symbol] = arrays(raw[raw["instrument_id"] == ids[0]])
        except ValueError as exc:
            errors.append({"symbol": symbol, "reason": str(exc)})
    return ready, errors, len(raw)


def one_screen(source):
    spec = json.loads((OUT / "specification.json").read_text())
    verify(spec)
    day = source["date"]
    parent_file = PARENT / "sessions" / (day + ".json")
    expected = next(r["sha256"] for r in spec["parent_sessions"] if r["date"] == day)
    assert sha(parent_file) == expected
    parent = json.loads(parent_file.read_text())
    ready, errors, count = source_arrays(source, spec["symbols"])
    assert errors == parent["source_errors"] and count == parent["source_rows"]
    opening = int(pd.Timestamp(day + " 09:30:00", tz="America/New_York").tz_convert("UTC").value)
    checks, admitted, failures = [], [], Counter()
    for diagnostics in parent["symbol_diagnostics"]:
        symbol = diagnostics["symbol"]
        for item in diagnostics["observations"]:
            e, reason = admit(ready[symbol], item["group"], opening)
            if e is not None:
                e.update(date=day, symbol=symbol)
                admitted.append(e)
            else:
                failures[reason] += 1
            checks.append({"symbol": symbol, "group": item["group"], "event": e, "reason": reason})
    result = {"date": day, "source": source, "source_rows": count, "source_errors": errors,
              "checks": checks, "admitted": admitted, "selected": select(admitted),
              "rejections": dict(failures), "specification_sha256": sha(OUT / "specification.json"),
              "returns_calculated": False}
    path = OUT / "screen_sessions" / (day + ".json")
    assert not path.exists()
    write(path, result)
    return {"date": day, "groups": len(checks), "admitted": len(admitted), "selected": len(result["selected"])}


def one_replay(source):
    spec = json.loads((OUT / "specification.json").read_text())
    verify(spec)
    day = source["date"]
    screen = json.loads((OUT / "screen_sessions" / (day + ".json")).read_text())
    result = json.loads((OUT / "screen_results.json").read_text())
    assert sha(OUT / "screen_sessions" / (day + ".json")) == result["session_hashes"][day]
    symbols = sorted({e["symbol"] for e in screen["selected"]})
    ready, errors, count = source_arrays(source, symbols) if symbols else ({}, [], 0)
    assert not errors
    rows = [replay(e, ready[e["symbol"]], hold, case) for e in screen["selected"]
            for hold in spec["hold_ms"] for case in spec["cases"]]
    output = {"date": day, "source_rows_reloaded": count, "outcomes": rows,
              "screen_session_sha256": sha(OUT / "screen_sessions" / (day + ".json")),
              "specification_sha256": sha(OUT / "specification.json")}
    write(OUT / "replay_sessions" / (day + ".json"), output)
    return {"date": day, "cases": len(rows), "priced": sum(r["outcome"] == "conditional_priced" for r in rows)}


def aggregates(rows, spec):
    summaries = []
    unknown_dates = {r["date"] for r in spec["inherited_unknown_symbol_dates"]}
    for rule in ("follow_buy_sweep", "fade_sell_sweep"):
        for hold in spec["hold_ms"]:
            for case in spec["cases"]:
                chosen = [r for r in rows if (r["rule"], r["hold_ms"], r["case"]) == (rule, hold, case["name"])]
                daily, unknown = defaultdict(Decimal), set(unknown_dates)
                for r in chosen:
                    if r["net_usd"] is None:
                        unknown.add(r["date"])
                    else:
                        daily[r["date"]] += Decimal(r["net_usd"])
                known = sum(daily.values(), Decimal(0))
                observed_complete = all(r["net_usd"] is not None for r in chosen)
                summaries.append({"rule": rule, "hold_ms": hold, "case": case["name"],
                                  "event_cases": len(chosen), "priced_events": sum(r["outcome"] == "conditional_priced" for r in chosen),
                                  "unknown_events": sum(r["net_usd"] is None for r in chosen),
                                  "known_component_usd": str(known),
                                  "observed_event_cohort_usd": str(known) if observed_complete else None,
                                  "unknown_calendar_dates": sorted(unknown),
                                  "full_calendar_usd": None if unknown else str(known),
                                  "daily_known_usd": {d: str(v) for d, v in sorted(daily.items())},
                                  "known_drop_best_3_dates_usd": str(known - sum(sorted(daily.values(), reverse=True)[:3], Decimal(0)))})
    return summaries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("screen", "replay"))
    action = parser.parse_args().action
    spec = json.loads((OUT / "specification.json").read_text())
    verify(spec)
    is_screen = action == "screen"
    folder = OUT / ("screen_sessions" if is_screen else "replay_sessions")
    target = OUT / ("screen_results.json" if is_screen else "replay_results.json")
    assert not target.exists()
    folder.mkdir(exist_ok=True)
    if not is_screen:
        screen = json.loads((OUT / "screen_results.json").read_text())
        assert not screen["errors"] and screen["selected_count"] > 0
        checkpoint = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
        state = json.loads(checkpoint.read_text())
        if not state.get("databento_fast_economic_configurations_started"):
            assert (state["current_configurations"], state["implementation_versions"]) == (139, 191)
            state.update(current_configurations=143, implementation_versions=195,
                         databento_fast_economic_configurations_started=4,
                         active_research_jobs=["Local Databento millisecond sweep conditional economic replay"])
            write(checkpoint, state)
    pending = [s for s in spec["sources"] if not (folder / (s["date"] + ".json")).exists()]
    errors, progress = [], Counter()
    with ProcessPoolExecutor(max_workers=2) as pool:
        jobs = {pool.submit(one_screen if is_screen else one_replay, s): s["date"] for s in pending}
        for n, job in enumerate(as_completed(jobs), 1):
            try:
                row = job.result()
                progress.update({k: v for k, v in row.items() if k != "date"})
                if n % 24 == 0 or n == len(jobs):
                    print(json.dumps({"sessions_completed": n, **dict(progress)}), flush=True)
            except Exception as exc:
                failure = {"date": jobs[job], "error": f"{type(exc).__name__}: {exc}"}
                errors.append(failure)
                print(json.dumps(failure), flush=True)
    sessions = [json.loads(p.read_text()) for p in sorted(folder.glob("*.json"))]
    common = {"created_at_utc": datetime.now(UTC).isoformat(), "sessions": len(sessions), "errors": errors,
              "specification_sha256": sha(OUT / "specification.json"),
              "session_hashes": {s["date"]: sha(folder / (s["date"] + ".json")) for s in sessions},
              "actual_execution_verified": False, "reliable_edge_established": False,
              "network_or_paid_calls": 0}
    if is_screen:
        counts = Counter()
        for s in sessions:
            counts.update(s["rejections"])
        selected = [e for s in sessions for e in s["selected"]]
        result = {**common, "source_rows": sum(s["source_rows"] for s in sessions),
                  "groups_checked": sum(len(s["checks"]) for s in sessions),
                  "admitted_count": sum(len(s["admitted"]) for s in sessions),
                  "selected_count": len(selected), "selected": selected, "rejections": dict(counts),
                  "selected_by_rule": dict(Counter(e["rule"] for e in selected)),
                  "source_errors": [{"date": s["date"], **r} for s in sessions for r in s["source_errors"]],
                  "economic_configurations_executed": 0, "returns_calculated": False}
    else:
        rows = [r for s in sessions for r in s["outcomes"]]
        result = {**common, "event_cases": len(rows), "outcome_counts": dict(Counter(r["outcome"] for r in rows)),
                  "economic_configurations_executed": 4, "economic_implementation_versions": 4,
                  "scenario_results": aggregates(rows, spec), "source_rows_reloaded": sum(s["source_rows_reloaded"] for s in sessions)}
    write(target, result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("session_hashes", "selected", "scenario_results")}), flush=True)


if __name__ == "__main__":
    main()
