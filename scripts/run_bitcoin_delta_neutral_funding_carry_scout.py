"""Run frozen Binance delta-neutral funding-carry scout."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from research.bitcoin_delta_neutral_funding_carry_scout import (
    build_trades,
    evaluate,
    load_inputs,
    load_spec,
    serializable,
)

ROOT = Path("data/parquet/bitcoin_delta_neutral_funding_carry_binance_v1")


def _unlock(partition: str, root: Path) -> None:
    order = ["development", "internal_validation", "final_holdout"]
    for prior in order[: order.index(partition)]:
        path = root / prior / "report.json"
        if not path.exists() or not json.loads(path.read_text(encoding="utf-8")).get("passed"):
            raise RuntimeError(f"{partition} locked: {prior} did not pass")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partition", choices=("development", "internal_validation", "final_holdout"), default="development")
    parser.add_argument("--output-root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.output_root.resolve()
    try:
        _unlock(args.partition, root)
    except RuntimeError as error:
        print(f"BLOCKED: {error}")
        return 2
    spec_path = Path("research_scout/bitcoin_delta_neutral_funding_carry_binance_v1.json")
    spec = load_spec(spec_path)
    bounds = spec["partitions"][args.partition]
    spot, perp, mark, funding = load_inputs()
    try:
        trades = build_trades(
            spot, perp, mark, funding, spec, start=bounds["start"], end=bounds["end"]
        )
    except ValueError as error:
        if "empty carry trades" not in str(error):
            raise
        output = root / args.partition
        output.mkdir(parents=True, exist_ok=True)
        machine = {
            "specification_id": spec["specification_id"],
            "partition": args.partition,
            "partition_bounds": bounds,
            "specification_sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest(),
            "trade_count": 0,
            "passed": False,
            "failure_reason": "no qualifying non-overlapping trades",
        }
        (output / "report.json").write_text(
            json.dumps(machine, indent=2) + "\n", encoding="utf-8"
        )
        text = (
            f"# Bitcoin Delta-Neutral Funding Carry — {args.partition}\n\n"
            "Verdict: **FAIL**\n\nNo qualifying non-overlapping trades.\n"
        )
        (output / "report.md").write_text(text, encoding="utf-8")
        print(text, end="")
        return 1
    result = evaluate(trades, spec)
    machine = serializable(result)
    machine.update({"partition": args.partition, "partition_bounds": bounds, "specification_sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest()})
    output = root / args.partition
    output.mkdir(parents=True, exist_ok=True)
    result["trades"].to_parquet(output / "trades.parquet", index=False)
    (output / "report.json").write_text(json.dumps(machine, indent=2) + "\n", encoding="utf-8")
    lines = [
        f"# Bitcoin Delta-Neutral Funding Carry — {args.partition}",
        "",
        f"Verdict: **{'PASS' if machine['passed'] else 'FAIL'}**",
        "",
        f"Trades: {machine['trade_count']}",
        f"Mean funding P&L: {machine['mean_funding_pnl_bps']:.4f} bps",
        f"Mean basis P&L: {machine['mean_basis_pnl_bps']:.4f} bps",
        f"Mean gross: {machine['mean_gross_bps']:.4f} bps",
        f"Mean conservative: {machine['mean_conservative_bps']:.4f} bps",
        f"Bootstrap 95% conservative: {machine['bootstrap_95_conservative_bps']}",
        "",
        "## Gates",
        "",
        *[f"- {key}: {'PASS' if value else 'FAIL'}" for key, value in machine["gates"].items()],
        "",
        "Later partitions remain locked unless every gate passes unchanged.",
    ]
    text = "\n".join(lines) + "\n"
    (output / "report.md").write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if machine["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
