"""Independently verify the observed no-leader-supply cohort from audited inputs."""

import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

import pandas as pd

from research_scout.prepare_market_lag_20261002 import OUT, PARENT, ROOT, sha


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    impl = json.loads((OUT / "implementation.json").read_text())
    result = json.loads((OUT / "screen_results.json").read_text())
    parent = json.loads((PARENT / "screen_results.json").read_text())
    assert sha(PARENT / "screen_results.json") == spec["parent_results_sha256"]
    assert sha(PARENT / "independent_verification.json") == spec["parent_audit_sha256"]
    assert json.loads((PARENT / "independent_verification.json").read_text())["verified"]
    assert sha(OUT / "specification.json") == impl["specification_sha256"]
    assert sha(OUT / "implementation.json") == result["implementation_sha256"]
    for path, digest in impl["code_sha256"].items():
        assert sha(ROOT / path) == digest
    for name in ("leaders", "targets", "selected"):
        assert sha(OUT / f"{name}.parquet") == result[f"{name}_sha256"]
    saved = pd.read_parquet(OUT / "leaders.parquet").to_dict("records")
    reasons, index, windows = Counter(), 0, []
    maximum_common = D(0)
    for window in parent["windows"]:
        assert sha(ROOT / window["signals_path"]) == window["signals_sha256"]
        frame = pd.read_parquet(ROOT / window["signals_path"])
        major = frame[frame.symbol.isin(["BTCUSDT", "ETHUSDT"])]
        count = 0
        for clock in sorted(frame.decision_ns.unique()):
            pair = major[major.decision_ns == clock].to_dict("records")
            expected = {"date": window["date"], "offset_minutes": window["offset"], "decision_ns": int(clock),
                        "leader_supply": False, "direction": 0, "common_move_bps": None,
                        "reason": "leader_endpoint_spread_or_depth"}
            valid = len(pair) == 2 and {r["symbol"] for r in pair} == {"BTCUSDT", "ETHUSDT"}
            valid = valid and all(r["valid_endpoints"] for r in pair)
            if valid:
                valid = all(D(r["minimum_touch_usdt"]) >= 2000 and D(r["anchor_spread_bps"]) <= 5
                            and D(r["current_spread_bps"]) <= 5 for r in pair)
            if valid:
                values = [D(r[k]) for r in pair for k in ("bid_return_bps", "ask_return_bps")]
                upward, downward = all(v >= 20 for v in values), all(v <= -20 for v in values)
                assert not upward and not downward, "This audit's observed zero-supply path does not handle a positive case"
                common = min(values) if all(v > 0 for v in values) else -max(values) if all(v < 0 for v in values) else D(0)
                maximum_common = max(maximum_common, common)
                expected.update(minimum_return_bps=str(min(values)), maximum_return_bps=str(max(values)),
                                reason="no_coherent_major_move")
            for key, value in expected.items():
                assert saved[index][key] == value, (index, key, saved[index][key], value)
            for key in saved[index].keys() - expected.keys():
                assert pd.isna(saved[index][key]), (index, key)
            reasons[expected["reason"]] += 1
            index += 1
            count += 1
        windows.append({"date": window["date"], "offset": window["offset"], "leader_grids": count,
                        "coherent_leader_grids": 0, "target_rows": 0, "raw_target_candidates": 0, "selected_events": 0})
    assert windows == result["windows"] and dict(reasons) == result["leader_reasons"]
    assert index == len(saved) == result["leader_grids"]
    assert all(result[k] == 0 for k in ("coherent_leader_grids", "target_rows", "raw_target_candidates", "selected_events"))
    assert pd.read_parquet(OUT / "targets.parquet").empty and pd.read_parquet(OUT / "selected.parquet").empty
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(), "source_windows_verified": len(windows),
             "leader_grids_verified": index, "coherent_leader_grids": 0, "selected_events_verified": 0,
             "maximum_coherent_same_direction_move_bps": str(maximum_common), "maximum_numeric_difference": "0",
             "results_sha256": sha(OUT / "screen_results.json"), "auditor_sha256": sha(Path(__file__)),
             "scope": "Independent leader quality and all-four-return predicates on every grid from the hash-verified parent ledgers, whose native clocks/returns were already independently audited. Complete observed zero-supply branch verified; no new raw replay or future-return calculation.",
             "economic_implementations": 0, "selection_2025_opened": False, "reliable_edge_established": False}
    with (OUT / "independent_verification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
