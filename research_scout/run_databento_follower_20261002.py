"""Local-only admission and fixed conditional replay of index follower lag."""

import argparse
import json
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

from research.equity_follower_lag import MULTIPLIERS, follower, leader, select
from research.equity_sweep_fast import replay
from research_scout.prepare_databento_fast_20261002 import PARENT, ROOT, sha, write
from research_scout.prepare_databento_follower_20261002 import OUT
from research_scout.run_databento_fast_20261002 import source_arrays


def verify(spec):
    for path, expected in spec["code_sha256"].items():
        assert sha(ROOT / path) == expected


def screen_one(source):
    spec = json.loads((OUT / "specification.json").read_text())
    verify(spec)
    day = source["date"]
    parent_file = PARENT / "sessions" / (day + ".json")
    assert sha(parent_file) == next(r["sha256"] for r in spec["parent_sessions"] if r["date"] == day)
    parent = json.loads(parent_file.read_text())
    ready, errors, count = source_arrays(source, spec["symbols"])
    assert errors == parent["source_errors"]
    opening = int(pd.Timestamp(day + " 09:30:00", tz="America/New_York").tz_convert("UTC").value)
    leader_checks, checks, admissions, failures = [], [], [], Counter()
    for diagnostics in parent["symbol_diagnostics"]:
        if diagnostics["symbol"] != "SPY":
            continue
        for item in diagnostics["observations"]:
            signal, reason = leader(ready["SPY"], item["group"], opening)
            leader_checks.append({"group": item["group"], "signal": signal, "reason": reason})
            if reason is not None:
                failures[reason] += 1
                continue
            for symbol in MULTIPLIERS:
                if symbol not in ready:
                    event, reason, detail = None, "unknown_follower_source", None
                else:
                    event, reason, detail = follower(ready[symbol], symbol, signal)
                if event is not None:
                    event["date"] = day
                    admissions.append(event)
                if reason:
                    failures[reason] += 1
                checks.append({"symbol": symbol, "signal": signal, "event": event, "reason": reason, "budget": detail})
    result = {"date": day, "source": source, "source_rows": count, "source_errors": errors,
              "leader_checks": leader_checks, "follower_checks": checks, "admitted": admissions,
              "selected": select(admissions), "rejections": dict(failures),
              "specification_sha256": sha(OUT / "specification.json"), "returns_calculated": False}
    path = OUT / "screen_sessions" / (day + ".json")
    assert not path.exists()
    write(path, result)
    return {"leader_groups": len(leader_checks), "follower_checks": len(checks),
            "budgets": sum(c["budget"] is not None for c in checks), "selected": len(result["selected"])}


def replay_one(source):
    spec = json.loads((OUT / "specification.json").read_text())
    verify(spec)
    day = source["date"]
    original = json.loads((OUT / "screen_results.json").read_text())
    path = OUT / "screen_sessions" / (day + ".json")
    assert sha(path) == original["session_hashes"][day]
    session = json.loads(path.read_text())
    symbols = sorted({e["symbol"] for e in session["selected"]})
    ready, errors, count = source_arrays(source, symbols) if symbols else ({}, [], 0)
    assert not errors
    rows = [replay(e, ready[e["symbol"]], h, c) for e in session["selected"] for h in spec["hold_ms"] for c in spec["cases"]]
    write(OUT / "replay_sessions" / (day + ".json"), {"date": day, "outcomes": rows, "source_rows_reloaded": count,
          "screen_session_sha256": sha(path), "specification_sha256": sha(OUT / "specification.json")})
    return {"event_cases": len(rows), "priced": sum(r["outcome"] == "conditional_priced" for r in rows)}


