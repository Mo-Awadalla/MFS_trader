"""Run the frozen BTC five-minute probability-model experiment."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.bitcoin_5m_probability_model import (
    DATA_ROOT,
    METRICS_PATH,
    SPEC_PATH,
    format_report,
    run_experiment,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_ROOT)
    parser.add_argument("--metrics-path", type=Path, default=METRICS_PATH)
    parser.add_argument("--spec", type=Path, default=SPEC_PATH)
    parser.add_argument("--output-dir", type=Path, default=DATA_ROOT)
    args = parser.parse_args()
    report = run_experiment(
        data_root=args.data_dir,
        metrics_path=args.metrics_path,
        spec_path=args.spec,
        output_dir=args.output_dir,
    )
    print(format_report(report))
    print(f"report={args.output_dir / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
