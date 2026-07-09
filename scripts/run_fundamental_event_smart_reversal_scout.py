"""Run the frozen FundamentalEventSmartReversal v1 research scout.

This script uses cached Alpaca SIP daily bars and cached official SEC filing
events. It writes descriptive scout evidence only and never creates or promotes
an Experiment through the currently known-flawed Validation Gauntlet.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.sec_filings import build_event_flag_matrix
from research.csmr_data import load_csmr_panel
from research.fundamental_event_smart_reversal_pipeline import (
    FundamentalEventSmartReversalScoutReport,
    run_scout,
)
from research.universes.residual_reversal_v1 import stock_symbols
from storage.parquet_io import parquet_path

DEFAULT_EVENTS = Path("data/parquet/sec_filings/sec_filing_events.parquet")
DEFAULT_OUTPUT_JSON = Path("docs/reports/fundamental_event_smart_reversal_scout.json")
DEFAULT_OUTPUT_MD = Path("docs/reports/fundamental_event_smart_reversal_scout.md")
STORAGE_DIR = Path("data/parquet/equity")
SOURCE = "alpaca_sip"
FREQUENCY = "1d"
BENCHMARK = "SPY"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run frozen SEC-event-veto smart-reversal scout on cached data"
    )
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end")
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    args = parser.parse_args()

    if not args.events.exists():
        parser.error(
            f"missing SEC event cache {args.events}; run scripts/download_sec_filing_events.py first"
        )

    symbols = stock_symbols() + (BENCHMARK,)
    paths = [parquet_path(STORAGE_DIR, symbol, FREQUENCY, source=SOURCE) for symbol in symbols]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        parser.error(f"missing {len(missing)} cached Alpaca SIP daily files")

    panel = load_csmr_panel(
        paths,
        start=args.start,
        end=_inclusive_end_timestamp(args.end),
        normalize_daily_index=True,
    )
    events = pd.read_parquet(args.events)
    flags = build_event_flag_matrix(events, panel.index, symbols=symbols)
    panel = _attach_event_flags(panel, flags)

    report = run_scout(panel)
    report.event_diagnostics["normalized_event_rows"] = int(len(events))
    report.event_diagnostics["unique_issuer_filings"] = int(
        len(events.drop_duplicates(["cik", "accession_number"]))
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.output_md.write_text(format_report(report), encoding="utf-8")

    print(f"panel_shape={panel.shape}")
    print(f"panel_start={panel.index.min()} panel_end={panel.index.max()}")
    print(f"normalized_event_rows={report.event_diagnostics['normalized_event_rows']}")
    print(
        "filing_flagged_symbol_sessions="
        f"{report.event_diagnostics['filing_flagged_symbol_sessions']}"
    )
    print(f"scout_passed={report.scout_passed}")
    print(f"gross_sharpe={report.gross_metrics.get('sharpe', 0.0):.4f}")
    print(f"default_net_sharpe={report.default_net_metrics.get('sharpe', 0.0):.4f}")
    print(f"spy_cagr={report.spy_metrics.get('cagr', 0.0):.4%}")
    print(f"strategy_net_cagr={report.default_net_metrics.get('cagr', 0.0):.4%}")
    print(f"output_json={args.output_json.resolve()}")
    print(f"output_md={args.output_md.resolve()}")
    return 0


def _inclusive_end_timestamp(value: str | None) -> str | None:
    """Convert a date-only CLI bound to the final nanosecond of that UTC date."""
    if value is None:
        return None
    end = pd.Timestamp(value)
    if end.time() != pd.Timestamp(0).time():
        return str(end)
    return str(end + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1))


def _attach_event_flags(panel: pd.DataFrame, flags: pd.DataFrame) -> pd.DataFrame:
    symbols = sorted(str(symbol) for symbol in panel.columns.get_level_values(0).unique())
    aligned = flags.reindex(index=panel.index, columns=symbols, fill_value=0)
    event_panel = aligned.astype(float)
    event_panel.columns = pd.MultiIndex.from_tuples(
        [(symbol, "fundamental_event") for symbol in symbols],
        names=["symbol", "field"],
    )
    enriched = pd.concat([panel, event_panel], axis=1)
    enriched.columns = pd.MultiIndex.from_tuples(
        [(str(symbol), str(field)) for symbol, field in enriched.columns],
        names=["symbol", "field"],
    )
    return enriched.sort_index(axis=1)


def format_report(report: FundamentalEventSmartReversalScoutReport) -> str:
    def metric_rows(label: str, metrics: dict[str, float]) -> str:
        return (
            f"| {label} | {metrics.get('total_return', 0.0):.2%} | "
            f"{metrics.get('cagr', 0.0):.2%} | {metrics.get('sharpe', 0.0):.4f} | "
            f"{metrics.get('sortino', 0.0):.4f} | {metrics.get('max_drawdown', 0.0):.2%} | "
            f"${metrics.get('final_equity', 0.0):,.2f} |"
        )

    lines = [
        "# FundamentalEventSmartReversal-v1 Scout Results",
        "",
        "This is survivorship-biased scout evidence, not validation or trading authorization.",
        "",
        f"Analysis: `{report.analysis_start}` through `{report.analysis_end}`.",
        "",
        "## Performance",
        "",
        "| Portfolio | Total return | CAGR | Sharpe | Sortino | Max drawdown | Final $10k |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        metric_rows("Strategy gross/no explicit costs", report.gross_metrics),
        metric_rows("Strategy repository-default costs", report.default_net_metrics),
        metric_rows("SPY buy-and-hold", report.spy_metrics),
        metric_rows(
            "100% SPY + 20% gross strategy overlay",
            report.spy_plus_20pct_overlay_metrics,
        ),
        "",
        "## SPY and implementation diagnostics",
        "",
        f"- Beta to SPY: `{report.factor_diagnostics['beta_to_spy']:.4f}`.",
        f"- Annualized alpha after default costs: `{report.factor_diagnostics['annualized_alpha']:.4%}`.",
        f"- Correlation to SPY: `{report.factor_diagnostics['correlation_to_spy']:.4f}`.",
        f"- Overlay gross exposure: `{report.overlay_diagnostics['strategy_overlay_gross']:.2%}`; total portfolio gross `{report.overlay_diagnostics['total_portfolio_gross']:.2%}` and net `{report.overlay_diagnostics['total_portfolio_net']:.2%}`.",
        f"- Mean Rank IC: `{report.rank_ic['mean']:.6f}` (reversal expects negative).",
        f"- Mean daily gross turnover: `{report.turnover['mean_daily_gross']:.4f}x` equity.",
        f"- Mean trading cost drag: `{report.cost_drag['mean_daily_trading_cost_bps']:.4f}` bps/day.",
        f"- Mean borrow drag: `{report.cost_drag['mean_daily_borrow_cost_bps']:.4f}` bps/day.",
        f"- SEC filing-flagged symbol-sessions: `{report.event_diagnostics['filing_flagged_symbol_sessions']}`.",
        f"- Normalized SEC event rows: `{report.event_diagnostics.get('normalized_event_rows', 0)}`.",
        f"- Unique issuer filings: `{report.event_diagnostics.get('unique_issuer_filings', 0)}`.",
        f"- Event-vetoed symbol-days: `{report.event_diagnostics['event_vetoed_symbol_days']}`.",
        f"- Event-forced exits: `{report.event_diagnostics['event_forced_exits']}`.",
        "",
        "## Frozen scout gates",
        "",
    ]
    lines.extend(
        f"- {'PASS' if passed else 'FAIL'} — `{name}`."
        for name, passed in report.scout_gates.items()
    )
    lines.extend(
        [
            "",
            f"Overall frozen scout verdict: **{'PASS' if report.scout_passed else 'FAIL'}**.",
            "",
            "The no-event comparator is diagnostic only and cannot replace this frozen candidate.",
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {limitation}" for limitation in report.limitations)
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