def aggregate(rows, hold, case, spec):
    chosen = [r for r in rows if (r["hold_ms"], r["case"]) == (hold, case)]
    unknown = {r["date"] for r in spec["inherited_unknown_symbol_dates"]}
    daily = defaultdict(Decimal)
    for r in chosen:
        if r["net_usd"] is None:
            unknown.add(r["date"])
        else:
            daily[r["date"]] += Decimal(r["net_usd"])
    net = sum(daily.values(), Decimal(0))
    return {"rule": "spy_follower_lag_long", "hold_ms": hold, "case": case,
            "event_cases": len(chosen), "unknown_events": sum(r["net_usd"] is None for r in chosen),
            "known_component_usd": str(net), "observed_event_cohort_usd": str(net) if all(r["net_usd"] is not None for r in chosen) else None,
            "full_calendar_usd": None if unknown else str(net), "unknown_calendar_dates": sorted(unknown),
            "daily_known_usd": {d: str(v) for d, v in sorted(daily.items())},
            "known_drop_best_3_dates_usd": str(net - sum(sorted(daily.values(), reverse=True)[:3], Decimal(0)))}


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
        original = json.loads((OUT / "screen_results.json").read_text())
        assert not original["errors"] and original["selected_count"] > 0
        checkpoint = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
        state = json.loads(checkpoint.read_text())
        if not state.get("databento_follower_economic_configurations_started"):
            assert (state["current_configurations"], state["implementation_versions"]) == (143, 195)
            state.update(current_configurations=145, implementation_versions=197,
                         databento_follower_economic_configurations_started=2,
                         active_research_jobs=["Local Databento follower conditional replay"])
            write(checkpoint, state)
    pending = [s for s in spec["sources"] if not (folder / (s["date"] + ".json")).exists()]
    errors, counts = [], Counter()
    with ProcessPoolExecutor(max_workers=2) as pool:
        jobs = {pool.submit(screen_one if is_screen else replay_one, s): s["date"] for s in pending}
        for n, job in enumerate(as_completed(jobs), 1):
            try:
                counts.update(job.result())
                if n % 32 == 0 or n == len(jobs):
                    print(json.dumps({"sessions_completed": n, **dict(counts)}), flush=True)
            except Exception as exc:
                e = {"date": jobs[job], "error": f"{type(exc).__name__}: {exc}"}
                errors.append(e)
                print(json.dumps(e), flush=True)
    sessions = [json.loads(p.read_text()) for p in sorted(folder.glob("*.json"))]
    common = {"created_at_utc": datetime.now(UTC).isoformat(), "sessions": len(sessions), "errors": errors,
              "specification_sha256": sha(OUT / "specification.json"),
              "session_hashes": {r["date"]: sha(folder / (r["date"] + ".json")) for r in sessions},
              "actual_execution_verified": False, "reliable_edge_established": False, "network_or_paid_calls": 0}
    if is_screen:
        rejections = Counter()
        for s in sessions:
            rejections.update(s["rejections"])
        selected = [e for s in sessions for e in s["selected"]]
        budgets = [{"date": s["date"], **c["budget"]} for s in sessions for c in s["follower_checks"] if c["budget"] is not None]
        result = {**common, "source_rows": sum(s["source_rows"] for s in sessions),
                  "leader_groups": sum(len(s["leader_checks"]) for s in sessions),
                  "valid_leader_signals": sum(c["signal"] is not None for s in sessions for c in s["leader_checks"]),
                  "follower_checks": sum(len(s["follower_checks"]) for s in sessions),
                  "budgets": len(budgets), "best_projected_net_bp": max((Decimal(r["projected_net_bp"]) for r in budgets), default=None),
                  "admitted_count": sum(len(s["admitted"]) for s in sessions), "selected_count": len(selected), "selected": selected,
                  "rejections": dict(rejections), "source_errors": [{"date": s["date"], **e} for s in sessions for e in s["source_errors"]],
                  "economic_configurations_executed": 0, "returns_calculated": False}
        if result["best_projected_net_bp"] is not None:
            result["best_projected_net_bp"] = str(result["best_projected_net_bp"])
    else:
        rows = [r for s in sessions for r in s["outcomes"]]
        result = {**common, "event_cases": len(rows), "outcome_counts": dict(Counter(r["outcome"] for r in rows)),
                  "economic_configurations_executed": 2, "economic_implementation_versions": 2,
                  "scenario_results": [aggregate(rows, h, c["name"], spec) for h in spec["hold_ms"] for c in spec["cases"]]}
    write(target, result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("session_hashes", "selected", "scenario_results")}), flush=True)


if __name__ == "__main__":
    main()
