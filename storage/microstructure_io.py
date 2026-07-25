"""Parquet storage for irregular market microstructure events."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

_EVENT_TYPES = {"trades", "quotes"}


def microstructure_path(
    storage_dir: str | Path,
    *,
    provider_feed: str,
    symbol: str,
    session_date: str,
    event_type: str,
) -> Path:
    """Return a deterministic partition path without treating timestamps as unique keys."""
    if event_type not in _EVENT_TYPES:
        raise ValueError(f"Unsupported event type: {event_type}")
    safe_source = _safe_component(provider_feed)
    safe_symbol = _safe_component(symbol.upper())
    safe_date = str(pd.Timestamp(session_date).date())
    return Path(storage_dir) / safe_source / "equity" / safe_symbol / safe_date / f"{event_type}.parquet"


def write_events(
    frame: pd.DataFrame,
    path: str | Path,
    *,
    compression: str = "zstd",
) -> dict[str, int | str]:
    """Atomically write event rows without timestamp-based deduplication."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    table = pa.Table.from_pandas(frame, preserve_index=False)
    pq.write_table(table, str(temporary), compression=compression)  # type: ignore[no-untyped-call]
    temporary.replace(destination)
    return {
        "path": str(destination),
        "rows": len(frame),
        "bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
    }


def read_events(path: str | Path) -> pd.DataFrame:
    table = pq.read_table(str(path))  # type: ignore[no-untyped-call]
    frame = table.to_pandas()
    if "timestamp" in frame.columns:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    return frame


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_component(value: str) -> str:
    cleaned = value.replace("/", "_").replace("\\", "_").strip()
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError(f"Invalid path component: {value!r}")
    return cleaned
