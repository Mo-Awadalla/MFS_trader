"""Run the frozen Binance-signal/Coinbase-spot Bitcoin reversal scout."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from research.bitcoin_binance_capitulation_coinbase_spot_scout import (
    attach_coinbase_execution,
    build_binance_signal_panel,
    evaluate_cross_venue_scout,
    load_binance_inputs,
    load_spec,
)

SPEC_PATH = Path("research_scout/bitcoin_binance_capitulation_coinbase_spot_v1.json")
OUTPUT_ROOT = Path("data/parquet/bitcoin_binance_capitulation_coinbase_spot_v1")


def _require_unlocked(partition: str, output_root: Path) -> None:
    ordering = ["development", "internal_validation", "final_holdout"]
    index = ordering.index(partition)
    for previous in ordering[:index]:
        report_path = output_root / previous / "report.json"
        if not report_path.exists():
            raise RuntimeError(f"{partition} locked: missing {previous} report")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if not bool(report.get("passed")):
            raise RuntimeError(f"{partition} locked: {previous} did not pass")


def _format_report(report: dict[str, Any]) -> str:
    verdict = "PASS" if report["passed"] else "FAIL"
    lines = [
        f"# Binance Capitulation Signal → Coinbase BTC-USD Spot — {report['partition']}",
        "",
        f"Verdict: **{verdict}**",
        "",
        "Cross-venue falsification scout; not a validated Strategy or trading authorization.",
        "",
        f"Specification SHA-256: `{report['specification_sha256']}`",
        "",
        "## Results",
        "",
        f"- Complete Binance funding events: {report['signal_complete_events']}",
        f"- Binance selected events: {report['binance_selected_events']}",
        f"- Coinbase executed trades: {report['coinbase_executed_trades']}",
        f"- Coinbase exclusions: {report['coinbase_exclusions']}",
        f"- Mean gross trade return: {report['mean_gross_trade_bps']:.4f} bps",
        f"- Mean after fee-only costs: {report['mean_fee_only_trade_bps']:.4f} bps",
        f"- Mean after conservative costs: {report['mean_conservative_trade_bps']:.4f} bps",
        f"- Gross directional accuracy: {report['gross_directional_accuracy']:.4%}",
        f"- Chronological gross halves: {report['chronological_halves_gross_bps']}",
        f"- Bootstrap 95% conservative interval: {report['bootstrap_95_conservative_bps']}",
        f"- Active calendar years: {report['active_calendar_years']}",
        f"- Exit reasons: {report['exit_reasons']}",
        f"- Gross total return on 5% capital sleeve: {report['gross_total_capital_return']:.4%}",
        f"- Conservative total return on 5% capital sleeve: {report['conservative_total_capital_return']:.4%}",
        "",
        "## Gates",
        "",
    ]
    lines.extend(f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in report["gates"].items())
    lines.extend(
        [
            "",
            "## Progression",
            "",
            "Later partitions remain locked unless every development gate passes unchanged.",
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

    spec = load_spec(SPEC_PATH)
    bounds = spec["partitions"][args.partition]
    funding, metrics, perp, spot = load_binance_inputs()
    signal_panel = build_binance_signal_panel(
        funding,
        metrics,
        perp,
        spot,
        spec,
        start=str(bounds["start"]),
        end=str(bounds["end"]),
    )
    output = output_root / args.partition
    output.mkdir(parents=True, exist_ok=True)
    signal_panel.to_parquet(output / "binance_signal_panel.parquet", index=False)
    transfer_panel, sources = attach_coinbase_execution(
        signal_panel,
        spec,
        output_root / "coinbase_btc_usd_5m_cache",
    )
    transfer_panel.to_parquet(output / "coinbase_execution_panel.parquet", index=False)
    report = evaluate_cross_venue_scout(signal_panel, transfer_panel, spec)
    report["partition"] = args.partition
    report["partition_bounds"] = bounds
    report["specification_sha256"] = hashlib.sha256(SPEC_PATH.read_bytes()).hexdigest()
    report["binance_manifest"] = str(
        Path("data/parquet/binance_bitcoin_derivatives_public_v1/manifest.json").resolve()
    )
    report["coinbase_sources"] = sources
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=True) + "\n", encoding="utf-8")
    human = _format_report(report)
    (output / "report.md").write_text(human, encoding="utf-8")
    print(human, end="")
    return 0 if bool(report["passed"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
