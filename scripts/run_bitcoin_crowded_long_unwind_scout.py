"""Run the frozen Binance BTCUSDT crowded-long unwind scout."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from research.bitcoin_crowded_long_unwind_scout import (
    build_daily_panel,
    evaluate_scout,
    load_inputs,
    load_premium,
    load_spec,
    serializable_report,
)

OUTPUT_ROOT = Path("data/parquet/bitcoin_crowded_long_unwind_binance_v1")


def _spec_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_unlocked(partition: str, output_root: Path) -> None:
    ordering = ["development", "internal_validation", "final_holdout"]
    index = ordering.index(partition)
    for previous in ordering[:index]:
        path = output_root / previous / "report.json"
        if not path.exists():
            raise RuntimeError(f"{partition} locked: missing {previous} report")
        report = json.loads(path.read_text(encoding="utf-8"))
        if not bool(report.get("passed")):
            raise RuntimeError(f"{partition} locked: {previous} did not pass")


def _format_report(report: dict[str, Any], partition: str, spec_hash: str) -> str:
    lines = [
        f"# Bitcoin Crowded-Long Unwind — {partition}",
        "",
        f"Verdict: **{'PASS' if report['passed'] else 'FAIL'}**",
        "",
        "Weak-evidence Binance BTCUSDT perpetual short/flat falsification scout; not a validated Strategy.",
        "",
        f"Specification SHA-256: `{spec_hash}`",
        "",
        "## Primary result",
        "",
        f"- Complete days: {report['days']}",
        f"- Triggered days: {report['selected_days']}",
        f"- Mean gross short return: {report['mean_selected_short_gross_bps']:.4f} bps",
        f"- Mean after fee-only costs: {report['mean_selected_fee_only_bps']:.4f} bps",
        f"- Mean after conservative costs: {report['mean_selected_conservative_bps']:.4f} bps",
        f"- Directional accuracy: {report['short_directional_accuracy']:.4%}",
        f"- Bootstrap 95% gross interval: {report['bootstrap_95_gross_bps']}",
        f"- Chronological halves: {report['chronological_halves_gross_bps']}",
        "",
        "## Controls",
        "",
    ]
    for name, values in report["controls"].items():
        lines.append(
            f"- {name}: days={values['days']}, mean short gross={values['mean_short_gross_bps']:.4f} bps, accuracy={values['short_directional_accuracy']:.4%}"
        )
    lines.extend(["", "## Gates", ""])
    lines.extend(f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in report["gates"].items())
    lines.extend(
        [
            "",
            "## Progression",
            "",
            "Later partitions remain locked unless every gate passes unchanged.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--partition",
        choices=("development", "internal_validation", "final_holdout"),
        default="development",
    )
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    try:
        _require_unlocked(args.partition, output_root)
    except RuntimeError as error:
        print(f"BLOCKED: {error}")
        return 2

    spec_path = Path("research_scout/bitcoin_crowded_long_unwind_binance_v1.json")
    spec = load_spec(spec_path)
    bounds = spec["partitions"][args.partition]
    perp, funding, metrics = load_inputs()
    premium = load_premium()
    panel = build_daily_panel(
        perp,
        funding,
        metrics,
        premium,
        spec,
        start=str(bounds["start"]),
        end=str(bounds["end"]),
    )
    report = evaluate_scout(panel, spec)
    spec_hash = _spec_hash(spec_path)
    machine = serializable_report(report)
    machine["partition"] = args.partition
    machine["partition_bounds"] = bounds
    machine["specification_sha256"] = spec_hash
    machine["data_manifest"] = str(
        Path("data/parquet/binance_bitcoin_derivatives_public_v1/manifest.json").resolve()
    )
    output = output_root / args.partition
    output.mkdir(parents=True, exist_ok=True)
    report["panel"].to_parquet(output / "panel.parquet", index=False)
    (output / "report.json").write_text(json.dumps(machine, indent=2) + "\n", encoding="utf-8")
    (output / "report.md").write_text(
        _format_report(machine, args.partition, spec_hash), encoding="utf-8"
    )
    print(_format_report(machine, args.partition, spec_hash), end="")
    return 0 if bool(machine["passed"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
