"""Same frozen signal during the early continuous session; prepare before any new screen."""

import argparse
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from research.iex_fast_displacement import screen
from research_scout.prepare_iex_fast_20261002 import OUT as PARENT
from research_scout.prepare_iex_fast_20261002 import ROOT, sha, write

OUT = PARENT / "early_window_v1"


def prepare():
    parent_results = json.loads((PARENT / "screen_results.json").read_text())
    audit = json.loads((PARENT / "independent_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == sha(PARENT / "screen_results.json")
    assert parent_results["candidate_count"] == 0
    spec = json.loads((PARENT / "specification.json").read_text())
    for source in spec["sources"].values():
        final = source["final_decision_ns"]
        source["first_decision_ns"] = final - 58000000000
        source["final_decision_ns"] = final - 30100000000
    spec.update(created_at_utc=datetime.now(UTC).isoformat(),
                variant="Earlier continuous trading only; every economic and activity threshold unchanged.",
                grid="09:30:02.000 through09:30:29.900 ET inclusive every100ms:280 decisions. Same strictly-before cutoff decision-1ms and reference cutoff-1s. Does not overlap the parent's09:30:30..09:31:00 decisions. Exclude cross prints by unchanged flags; require both valid recent states.",
                motivation="Later opening interval had no qualifying signals. Test an earlier interval where price discovery might create larger, active displacements, without loosening price, activity, quote, size or cost criteria.",
                parent_admission_results_sha256=sha(PARENT / "screen_results.json"),
                parent_admission_audit_sha256=sha(PARENT / "independent_verification.json"))
    spec["code_sha256"].pop("research_scout/screen_iex_fast_20261002.py")
    spec["code_sha256"]["research_scout/iex_fast_early_20261002.py"] = sha(Path(__file__))
    OUT.mkdir(exist_ok=True)
    assert not (OUT / "specification.json").exists()
    write(OUT / "specification.json", spec)
    print(json.dumps({"specification_sha256": sha(OUT / "specification.json"), "grids_per_date": 280}))


def one(day):
    spec = json.loads((OUT / "specification.json").read_text())
    for relative, expected in spec["code_sha256"].items():
        assert sha(ROOT / relative) == expected
    source = spec["sources"][day]
    path = Path(source["prefix_path"])
    assert sha(path) == source["prefix_sha256"]
    result = screen(path, source["first_decision_ns"], source["final_decision_ns"])
    assert result["covered"] and result["decision_grids"] == 280
    result.update(date=day, source=source, specification_sha256=sha(OUT / "specification.json"),
                  runner_sha256=sha(Path(__file__)))
    target = OUT / "sessions" / (day + ".json")
    assert not target.exists()
    write(target, result)
    return {"date": day, "messages": result["source_messages_checked"],
            "candidates": len(result["candidates"]),
            "selected": [{"symbol": r["symbol"], "rule": r["rule"], "decision_ns": r["decision_ns"],
                          "move_bp": r["move_bp"], "causal_cost_bp": r["causal_cost_bp"]}
                         for r in result["selected"]]}


def run():
    spec = json.loads((OUT / "specification.json").read_text())
    assert not (OUT / "screen_results.json").exists()
    (OUT / "sessions").mkdir(exist_ok=True)
    pending = [d for d in spec["sources"] if not (OUT / "sessions" / (d + ".json")).exists()]
    errors = []
    with ProcessPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(one, day): day for day in pending}
        for future in as_completed(futures):
            try:
                print(json.dumps(future.result()), flush=True)
            except Exception as exc:
                error = {"date": futures[future], "error": f"{type(exc).__name__}: {exc}"}
                errors.append(error)
                print(json.dumps(error), flush=True)
    sessions = [json.loads(p.read_text()) for p in sorted((OUT / "sessions").glob("*.json"))]
    counts = Counter()
    for s in sessions:
        assert s["specification_sha256"] == sha(OUT / "specification.json")
        counts.update(s["outcomes"])
    results = {"intact_dates_screened": len(sessions), "errors": errors,
               "unknown_admission_dates": spec["unknown_admission_dates"],
               "source_messages_checked": sum(s["source_messages_checked"] for s in sessions),
               "decision_grids": sum(s["decision_grids"] for s in sessions),
               "symbol_grids": sum(s["symbol_grids"] for s in sessions), "outcomes": dict(counts),
               "candidate_count": sum(len(s["candidates"]) for s in sessions),
               "selected": [{"date": s["date"], **r} for s in sessions for r in s["selected"]],
               "session_hashes": {s["date"]: sha(OUT / "sessions" / (s["date"] + ".json")) for s in sessions},
               "specification_sha256": sha(OUT / "specification.json"), "runner_sha256": sha(Path(__file__)),
               "economic_configurations_executed": 0, "returns_calculated": False,
               "actual_execution_verified": False, "reliable_edge_established": False}
    write(OUT / "screen_results.json", results)
    print(json.dumps({k: v for k, v in results.items() if k not in ("selected", "session_hashes")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "run"))
    args = parser.parse_args()
    prepare() if args.action == "prepare" else run()
