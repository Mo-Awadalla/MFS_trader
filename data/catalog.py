"""Canonical read seam for stored market bars.

The catalog centralizes path resolution and read-time normalization while
leaving source-specific downloading to the existing downloader adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from storage.parquet_io import parquet_path, read_bars


@dataclass(frozen=True)
class BarRequest:
    """A deterministic request for one symbol or an aligned symbol panel."""

    storage_dir: str | Path
    symbols: tuple[str, ...]
    frequency: str
    source: str = ""
    start: str | None = None
    end: str | None = None
    require_complete_panel: bool = True

    def __post_init__(self) -> None:
        if not self.symbols:
            raise ValueError("BarRequest requires at least one symbol")
        if any(not symbol or symbol.strip() != symbol for symbol in self.symbols):
            raise ValueError("BarRequest symbols must be non-empty and trimmed")


@dataclass(frozen=True)
class DataProvenance:
    """Read provenance carried alongside loaded bars."""

    storage_dir: str
    paths: tuple[str, ...]
    symbols: tuple[str, ...]
    frequency: str
    source: str
    start: str | None
    end: str | None


@dataclass(frozen=True)
class LoadedBars:
    """Bars plus the canonical provenance of the read."""

    frame: pd.DataFrame
    provenance: DataProvenance


class DataCatalog:
    """Read market bars through one stable interface."""

    def load(self, request: BarRequest) -> LoadedBars:
        frames: list[pd.DataFrame] = []
        paths: list[str] = []
        for symbol in request.symbols:
            path = parquet_path(
                request.storage_dir,
                symbol,
                request.frequency,
                source=request.source,
            )
            if not path.exists():
                raise FileNotFoundError(f"No Parquet file at {path}")
            frame = self._slice(read_bars(path), request.start, request.end)
            if frame.empty:
                raise ValueError(f"No bars available for {symbol} in requested range")
            frames.append(frame)
            paths.append(str(path))

        if len(frames) == 1:
            loaded = frames[0]
        else:
            if request.require_complete_panel:
                self._require_aligned_panel(request.symbols, frames)
            loaded = pd.concat(
                frames,
                axis=1,
                keys=request.symbols,
                names=["symbol", "field"],
                join="inner" if request.require_complete_panel else "outer",
            ).sort_index()

        provenance = DataProvenance(
            storage_dir=str(Path(request.storage_dir)),
            paths=tuple(paths),
            symbols=request.symbols,
            frequency=request.frequency,
            source=request.source,
            start=request.start,
            end=request.end,
        )
        return LoadedBars(frame=loaded, provenance=provenance)

    @staticmethod
    def _slice(
        frame: pd.DataFrame,
        start: str | None,
        end: str | None,
    ) -> pd.DataFrame:
        result = frame
        if start is not None:
            result = result[result.index >= _utc_timestamp(start)]
        if end is not None:
            result = result[result.index <= _utc_timestamp(end)]
        return result.sort_index()

    @staticmethod
    def _require_aligned_panel(
        symbols: tuple[str, ...],
        frames: list[pd.DataFrame],
    ) -> None:
        reference_index = frames[0].index
        for symbol, frame in zip(symbols[1:], frames[1:], strict=True):
            if not frame.index.equals(reference_index):
                raise ValueError(
                    "Incomplete or misaligned data panel: "
                    f"{symbol} does not match {symbols[0]}"
                )


def _utc_timestamp(value: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")
