"""Declared, versioned exchange calendar for paper-run cycle accounting.

The paper loop derives *expected* bar cycles from this calendar instead of
counting loop iterations. The calendar is intentionally small and explicit:

- ``calendar_id`` / ``version`` are recorded in every paper evidence artifact
  so a qualification can be re-derived against the same declaration.
- Coverage is limited to the declared years. Any query outside the coverage
  range raises ``CalendarCoverageError`` (fail closed) instead of guessing.
- Sessions are XNYS-style: weekdays, minus NYSE full-day holidays, with
  13:00 America/New_York early closes. Open/close instants are converted to
  UTC through ``zoneinfo`` so DST transitions are handled by the tz database.

Only pandas and the standard library are used; no market-calendar dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

NEW_YORK = ZoneInfo("America/New_York")


class CalendarCoverageError(ValueError):
    """Raised when a calendar query falls outside the declared coverage."""


class UnsupportedCadenceError(ValueError):
    """Raised when a bar frequency cannot be mapped onto the calendar."""


@dataclass(frozen=True)
class MarketSession:
    session_date: date
    open_utc: datetime
    close_utc: datetime
    early_close: bool


@dataclass(frozen=True)
class ExpectedCycle:
    """One calendar-derived bar cycle the paper loop is expected to complete."""

    cycle_key: str
    market_session: str
    bar_start_utc: datetime
    expected_at: datetime

    def deadline(self, grace: timedelta) -> datetime:
        return self.expected_at + grace


@dataclass(frozen=True)
class MarketCalendar:
    calendar_id: str
    version: str
    timezone: str
    coverage_start: date
    coverage_end: date
    regular_open: time
    regular_close: time
    early_close: time
    holidays: frozenset[date]
    early_closes: frozenset[date]

    def declaration(self) -> dict[str, str]:
        return {
            "calendar_id": self.calendar_id,
            "version": self.version,
            "timezone": self.timezone,
            "coverage_start": self.coverage_start.isoformat(),
            "coverage_end": self.coverage_end.isoformat(),
        }

    def _require_covered(self, day: date) -> None:
        if not (self.coverage_start <= day <= self.coverage_end):
            raise CalendarCoverageError(
                f"{self.calendar_id} {self.version} covers "
                f"{self.coverage_start.isoformat()}..{self.coverage_end.isoformat()}; "
                f"{day.isoformat()} is outside the declared coverage"
            )

    def is_session(self, day: date) -> bool:
        self._require_covered(day)
        return day.weekday() < 5 and day not in self.holidays

    def session(self, day: date) -> MarketSession:
        if not self.is_session(day):
            raise ValueError(f"{day.isoformat()} is not a {self.calendar_id} session")
        tz = ZoneInfo(self.timezone)
        early = day in self.early_closes
        close_local = self.early_close if early else self.regular_close
        open_utc = datetime.combine(day, self.regular_open, tzinfo=tz).astimezone(UTC)
        close_utc = datetime.combine(day, close_local, tzinfo=tz).astimezone(UTC)
        return MarketSession(day, open_utc, close_utc, early)

    def sessions_between(self, start: date, end: date) -> list[MarketSession]:
        """Sessions with ``start <= session_date <= end`` (both inclusive)."""
        self._require_covered(start)
        self._require_covered(end)
        sessions: list[MarketSession] = []
        day = start
        while day <= end:
            if self.is_session(day):
                sessions.append(self.session(day))
            day += timedelta(days=1)
        return sessions

    def expected_cycles(
        self,
        frequency: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[ExpectedCycle]:
        """Expected cycles whose ``expected_at`` lies in ``[start_utc, end_utc]``."""
        if end_utc < start_utc:
            return []
        step = cadence(frequency)
        first_day = start_utc.astimezone(NEW_YORK).date()
        last_day = end_utc.astimezone(NEW_YORK).date()
        cycles: list[ExpectedCycle] = []
        for session in self.sessions_between(first_day, last_day):
            for cycle in _session_cycles(session, step):
                if start_utc <= cycle.expected_at <= end_utc:
                    cycles.append(cycle)
        return cycles

    def cycle_for_bar(self, frequency: str, bar_timestamp: pd.Timestamp) -> ExpectedCycle | None:
        """Map a bar label onto its expected cycle, or ``None`` if ineligible.

        Daily bars are labelled by the UTC calendar date of the session (the
        Alpaca convention also relied on by ``completed_daily_bars``).
        Intraday bars are labelled by their start instant.
        """
        ts = _as_utc(bar_timestamp)
        step = cadence(frequency)
        if step is None:
            day = ts.date()
            if not self.is_session(day):
                return None
            return _daily_cycle(self.session(day))
        day = ts.astimezone(NEW_YORK).date()
        if not self.is_session(day):
            return None
        session = self.session(day)
        for cycle in _session_cycles(session, step):
            if cycle.bar_start_utc == ts.to_pydatetime():
                return cycle
        return None


def cadence(frequency: str) -> timedelta | None:
    """Return the intraday bar length, or ``None`` for one bar per session."""
    normalized = frequency.strip().lower()
    if normalized in {"1d", "d", "day", "1day"}:
        return None
    unit_aliases = {"m": "min", "t": "min"}
    if normalized[-1:] in unit_aliases and normalized[:-1].isdigit():
        normalized = normalized[:-1] + unit_aliases[normalized[-1]]
    try:
        step = pd.Timedelta(normalized).to_pytimedelta()
    except ValueError as exc:
        raise UnsupportedCadenceError(f"unsupported paper bar frequency: {frequency!r}") from exc
    if step < timedelta(minutes=1) or step >= timedelta(days=1):
        raise UnsupportedCadenceError(f"unsupported paper bar frequency: {frequency!r}")
    return step


def default_data_grace(frequency: str) -> timedelta:
    """Grace after a cycle's expected time before fresh data is overdue.

    Daily bars are consumed only once the New York date has rolled over
    (``completed_daily_bars``), so the default allows the overnight gap.
    """
    step = cadence(frequency)
    return timedelta(hours=18) if step is None else step


def _daily_cycle(session: MarketSession) -> ExpectedCycle:
    key = session.session_date.isoformat()
    return ExpectedCycle(
        cycle_key=key,
        market_session=key,
        bar_start_utc=session.open_utc,
        expected_at=session.close_utc,
    )


def _session_cycles(session: MarketSession, step: timedelta | None) -> list[ExpectedCycle]:
    if step is None:
        return [_daily_cycle(session)]
    cycles: list[ExpectedCycle] = []
    start = session.open_utc
    while start < session.close_utc:
        end = min(start + step, session.close_utc)
        cycles.append(
            ExpectedCycle(
                cycle_key=start.isoformat(),
                market_session=session.session_date.isoformat(),
                bar_start_utc=start,
                expected_at=end,
            )
        )
        start += step
    return cycles


def _as_utc(value: pd.Timestamp | datetime | str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


_NYSE_HOLIDAYS = frozenset(
    date.fromisoformat(day)
    for day in (
        # 2024
        "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27",
        "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
        # 2025 (includes the 2025-01-09 national day of mourning closure)
        "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18",
        "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27",
        "2025-12-25",
        # 2026 (Independence Day observed Friday 2026-07-03)
        "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
        "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    )
)

_NYSE_EARLY_CLOSES = frozenset(
    date.fromisoformat(day)
    for day in (
        "2024-07-03", "2024-11-29", "2024-12-24",
        "2025-07-03", "2025-11-28", "2025-12-24",
        "2026-11-27", "2026-12-24",
    )
)

XNYS_PAPER_CALENDAR = MarketCalendar(
    calendar_id="XNYS-mfs",
    version="2026.1",
    timezone="America/New_York",
    coverage_start=date(2024, 1, 1),
    coverage_end=date(2026, 12, 31),
    regular_open=time(9, 30),
    regular_close=time(16, 0),
    early_close=time(13, 0),
    holidays=_NYSE_HOLIDAYS,
    early_closes=_NYSE_EARLY_CLOSES,
)

PAPER_CALENDARS = {
    (XNYS_PAPER_CALENDAR.calendar_id, XNYS_PAPER_CALENDAR.version): XNYS_PAPER_CALENDAR,
}


def resolve_calendar(calendar_id: str, version: str) -> MarketCalendar:
    try:
        return PAPER_CALENDARS[(calendar_id, version)]
    except KeyError as exc:
        raise CalendarCoverageError(
            f"undeclared paper calendar {calendar_id!r} version {version!r}"
        ) from exc
