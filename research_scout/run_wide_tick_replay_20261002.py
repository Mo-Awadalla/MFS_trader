"""Freeze the tested implementation and replay both schedules and all stresses."""

import calendar
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime

from research.wide_tick_replay import SCENARIOS, load_day, replay_portfolio
from research_scout.prepare_wide_tick_20260930 import OUT, ROOT

RUN = OUT / "replay_v1_20261002"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    RUN.mkdir(exist_ok=True)
    if (RUN / "implementation.json").exists():
        raise RuntimeError("Preserve the original implementation freeze and partial/complete results")
    spec = json.loads((OUT / "replay_specification.json").read_text())
    manifest = json.loads((OUT / "replay_manifest.json").read_text())
    assert manifest["complete"] and len(manifest["files"]) == 30
    assert sha(OUT / "replay_specification.json") == manifest["specification_sha256"]
    assert sha(OUT / "selected.parquet") == spec["selected_sha256"]
    assert spec["rest_seconds"] == [10, 22]
    assert set(spec["stress_scenarios"]) == set(SCENARIOS)
    freeze = {"created_at_utc": datetime.now(UTC).isoformat(), "economic_configurations": 2,
              "scenarios_per_configuration": 6,
              "inputs_sha256": {name: sha(OUT/name) for name in ["replay_specification.json", "replay_interval_clarification.json", "replay_manifest.json", "selected.parquet", "verification.json", "pre_replay_review_20261002.json"]},
              "implementation_sha256": {name: sha(ROOT/name) for name in ["research/wide_tick_replay.py", "research/wide_tick_supply.py", "research_scout/run_wide_tick_replay_20261002.py", "tests/unit/test_wide_tick_replay.py"]},
              "execution_scenarios": SCENARIOS, "actual_execution_verified": False, "reliable_edge_established": False}
    (RUN / "implementation.json").write_text(json.dumps(freeze, indent=2)+"\n")
    records, sources, ledgers = [], [], []
    for cohort in spec["cohorts"]:
        day = cohort["date"]
        midnight = calendar.timegm(datetime.strptime(day, "%Y-%m-%d").timetuple())*1_000_000_000
        files = [r for r in manifest["files"] if r["date"] == day]
        assert {r["offset"] for r in files} == {540, 550, 560}
        tapes, diagnostics = load_day(ROOT, files, day, midnight, cohort["symbols"])
        sources.append(diagnostics)
        (RUN / "source_diagnostics.json").write_text(json.dumps(sources, indent=2)+"\n")
        for rest in spec["rest_seconds"]:
            for name, scenario in SCENARIOS.items():
                rows, outcome = replay_portfolio(tapes, midnight, rest, scenario)
                ledger = RUN / f"{day}_{rest}s_{name}.jsonl"
                with ledger.open("x", encoding="utf-8") as stream:
                    for row in rows:
                        stream.write(json.dumps({"date": day, "rest_seconds": rest, "scenario": name, **row}, allow_nan=False)+"\n")
                closed = [r for r in rows if r["status"] == "bounded_complete"]
                fills = [r for r in closed if max(r["buy_quantity_bounds"][1], r["sell_quantity_bounds"][1]) > 0]
                positive = sum(r["net_low"] > 1e-10 for r in fills)
                negative = sum(r["net_high"] < -1e-10 for r in fills)
                outcome.update(date=day, rest_seconds=rest, scenario=name,
                               submitted_cycles=sum("intended_quantity" in r for r in rows), bounded_cycles=len(closed),
                               cycles_with_possible_fills=len(fills), definitely_profitable_cycles=positive,
                               definitely_losing_cycles=negative, reasons=dict(Counter(r.get("reason", r["status"]) for r in rows)))
                records.append(outcome)
                ledgers.append({"date": day, "rest_seconds": rest, "scenario": name, "file": ledger.name, "sha256": sha(ledger), "rows": len(rows)})
        (RUN / "daily_results.json").write_text(json.dumps(records, indent=2, allow_nan=False)+"\n")
        (RUN / "ledger_manifest.json").write_text(json.dumps(ledgers, indent=2)+"\n")
        print(json.dumps({"date": day, "native_messages": diagnostics["native_messages"],
                          "baselines": [{k: r[k] for k in ["rest_seconds", "complete", "net_low", "net_high", "closed_portion_net_low", "cycles_with_possible_fills", "statuses"]} for r in records if r["date"] == day and r["scenario"] == "base"]}), flush=True)
    summaries = []
    for rest in spec["rest_seconds"]:
        for name in SCENARIOS:
            days = [r for r in records if r["rest_seconds"] == rest and r["scenario"] == name]
            complete = all(r["complete"] for r in days)
            low = sum(r["net_low"] for r in days) if complete else None
            high = sum(r["net_high"] for r in days) if complete else None
            reasons = Counter()
            for row in days:
                reasons.update(row["reasons"])
            summaries.append({"rest_seconds": rest, "scenario": name, "complete": complete,
                              "complete_dates": sum(r["complete"] for r in days), "selected_dates": len(days),
                              "net_low": low, "net_high": high, "net_low_over_reference_capital_bps": low if low is not None else None,
                              "closed_portion_net_low": sum(r["closed_portion_net_low"] for r in days),
                              "closed_portion_net_high": sum(r["closed_portion_net_high"] for r in days),
                              "submitted_cycles": sum(r["submitted_cycles"] for r in days),
                              "cycles_with_possible_fills": sum(r["cycles_with_possible_fills"] for r in days),
                              "definitely_profitable_cycles": sum(r["definitely_profitable_cycles"] for r in days),
                              "definitely_losing_cycles": sum(r["definitely_losing_cycles"] for r in days),
                              "reasons": dict(reasons)})
    result = {"completed_at_utc": datetime.now(UTC).isoformat(), "configurations_run": 2,
              "scenario_results": summaries, "source_native_messages": sum(r["native_messages"] for r in sources),
              "ledger_files": len(ledgers), "counterfactual_public_tape_model": True,
              "order_grid_assumption_verified": False, "actual_execution_verified": False,
              "independent_accounting_verified": False, "reliable_edge_established": False,
              "selection_2025_opened": False,
              "artifacts_sha256": {name: sha(RUN/name) for name in ["implementation.json", "source_diagnostics.json", "daily_results.json", "ledger_manifest.json"]}}
    (RUN / "results.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps({"configurations_run": 2, "native_messages": result["source_native_messages"], "summaries": [{k: v for k, v in r.items() if k != "reasons"} for r in summaries]}, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
