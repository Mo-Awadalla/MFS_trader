"""Explicit output-folder adapter for the frozen 2024 worker; unchanged 2025 signal."""

import argparse
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from research_scout import databento_follower_2024_20261002 as frozen
from research_scout.prepare_databento_fast_20261002 import ROOT, sha, write

PARENT = frozen.OUT
OUT = PARENT.parent / "development_2025"


def prepare():
    before = json.loads((PARENT / "screen_results.json").read_text())
    audit = json.loads((PARENT / "independent_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == sha(PARENT / "screen_results.json")
    assert before["selected_count"] == 0
    spec = json.loads((PARENT / "specification.json").read_text())
    folder = ROOT / "external_artifacts/databento_cash_etf_mbp1_open_v55/EQUS.MINI/mbp-1"
    files = sorted(folder.glob("2025-*.dbn.zst"))
    assert len(files) == 250
    spec.update(created_at_utc=datetime.now(UTC).isoformat(),
                relationship="Final unchanged supply-only expansion over all250cached2025opening sessions.2023and2024supply was empty. No parameter adaptation,selected volatility dates or future-return filtering.2025was used in unrelated prior work,so this is discovery rather than globally untouched validation. Keep112cached2026files unopened for this family.",
                sources=[{"date": p.name[:10], "path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size,
                          "sha256": sha(p)} for p in files],
                leader="Enumerate every SPY trade-bearing source group with unchanged frozen predicate. The same2024worker is reused in isolated process workers with only its output-folder binding changed todevelopment_2025. No frozen file or economic/source logic is modified.",
                source_unknowns="Detect data-quality errors independently for each2025symbol/session,including bad or nonmonotone receive clocks. Keep unassessable admission unknown. Do not inherit a prior year's bad-date list.",
                preceding_2024_results_sha256=sha(PARENT / "screen_results.json"),
                preceding_2024_audit_sha256=sha(PARENT / "independent_verification.json"),
                stopping_rule="If no candidate passes in2025,close this exact sweep-triggered follower hypothesis over these cached development windows. Do not lower thresholds or automatically consume2026data. A surviving signal only earns a separately frozen execution test.",
                economic_configurations_executed=0, returns_calculated=False)
    spec["code_sha256"]["research_scout/databento_follower_2025_20261003.py"] = sha(Path(__file__))
    OUT.mkdir(exist_ok=True)
    assert not (OUT / "specification.json").exists()
    write(OUT / "specification.json", spec)
    checkpoint = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    state = json.loads(checkpoint.read_text())
    state.update(updated_at_utc=datetime.now(UTC).isoformat(),
                 active_research_jobs=["Unchanged follower supply on250cached2025Databento sessions"],
                 databento_follower_2025_specification=str(OUT / "specification.json"),
                 previous_goal_turn_classification="progress",
                 remaining_evidence_work="Final unchanged2025SPY/follower supply expansion frozen.2023/24were independently audited empty. No future return or paid call;2026remains reserved.")
    write(checkpoint, state)
    print(json.dumps({"sessions": len(files), "bytes": sum(p.stat().st_size for p in files),
                      "specification_sha256": sha(OUT / "specification.json")}))


def one(source):
    assert source["date"].startswith("2025-")
    assert frozen.OUT == PARENT and OUT != PARENT
    # Each process runs one task at a time. Only the destination binding changes.
    previous = frozen.OUT
    try:
        frozen.OUT = OUT
        return frozen.one(source)
    finally:
        frozen.OUT = previous


def screen():
    spec = json.loads((OUT / "specification.json").read_text())
    assert not (OUT / "screen_results.json").exists()
    (OUT / "sessions").mkdir(exist_ok=True)
    pending = [s for s in spec["sources"] if not (OUT / "sessions" / (s["date"] + ".json")).exists()]
    errors, counters = [], Counter()
    with ProcessPoolExecutor(max_workers=2) as pool:
        jobs = {pool.submit(one, s): s["date"] for s in pending}
        for n, job in enumerate(as_completed(jobs), 1):
            try:
                counters.update(job.result())
                if n % 32 == 0 or n == len(jobs):
                    print(json.dumps({"sessions_completed": n, **dict(counters)}), flush=True)
            except Exception as exc:
                e = {"date": jobs[job], "error": f"{type(exc).__name__}: {exc}"}
                errors.append(e)
                print(json.dumps(e), flush=True)
    sessions = [json.loads(p.read_text()) for p in sorted((OUT / "sessions").glob("*.json"))]
    failures, grouping = Counter(), Counter()
    for session in sessions:
        assert session["specification_sha256"] == sha(OUT / "specification.json")
        failures.update(session["rejections"])
        grouping.update(session["group_counts"])
    selected = [e for s in sessions for e in s["selected"]]
    budgets = [r["budget"] for s in sessions for r in s["follower_checks"] if r["budget"] is not None]
    best = max((Decimal(r["projected_net_bp"]) for r in budgets), default=None)
    results = {"created_at_utc": datetime.now(UTC).isoformat(), "sessions": len(sessions), "errors": errors,
               "source_rows": sum(s["source_rows"] for s in sessions), "group_counts": dict(grouping),
               "leader_groups": sum(len(s["leader_checks"]) for s in sessions),
               "valid_leader_signals": sum(c["signal"] is not None for s in sessions for c in s["leader_checks"]),
               "follower_checks": sum(len(s["follower_checks"]) for s in sessions), "budgets": len(budgets),
               "best_projected_net_bp": str(best) if best is not None else None,
               "admitted_count": sum(len(s["admitted"]) for s in sessions), "selected_count": len(selected), "selected": selected,
               "rejections": dict(failures), "source_errors": [{"date": s["date"], **e} for s in sessions for e in s["source_errors"]],
               "session_hashes": {s["date"]: sha(OUT / "sessions" / (s["date"] + ".json")) for s in sessions},
               "specification_sha256": sha(OUT / "specification.json"), "economic_configurations_executed": 0,
               "returns_calculated": False, "actual_execution_verified": False,
               "reliable_edge_established": False, "network_or_paid_calls": 0}
    assert sha(PARENT / "screen_results.json") == spec["preceding_2024_results_sha256"]
    assert sha(PARENT / "independent_verification.json") == spec["preceding_2024_audit_sha256"]
    write(OUT / "screen_results.json", results)
    print(json.dumps({k: v for k, v in results.items() if k not in ("selected", "session_hashes")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "screen"))
    args = parser.parse_args()
    prepare() if args.action == "prepare" else screen()
