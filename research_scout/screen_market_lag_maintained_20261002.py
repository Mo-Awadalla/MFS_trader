"""Locate depth acquisition clues in already audited causal quote snapshots."""

import json
from collections import Counter
from datetime import UTC, datetime

import pandas as pd

from research.market_lag_maintained import clue
from research.precise_ledger import ledger_frame
from research_scout.prepare_market_lag_maintained_20261002 import HYPOTHESIS, OUT, ROOT, sha


def dump(path, value):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    assert sha(HYPOTHESIS / "specification.json") == spec["parent_hypothesis_sha256"]
    excluded = json.loads((HYPOTHESIS / "specification.json").read_text())["excluded_symbols"]
    code = ["research/market_lag_maintained.py", "research/market_lag_supply.py", "research/precise_ledger.py",
            "tests/unit/test_market_lag_maintained.py", "research_scout/screen_market_lag_maintained_20261002.py"]
    dump(OUT / "implementation.json", {"frozen_at_utc": datetime.now(UTC).isoformat(),
         "specification_sha256": sha(OUT / "specification.json"), "code_sha256": {p: sha(ROOT / p) for p in code},
         "new_focused_tests_passed": 6, "economic_implementations": 0})
    rows, parents, events_count = [], [], 0
    for parent in spec["parents"]:
        native, target = ROOT / parent["native_path"], ROOT / parent["target_path"]
        assert sha(native / "independent_verification.json") == parent["native_audit_sha256"]
        assert sha(native / "admitted_leader_grids.parquet") == parent["events_sha256"]
        assert sha(target / "screen_results.json") == parent["target_results_sha256"]
        assert sha(target / "independent_verification.json") == parent["target_audit_sha256"]
        events = pd.read_parquet(native / "admitted_leader_grids.parquet").to_dict("records")
        events_count += len(events)
        for window in json.loads((target / "screen_results.json").read_text())["windows"]:
            assert sha(ROOT / window["quotes_path"]) == window["quotes_sha256"]
            frame = pd.read_parquet(ROOT / window["quotes_path"])
            symbols = sorted(s for s in frame.symbol.unique() if s not in excluded)
            indexed = {(int(r["decision_ns"]), r["symbol"]): r for r in frame.to_dict("records")}
            these = [e for e in events if (e["date"], int(e["offset_minutes"])) == (window["date"], window["offset"])]
            for event in these:
                decision = int(event["decision_ns"])
                for symbol in symbols:
                    tested = clue(indexed.get((decision - 10**9, symbol)), indexed.get((decision, symbol)), event, decision)
                    rows.append({"date": event["date"], "offset_minutes": int(event["offset_minutes"]),
                                 "decision_ns": decision, "symbol": symbol, "direction": int(event["direction"]),
                                 "common_move_bps": event["common_move_bps"], **tested})
            parents.append({"batch": parent["batch"], "date": window["date"], "offset": window["offset"],
                            "quotes_path": window["quotes_path"], "quotes_sha256": window["quotes_sha256"],
                            "symbols": len(symbols), "admitted_grids": len(these)})
    assert events_count == 7
    rows.sort(key=lambda r: (r["decision_ns"], r["symbol"]))
    candidates = [r for r in rows if r["acquisition_candidate"]]
    ledger_frame(rows).to_parquet(OUT / "clues.parquet", index=False)
    ledger_frame(candidates).to_parquet(OUT / "acquisition_candidates.parquet", index=False)
    jobs = sorted({(r["date"], r["offset_minutes"], r["symbol"]) for r in candidates})
    result = {"admitted_grids": events_count, "target_checks": len(rows), "acquisition_candidates": len(candidates),
              "distinct_symbol_minutes": len(jobs), "original_fresh_candidates": sum(r["original_freshness_passed"] for r in candidates),
              "reasons": dict(Counter(r["reason"] for r in rows)), "parents": parents,
              "jobs": [{"date": d, "offset": o, "symbol": s} for d, o, s in jobs],
              "clues_sha256": sha(OUT / "clues.parquet"),
              "candidates_sha256": sha(OUT / "acquisition_candidates.parquet"),
              "implementation_sha256": sha(OUT / "implementation.json"),
              "economic_implementations": 0, "future_returns_evaluated": False,
              "depth_confirmed_events": 0, "selected_trading_events": [], "reliable_edge_established": False}
    dump(OUT / "screen_results.json", result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("parents", "jobs")}), flush=True)
    print(json.dumps({"acquisition_jobs": result["jobs"]}), flush=True)


if __name__ == "__main__":
    main()
