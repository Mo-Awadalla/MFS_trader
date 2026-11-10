"""Independent native reconstruction and causal acquisition-grid alignment."""

import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

import pandas as pd

from research.precise_ledger import ledger_frame
from research_scout.audit_perp_shock_20261002 import compare, verify
from research_scout.prepare_market_lag_native_20261002 import COVERAGE, OUT, ROOT, sha


def check(job):
    source, window = job
    checked = verify(job)
    quotes = pd.read_parquet(ROOT / window["quotes_path"]).to_dict("records")
    metrics = pd.read_parquet(ROOT / window["signals_path"]).to_dict("records")
    indexed = {(r["decision_ns"], r["symbol"]): r for r in quotes}
    marginal = {(r["decision_ns"], r["symbol"]): r for r in metrics}
    maximum, count = D(0), 0
    for saved in window["leader_rows"]:
        decision = saved["decision_ns"]
        expected = {"date": source["date"], "offset_minutes": source["offset"], "decision_ns": decision,
                    "leader_supply": False, "direction": 0, "common_move_bps": None,
                    "reason": "leader_endpoint_spread_or_depth"}
        endpoints = [(indexed[(decision - 10**9, s)], indexed[(decision, s)]) for s in ("BTCUSDT", "ETHUSDT")]
        quality = all(marginal[(decision, s)]["valid_endpoints"] for s in ("BTCUSDT", "ETHUSDT"))
        if quality:
            quality = all(4000 * (D(q["ask"]) - D(q["bid"])) <= D(q["ask"]) + D(q["bid"])
                          and D(q["bid"]) * D(q["bid_quantity"]) >= 2000
                          and D(q["ask"]) * D(q["ask_quantity"]) >= 2000 for pair in endpoints for q in pair)
        if quality:
            differences = [(D(b[k]) - D(a[k]), D(a[k])) for a, b in endpoints for k in ("bid", "ask")]
            up = all(change * 10000 >= 20 * base for change, base in differences)
            down = all(change * 10000 <= -20 * base for change, base in differences)
            direction = 1 if up else -1 if down else 0
            returns = [change * 10000 / base for change, base in differences]
            expected.update(minimum_return_bps=min(returns), maximum_return_bps=max(returns),
                            reason="no_coherent_major_move")
            if direction:
                expected.update(leader_supply=True, direction=direction,
                                common_move_bps=min(direction * r for r in returns), reason="check_target_lags")
                count += 1
        maximum = max(maximum, compare(saved, expected))
    assert count == window["coherent_leader_grids"]
    return {**checked, "coherent_leader_grids": count, "leader_grids": len(window["leader_rows"]),
            "maximum_joint_numeric_difference": str(maximum)}


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    alignment = json.loads((OUT / "causal_selection_specification_v2.json").read_text())
    impl = json.loads((OUT / "implementation.json").read_text())
    result = json.loads((OUT / "screen_results.json").read_text())
    sources = json.loads((OUT / "source_manifest.json").read_text())
    assert sources["complete"] and sha(OUT / "specification.json") == impl["specification_sha256"] == alignment["parent_native_specification_sha256"]
    assert sha(OUT / "source_manifest.json") == impl["source_manifest_sha256"]
    assert sha(OUT / "implementation.json") == result["implementation_sha256"]
    assert sha(COVERAGE / "screen_results.json") == alignment["coverage_results_sha256"] == spec["coverage_results_sha256"]
    assert sha(COVERAGE / "independent_verification.json") == spec["coverage_audit_sha256"]
    helper = ROOT / "research_scout/audit_perp_shock_20261002.py"
    old_audit = json.loads((ROOT / "research_scout/perp_shock_hft_20261002/independent_verification.json").read_text())
    assert sha(helper) == old_audit["auditor_sha256"]
    for path, digest in impl["code_sha256"].items():
        assert sha(ROOT / path) == digest
    indexed = {(r["date"], r["offset"]): r for r in sources["files"]}
    jobs = [(indexed[(w["date"], w["offset"])], w) for w in result["windows"]]
    verified, counts = [], Counter()
    with ProcessPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(check, job) for job in jobs]):
            row = future.result()
            verified.append(row)
            counts.update(row["source_counts"])
            print(json.dumps({k: row[k] for k in ("date", "offset", "coherent_leader_grids")}), flush=True)
    assert dict(counts) == result["source_counts"]
    assert sum(r["coherent_leader_grids"] for r in verified) == result["coherent_leader_grids"]
    leaders = [r for w in result["windows"] for r in w["leader_rows"]]
    assert sha(OUT / "leaders.parquet") == result["leaders_sha256"]
    actual = pd.read_parquet(OUT / "leaders.parquet").to_dict("records")
    assert len(actual) == len(leaders)
    for a, b in zip(actual, leaders, strict=True):
        for key, value in b.items():
            if value is None:
                assert pd.isna(a[key])
                a[key] = None
        compare(a, b)
    selected = [r for r in leaders if r["leader_supply"]]
    assert sha(OUT / "selected_leader_grids.parquet") == result["selected_leader_grids_sha256"]
    assert pd.read_parquet(OUT / "selected_leader_grids.parquet").to_dict("records") == selected
    coverage = json.loads((COVERAGE / "screen_results.json").read_text())
    eligible_clocks = set()
    for window in coverage["windows"]:
        assert sha(ROOT / window["candidate_path"]) == window["candidate_sha256"]
        for row in pd.read_parquet(ROOT / window["candidate_path"]).to_dict("records"):
            eligible_clocks.add((row["date"], row["offset_minutes"], row["decision_ns"]))
    admitted = [r for r in selected if (r["date"], r["offset_minutes"], r["decision_ns"]) in eligible_clocks]
    path = OUT / "admitted_leader_grids.parquet"
    ledger_frame(admitted).to_parquet(path, index=False)
    target_jobs = [{"date": day, "offset": offset} for day, offset in sorted({(r["date"], r["offset_minutes"]) for r in admitted})]
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
             "source_files_verified": len(verified), "source_counts": dict(counts),
             "quote_rows_verified": sum(r["quote_rows"] for r in verified),
             "marginal_signal_rows_verified": sum(r["signal_rows"] for r in verified),
             "leader_grids_verified": sum(r["leader_grids"] for r in verified),
             "diagnostic_coherent_grids": len(selected), "causally_admitted_leader_grids": len(admitted),
             "excluded_by_causal_alignment": len(selected) - len(admitted), "target_acquisition_jobs": target_jobs,
             "admitted_leader_grids_sha256": sha(path),
             "causal_selection_specification_sha256": sha(OUT / "causal_selection_specification_v2.json"),
             "maximum_joint_numeric_difference": str(max(D(r["maximum_joint_numeric_difference"]) for r in verified)),
             "results_sha256": sha(OUT / "screen_results.json"), "auditor_sha256": sha(Path(__file__)),
             "independent_raw_reconstruction_helper_sha256": sha(helper),
             "audit_comparison_repair": "First audit completed all native/joint checks but the final Parquet comparison rejected NaN versus JSON None for absent common_move_bps. Only missing-value comparison was normalized; no source, rule, numeric value or result changed.",
             "scope": "Independent full native clock-bucket reconstruction reused from the frozen audited helper; every quote/marginal return/quality predicate, direct cross-product joint-leader gate and exact normalized acquisition-grid alignment verified. No production parser or signal calculation called by the audit. Ledger writer is serialization only.",
             "target_eligibility_tested": False, "economic_implementations": 0,
             "future_returns_evaluated": False, "reliable_edge_established": False}
    with (OUT / "independent_verification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
