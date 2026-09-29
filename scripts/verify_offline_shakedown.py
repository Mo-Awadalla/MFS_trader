"""Validate the report emitted by the credential-free MA shakedown.

The checker intentionally uses only the standard library so it can validate a
wheel-installed command from outside a source checkout.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def verify_shakedown(out_dir: Path) -> None:
    """Raise ``SystemExit`` unless the synthetic report proves every scenario."""

    report_path = out_dir / "ma_shakedown_report.json"
    if not report_path.is_file():
        raise SystemExit(f"Missing shakedown JSON report: {report_path}")

    with report_path.open(encoding="utf-8") as report_file:
        report = json.load(report_file)

    if report.get("passed") is not True:
        raise SystemExit(f"Shakedown did not pass: {report.get('blockers', [])}")
    if not (out_dir / "ma_shakedown_report.md").is_file():
        raise SystemExit(f"Missing shakedown Markdown report: {out_dir / 'ma_shakedown_report.md'}")

    scenarios = {scenario.get("name"): scenario for scenario in report.get("scenarios", [])}
    required = {"baseline", "rejection", "timeout", "partial_fill"}
    missing = required.difference(scenarios)
    if missing:
        raise SystemExit(f"Missing shakedown scenarios: {', '.join(sorted(missing))}")

    for name in required:
        if scenarios[name].get("passed") is not True:
            raise SystemExit(f"Scenario did not pass: {name}")

    replay = {name: scenarios[name].get("replay", {}) for name in required}
    if replay["baseline"].get("orders_filled", 0) <= 0:
        raise SystemExit("Baseline scenario did not produce fills.")
    if replay["rejection"].get("orders_rejected", 0) <= 0:
        raise SystemExit("Rejection scenario did not record rejected orders.")
    if replay["timeout"].get("orders_timed_out", 0) <= 0:
        raise SystemExit("Timeout scenario did not record timed-out orders.")

    partial_report = scenarios["partial_fill"].get("operational_report", {})
    partial_states = partial_report.get("order_state_counts", {})
    if partial_states.get("PARTIALLY_FILLED", 0) <= 0:
        raise SystemExit("Partial-fill scenario did not record a partially filled order.")


def main() -> None:
    """Parse arguments and print a concise successful verification result."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("runs/ma_shakedown"))
    args = parser.parse_args()
    verify_shakedown(args.out_dir)
    print(f"Offline MA shakedown verification: PASS ({args.out_dir})")


if __name__ == "__main__":
    main()
