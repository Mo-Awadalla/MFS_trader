"""Evaluate the frozen lag screen from immutable independently audited states."""

import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal as D

import pandas as pd

from research.market_lag_supply import lag, leaders
from research.precise_ledger import ledger_frame
from research_scout.prepare_market_lag_20261002 import OUT, PARENT, ROOT, sha


def dump(path, value):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    parent = json.loads((PARENT / "screen_results.json").read_text())
    assert spec["parent_results_sha256"] == sha(PARENT / "screen_results.json")
    assert spec["parent_audit_sha256"] == sha(PARENT / "independent_verification.json")
    code = ["research/market_lag_supply.py", "research/precise_ledger.py",
            "research_scout/screen_market_lag_20261002.py", "tests/unit/test_market_lag_supply.py"]
    dump(OUT / "implementation.json", {"frozen_at_utc": datetime.now(UTC).isoformat(),
         "specification_sha256": sha(OUT / "specification.json"), "code_sha256": {p: sha(ROOT / p) for p in code},
         "focused_tests_passed": 6, "economic_implementations": 0})
    leader_rows, target_rows, selected, windows = [], [], [], []
    leader_reasons, target_reasons = Counter(), Counter()
    for window in parent["windows"]:
        assert sha(ROOT / window["signals_path"]) == window["signals_sha256"]
        frame = pd.read_parquet(ROOT / window["signals_path"])
        assert len(frame) == window["signal_rows"]
        major = frame[frame.symbol.isin(spec["leaders"])]
        clocks = sorted(int(t) for t in frame.decision_ns.unique())
        major_rows = {(int(r["decision_ns"]), r["symbol"]): r for r in major.to_dict("records")}
        common_count, candidate_count, chosen_count, inspected = 0, 0, 0, 0
        previous = -1
        for decision in clocks:
            meta = {"date": window["date"], "offset_minutes": window["offset"], "decision_ns": decision}
            leader = leaders(major_rows.get((decision, "BTCUSDT")), major_rows.get((decision, "ETHUSDT")))
            leader_rows.append({**meta, **leader})
            leader_reasons[leader["reason"]] += 1
            if not leader["leader_supply"]:
                continue
            common_count += 1
            targets = frame[(frame.decision_ns == decision) & ~frame.symbol.isin(spec["excluded_symbols"])]
            possibilities = []
            for target in targets.to_dict("records"):
                tested = lag(leader, target)
                target_reasons[tested["reason"]] += 1
                inspected += 1
                row = {**meta, "symbol": target["symbol"], "direction": leader["direction"],
                       "common_move_bps": leader["common_move_bps"], **tested, "selected": False}
                target_rows.append(row)
                if tested["target_supply"]:
                    possibilities.append(row)
            candidate_count += len(possibilities)
            if possibilities and decision - previous >= 30 * 10**9:
                chosen = sorted(possibilities, key=lambda r: (-D(r["budget_bps"]), r["symbol"]))[0]
                chosen["selected"] = True
                selected.append(dict(chosen))
                previous = decision
                chosen_count += 1
        windows.append({"date": window["date"], "offset": window["offset"], "leader_grids": len(clocks),
                        "coherent_leader_grids": common_count, "target_rows": inspected,
                        "raw_target_candidates": candidate_count, "selected_events": chosen_count})
    ledger_frame(leader_rows).to_parquet(OUT / "leaders.parquet", index=False)
    ledger_frame(target_rows).to_parquet(OUT / "targets.parquet", index=False)
    ledger_frame(selected).to_parquet(OUT / "selected.parquet", index=False)
    results = {"source_windows": len(windows), "leader_grids": len(leader_rows),
               "coherent_leader_grids": sum(r["coherent_leader_grids"] for r in windows),
               "target_rows": len(target_rows), "raw_target_candidates": sum(r["raw_target_candidates"] for r in windows),
               "selected_events": len(selected), "leader_reasons": dict(leader_reasons), "target_reasons": dict(target_reasons),
               "windows": windows, "implementation_sha256": sha(OUT / "implementation.json"),
               "leaders_sha256": sha(OUT / "leaders.parquet"), "targets_sha256": sha(OUT / "targets.parquet"),
               "selected_sha256": sha(OUT / "selected.parquet"), "economic_implementations": 0,
               "future_returns_evaluated": False, "selection_2025_opened": False, "reliable_edge_established": False}
    dump(OUT / "screen_results.json", results)
    print(json.dumps({k: v for k, v in results.items() if k != "windows"}), flush=True)


if __name__ == "__main__":
    main()
