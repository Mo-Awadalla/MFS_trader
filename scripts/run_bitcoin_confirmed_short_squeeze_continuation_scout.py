"""Run the frozen BTC confirmed short-squeeze continuation research scout."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from research.bitcoin_confirmed_short_squeeze_continuation_scout import (
    apply_analogue_model,
    audit_inputs,
    build_decision_panel,
    evaluate_partition,
    load_inputs,
    load_spec,
    serializable_report,
)

SPEC_PATH = Path("research_scout/bitcoin_confirmed_short_squeeze_continuation_v1.json")
HASH_PATH = Path("research_scout/bitcoin_confirmed_short_squeeze_continuation_v1.sha256")
OUTPUT_ROOT = Path("data/parquet/bitcoin_confirmed_short_squeeze_continuation_v1")


def specification_hash(path: Path = SPEC_PATH) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_frozen_spec() -> str:
    actual = specification_hash()
    if not HASH_PATH.exists():
        raise RuntimeError(f"missing frozen specification hash: {HASH_PATH}")
    expected = HASH_PATH.read_text(encoding="utf-8").strip().split()[0]
    if actual != expected:
        raise RuntimeError(
            "specification hash mismatch; freeze and document a new trial instead of "
            "evaluating a modified specification"
        )
    return actual


def require_unlocked(partition: str, output_root: Path) -> None:
    ordering = ["development", "internal_validation", "final_holdout"]
    for previous in ordering[: ordering.index(partition)]:
        report_path = output_root / previous / "report.json"
        if not report_path.exists():
            raise RuntimeError(f"{partition} locked: missing {previous} report")
        previous_report = json.loads(report_path.read_text(encoding="utf-8"))
        if not bool(previous_report.get("passed")):
            raise RuntimeError(f"{partition} locked: {previous} did not pass")


def _format_feasibility(report: dict[str, Any], spec_hash: str) -> str:
    counts = report["candidate_counts"]
    lines = [
        "# BTC Confirmed Short-Squeeze Continuation v1 — Feasibility",
        "",
        "This report audits point-in-time feature availability only. It does not inspect "
        "forward returns or authorize trading.",
        "",
        f"Specification SHA-256: `{spec_hash}`",
        "",
        f"- Complete point-in-time decisions: {counts['complete_decisions']}",
        f"- Rolling-normalization-ready decisions: {counts['rolling_ready']}",
        f"- Stage-1 candidates: {counts['stage_1']}",
        f"- Stage-2 candidates: {counts['stage_2']}",
        f"- Timestamp alignment valid: {report['timestamp_alignment_valid']}",
        "",
        "## Input coverage",
        "",
    ]
    for name, values in report["input_audit"].items():
        lines.append(
            f"- {name}: rows={values['rows']}, {values['start']} through {values['end']}, "
            f"duplicate timestamps={values['duplicate_timestamps']}"
        )
    return "\n".join(lines) + "\n"


def _format_evaluation(report: dict[str, Any], spec_hash: str) -> str:
    ordinary = report["ordinary"]
    counts = report["candidate_counts"]
    lines = [
        f"# BTC Confirmed Short-Squeeze Continuation v1 — {report['partition']}",
        "",
        f"Verdict: **{'PASS' if report['passed'] else 'FAIL'}**",
        "",
        "Frozen Binance-only BTCUSDT spot research scout; not approved for paper or live trading.",
        "",
        f"Specification SHA-256: `{spec_hash}`",
        "",
        "## Candidate funnel",
        "",
        f"- Complete decisions: {counts['complete_decisions']}",
        f"- Stage 1: {counts['stage_1']}",
        f"- Stage 2: {counts['stage_2']}",
        f"- Analogue pass: {counts['analogue_pass']}",
        f"- Completed trades after throttle: {counts['completed_trades_after_24h_throttle']}",
        "",
        "## Performance",
        "",
        f"- Mean gross instrument return: {ordinary['mean_gross_bps']} bps",
        f"- Mean net instrument return: {ordinary['mean_net_bps']} bps",
        f"- Hit rate: {ordinary['hit_rate']}",
        f"- Profit factor: {ordinary['profit_factor']}",
        f"- Compounded portfolio return: {ordinary['compounded_return']}",
        f"- Maximum drawdown: {ordinary['maximum_drawdown']}",
        f"- Event-bootstrap 95% net interval: {report['event_bootstrap_95_net_bps']} bps",
        "",
        "## Progression gates",
        "",
    ]
    lines.extend(
        f"- {'PASS' if passed else 'FAIL'} — {name}" for name, passed in report["gates"].items()
    )
    lines.extend(
        [
            "",
            "Later partitions remain locked unless every gate passes unchanged.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_once(path: Path, content: str) -> None:
    if path.exists():
        raise RuntimeError(f"immutable output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("feasibility", "evaluate"), default="feasibility")
    parser.add_argument(
        "--partition",
        choices=("development", "internal_validation", "final_holdout"),
        default="development",
    )
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()

    try:
        spec_hash = require_frozen_spec()
        output_root = args.output_root.resolve()
        if args.mode == "evaluate":
            require_unlocked(args.partition, output_root)
    except RuntimeError as error:
        print(f"BLOCKED: {error}")
        return 2

    spec = load_spec()
    spot, metrics, funding, premium = load_inputs(spec)
    audit = audit_inputs(spot, metrics, funding, premium)
    earliest = str(spec["partitions"]["development"]["start"])
    latest = str(spec["partitions"]["final_holdout"]["end"])

    if args.mode == "feasibility":
        panel = build_decision_panel(
            spot,
            metrics,
            funding,
            premium,
            spec,
            start=earliest,
            end=latest,
            include_outcomes=False,
        )
        report = {
            "specification_id": spec["specification_id"],
            "specification_sha256": spec_hash,
            "mode": "non_return_feasibility",
            "input_audit": audit,
            "candidate_counts": {
                "complete_decisions": int(len(panel)),
                "rolling_ready": int(
                    (
                        panel["rolling_observations"]
                        >= int(spec["rolling"]["minimum_prior_decisions"])
                    ).sum()
                ),
                "stage_1": int(panel["stage_1"].sum()),
                "stage_2": int(panel["stage_2"].sum()),
            },
            "timestamp_alignment_valid": bool(panel["timestamp_alignment_valid"].all()),
        }
        output = output_root / "feasibility"
        _write_once(output / "report.json", json.dumps(report, indent=2) + "\n")
        _write_once(output / "report.md", _format_feasibility(report, spec_hash))
        panel.drop(columns=["entry_open", "forward_gross_return_6h"], errors="ignore").to_parquet(
            output / "feature_panel.parquet", index=False
        )
        print(_format_feasibility(report, spec_hash), end="")
        return 0

    panel = build_decision_panel(
        spot,
        metrics,
        funding,
        premium,
        spec,
        start=earliest,
        end=latest,
        include_outcomes=True,
    )
    panel = apply_analogue_model(panel, spec)
    report = evaluate_partition(panel, spot, spec, partition=args.partition)
    machine = serializable_report(report)
    machine["specification_sha256"] = spec_hash
    machine["input_audit"] = audit
    output = output_root / args.partition
    if output.exists():
        raise RuntimeError(f"immutable partition output already exists: {output}")
    output.mkdir(parents=True)
    report["panel"].to_parquet(output / "panel.parquet", index=False)
    report["trades"].to_parquet(output / "trades.parquet", index=False)
    (output / "report.json").write_text(json.dumps(machine, indent=2) + "\n", encoding="utf-8")
    (output / "report.md").write_text(_format_evaluation(machine, spec_hash), encoding="utf-8")
    print(_format_evaluation(machine, spec_hash), end="")
    return 0 if bool(machine["passed"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
