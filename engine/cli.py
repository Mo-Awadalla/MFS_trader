"""CLI for engine preflight, local shakedowns, and operational reports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config.loader import ConfigError, get_broker_creds, load_config
from engine.ma_replay import run_ma_real_data_replay
from engine.paper_dry_run import run_ma_paper_dry_run
from engine.paper_trade import halt_paper_trading, run_ma_paper_trade_once
from engine.shakedown import run_ma_shakedown
from execution.alpaca.adapter import AlpacaAdapter
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


def cmd_replay_ma(args: argparse.Namespace) -> int:
    """Run MA on stored real bars through research and engine replay paths."""

    if not args.config:
        print("replay-ma requires --config", file=sys.stderr)
        return 2
    try:
        cfg = load_config(args.config)
        result = run_ma_real_data_replay(
            config=cfg,
            symbol=args.symbol,
            frequency=args.frequency,
            source=args.source,
            start=args.start,
            end=args.end,
            out_dir=args.out_dir,
            fast_window=args.fast_window,
            slow_window=args.slow_window,
            trend_filter_active=not args.no_trend_filter,
            initial_capital=args.initial_capital,
        )
    except (ConfigError, FileNotFoundError, ValueError) as exc:
        print(f"Replay error: {exc}", file=sys.stderr)
        return 1

    stem = f"{args.symbol.replace('/', '_')}_{args.frequency}_comparison"
    print(f"MA real-data replay status: {'PASS' if result.passed else 'DIFFS FOUND'}")
    print(f"Markdown: {Path(args.out_dir) / f'{stem}.md'}")
    print(f"JSON:     {Path(args.out_dir) / f'{stem}.json'}")
    print(f"Replay DB: {result.db_path}")
    if result.differences:
        print("Differences:")
        for difference in result.differences:
            print(f"  - {difference}")
    return 0 if result.passed or args.allow_diffs else 1


def cmd_paper_dry_run_ma(args: argparse.Namespace) -> int:
    """Run one read-only MA paper dry-run cycle against Alpaca."""

    if not args.config:
        print("paper-dry-run-ma requires --config", file=sys.stderr)
        return 2
    broker = None
    try:
        cfg = load_config(args.config)
        broker_cfg = next((b for b in cfg.brokers if b.name == "alpaca"), None)
        if broker_cfg is None:
            raise ConfigError("No alpaca broker configured")
        api_key, api_secret = get_broker_creds(broker_cfg)
        broker = AlpacaAdapter(
            api_key=api_key,
            api_secret=api_secret,
            base_url=broker_cfg.base_url,
            data_url=broker_cfg.data_url or "https://data.alpaca.markets",
        )
        broker.connect()
        if not broker.is_connected:
            raise ConfigError("Alpaca broker did not connect")
        result = run_ma_paper_dry_run(
            config=cfg,
            broker=broker,
            symbol=args.symbol,
            frequency=args.frequency,
            source=args.source,
            out_dir=args.out_dir,
            fast_window=args.fast_window,
            slow_window=args.slow_window,
            trend_filter_active=not args.no_trend_filter,
        )
    except (ConfigError, FileNotFoundError, ValueError) as exc:
        print(f"Paper dry-run error: {exc}", file=sys.stderr)
        return 1
    finally:
        if broker is not None:
            broker.disconnect()

    print(f"MA paper dry-run status: {'PASS' if result.passed else 'BLOCKED'}")
    print(f"Report: {result.report_path}")
    print(f"JSON:   {result.json_path}")
    print(f"DB:     {result.db_path}")
    if result.blockers:
        print("Blockers:")
        for blocker in result.blockers:
            print(f"  - {blocker}")
    return 0 if result.passed or args.allow_blockers else 1


def cmd_paper_trade_ma(args: argparse.Namespace) -> int:
    """Submit at most one tiny MA paper order."""

    if not args.config:
        print("paper-trade-ma requires --config", file=sys.stderr)
        return 2
    broker = None
    try:
        cfg = load_config(args.config)
        broker_cfg = next((b for b in cfg.brokers if b.name == "alpaca"), None)
        if broker_cfg is None:
            raise ConfigError("No alpaca broker configured")
        api_key, api_secret = get_broker_creds(broker_cfg)
        broker = AlpacaAdapter(
            api_key=api_key,
            api_secret=api_secret,
            base_url=broker_cfg.base_url,
            data_url=broker_cfg.data_url or "https://data.alpaca.markets",
        )
        broker.connect()
        if not broker.is_connected:
            raise ConfigError("Alpaca broker did not connect")
        result = run_ma_paper_trade_once(
            config=cfg,
            broker=broker,
            symbol=args.symbol,
            frequency=args.frequency,
            source=args.source,
            out_dir=args.out_dir,
            fast_window=args.fast_window,
            slow_window=args.slow_window,
            trend_filter_active=not args.no_trend_filter,
        )
    except (ConfigError, FileNotFoundError, ValueError) as exc:
        print(f"Paper trade error: {exc}", file=sys.stderr)
        return 1
    finally:
        if broker is not None:
            broker.disconnect()

    print(f"MA paper trade status: {'PASS' if result.passed else 'BLOCKED'}")
    print(f"Submitted: {result.submitted}")
    print(f"Duplicate skipped: {result.duplicate_skipped}")
    print(f"Client order id: {result.client_order_id or 'n/a'}")
    print(f"Order state: {result.order_state or 'n/a'}")
    print(f"Broker status: {result.broker_status or 'n/a'}")
    print(f"Report: {result.report_path}")
    print(f"JSON:   {result.json_path}")
    print(f"DB:     {result.db_path}")
    if result.blockers:
        print("Blockers:")
        for blocker in result.blockers:
            print(f"  - {blocker}")
    return 0 if result.passed or args.allow_blockers else 1


def cmd_paper_halt(args: argparse.Namespace) -> int:
    halt_paper_trading(args.db, reason=args.reason)
    print(f"Paper trading halted in {args.db}: {args.reason}")
    return 0


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

    p_replay = sub.add_parser(
        "replay-ma",
        help="Run MA on stored real bars and compare research vs engine replay",
    )
    p_replay.add_argument("--symbol", required=True, help="Symbol to replay, e.g. AAPL")
    p_replay.add_argument("--frequency", default="1d", help="Stored bar frequency, e.g. 1d")
    p_replay.add_argument("--source", default="alpaca", help="Stored data source directory")
    p_replay.add_argument("--start", help="Optional inclusive start timestamp/date")
    p_replay.add_argument("--end", help="Optional inclusive end timestamp/date")
    p_replay.add_argument("--out-dir", default="runs/ma_real_data_replay", help="Artifact directory")
    p_replay.add_argument("--fast-window", type=int, default=20)
    p_replay.add_argument("--slow-window", type=int, default=100)
    p_replay.add_argument("--no-trend-filter", action="store_true")
    p_replay.add_argument("--initial-capital", type=float, default=10000.0)
    p_replay.add_argument(
        "--allow-diffs",
        action="store_true",
        help="Exit 0 even if research/replay structural differences are found",
    )
    p_replay.set_defaults(func=cmd_replay_ma)

    p_dry = sub.add_parser(
        "paper-dry-run-ma",
        help="Run one read-only MA dry-run cycle against Alpaca paper",
    )
    p_dry.add_argument("--symbol", default="AAPL", help="Symbol to dry-run; Phase 3.5 allows AAPL only")
    p_dry.add_argument("--frequency", default="1d", help="Stored bar frequency, e.g. 1d")
    p_dry.add_argument("--source", default="alpaca", help="Stored data source directory")
    p_dry.add_argument("--out-dir", default="runs/ma_paper_dry_run", help="Artifact directory")
    p_dry.add_argument("--fast-window", type=int, default=20)
    p_dry.add_argument("--slow-window", type=int, default=100)
    p_dry.add_argument("--no-trend-filter", action="store_true")
    p_dry.add_argument(
        "--allow-blockers",
        action="store_true",
        help="Exit 0 even if the dry-run gate finds blockers",
    )
    p_dry.set_defaults(func=cmd_paper_dry_run_ma)

    p_trade = sub.add_parser(
        "paper-trade-ma",
        help="Submit at most one tiny MA paper order against Alpaca paper",
    )
    p_trade.add_argument("--symbol", default="AAPL", help="Symbol to trade; Phase 3.6 allows AAPL only")
    p_trade.add_argument("--frequency", default="1d", help="Stored bar frequency, e.g. 1d")
    p_trade.add_argument("--source", default="alpaca", help="Stored data source directory")
    p_trade.add_argument("--out-dir", default="runs/ma_paper_trade", help="Artifact directory")
    p_trade.add_argument("--fast-window", type=int, default=20)
    p_trade.add_argument("--slow-window", type=int, default=100)
    p_trade.add_argument("--no-trend-filter", action="store_true")
    p_trade.add_argument(
        "--allow-blockers",
        action="store_true",
        help="Exit 0 even if the paper trade gate finds blockers",
    )
    p_trade.set_defaults(func=cmd_paper_trade_ma)

    p_halt = sub.add_parser("paper-halt", help="Persist a paper trading kill switch")
    p_halt.add_argument("--db", required=True, help="Paper trading SQLite DB")
    p_halt.add_argument("--reason", default="manual_halt")
    p_halt.set_defaults(func=cmd_paper_halt)

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
