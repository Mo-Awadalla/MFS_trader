"""Run the frozen Binance BTCUSDT spot–perpetual basis-convergence scout."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from research.bitcoin_spot_perp_basis_convergence_scout import (
    build_daily_panel,
    evaluate_scout,
    load_inputs,
    load_spec,
    serializable_report,
)

OUTPUT_ROOT = Path("data/parquet/bitcoin_spot_perp_basis_convergence_binance_v1")


def _unlock(partition: str, root: Path) -> None:
    order = ["development", "internal_validation", "final_holdout"]
    for prior in order[: order.index(partition)]:
        path = root / prior / "report.json"
        if not path.exists() or not json.loads(path.read_text(encoding="utf-8")).get("passed"):
            raise RuntimeError(f"{partition} locked: {prior} did not pass")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partition", choices=("development", "internal_validation", "final_holdout"), default="development")
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    root = args.output_root.resolve()
    try:
        _unlock(args.partition, root)
    except RuntimeError as error:
        print(f"BLOCKED: {error}")
        return 2
    spec_path = Path("research_scout/bitcoin_spot_perp_basis_convergence_binance_v1.json")
    spec = load_spec(spec_path)
    bounds = spec["partitions"][args.partition]
    spot, perp, funding = load_inputs()
    panel = build_daily_panel(spot, perp, funding, spec, start=bounds["start"], end=bounds["end"])
    report = evaluate_scout(panel, spec)
    machine = serializable_report(report)
    machine.update(
        {
            "partition": args.partition,
            "partition_bounds": bounds,
            "specification_sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest(),
        }
    )
    output = root / args.partition
    output.mkdir(parents=True, exist_ok=True)
    report["panel"].to_parquet(output / "panel.parquet", index=False)
    (output / "report.json").write_text(json.dumps(machine, indent=2) + "\n", encoding="utf-8")
    lines = [
        f"# Bitcoin Spot–Perpetual Basis Convergence — {args.partition}",
        "",
        f"Verdict: **{'PASS' if machine['passed'] else 'FAIL'}**",
        "",
        f"Selected days: {machine['selected_days']}",
        f"Mean basis change: {machine['mean_basis_change_bps']:.4f} bps",
        f"Mean gross capital return: {machine['mean_gross_capital_bps']:.4f} bps",
        f"Mean conservative capital return: {machine['mean_conservative_capital_bps']:.4f} bps",
        f"Bootstrap 95%: {machine['bootstrap_95_gross_bps']}",
        "",
        "## Gates",
        "",
        *[f"- {name}: {'PASS' if value else 'FAIL'}" for name, value in machine["gates"].items()],
        "",
        "Later partitions remain locked unless every gate passes unchanged.",
    ]
    text = "\n".join(lines) + "\n"
    (output / "report.md").write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if machine["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
