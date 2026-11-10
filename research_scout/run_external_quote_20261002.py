"""Freeze and run both external-price quote schedules without outcome tuning."""

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime

from research.external_quote_hft import load_external, replay_portfolio
from research.wide_tick_replay import SCENARIOS, load_day
from research_scout.prepare_external_quote_20261002 import OUT, PARENT, ROOT

RUN = OUT/"replay_v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    RUN.mkdir(exist_ok=True)
    if (RUN/"implementation.json").exists():
        raise FileExistsError("Preserve the frozen run; do not overwrite any partial or final outcome")
    spec = json.loads((OUT/"specification.json").read_text())
    source = json.loads((OUT/"source_manifest_network_retry1.json").read_text())
    binance = json.loads((PARENT/"replay_manifest.json").read_text())
    assert source["complete"] and binance["complete"]
    assert source["specification_sha256"] == sha(OUT/"specification.json")
    assert spec["parent_specification_sha256"] == sha(PARENT/"replay_specification.json")
    assert spec["selected_sha256"] == sha(PARENT/"selected.parquet")
    code = ["research/external_quote_hft.py", "research/wide_tick_replay.py", "research/wide_tick_supply.py",
            "research_scout/run_external_quote_20261002.py", "tests/unit/test_external_quote_hft.py"]
    freeze = {"created_at_utc": datetime.now(UTC).isoformat(), "economic_configurations": 2,
              "execution_scenarios": SCENARIOS, "execution_tests_passed": 15,
              "code_sha256": {p: sha(ROOT/p) for p in code},
              "inputs_sha256": {str(p.relative_to(ROOT)): sha(p) for p in [OUT/"specification.json", OUT/"source_semantics_addendum.json",
                                  OUT/"source_manifest_network_retry1.json", PARENT/"replay_manifest.json", PARENT/"selected.parquet"]}}
    (RUN/"implementation.json").write_text(json.dumps(freeze, indent=2)+"\n")
    daily, ledgers, diagnostics = [], [], []
    for cohort in spec["cohorts"]:
        day, symbols = cohort["date"], cohort["symbols"]
        midnight = int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())*1_000_000_000
        native, bn = load_day(ROOT, [f for f in binance["files"] if f["date"] == day], day, midnight, symbols)
        external, by = load_external(ROOT, [f for f in source["files"] if f["date"] == day], day, midnight, symbols)
        diagnostics.append({"date": day, "binance": bn, "bybit": by})
        for rest in spec["rest_seconds"]:
            for name, scenario in SCENARIOS.items():
                rows, outcome = replay_portfolio(native, external, midnight, rest, scenario)
                path = RUN/f"{day}_{rest}s_{name}.jsonl"
                with path.open("x", encoding="utf-8") as stream:
                    for row in rows:
                        stream.write(json.dumps({"date": day, "rest_seconds": rest, "scenario": name, **row}, allow_nan=False)+"\n")
                closed = [r for r in rows if r["status"] == "bounded_complete"]
                fills = [r for r in closed if max(r["buy_quantity_bounds"][1], r["sell_quantity_bounds"][1]) > 0]
                cancels = Counter(r["external_plan"][side]["reason"] for r in rows if "intended_quantity" in r
                                  for side in ("buy", "sell") if r["external_plan"][side]["admitted"])
                outcome.update(date=day, rest_seconds=rest, scenario=name,
                               submitted_cycles=sum("intended_quantity" in r for r in rows), cycles_with_possible_fills=len(fills),
                               definitely_profitable_cycles=sum(r["net_low"] > 1e-10 for r in fills),
                               definitely_losing_cycles=sum(r["net_high"] < -1e-10 for r in fills),
                               cancellation_reasons=dict(cancels), reasons=dict(Counter(r.get("reason", r["status"]) for r in rows)))
                daily.append(outcome)
                ledgers.append({"date": day, "rest_seconds": rest, "scenario": name, "file": path.name, "rows": len(rows), "sha256": sha(path)})
        (RUN/"daily_results.json").write_text(json.dumps(daily, indent=2)+"\n")
        (RUN/"ledger_manifest.json").write_text(json.dumps(ledgers, indent=2)+"\n")
        (RUN/"source_diagnostics.json").write_text(json.dumps(diagnostics, indent=2)+"\n")
        print(json.dumps({"date": day, "external_source": by, "baselines": [{k: x[k] for k in ["rest_seconds", "complete", "net_low", "net_high", "submitted_cycles", "cycles_with_possible_fills"]} for x in daily if x["date"] == day and x["scenario"] == "base"]}), flush=True)
    summaries = []
    for rest in spec["rest_seconds"]:
        for name in SCENARIOS:
            selected = [r for r in daily if (r["rest_seconds"], r["scenario"]) == (rest, name)]
            complete = all(x["complete"] for x in selected)
            summary = {"rest_seconds": rest, "scenario": name, "complete": complete, "complete_dates": sum(x["complete"] for x in selected),
                       "net_low": sum(x["net_low"] for x in selected) if complete else None,
                       "net_high": sum(x["net_high"] for x in selected) if complete else None}
            for key in ("closed_portion_net_low", "closed_portion_net_high", "submitted_cycles", "cycles_with_possible_fills", "definitely_profitable_cycles", "definitely_losing_cycles"):
                summary[key] = sum(x[key] for x in selected)
            for key in ("reasons", "cancellation_reasons"):
                count = Counter()
                for row in selected:
                    count.update(row[key])
                summary[key] = dict(count)
            summaries.append(summary)
    results = {"completed_at_utc": datetime.now(UTC).isoformat(), "configurations_run": 2, "scenario_results": summaries,
               "ledger_files": len(ledgers), "ledger_rows": sum(x["rows"] for x in ledgers),
               "source_native_messages": {v: sum(x[v]["native_messages"] for x in diagnostics) for v in ("binance", "bybit")},
               "independent_accounting_verified": False, "actual_execution_verified": False, "reliable_edge_established": False,
               "selection_2025_opened": False, "conditional_public_tape_model": True,
               "artifacts_sha256": {p: sha(RUN/p) for p in ["implementation.json", "source_diagnostics.json", "daily_results.json", "ledger_manifest.json"]}}
    (RUN/"results.json").write_text(json.dumps(results, indent=2, allow_nan=False)+"\n")
    print(json.dumps({"configurations_run": 2, "summaries": [{k:v for k,v in x.items() if k not in ["reasons", "cancellation_reasons"]} for x in summaries]}), flush=True)


if __name__ == "__main__":
    main()
