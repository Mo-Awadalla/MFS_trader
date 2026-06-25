"""Data CLI — download and validate OHLCV data.

Usage:
    mfs-data download --config config/research.toml
    mfs-data download --config config/research.toml --symbol AAPL
    mfs-data status --config config/research.toml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import structlog

from config.loader import get_broker_creds, load_config
from data.pipeline import build_downloader, download_and_store, load_bars
from storage.parquet_io import parquet_path

log = structlog.get_logger(__name__)


def cmd_download(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)

    db_path = Path("storage/mfs.sqlite")
    from storage.schema import init_db

    conn = init_db(db_path) if args.db else None

    for data_cfg in cfg.data:
        # Find matching broker for this asset class
        broker = next(
            (b for b in cfg.brokers if b.asset_class == data_cfg.asset_class), None
        )
        if broker is None:
            log.error("no_broker_for_asset_class", asset_class=data_cfg.asset_class)
            continue

        try:
            api_key, api_secret = get_broker_creds(broker)
        except Exception as e:
            log.error("missing_credentials", broker=broker.name, error=str(e))
            continue

        downloader = build_downloader(data_cfg, api_key, api_secret, is_paper=broker.is_paper)

        symbols = data_cfg.symbols
        if args.symbol:
            symbols = [s for s in symbols if s == args.symbol]
            if not symbols:
                log.error("symbol_not_in_config", symbol=args.symbol)
                continue

        # Temporarily filter symbols
        from dataclasses import replace

        filtered_cfg = replace(data_cfg, symbols=symbols)
        summary = download_and_store(filtered_cfg, downloader, environment=cfg.mode.value, conn=conn)

        for sym, result in summary["symbols"].items():
            print(f"  {sym:10s}  {result['status']:6s}  bars={result.get('bars', 0):>8}  stored={result.get('stored', False)}")

    if conn:
        conn.close()
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)

    for data_cfg in cfg.data:
        print(f"\n  Asset class: {data_cfg.asset_class.value}")
        print(f"  Storage:     {data_cfg.storage_dir}")
        print(f"  {'Symbol':<12s} {'1min':>8s} {'1h':>8s} {'1d':>8s}")
        print(f"  {'─' * 40}")
        for sym in data_cfg.symbols:
            counts = {}
            for freq in ["1min", "1h", "1d"]:
                path = parquet_path(data_cfg.storage_dir, sym, freq, source=f"ccxt_{data_cfg.exchange}" if data_cfg.asset_class.value == "crypto" else "alpaca")
                if path.exists():
                    try:
                        df = load_bars(data_cfg.storage_dir, sym, freq, source=f"ccxt_{data_cfg.exchange}" if data_cfg.asset_class.value == "crypto" else "alpaca")
                        counts[freq] = len(df)
                    except Exception:
                        counts[freq] = 0
                else:
                    counts[freq] = 0
            print(f"  {sym:<12s} {counts.get('1min', 0):>8} {counts.get('1h', 0):>8} {counts.get('1d', 0):>8}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mfs-data", description="Data pipeline CLI")
    parser.add_argument("--config", "-c", required=True, help="Path to TOML config file")
    parser.add_argument("--db", action="store_true", default=True, help="Log to SQLite")
    sub = parser.add_subparsers(dest="command", required=True)

    p_download = sub.add_parser("download", help="Download and store OHLCV data")
    p_download.add_argument("--symbol", "-s", help="Download only this symbol")
    p_download.set_defaults(func=cmd_download)

    p_status = sub.add_parser("status", help="Show stored data status")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
