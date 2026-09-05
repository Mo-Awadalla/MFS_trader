"""Overnight loser data loading helpers.

One-time universe download (requires MASSIVE_API_KEY):

    python -m research.overnight_loser_data --download --universe sector_spdrs
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd

from storage.parquet_io import read_bars
from strategies.overnight_loser.signal import universe_symbols

STORAGE_DIR = Path("data/parquet/equity/massive_daily")
OHLCV_FIELDS = ("open", "high", "low", "close", "volume")


def load_overnight_loser_panel(
    universe: str = "sector_spdrs",
    *,
    storage_dir: str | Path = STORAGE_DIR,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Load the daily OHLCV panel for one overnight-loser universe."""
    symbols = universe_symbols(universe)
    frames: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        path = Path(storage_dir) / f"{symbol}_1d.parquet"
        if not path.exists():
            raise FileNotFoundError(
                f"missing daily bars for {symbol} at {path}; download the "
                f"{universe!r} universe before running overnight_loser research"
            )
        df = read_bars(path)
        if start:
            df = df[df.index >= pd.Timestamp(start, tz="UTC")]
        if end:
            df = df[df.index <= pd.Timestamp(end, tz="UTC")]
        frames[symbol] = df.loc[:, list(OHLCV_FIELDS)].astype(float)

    panel = pd.concat(frames, axis=1)
    panel.columns = pd.MultiIndex.from_tuples(
        [(str(symbol), str(field)) for symbol, field in panel.columns],
        names=["symbol", "field"],
    )
    return panel.sort_index()


def main() -> None:
    parser = argparse.ArgumentParser(description="Overnight loser universe data helper.")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--universe", default="sector_spdrs")
    parser.add_argument("--start", default="2004-01-01")
    parser.add_argument("--end")
    args = parser.parse_args()
    if not args.download:
        raise SystemExit("nothing to do; pass --download")
    api_key = os.environ.get("MASSIVE_API_KEY")
    if not api_key:
        raise SystemExit("MASSIVE_API_KEY is required for --download")
    from research.etf_tsmom_pipeline import download_massive_daily_bars

    summary = download_massive_daily_bars(
        universe_symbols(args.universe),
        api_key=api_key,
        start=args.start,
        end=args.end,
        storage_dir=STORAGE_DIR,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
