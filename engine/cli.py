"""CLI for engine preflight, local shakedowns, and operational reports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config.loader import ConfigError, load_config
from engine.shakedown import run_ma_shakedown
from monitoring.reports import (
    build_operational_report,
    format_operational_report,
    write_operational_report,
)


def cmd_preflight(args: argparse.Namespace) -> int:
    """Validate config and print what would run."""

    if not args.config:
        print("preflight requires --config", file=sys.stderr)
        return 2
    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    print("Config OK")
    print(f"  mode: {cfg.mode.value}")
    print(f"  strategy: {cfg.strategy_name} {cfg.strategy_version}")
    print(f"  enabled strategies: {', '.join(cfg.strategies_enabled) or '(none)'}")
    print(f"  brokers: {', '.join(b.name for b in cfg.brokers)}")
    print(f"  data symbols: {sum(len(d.symbols) for d in cfg.data)}")
    print("Runtime note: use `mfs-engine shakedown-ma` for local synthetic replay, ")
    print("or wire a broker/data feed before running a continuous paper/live loop.")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Generate an operational report from an engine SQLite DB."""

    report = build_operational_report(args.db)
    if args.output:
        write_operational_report(report, args.output, fmt=args.format)
        print(f"Wrote {args.format} operational report: {args.output}")
    else:
        if args.format == "json":
            import json

            print(json.dumps(report.to_dict(), indent=2, default=str))
        else:
            print(format_operational_report(report))
    return 0 if report.passed or args.allow_blockers else 1


def cmd_shakedown_ma(args: argparse.Namespace) -> int:
    """Run the synthetic MA operational shakedown."""

    out_dir = Path(args.out_dir)
    result = run_ma_shakedown(
        out_dir=out_dir,
        bars=args.bars,
        seed=args.seed,
        fast_window=args.fast_window,
        slow_window=args.slow_window,
        trend_filter_active=not args.no_trend_filter,
        initial_capital=args.initial_capital,
    )
    print(f"MA shakedown status: {'PASS' if result.passed else 'BLOCKED'}")
    print(f"Report: {result.report_path}")
    print(f"JSON:   {result.json_path}")
    if result.blockers:
        print("Blockers:")
        for blocker in result.blockers:
            print(f"  - {blocker}")
    return 0 if result.passed or args.allow_blockers else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mfs-engine", description="MFS trading engine tools")
    parser.add_argument("--config", "-c", help="Path to TOML config file for preflight")
    sub = parser.add_subparsers(dest="command")

    p_preflight = sub.add_parser("preflight", help="Validate config without placing orders")
    p_preflight.set_defaults(func=cmd_preflight)

    p_report = sub.add_parser("report", help="Generate operational report from SQLite DB")
    p_report.add_argument("--db", required=True, help="Path to engine/replay SQLite DB")
    p_report.add_argument("--output", "-o", help="Write report to this path instead of stdout")
    p_report.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p_report.add_argument(
        "--allow-blockers",
        action="store_true",
        help="Exit 0 even if the report contains promotion blockers",
    )
    p_report.set_defaults(func=cmd_report)

    p_shakedown = sub.add_parser(
        "shakedown-ma",
        help="Run synthetic MA research/replay/failure-mode shakedown",
    )
    p_shakedown.add_argument("--out-dir", default="runs/ma_shakedown", help="Artifact directory")
    p_shakedown.add_argument("--bars", type=int, default=300, help="Synthetic daily bars")
    p_shakedown.add_argument("--seed", type=int, default=42, help="Synthetic data RNG seed")
    p_shakedown.add_argument("--fast-window", type=int, default=20)
    p_shakedown.add_argument("--slow-window", type=int, default=100)
    p_shakedown.add_argument("--no-trend-filter", action="store_true")
    p_shakedown.add_argument("--initial-capital", type=float, default=10000.0)
    p_shakedown.add_argument(
        "--allow-blockers",
        action="store_true",
        help="Exit 0 even if the shakedown finds blockers",
    )
    p_shakedown.set_defaults(func=cmd_shakedown_ma)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        if args.config:
            args.func = cmd_preflight
        else:
            parser.print_help()
            return 0
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
