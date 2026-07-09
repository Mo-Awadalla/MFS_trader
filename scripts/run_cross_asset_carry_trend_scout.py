"""Run the one frozen public-data cross-asset carry/trend scout."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.cross_asset_carry_trend_report import run_scout  # noqa: E402
from research.cross_asset_carry_trend_scout import (  # noqa: E402
    SOURCE_COMMIT,
    CrossAssetCarryTrendScoutReport,
    load_public_panels,
)

DEFAULT_DATA_DIR = (
    ROOT / "external_artifacts" / "pysystemtrade_futures_data" / SOURCE_COMMIT[:12]
)
DEFAULT_SPY_PATH = ROOT / "data" / "parquet" / "equity" / "yahoo_chart" / "SPY_1d.parquet"
DEFAULT_JSON_PATH = ROOT / "docs" / "reports" / "cross_asset_carry_trend_scout.json"
DEFAULT_MD_PATH = ROOT / "docs" / "reports" / "cross_asset_carry_trend_scout.md"


def _load_spy_close(path: Path) -> pd.Series:
    frame = pd.read_parquet(path)
    required = {"timestamp", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"SPY cache is missing columns: {sorted(missing)}")
    timestamp = pd.to_datetime(frame["timestamp"], utc=True).dt.tz_localize(None).dt.normalize()
    close = pd.Series(pd.to_numeric(frame["close"], errors="coerce").to_numpy(), index=timestamp)
    return close.loc[~close.index.duplicated(keep="last")].sort_index()


def _metric_table(
    rows: list[tuple[str, dict[str, Any]]],
) -> list[str]:
    result = [
        "| Path | Total return | Ann. arithmetic | CAGR | Sharpe | Sortino | Ann. vol | Max drawdown | Final equity |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, metrics in rows:
        result.append(
            f"| {label} | {metrics['total_return']:.2%} | "
            f"{metrics['annualized_return']:.2%} | {metrics['cagr']:.2%} | "
            f"{metrics['sharpe']:.4f} | {metrics['sortino']:.4f} | "
            f"{metrics['ann_volatility']:.2%} | {metrics['max_drawdown']:.2%} | "
            f"{metrics['final_equity']:.4f} |"
        )
    return result


def _asset_class_table(report: CrossAssetCarryTrendScoutReport) -> list[str]:
    result = [
        "| Asset class | Gross P&L | Default-net P&L | Gross return contribution | Net return contribution |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    diagnostics = report.asset_class_diagnostics
    for asset_class, metrics in diagnostics["metrics"].items():
        result.append(
            f"| {asset_class} | {diagnostics['gross_pnl'][asset_class]:.2%} | "
            f"{diagnostics['default_net_pnl'][asset_class]:.2%} | "
            f"{metrics['gross']['total_return']:.2%} | "
            f"{metrics['default_net']['total_return']:.2%} |"
        )
    return result


def format_report(report: CrossAssetCarryTrendScoutReport) -> str:
    component_rows: list[tuple[str, dict[str, Any]]] = []
    for component in ("carry", "trend", "combined"):
        component_rows.extend(
            [
                (f"{component} gross", report.component_metrics[component]["gross"]),
                (
                    f"{component} net ({report.params['default_cost_bps']:.1f} bps)",
                    report.component_metrics[component]["default_net"],
                ),
            ]
        )
    benchmark_rows = [("SPY", report.spy_metrics)] + [
        (name.replace("_", " "), metrics) for name, metrics in report.overlay_metrics.items()
    ]
    subperiod_rows = list(report.subperiod_metrics.items())
    cost_rows = [(f"combined {bps} bps", metrics) for bps, metrics in report.cost_sensitivity_bps.items()]
    leave_out_rows = [
        (f"without {asset_class}", metrics)
        for asset_class, metrics in report.leave_one_asset_class_out.items()
    ]

    lines = [
        "# Cross-Asset Carry + Trend Public-Data Scout v1",
        "",
        f"**Verdict: {'PASS' if report.scout_passed else 'FAIL'}**",
        "",
        "This is a frozen falsification scout using curated public pysystemtrade data. It is not validation or trading approval.",
        "",
        "## Inputs",
        "",
        f"- Source commit: `{report.source_commit}`",
        f"- Analysis: {report.analysis_start} through {report.analysis_end}",
        "- Universe: 15 predeclared futures markets across six asset classes",
        "- Primary signal: equal-weight carry sign plus 12-month trend sign",
        f"- Target volatility: {report.params['target_volatility']:.1%}",
        f"- Default one-way cost: {report.params['default_cost_bps']:.1f} bps",
        f"- Execution lag: {report.params['execution_lag_sessions']} common sessions",
        "",
        "## Component attribution",
        "",
        *_metric_table(component_rows),
        "",
        "## Frozen subperiods",
        "",
        *_metric_table(subperiod_rows),
        "",
        "## Cost sensitivity",
        "",
        *_metric_table(cost_rows),
        "",
        "## Asset-class contributions",
        "",
        *_asset_class_table(report),
        "",
        "## Leave-one-asset-class-out",
        "",
        *_metric_table(leave_out_rows),
        "",
        "## SPY utility",
        "",
        *_metric_table(benchmark_rows),
        "",
        "## Portfolio diagnostics",
        "",
    ]
    for key, value in report.portfolio_diagnostics.items():
        lines.append(f"- {key}: `{value:.6f}`")
    lines.extend(
        [
            f"- largest_absolute_gross_asset_class_pnl_share: `{report.asset_class_diagnostics['largest_absolute_gross_pnl_share']:.2%}`",
            f"- best_12_positive_month_pnl_share: `{report.monthly_concentration['best_12_positive_pnl_share']:.2%}`",
            "",
            "## Frozen hard gates",
            "",
        ]
    )
    for name, passed in report.gates.items():
        lines.append(f"- [{'x' if passed else ' '}] {name}")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {limitation}" for limitation in report.limitations)
    lines.extend(
        [
            "",
            "## Decision rule",
            "",
            "A FAIL rejects this exact construction without parameter rescue. A PASS only permits a five-market raw-contract replication; it does not permit paper or live trading.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--spy-path", type=Path, default=DEFAULT_SPY_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MD_PATH)
    args = parser.parse_args()

    panels = load_public_panels(args.data_dir)
    spy_close = _load_spy_close(args.spy_path)
    report = run_scout(panels, spy_close)

    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(format_report(report), encoding="utf-8")

    combined = report.component_metrics["combined"]["default_net"]
    print(f"verdict={'PASS' if report.scout_passed else 'FAIL'}")
    print(f"combined_net_total_return={combined['total_return']:.6f}")
    print(f"combined_net_sharpe={combined['sharpe']:.6f}")
    print(f"json={args.json_output.resolve()}")
    print(f"markdown={args.markdown_output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
