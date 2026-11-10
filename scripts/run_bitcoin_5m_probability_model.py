"""Run the frozen BTC v1 research or opt into the repaired exchange model."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from threadpoolctl import threadpool_limits

from research.bitcoin_5m_probability_model import (
    DATA_ROOT,
    METRICS_PATH,
    SPEC_PATH,
    format_report,
    run_experiment,
)
from scripts.run_bitcoin_5m_exchange_model import DEFAULT_OUTPUT, run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--legacy-v1", action="store_true", help="Explicitly select the default v1 model")
    mode.add_argument("--exchange-v2", action="store_true", help="Run the repaired exchange model")
    parser.add_argument("--data-dir", type=Path, help="Legacy v1 price input directory")
    parser.add_argument("--metrics-path", type=Path, help="Legacy v1 derivatives input")
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.exchange_v2:
        if args.data_dir is not None or args.metrics_path is not None:
            parser.error("v2 uses its frozen input manifest")
        if args.output_dir is None:
            parser.error("--exchange-v2 requires a fresh --output-dir")
        with threadpool_limits(limits=4):
            result = run(args.output_dir, args.spec or DEFAULT_OUTPUT / "spec.json")
        print(f"status={result['status']}")
        return 0
    output_dir = args.output_dir or DATA_ROOT
    if any((output_dir / name).exists() for name in ("model.pkl", "panel.parquet", "report.json")):
        parser.error("Preserve existing v1 evidence; pass --output-dir with a new directory")
    report = run_experiment(
        data_root=args.data_dir or DATA_ROOT,
        metrics_path=args.metrics_path or METRICS_PATH,
        spec_path=args.spec or SPEC_PATH,
        output_dir=output_dir,
    )
    print(format_report(report))
    print(f"report={output_dir / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
