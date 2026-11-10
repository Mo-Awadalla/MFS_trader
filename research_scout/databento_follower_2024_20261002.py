"""Freeze and screen every local 2024 session using the unchanged follower rule."""

import argparse
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal

import databento as db
import pandas as pd

from research.equity_follower_lag import MULTIPLIERS, follower, leader, select
from research.equity_resilience import arrays
from research.equity_sweep import sweep_groups
from research_scout.prepare_databento_fast_20261002 import ROOT, sha, write
from research_scout.prepare_databento_follower_20261002 import OUT as PARENT

OUT = PARENT / "development_2024"


def prepare():
    original = json.loads((PARENT / "screen_results.json").read_text())
    audit = json.loads((PARENT / "independent_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == sha(PARENT / "screen_results.json")
    assert original["selected_count"] == 0
    previous = json.loads((PARENT / "specification.json").read_text())
    spec = {k: v for k, v in previous.items() if k not in (
        "sources", "parent_sessions", "parent_screen_sha256", "parent_candidate_audit_sha256",
        "preceding_fast_audit_sha256", "inherited_unknown_symbol_dates", "code_sha256")}
    folder = ROOT / "external_artifacts/databento_cash_etf_mbp1_open_v55/EQUS.MINI/mbp-1"
    files = sorted(folder.glob("2024-*.dbn.zst"))
    assert len(files) == 252
    code = ("research/equity_follower_lag.py", "research/equity_resilience.py", "research/equity_sweep.py",
            "research/equity_sweep_fast.py", "research/exact_json.py",
            "research_scout/databento_follower_2024_20261002.py")
    spec.update(created_at_utc=datetime.now(UTC).isoformat(),
                relationship="Unchanged signal and cost thresholds applied to all252cached2024sessions after the2023supply screen was empty. Further discovery across a different period,not validation of an established edge. Prior unrelated work has used2024data;do not claim a globally untouched holdout.",
                sources=[{"date": p.name[:10], "path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size,
                          "sha256": sha(p)} for p in files],
                leader="Enumerate all completed SPY trade-bearing groups in each local2024session with the EXACT frozen research/equity_sweep.py predicate used in2023. Preserve accepted and rejected groups,counts and raw indexes. Any BAD_TS_RECV SPY session stays unassessable;other follower source errors remain explicit.",
                source_unknowns="Derive each symbol/date's data-quality errors directly from2024records;do not reuse the2023bad-date list. Such missing admission cannot be zero if a later economic replay is run.",
                preceding_2023_results_sha256=sha(PARENT / "screen_results.json"),
                preceding_2023_audit_sha256=sha(PARENT / "independent_verification.json"),
                code_sha256={p: sha(ROOT / p) for p in code}, economic_configurations_executed=0,
                returns_calculated=False)
    OUT.mkdir(exist_ok=True)
    assert not (OUT / "specification.json").exists()
    write(OUT / "specification.json", spec)
    checkpoint = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    state = json.loads(checkpoint.read_text())
    state.update(updated_at_utc=datetime.now(UTC).isoformat(),
                 active_research_jobs=["Unchanged Databento follower admission on all252cached2024sessions"],
                 databento_follower_2024_specification=str(OUT / "specification.json"),
                 remaining_evidence_work="2023follower supply independently verified empty.2024expansion frozen with unchanged rules over252localfiles;no economic variant or return yet. No paid calls.")
    write(checkpoint, state)
    print(json.dumps({"source_sessions": 252, "source_bytes": sum(p.stat().st_size for p in files),
                      "specification_sha256": sha(OUT / "specification.json")}))


def one(source):
    spec = json.loads((OUT / "specification.json").read_text())
    for relative, expected in spec["code_sha256"].items():
        assert sha(ROOT / relative) == expected
    path, day = ROOT / source["path"], source["date"]
    assert sha(path) == source["sha256"]
    store = db.read_dbn(path)
    assert store.metadata.dataset == "EQUS.MINI" and str(store.metadata.schema) == "mbp-1"
    raw = store.to_ndarray()
    ready, errors, spy = {}, [], None
    for symbol in spec["symbols"]:
        ids = [int(m["symbol"]) for m in store.metadata.mappings[symbol]
               if str(m["start_date"]) <= day < str(m["end_date"])]
        assert len(ids) == 1
        subset = raw[raw["instrument_id"] == ids[0]]
        try:
            ready[symbol] = arrays(subset)
            if symbol == "SPY":
                spy = subset
        except ValueError as exc:
            errors.append({"symbol": symbol, "reason": str(exc)})
    groups, rejected, group_counts = sweep_groups(spy, ready["SPY"]) if spy is not None else ([], [], {})
    opening = int(pd.Timestamp(day + " 09:30:00", tz="America/New_York").tz_convert("UTC").value)
    leaders, checks, admissions, failures = [], [], [], Counter()
    for group in groups:
        signal, why = leader(ready["SPY"], group, opening)
        leaders.append({"group": group, "signal": signal, "reason": why})
        if why:
            failures[why] += 1
            continue
        for symbol in MULTIPLIERS:
            if symbol in ready:
                event, why, detail = follower(ready[symbol], symbol, signal)
            else:
                event, why, detail = None, "unknown_follower_source", None
            if why:
                failures[why] += 1
            if event is not None:
                event["date"] = day
                admissions.append(event)
            checks.append({"symbol": symbol, "signal": signal, "event": event, "reason": why, "budget": detail})
    result = {"date": day, "source": source, "source_rows": len(raw), "source_errors": errors,
              "group_counts": group_counts, "rejected_groups": rejected,
              "leader_checks": leaders, "follower_checks": checks, "admitted": admissions,
              "selected": select(admissions), "rejections": dict(failures),
              "specification_sha256": sha(OUT / "specification.json"), "returns_calculated": False}
    target = OUT / "sessions" / (day + ".json")
    assert not target.exists()
    write(target, result)
    return {"source_rows": len(raw), "groups": len(groups), "follower_checks": len(checks),
            "budgets": sum(c["budget"] is not None for c in checks), "selected": len(result["selected"])}


def screen():
    spec = json.loads((OUT / "specification.json").read_text())
    assert not (OUT / "screen_results.json").exists()
    (OUT / "sessions").mkdir(exist_ok=True)
    pending = [s for s in spec["sources"] if not (OUT / "sessions" / (s["date"] + ".json")).exists()]
    counts, errors = Counter(), []
    with ProcessPoolExecutor(max_workers=2) as pool:
        jobs = {pool.submit(one, s): s["date"] for s in pending}
        for n, job in enumerate(as_completed(jobs), 1):
            try:
                counts.update(job.result())
                if n % 36 == 0 or n == len(jobs):
                    print(json.dumps({"sessions_completed": n, **dict(counts)}), flush=True)
            except Exception as exc:
                e = {"date": jobs[job], "error": f"{type(exc).__name__}: {exc}"}
                errors.append(e)
                print(json.dumps(e), flush=True)
    sessions = [json.loads(p.read_text()) for p in sorted((OUT / "sessions").glob("*.json"))]
    rejections, grouping = Counter(), Counter()
    for s in sessions:
        rejections.update(s["rejections"])
        grouping.update(s["group_counts"])
    selected = [r for s in sessions for r in s["selected"]]
    budgets = [r["budget"] for s in sessions for r in s["follower_checks"] if r["budget"] is not None]
    best = max((Decimal(r["projected_net_bp"]) for r in budgets), default=None)
    results = {"created_at_utc": datetime.now(UTC).isoformat(), "sessions": len(sessions), "errors": errors,
               "source_rows": sum(s["source_rows"] for s in sessions), "group_counts": dict(grouping),
               "leader_groups": sum(len(s["leader_checks"]) for s in sessions),
               "valid_leader_signals": sum(r["signal"] is not None for s in sessions for r in s["leader_checks"]),
               "follower_checks": sum(len(s["follower_checks"]) for s in sessions), "budgets": len(budgets),
               "best_projected_net_bp": str(best) if best is not None else None,
               "admitted_count": sum(len(s["admitted"]) for s in sessions), "selected_count": len(selected), "selected": selected,
               "rejections": dict(rejections), "source_errors": [{"date": s["date"], **e} for s in sessions for e in s["source_errors"]],
               "session_hashes": {s["date"]: sha(OUT / "sessions" / (s["date"] + ".json")) for s in sessions},
               "specification_sha256": sha(OUT / "specification.json"), "economic_configurations_executed": 0,
               "returns_calculated": False, "actual_execution_verified": False,
               "reliable_edge_established": False, "network_or_paid_calls": 0}
    write(OUT / "screen_results.json", results)
    print(json.dumps({k: v for k, v in results.items() if k not in ("session_hashes", "selected")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "screen"))
    args = parser.parse_args()
    prepare() if args.action == "prepare" else screen()
