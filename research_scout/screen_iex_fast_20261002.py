"""Run the frozen native DEEP displacement supply screen without economic returns."""

import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from research.iex_fast_displacement import screen
from research_scout.prepare_iex_fast_20261002 import OUT, ROOT, sha, write


def one(day):
    spec = json.loads((OUT / "specification.json").read_text())
    for relative, expected in spec["code_sha256"].items():
        assert sha(ROOT / relative) == expected
    source = spec["sources"][day]
    path = Path(source["prefix_path"])
    assert sha(path) == source["prefix_sha256"]
    result = screen(path, source["first_decision_ns"], source["final_decision_ns"])
    assert result["covered"] and result["decision_grids"] == 301
    result.update(date=day, source=source, specification_sha256=sha(OUT / "specification.json"),
                  runner_sha256=sha(Path(__file__)))
    target = OUT / "sessions" / (day + ".json")
    assert not target.exists()
    write(target, result)
    return {"date": day, "messages": result["source_messages_checked"],
            "candidates": len(result["candidates"]),
            "selected": [{"symbol": r["symbol"], "rule": r["rule"], "decision_ns": r["decision_ns"]}
                         for r in result["selected"]]}


def main():
    assert not (OUT / "screen_results.json").exists()
    spec = json.loads((OUT / "specification.json").read_text())
    (OUT / "sessions").mkdir(exist_ok=True)
    pending = [d for d in spec["sources"] if not (OUT / "sessions" / (d + ".json")).exists()]
    errors = []
    with ProcessPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(one, day): day for day in pending}
        for job in as_completed(jobs):
            try:
                print(json.dumps(job.result()), flush=True)
            except Exception as exc:
                failure = {"date": jobs[job], "error": f"{type(exc).__name__}: {exc}"}
                errors.append(failure)
                print(json.dumps(failure), flush=True)
    sessions = [json.loads(p.read_text()) for p in sorted((OUT / "sessions").glob("*.json"))]
    counts = Counter()
    for r in sessions:
        assert r["specification_sha256"] == sha(OUT / "specification.json")
        counts.update(r["outcomes"])
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
    main()
