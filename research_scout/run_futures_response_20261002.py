"""Replay both predeclared SPY responses, retaining unknown inventory and costs."""

import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal as D

import pandas as pd

from research.futures_response_hft import Account, Tape, plan, replay
from research_scout.prepare_futures_response_20261002 import OUT, PARENT, ROOT, sha


def encode(value):
    if isinstance(value, D):
        return str(value)
    raise TypeError(type(value).__name__)


def save(path, value):
    with path.open("x") as stream:
        stream.write(json.dumps(value, default=encode, allow_nan=False, indent=2)+"\n")


def main():
    run = OUT/"replay_v1"
    run.mkdir(exist_ok=True)
    assert not (run/"results.json").exists()
    spec = json.loads((OUT/"specification.json").read_text())
    assert sha(ROOT/spec["events_path"]) == spec["events_sha256"]
    assert sha(ROOT/spec["quote_manifest_path"]) == spec["quote_manifest_sha256"]
    freeze = {"created_at_utc": datetime.now(UTC).isoformat(), "specification_sha256": sha(OUT/"specification.json"),
              "code_sha256": {p: sha(ROOT/p) for p in ["research_scout/run_futures_response_20261002.py", "research/futures_response_hft.py", "research/same_index_supply.py", "tests/unit/test_futures_response_hft.py"]},
              "events_sha256": spec["events_sha256"], "quote_manifest_sha256": spec["quote_manifest_sha256"],
              "focused_tests_passed": 8, "economic_rules": 2, "scenarios": 12}
    freeze_path = run/"implementation.json"
    if freeze_path.exists():
        prior = json.loads(freeze_path.read_text())
        for key in ("code_sha256", "events_sha256", "quote_manifest_sha256", "specification_sha256"):
            assert prior[key] == freeze[key]
    else:
        save(freeze_path, freeze)
    events = pd.read_parquet(ROOT/spec["events_path"]).sort_values(["date", "decision_ns"]).to_dict("records")
    manifest = json.loads((ROOT/spec["quote_manifest_path"]).read_text())
    tapes, source_for = {}, {}
    for source in manifest["files"]:
        if source["complete"]:
            assert sha(ROOT/source["path"]) == source["sha256"]
            tapes[source["window_id"]] = Tape(pd.read_parquet(ROOT/source["path"]))
        for decision in source["decision_ns"]:
            source_for[(source["date"], decision)] = source
    intents = {}
    for rule in spec["rules"]:
        values = []
        for event in events:
            source = source_for[(event["date"], event["decision_ns"])]
            intent = {"date": event["date"], "decision_ns": event["decision_ns"], "rule": rule, "window_id": source["window_id"]}
            if source["complete"]:
                intent.update(plan(tapes[source["window_id"]], event, rule))
            else:
                intent.update(eligible=False, reason="unknown_source")
            values.append(intent)
        intents[rule] = values
    save(run/"intents.json", intents)
    summaries = []
    for rule in spec["rules"]:
        for scenario in spec["scenarios"]:
            accounts, rows = {}, []
            for event, intent in zip(events, intents[rule], strict=True):
                account = accounts.setdefault(event["date"], Account())
                row = {"date": event["date"], "decision_ns": event["decision_ns"], "rule": rule, "scenario": scenario["name"],
                       "window_id": intent["window_id"], "submitted": False, "status": "predecision_no_order", "reason": intent["reason"],
                       "cash_lower_before": account.lower, "cash_upper_before": account.upper}
                if account.halted:
                    row.update(status="halted_after_unknown_inventory", reason="earlier_same_date_position_unresolved")
                elif intent["reason"] == "unknown_source":
                    row.update(status="unknown_source", reason="missing_source_decision_and_execution")
                    account.book(row)
                elif intent["eligible"]:
                    if intent["capital_reserved"] > account.lower:
                        row["reason"] = "insufficient_known_collateral"
                    else:
                        row.update(replay(tapes[intent["window_id"]], event, intent, scenario), reason="conditional_execution")
                        # If the retrospective entry interval exceeds the full
                        # collateral reserve, acceptance is unresolved.
                        if row["entry_outcome"] == "filled" and row["entry_quotes"]["price_upper"]*intent["quantity"] > account.lower:
                            row.update(status="unknown_entry_collateral", reason="entry_notional_exceeds_known_capital")
                        account.book(row)
                row.update(cash_lower_after=account.lower, cash_upper_after=account.upper, halted_after=account.halted)
                rows.append(row)
            name = f"{rule}_{scenario['name']}.json"
            save(run/name, {"events": rows})
            daily = []
            for date, account in sorted(accounts.items()):
                today = [r for r in rows if r["date"] == date]
                daily.append({"date": date, "complete": not account.halted,
                              "net_lower": account.lower-10000 if not account.halted else None,
                              "net_upper": account.upper-10000 if not account.halted else None,
                              "known_component_lower": account.lower-10000, "known_component_upper": account.upper-10000,
                              "submitted": sum(r["submitted"] for r in today), "outcomes": dict(Counter(r["status"] for r in today))})
            complete = all(d["complete"] for d in daily)
            lower = sum((d["known_component_lower"] for d in daily), D(0))
            upper = sum((d["known_component_upper"] for d in daily), D(0))
            net_dates = sorted((d["net_lower"] for d in daily if d["complete"]), reverse=True)
            priced = [r for r in rows if r["status"] == "conditional_complete"]
            summary = {"rule": rule, "scenario": scenario["name"], "complete": complete, "events": len(rows),
                       "submitted": sum(r["submitted"] for r in rows), "priced_events": len(priced),
                       "positive_lower_events": sum(r["lower"]["net"] > 0 for r in priced),
                       "negative_upper_events": sum(r["upper"]["net"] < 0 for r in priced),
                       "net_lower": lower if complete else None, "net_upper": upper if complete else None,
                       "known_component_lower": lower, "known_component_upper": upper,
                       "drop_best_three_dates_lower": lower-sum(net_dates[:3], D(0)) if complete else None,
                       "outcomes": dict(Counter(r["status"] for r in rows)), "by_date": daily,
                       "ledger": name, "ledger_sha256": sha(run/name)}
            summaries.append(summary)
            print(json.dumps({k: v for k, v in summary.items() if k != "by_date"}, default=encode), flush=True)
    candidates = []
    for rule in spec["rules"]:
        cohort = [r for r in summaries if r["rule"] == rule]
        required = [r for r in cohort if r["scenario"] in ("base", "fees_2x", "adverse_2x", "latency_250ms")]
        if all(r["complete"] and r["net_lower"] > 0 and r["drop_best_three_dates_lower"] > 0 for r in required):
            candidates.append(rule)
    result = {"economic_configurations_run": 2, "scenario_cases": 12, "scenarios": summaries,
              "complete_scenarios": sum(r["complete"] for r in summaries),
              "positive_complete_lower_scenarios": sum(r["complete"] and r["net_lower"] > 0 for r in summaries),
              "candidates_for_later_date_test": candidates, "intents_sha256": sha(run/"intents.json"),
              "implementation_sha256": sha(freeze_path), "parent_source_audit": str((PARENT/"independent_verification.json").relative_to(ROOT)),
              "independent_execution_audit_complete": False, "selection_2024_2025_opened_by_this_family": False,
              "actual_execution_verified": False, "reliable_edge_established": False}
    save(run/"results.json", result)


if __name__ == "__main__":
    main()
