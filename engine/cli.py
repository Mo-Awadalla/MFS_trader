"""CLI for engine preflight, local shakedowns, and operational reports."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from config.loader import ConfigError, get_broker_creds, load_config
from engine.ma_replay import run_ma_real_data_replay
from engine.paper_dry_run import run_ma_paper_dry_run
from engine.paper_run import PaperRunConfig, PaperRunLoop
from engine.paper_session import (
    PaperSessionGateError,
    paper_caps_from_config,
    run_alpaca_paper_smoke,
    run_simulated_paper_drills,
    validate_tiny_paper_caps,
    write_paper_operator_report,
)
from engine.paper_trade import halt_paper_trading, run_ma_paper_trade_once
from engine.shakedown import run_ma_shakedown
from execution.alpaca.adapter import AlpacaAdapter
from execution.sim_broker.broker import SimBroker
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


def _open_registry(args: argparse.Namespace):
    from experiments.registry import ExperimentRegistry

    return ExperimentRegistry(args.experiment_root)


def cmd_confirm_paper_ops_pass(args: argparse.Namespace) -> int:
    """Operator confirmation: paper_ops -> live_dry_run."""
    from experiments.models import ExperimentNotFoundError
    from experiments.operator_confirmations import (
        ConfirmedExperimentError,
        confirm_paper_ops_pass,
    )

    registry = _open_registry(args)
    try:
        result = confirm_paper_ops_pass(
            registry,
            uuid=args.experiment_uuid,
            expected_hash=args.experiment_hash,
            paper_session_id=args.paper_session_id,
            operator=args.operator,
        )
    except (ExperimentNotFoundError, ValueError) as exc:
        print(f"confirm-paper-ops-pass error: {exc}", file=sys.stderr)
        return 1
    except ConfirmedExperimentError as exc:
        print(f"confirm-paper-ops-pass rejected: {exc}", file=sys.stderr)
        return 2
    finally:
        registry.close()
    print(f"Promoted experiment {result.experiment.uuid} via {result.transition}")
    print(f"  promotion_status: {result.experiment.promotion_status.value}")
    print(f"  experiment_hash:   {result.experiment.experiment_hash}")
    print(f"  paper_session_id:  {result.paper_session_id}")
    print(f"  confirmation:      {result.confirmation_artifact_path}")
    print(f"  operator:          {result.operator or '(unspecified)'}")
    return 0


def cmd_confirm_resume(args: argparse.Namespace) -> int:
    """Operator confirmation: suspended -> suspended_from_status (+ clear kill switch)."""
    from experiments.models import ExperimentNotFoundError
    from experiments.operator_confirmations import (
        ConfirmedExperimentError,
        confirm_resume,
    )

    registry = _open_registry(args)
    try:
        result = confirm_resume(
            registry,
            uuid=args.experiment_uuid,
            expected_hash=args.experiment_hash,
            operator=args.operator,
        )
    except (ExperimentNotFoundError, ValueError) as exc:
        print(f"confirm-resume error: {exc}", file=sys.stderr)
        return 1
    except ConfirmedExperimentError as exc:
        print(f"confirm-resume rejected: {exc}", file=sys.stderr)
        return 2
    finally:
        registry.close()
    print(f"Resumed experiment {result.experiment.uuid} via {result.transition}")
    print(f"  promotion_status:    {result.experiment.promotion_status.value}")
    print(f"  cleared kill switch: {result.cleared_kill_switch}")
    print(f"  operator:            {result.operator or '(unspecified)'}")
    return 0


def cmd_confirm_retire(args: argparse.Namespace) -> int:
    """Operator confirmation: any non-terminal stage -> retired."""
    from experiments.models import ExperimentNotFoundError
    from experiments.operator_confirmations import (
        ConfirmedExperimentError,
        confirm_retire,
    )

    registry = _open_registry(args)
    try:
        result = confirm_retire(
            registry,
            uuid=args.experiment_uuid,
            expected_hash=args.experiment_hash,
            operator=args.operator,
        )
    except (ExperimentNotFoundError, ValueError) as exc:
        print(f"confirm-retire error: {exc}", file=sys.stderr)
        return 1
    except ConfirmedExperimentError as exc:
        print(f"confirm-retire rejected: {exc}", file=sys.stderr)
        return 2
    finally:
        registry.close()
    print(f"Retired experiment {result.experiment.uuid} via {result.transition}")
    print(f"  promotion_status: {result.experiment.promotion_status.value}")
    print(f"  operator:          {result.operator or '(unspecified)'}")
    return 0


def cmd_paper_run(args: argparse.Namespace) -> int:
    """Run continuous paper trading with Experiment lifecycle checks."""

    from data.pipeline import load_bars

    if not args.config:
        print("paper-run requires --config", file=sys.stderr)
        return 2

    broker = None
    try:
        cfg = load_config(args.config)
        cfg = _apply_paper_caps_overrides(cfg, args)
        caps = paper_caps_from_config(cfg)
        if args.broker == "alpaca_paper" or args.run_sim_drills:
            validate_tiny_paper_caps(caps)
        registry = _open_registry(args)
        try:
            if args.run_sim_drills:
                result = run_simulated_paper_drills(
                    registry=registry,
                    config=cfg,
                    experiment_uuid=args.experiment_uuid,
                    experiment_hash=args.experiment_hash,
                    operator=args.operator,
                    session_id=args.session_id,
                )
                print(f"Sim paper drills status: {'PASS' if result.passed else 'BLOCKED'}")
                print(f"Session:  {result.session_id}")
                print(f"Artifact: {result.artifact_path}")
                for blocker in result.blockers:
                    print(f"  - {blocker}")
                return 0 if result.passed else 1
        finally:
            registry.close()

        data_cfg = next((d for d in cfg.data if args.symbol in d.symbols), None)
        if data_cfg is None:
            raise ConfigError(f"No data config contains symbol {args.symbol}")

        if args.broker == "alpaca_paper":
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
                raise ConfigError("Alpaca paper broker did not connect")
            if args.alpaca_paper_smoke:
                registry = _open_registry(args)
                try:
                    result = run_alpaca_paper_smoke(
                        registry=registry,
                        config=cfg,
                        broker=broker,
                        experiment_uuid=args.experiment_uuid,
                        experiment_hash=args.experiment_hash,
                        operator=args.operator,
                        session_id=args.session_id,
                        symbol=args.symbol,
                        confirm_paper_broker=args.confirm_paper_broker,
                    )
                    print(f"Alpaca paper smoke status: {'PASS' if result.passed else 'BLOCKED'}")
                    print(f"Session:  {result.session_id}")
                    print(f"Artifact: {result.artifact_path}")
                    for blocker in result.blockers:
                        print(f"  - {blocker}")
                    return 0 if result.passed else 1
                finally:
                    registry.close()
        else:
            broker = SimBroker()
            broker.connect()
            if not broker.is_connected:
                raise ConfigError("Sim broker did not connect")

        if args.broker == "alpaca_paper" and not args.confirm_paper_broker:
            raise PaperSessionGateError(
                "--confirm-paper-broker is required for continuous alpaca_paper runs"
            )

        bars = load_bars(
            data_cfg.storage_dir,
            args.symbol,
            args.frequency,
            source="alpaca",
        )
        if not bars.empty and "close" in bars:
            broker.set_price(args.symbol, float(bars["close"].iloc[-1]))

        run_config = PaperRunConfig(
            experiment_uuid=args.experiment_uuid,
            experiment_hash=args.experiment_hash,
            experiment_root=args.experiment_root,
            operator=args.operator,
            symbols=(args.symbol,),
            session_id=args.session_id,
            session_kind=args.session_kind,
            bar_frequency=args.frequency,
            window_calendar_days=args.window_calendar_days,
            window_market_sessions=args.window_market_sessions,
            window_trades=args.window_trades,
            window_unplanned_interruptions=args.window_unplanned_interruptions,
            insufficient_activity_override_approved=(
                args.insufficient_activity_override_approved
            ),
            slippage_samples=tuple(_load_json_list_arg(args.slippage_samples_json)),
            kill_switch_drill=_load_json_object_arg(args.kill_switch_drill_json),
            sleep_between_bars_seconds=args.sleep,
            max_cycles=args.max_cycles,
        )

        from strategies.ma.signal import MAParams, generate_signals

        def strategy_fn(bars: pd.DataFrame, params: dict[str, Any]) -> dict[str, float]:
            ma_params = MAParams(
                fast_ma_window=int(params.get("fast_ma_window", 20)),
                slow_ma_window=int(params.get("slow_ma_window", 100)),
                trend_filter_active=bool(params.get("trend_filter_active", True)),
                long_only=True,
            )
            signals = generate_signals(bars, ma_params)
            if signals.empty or "position" not in signals:
                return {}
            return {args.symbol: float(signals["position"].iloc[-1])}

        loop = PaperRunLoop(
            config=cfg,
            broker=broker,
            strategy_fn=strategy_fn,
            strategy_name=cfg.strategy_name or "dual_ma_crossover",
            run_config=run_config,
            strategy_params={
                "fast_ma_window": args.fast_window,
                "slow_ma_window": args.slow_window,
                "trend_filter_active": not args.no_trend_filter,
            },
        )

        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        db_path = out_dir / "paper_run.sqlite"

        result = loop.run(bars=bars, db_path=db_path)

        print(f"Paper run completed: {result.cycle_count} cycles")
        print(f"  halted:           {result.halted}")
        print(f"  halt_reason:      {result.halt_reason or 'n/a'}")
        print(f"  total_orders:     {result.total_orders_submitted}")
        print(f"  evidence:         {result.evidence_path or 'n/a'}")
        print(f"  errors:           {len(result.errors)}")
        for err in result.errors[:5]:
            print(f"    - {err}")
        return 1 if result.halted or result.errors else 0

    except (ConfigError, FileNotFoundError, ValueError, PaperSessionGateError) as exc:
        print(f"Paper run error: {exc}", file=sys.stderr)
        return 1
    finally:
        if broker is not None:
            with contextlib.suppress(Exception):
                broker.disconnect()


def _apply_paper_caps_overrides(cfg, args):
    live = cfg.live_deployment
    max_notional_per_order = (
        args.max_notional_per_order
        if args.max_notional_per_order is not None
        else live.max_notional_per_order
    )
    max_paper_session_notional = (
        args.max_paper_session_notional
        if args.max_paper_session_notional is not None
        else live.max_paper_session_notional
    )
    max_open_paper_exposure = (
        args.max_open_paper_exposure
        if args.max_open_paper_exposure is not None
        else live.max_open_paper_exposure
    )
    return replace(
        cfg,
        live_deployment=replace(
            live,
            max_notional_per_order=max_notional_per_order,
            max_paper_session_notional=max_paper_session_notional,
            max_open_paper_exposure=max_open_paper_exposure,
        ),
    )


def _load_json_list_arg(value: str | None) -> list[dict[str, Any]]:
    if not value:
        return []
    payload = json.loads(Path(value).read_text(encoding="utf-8") if Path(value).exists() else value)
    if not isinstance(payload, list):
        raise ValueError("expected JSON list")
    if not all(isinstance(item, dict) for item in payload):
        raise ValueError("expected JSON list of objects")
    return payload


def _load_json_object_arg(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    payload = json.loads(Path(value).read_text(encoding="utf-8") if Path(value).exists() else value)
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object")
    return payload


def cmd_paper_operator_report(args: argparse.Namespace) -> int:
    registry = _open_registry(args)
    try:
        json_path, md_path, report = write_paper_operator_report(
            registry=registry,
            experiment_uuid=args.experiment_uuid,
            db_path=args.db,
        )
    except Exception as exc:
        print(f"paper-operator-report error: {exc}", file=sys.stderr)
        return 1
    finally:
        registry.close()
    print(f"Paper operator report status: {'PASS' if report['passed'] else 'BLOCKED'}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    for blocker in report["blockers"]:
        print(f"  - {blocker}")
    return 0 if report["passed"] or args.allow_blockers else 1


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

    p_confirm_paper_ops = sub.add_parser(
        "confirm-paper-ops-pass",
        help="Operator confirmation: promote paper_ops -> live_dry_run",
    )
    p_confirm_paper_ops.add_argument(
        "--experiment-root", required=True, help="Path to experiments registry root"
    )
    p_confirm_paper_ops.add_argument(
        "--experiment-uuid", required=True, help="Explicit Experiment UUID to promote"
    )
    p_confirm_paper_ops.add_argument(
        "--experiment-hash",
        required=True,
        help="Operator-supplied experiment_hash (defends against 'run latest')",
    )
    p_confirm_paper_ops.add_argument(
        "--operator",
        help="Operator identity recorded with the confirmation",
    )
    p_confirm_paper_ops.add_argument(
        "--paper-session-id",
        required=True,
        help="Immutable paper_ops_pass session id to evaluate",
    )
    p_confirm_paper_ops.set_defaults(func=cmd_confirm_paper_ops_pass)

    p_confirm_resume = sub.add_parser(
        "confirm-resume",
        help="Operator confirmation: suspended -> suspended_from_status",
    )
    p_confirm_resume.add_argument(
        "--experiment-root", required=True, help="Path to experiments registry root"
    )
    p_confirm_resume.add_argument(
        "--experiment-uuid", required=True, help="Explicit Experiment UUID to resume"
    )
    p_confirm_resume.add_argument(
        "--experiment-hash",
        required=True,
        help="Operator-supplied experiment_hash (defends against 'run latest')",
    )
    p_confirm_resume.add_argument(
        "--operator",
        help="Operator identity recorded with the confirmation",
    )
    p_confirm_resume.set_defaults(func=cmd_confirm_resume)

    p_confirm_retire = sub.add_parser(
        "confirm-retire",
        help="Operator confirmation: terminal retirement from any non-terminal stage",
    )
    p_confirm_retire.add_argument(
        "--experiment-root", required=True, help="Path to experiments registry root"
    )
    p_confirm_retire.add_argument(
        "--experiment-uuid", required=True, help="Explicit Experiment UUID to retire"
    )
    p_confirm_retire.add_argument(
        "--experiment-hash",
        required=True,
        help="Operator-supplied experiment_hash (defends against 'run latest')",
    )
    p_confirm_retire.add_argument(
        "--operator",
        help="Operator identity recorded with the confirmation",
    )
    p_confirm_retire.set_defaults(func=cmd_confirm_retire)

    p_paper_run = sub.add_parser(
        "paper-run",
        help="Continuous paper trading loop with Experiment lifecycle checks",
    )
    p_paper_run.add_argument("--config", "-c", required=True, help="Path to TOML config file")
    p_paper_run.add_argument("--experiment-root", required=True, help="Path to experiments registry root")
    p_paper_run.add_argument("--experiment-uuid", required=True, help="Explicit Experiment UUID to run")
    p_paper_run.add_argument(
        "--experiment-hash",
        required=True,
        help="Operator-supplied experiment_hash (defends against 'run latest')",
    )
    p_paper_run.add_argument("--operator", help="Operator identity")
    p_paper_run.add_argument("--symbol", default="AAPL", help="Symbol to trade")
    p_paper_run.add_argument("--frequency", default="1d", help="Bar frequency")
    p_paper_run.add_argument("--session-id", required=True, help="Unique paper session evidence id")
    p_paper_run.add_argument(
        "--session-kind",
        choices=["paper_ops_smoke", "paper_ops_pass"],
        default="paper_ops_smoke",
        help="Evidence kind for the immutable paper session summary",
    )
    p_paper_run.add_argument(
        "--broker",
        default="sim_broker",
        choices=["sim_broker", "alpaca_paper"],
        help="Broker authority for paper-run; alpaca_paper requires explicit confirmation and gates",
    )
    p_paper_run.add_argument(
        "--confirm-paper-broker",
        action="store_true",
        help="Required to allow Alpaca paper broker authority",
    )
    p_paper_run.add_argument(
        "--alpaca-paper-smoke",
        action="store_true",
        help="Run one-shot Alpaca paper submit/cancel smoke instead of the continuous loop",
    )
    p_paper_run.add_argument(
        "--run-sim-drills",
        action="store_true",
        help="Run forced sim reject/timeout/reconciliation drills and write evidence",
    )
    p_paper_run.add_argument(
        "--max-notional-per-order",
        type=float,
        help="Tiny paper cap override; must be <= 25 for Alpaca/drills",
    )
    p_paper_run.add_argument(
        "--max-paper-session-notional",
        type=float,
        help="Tiny paper session cap override; must be <= 100 for Alpaca/drills",
    )
    p_paper_run.add_argument(
        "--max-open-paper-exposure",
        type=float,
        help="Tiny paper open exposure cap override; must be <= 100 for Alpaca/drills",
    )
    p_paper_run.add_argument("--out-dir", default="runs/ma_paper_run", help="Artifact directory")
    p_paper_run.add_argument("--fast-window", type=int, default=20)
    p_paper_run.add_argument("--slow-window", type=int, default=100)
    p_paper_run.add_argument("--no-trend-filter", action="store_true")
    p_paper_run.add_argument(
        "--window-calendar-days",
        type=int,
        help="Predeclared calendar-day count for paper_ops_pass evidence",
    )
    p_paper_run.add_argument(
        "--window-market-sessions",
        type=int,
        help="Predeclared market-session count for paper_ops_pass evidence",
    )
    p_paper_run.add_argument(
        "--window-trades",
        type=int,
        help="Predeclared trade count for paper_ops_pass evidence",
    )
    p_paper_run.add_argument(
        "--window-unplanned-interruptions",
        type=int,
        default=0,
        help="Unplanned interruption count for paper ops smoke/pass evidence",
    )
    p_paper_run.add_argument(
        "--insufficient-activity-override-approved",
        action="store_true",
        help="Record explicit operator-approved insufficient-activity override",
    )
    p_paper_run.add_argument(
        "--slippage-samples-json",
        help="JSON list or file path of slippage samples for paper_ops_pass",
    )
    p_paper_run.add_argument(
        "--kill-switch-drill-json",
        help="JSON object or file path with kill-switch drill evidence",
    )
    p_paper_run.add_argument(
        "--sleep", type=float, default=60.0, help="Seconds to sleep between bar cycles"
    )
    p_paper_run.add_argument(
        "--max-cycles", type=int, default=None, help="Max bar cycles before graceful stop"
    )
    p_paper_run.set_defaults(func=cmd_paper_run)

    p_paper_report = sub.add_parser(
        "paper-operator-report",
        help="Write Experiment-level paper readiness evidence",
    )
    p_paper_report.add_argument("--experiment-root", required=True, help="Path to experiments registry root")
    p_paper_report.add_argument("--experiment-uuid", required=True, help="Experiment UUID")
    p_paper_report.add_argument("--db", help="Optional engine SQLite DB to include")
    p_paper_report.add_argument(
        "--allow-blockers",
        action="store_true",
        help="Exit 0 even if the report contains blockers",
    )
    p_paper_report.set_defaults(func=cmd_paper_operator_report)

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
