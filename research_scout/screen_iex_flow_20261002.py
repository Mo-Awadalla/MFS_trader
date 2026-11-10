"""Screen native historical prints at both proposed limits without computing returns."""

import gzip
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from decimal import Decimal
from pathlib import Path

from research.iex_two_sided_activity import admit, collect
from research_scout.prepare_iex_flow_20261002 import OUT, PARENT, ROOT, digest


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def one_date(day):
    spec = json.loads((OUT / "specification.json").read_text())
    for relative, field in (("research/iex_two_sided_activity.py", "implementation_sha256"),
                            ("research/iex_deep_supply.py", "deep_decoder_sha256"),
                            ("research/iex_native_prefix.py", "packet_decoder_sha256")):
        assert digest(ROOT / relative) == spec[field]
    parent = json.loads((PARENT / "screen_results.json").read_text())
    parent_path = PARENT / "sessions" / (day + ".json")
    assert digest(parent_path) == parent["session_hashes"][day]
    old = json.loads(parent_path.read_text())
    source = Path(old["prefix_path"])
    assert digest(source) == old["prefix_sha256"]
    symbols = [r["symbol"] for r in old["candidates"]]
    if symbols:
        rows, coverage = collect(source, symbols, old["cutoff_ns"])
        assert coverage["covered"] and coverage["source_messages_checked"] == old["messages_checked"]
    else:
        rows, coverage = [], {"covered": True, "source_messages_checked": 0,
                              "inherited_verified_parent_has_no_budget_candidate": True}
    records_path = OUT / "records" / (day + ".jsonl.gz")
    with gzip.open(records_path, "wt", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    checks, qualified = [], []
    for candidate in old["candidates"]:
        detail = admit(candidate, rows, old["cutoff_ns"])
        assert detail["eligible_prior_trade_count"] == candidate["prior_trade_count"]
        assert Decimal(detail["eligible_prior_notional_units"]) / 10000 == Decimal(candidate["prior_trade_notional_usd"])
        checks.append({"candidate": candidate, "activity": detail})
        if detail["qualified"]:
            qualified.append(candidate)
    qualified.sort(key=lambda r: (-Decimal(r["quoted_net_budget_bps"]),
                                  -Decimal(r["prior_trade_notional_usd"]), r["symbol"]))
    result = {"date": day, "decision_ns": old["decision_ns"], "cutoff_ns": old["cutoff_ns"],
              "checks": checks, "qualified": qualified, "selected": qualified[:1], "coverage": coverage,
              "records_path": str(records_path), "records_sha256": digest(records_path),
              "source_path": str(source), "source_sha256": digest(source),
              "parent_session_sha256": digest(parent_path),
              "specification_sha256": digest(OUT / "specification.json"), "runner_sha256": digest(Path(__file__)),
              "returns_calculated": False, "actual_execution_verified": False}
    path = OUT / "sessions" / (day + ".json")
    assert not path.exists()
    write(path, result)
    return {"date": day, "candidates_checked": len(checks), "qualified": len(qualified),
            "selected": [r["symbol"] for r in result["selected"]]}


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    assert digest(PARENT / "screen_results.json") == spec["parent_screen_sha256"]
    assert digest(PARENT / "independent_verification.json") == spec["parent_audit_sha256"]
    assert not (OUT / "screen_results.json").exists()
    (OUT / "sessions").mkdir(exist_ok=True)
    (OUT / "records").mkdir(exist_ok=True)
    pending = [d for d in spec["intact_dates"] if not (OUT / "sessions" / (d + ".json")).exists()]
    errors = []
    with ProcessPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(one_date, d): d for d in pending}
        for job in as_completed(jobs):
            try:
                print(json.dumps(job.result()), flush=True)
            except Exception as exc:
                row = {"date": jobs[job], "error": f"{type(exc).__name__}: {exc}"}
                errors.append(row)
                print(json.dumps(row), flush=True)
    sessions = [json.loads((OUT / "sessions" / (d + ".json")).read_text()) for d in spec["intact_dates"]
                if (OUT / "sessions" / (d + ".json")).exists()]
    result = {"dates_requested": len(spec["dates"]), "intact_dates_screened": len(sessions),
              "unknown_admission_dates": spec["unknown_admission_dates"], "errors": errors,
              "source_messages_checked": sum(r["coverage"]["source_messages_checked"] for r in sessions),
              "candidate_checks": sum(len(r["checks"]) for r in sessions),
              "qualified": sum(len(r["qualified"]) for r in sessions),
              "selected": [{"date": r["date"], **c} for r in sessions for c in r["selected"]],
              "session_hashes": {r["date"]: digest(OUT / "sessions" / (r["date"] + ".json")) for r in sessions},
              "specification_sha256": digest(OUT / "specification.json"), "runner_sha256": digest(Path(__file__)),
              "economic_configurations_executed": 0, "returns_calculated": False,
              "actual_execution_verified": False, "reliable_edge_established": False}
    if not errors:
        assert result["candidate_checks"] == spec["candidate_count"]
    write(OUT / "screen_results.json", result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("session_hashes", "selected")}), flush=True)


if __name__ == "__main__":
    main()
