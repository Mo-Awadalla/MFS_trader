"""Explicit US-equity date bounds and exchange-session coverage checks."""

from __future__ import annotations

import re
from typing import Any

import exchange_calendars as xc
import pandas as pd

NY = "America/New_York"
DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def equity_request_bounds(start: str, end: str | None) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Date-only bounds include the entire New York end date.

    Explicit timestamps retain inclusive endpoint semantics; naive timestamps
    with a clock are UTC for backward compatibility. Both outputs are UTC.
    """

    def parse(value: str, is_end: bool) -> pd.Timestamp:
        if DATE_ONLY.fullmatch(value):
            ts = pd.Timestamp(value, tz=NY)
            if is_end:
                ts = ts + pd.DateOffset(days=1) - pd.Timedelta(nanoseconds=1)
        else:
            ts = pd.Timestamp(value)
            ts = ts.tz_localize("UTC") if ts.tz is None else ts
        return ts.tz_convert("UTC")

    first = parse(start, False)
    last = parse(end, True) if end else pd.Timestamp.now(tz="UTC")
    if last < first:
        raise ValueError("Equity request end precedes start")
    return first, last


def equity_session_coverage(
    frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, frequency: str
) -> dict[str, Any]:
    """Audit all complete RTH sessions inside the request, including empty days.

    Intraday bars use start labels. Alpaca hourly bars are clock-hour aligned;
    the 09:00 bar overlaps the first half-hour of the regular session. An
    explicit partial-session request is not mistaken for a full-session audit.
    Missing bars may represent no venue trades, but are never certified complete.
    """
    if start.tz is None or end.tz is None:
        raise ValueError("Coverage bounds must be timezone-aware")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("Bars must have a timezone-aware DatetimeIndex")
    if frame.index.has_duplicates:
        raise ValueError("Duplicate bar timestamps")
    if not frame.index.is_monotonic_increasing:
        raise ValueError("Bar timestamps must be sorted")
    if frequency not in {"1min", "5min", "15min", "30min", "1h", "1d"}:
        raise ValueError(f"Unsupported session-audit frequency: {frequency}")
    first = start.tz_convert(NY).date()
    last = end.tz_convert(NY).date()
    cal = xc.get_calendar(
        "XNYS", start=str(first - pd.Timedelta(days=7)), end=str(last + pd.Timedelta(days=7))
    )
    index = frame.index.tz_convert(NY)
    days_present = set(index.strftime("%Y-%m-%d"))
    absent: dict[str, int] = {}
    samples: list[str] = []
    sessions = expected_total = 0
    for day, row in cal.schedule.iterrows():
        opening = pd.Timestamp(row["open"])
        closing = pd.Timestamp(row["close"])
        if opening < start or closing > end:
            continue
        sessions += 1
        if frequency == "1d":
            expected_total += 1
            if day.strftime("%Y-%m-%d") not in days_present:
                absent[day.strftime("%Y-%m-%d")] = 1
            continue
        begin = opening.tz_convert(NY)
        if frequency == "1h":
            begin = begin.floor("h")
        expected = pd.date_range(begin, closing.tz_convert(NY), freq=frequency, inclusive="left")
        expected_total += len(expected)
        missing = expected.difference(index)
        if len(missing):
            absent[day.strftime("%Y-%m-%d")] = len(missing)
            samples.extend(str(t) for t in missing[: max(0, 20 - len(samples))])
    return {
        "contract": "us_equity_session_v2",
        "complete_sessions_requested": sessions,
        "expected_bars": expected_total,
        "missing_bars": sum(absent.values()),
        "incomplete_sessions": absent,
        "missing_timestamp_sample": samples,
        "complete": not absent,
        "partial_request_only": sessions == 0,
    }
