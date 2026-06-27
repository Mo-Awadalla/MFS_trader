"""CSMR data loading helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from storage.parquet_io import read_bars

OHLCV_FIELDS = ("open", "high", "low", "close", "volume")


def load_csmr_panel(
    paths: list[str | Path],
    *,
    start: str | None = None,
    end: str | None = None,
    normalize_daily_index: bool = True,
) -> pd.DataFrame:
    """Load per-symbol OHLCV parquet files into a CSMR MultiIndex panel."""
    frames: dict[str, pd.DataFrame] = {}
    for path in paths:
        parquet_path = Path(path)
        symbol = _symbol_from_parquet_path(parquet_path)
        df = read_bars(parquet_path)
        missing = set(OHLCV_FIELDS) - set(df.columns)
        if missing:
            raise ValueError(f"{parquet_path} missing OHLCV columns: {sorted(missing)}")
        if start:
            df = df[df.index >= pd.Timestamp(start, tz="UTC")]
        if end:
            df = df[df.index <= pd.Timestamp(end, tz="UTC")]
        if normalize_daily_index:
            df = _normalize_daily_index(df)
        frames[symbol] = df.loc[:, list(OHLCV_FIELDS)].astype(float)

    if not frames:
        columns = pd.MultiIndex.from_arrays([[], []], names=["symbol", "field"])
        return pd.DataFrame(columns=columns)

    panel = pd.concat(frames, axis=1)
    panel.columns = pd.MultiIndex.from_tuples(
        [(str(symbol), str(field)) for symbol, field in panel.columns],
        names=["symbol", "field"],
    )
    return panel.sort_index()


def discover_ohlcv_parquet(
    storage_dir: str | Path = "data/parquet/equity",
    *,
    source: str = "alpaca",
    frequency: str = "1d",
) -> list[Path]:
    """Return stored OHLCV parquet files for one source/frequency."""
    root = Path(storage_dir) / source
    return sorted(root.glob(f"*_{frequency}.parquet"))


def _symbol_from_parquet_path(path: Path) -> str:
    name = path.name
    for suffix in ("_1d.parquet", "_1h.parquet", "_1min.parquet"):
        if name.endswith(suffix):
            return name[: -len(suffix)].replace("_", "/")
    return path.stem


def _normalize_daily_index(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized.index = pd.DatetimeIndex(normalized.index).normalize()
    normalized = normalized[~normalized.index.duplicated(keep="last")]
    return normalized.sort_index()
