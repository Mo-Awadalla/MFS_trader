"""Offline corrected-evidence inspection and explicit unavailable declarations."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from experiments.artifacts import ArtifactError
from experiments.corrected_evaluations import (
    abandon_corrected_evaluation,
    check_current_qualification,
    evaluate_corrected,
)
from experiments.models import ExperimentNotFoundError
from experiments.registry import ExperimentRegistry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-root", required=True)
    parser.add_argument("--uuid", required=True)
    parser.add_argument("--hash", required=True, dest="expected_hash")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="Check current numerical qualification; never promote")
    unavailable = commands.add_parser("unavailable", help="Record missing prerequisites in a new immutable version")
    unavailable.add_argument("--evaluation-id", required=True, help="New canonical UUID; attempts cannot be retried")
    unavailable.add_argument("--reason", required=True)
    abandon = commands.add_parser("abandon", help="Append an interrupted-attempt disposition; never qualify")
    abandon.add_argument("--evaluation-id", required=True)
    abandon.add_argument("--operator", required=True)
    abandon.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    registry = ExperimentRegistry(args.experiment_root)
    try:
        if args.command == "abandon":
            path = abandon_corrected_evaluation(
                registry, args.uuid, args.expected_hash, evaluation_id=args.evaluation_id,
                operator=args.operator, reason=args.reason,
            )
            print(json.dumps({"artifact": str(path), "status": "requiring_re_evaluation"}))
            return 1
        if args.command == "unavailable":
            path = evaluate_corrected(
                registry, args.uuid, args.expected_hash, evaluation_id=args.evaluation_id,
                unavailable_reason=args.reason,
            )
            print(json.dumps({"artifact": str(path), "status": "requiring_re_evaluation"}))
            return 1
        result = check_current_qualification(registry, args.uuid, args.expected_hash)
        print(json.dumps(asdict(result), sort_keys=True))
        return 0 if result.qualified else 1
    except (ArtifactError, ExperimentNotFoundError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        registry.close()


if __name__ == "__main__":
    raise SystemExit(main())
