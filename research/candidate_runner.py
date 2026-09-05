"""One-command candidate runner.

Usage:
    python -m research.candidate_runner list
    python -m research.candidate_runner run C12_v1_hard_cash
    python -m research.candidate_runner run --family C12_DispersionGated_TSMOM
"""

from __future__ import annotations

import argparse
import importlib
import json
from typing import Any

from research.candidate_registry import REGISTRY, get_candidate


def run_candidate(candidate_id: str) -> dict[str, Any]:
    spec = get_candidate(candidate_id)
    if not spec.runner:
        raise ValueError(f"candidate {candidate_id!r} has no registered runner (status: {spec.status})")
    module_name, function_name = spec.runner.split(":")
    module = importlib.import_module(module_name)
    return getattr(module, function_name)(candidate_id)


def _summary(artifact: dict[str, Any]) -> dict[str, Any]:
    net = artifact.get("net_metrics", {})
    return {
        "candidate": artifact.get("candidate"),
        "verdict": artifact.get("verdict"),
        "promotion_status": artifact.get("promotion_status"),
        "sharpe": net.get("sharpe"),
        "sortino": net.get("sortino"),
        "cagr": net.get("cagr"),
        "max_drawdown": net.get("max_drawdown"),
        "calmar": net.get("calmar"),
        "stability_score": net.get("stability_score"),
        "wfa_pass": artifact.get("wfa_primary", {}).get("strict_wfa_pass"),
        "mc_pass": artifact.get("monte_carlo", {}).get("strict_mc_pass"),
        "dsr_pvalue": artifact.get("dsr", {}).get("pvalue"),
        "gate_on_percentage": artifact.get("gate_diagnostics", {}).get("gate_on_percentage"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run registered research candidates.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List registered candidates.")
    run_parser = subparsers.add_parser("run", help="Run one candidate or a family.")
    run_parser.add_argument("candidate_id", nargs="?", help="Registered candidate id.")
    run_parser.add_argument("--family", help="Run every runnable candidate in a family.")
    args = parser.parse_args()

    if args.command == "list":
        rows = [
            {
                "candidate_id": spec.candidate_id,
                "family": spec.family,
                "status": spec.status,
                "runnable": bool(spec.runner),
                "artifact": spec.artifact_path,
            }
            for spec in REGISTRY.values()
        ]
        print(json.dumps(rows, indent=2))
        return

    if args.family:
        targets = [cid for cid, spec in REGISTRY.items() if spec.family == args.family and spec.runner]
        if not targets:
            raise SystemExit(f"no runnable candidates in family {args.family!r}")
    elif args.candidate_id:
        targets = [args.candidate_id]
    else:
        raise SystemExit("provide a candidate_id or --family")

    summaries = [_summary(run_candidate(candidate_id)) for candidate_id in targets]
    print(json.dumps(summaries if len(summaries) > 1 else summaries[0], indent=2))


if __name__ == "__main__":
    main()
