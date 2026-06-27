"""Strategy template contract — shared plug-in surface for every strategy.

Bollinger Bands (bollinger_bands:v2) is the reference implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

import numpy as np
import pandas as pd

ParamsT = TypeVar("ParamsT")


@dataclass(frozen=True)
class StrategyDiagnostics:
    """Reusable diagnostics for any strategy template."""

    bars: int
    warmup_bars: int
    raw_entry_events: int
    filtered_entry_events: int
    raw_exit_events: int
    filtered_exit_events: int
    entry_signals: int
    exit_signals: int
    bars_held_long: int
    bars_held_short: int
    pct_time_invested: float
    avg_holding_period_bars: float
    turnover: float
    rejected_by_reason: dict[str, int] = field(default_factory=dict)
    nan_position_bars: int = 0
    execution_mode: str = "next_bar_open"
    entry_signal_timestamps: tuple[str, ...] = ()
    exit_signal_timestamps: tuple[str, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bars": self.bars,
            "warmup_bars": self.warmup_bars,
            "raw_entry_events": self.raw_entry_events,
            "filtered_entry_events": self.filtered_entry_events,
            "raw_exit_events": self.raw_exit_events,
            "filtered_exit_events": self.filtered_exit_events,
            "entry_signals": self.entry_signals,
            "exit_signals": self.exit_signals,
            "bars_held_long": self.bars_held_long,
            "bars_held_short": self.bars_held_short,
            "pct_time_invested": self.pct_time_invested,
            "avg_holding_period_bars": self.avg_holding_period_bars,
            "turnover": self.turnover,
            "rejected_by_reason": self.rejected_by_reason,
            "nan_position_bars": self.nan_position_bars,
            "execution_mode": self.execution_mode,
            "entry_signal_timestamps": list(self.entry_signal_timestamps),
            "exit_signal_timestamps": list(self.exit_signal_timestamps),
            "extra": self.extra,
        }


class StrategyTemplate(ABC, Generic[ParamsT]):
    """Required surface — every strategy template implements this."""

    name: str
    template_version: str

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame, params: ParamsT) -> pd.DataFrame: ...

    @abstractmethod
    def default_params(self) -> ParamsT: ...

    @abstractmethod
    def sweep_grid(self) -> list[ParamsT]: ...

    @abstractmethod
    def compact_sweep_grid(self) -> list[ParamsT]: ...

    @abstractmethod
    def diagnose_signals(self, df: pd.DataFrame, params: ParamsT) -> StrategyDiagnostics: ...

    @abstractmethod
    def validate_inputs(self, df: pd.DataFrame) -> None: ...

    @abstractmethod
    def required_columns(self) -> tuple[str, ...]: ...

    @abstractmethod
    def warmup_bars(self, params: ParamsT) -> int: ...

    @abstractmethod
    def supports_long(self) -> bool: ...

    @abstractmethod
    def supports_short(self) -> bool: ...

    @abstractmethod
    def metadata(self) -> dict[str, Any]: ...

    @property
    def strategy_template_version(self) -> str:
        return f"{self.name}:{self.template_version}"


def validate_ohlcv_inputs(
    df: pd.DataFrame,
    required: tuple[str, ...] = ("open", "high", "low", "close", "volume"),
) -> None:
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("OHLCV DataFrame must have a DatetimeIndex")


def diagnose_from_signal_frame(
    signals: pd.DataFrame,
    *,
    bars: int,
    warmup_bars: int,
    raw_entry_col: str,
    raw_exit_col: str,
    filter_col: str | None = None,
    rejected_by_reason: dict[str, int] | None = None,
    extra: dict[str, Any] | None = None,
    include_signal_timestamps: bool = True,
) -> StrategyDiagnostics:
    """Build standard diagnostics from a strategy signal DataFrame."""
    empty = StrategyDiagnostics(
        bars=bars,
        warmup_bars=warmup_bars,
        raw_entry_events=0,
        filtered_entry_events=0,
        raw_exit_events=0,
        filtered_exit_events=0,
        entry_signals=0,
        exit_signals=0,
        bars_held_long=0,
        bars_held_short=0,
        pct_time_invested=0.0,
        avg_holding_period_bars=0.0,
        turnover=0.0,
        rejected_by_reason=rejected_by_reason or {},
        extra=extra or {},
    )
    if signals.empty or "position" not in signals.columns or "signal" not in signals.columns:
        return empty

    position = signals["position"]
    signal = signals["signal"]
    raw_entries = int(signals[raw_entry_col].sum()) if raw_entry_col in signals.columns else 0
    raw_exits = int(signals[raw_exit_col].sum()) if raw_exit_col in signals.columns else 0
    reject_reasons = dict(rejected_by_reason or {})

    if filter_col and filter_col in signals.columns:
        allowed = signals[filter_col].fillna(False)
        filtered_entries = int((signals[raw_entry_col] & allowed).sum()) if raw_entry_col in signals.columns else 0
        rejected = raw_entries - filtered_entries
        if rejected > 0:
            reject_reasons["width_filter"] = reject_reasons.get("width_filter", 0) + rejected
    else:
        filtered_entries = raw_entries

    filtered_exits = raw_exits

    bars_long = int((position == 1).sum())
    bars_short = int((position == -1).sum())
    invested = bars_long + bars_short
    pct_invested = round(100.0 * invested / len(signals), 2) if len(signals) else 0.0
    turnover = float(signal.abs().sum())

    holding_periods: list[int] = []
    in_leg = False
    leg_start = 0
    for i, pos in enumerate(position.tolist()):
        if pos == 1 and not in_leg:
            in_leg = True
            leg_start = i
        elif pos != 1 and in_leg:
            holding_periods.append(i - leg_start)
            in_leg = False
    if in_leg:
        holding_periods.append(len(position) - leg_start)
    avg_hold = float(np.mean(holding_periods)) if holding_periods else 0.0

    entry_ts: tuple[str, ...] = ()
    exit_ts: tuple[str, ...] = ()
    if include_signal_timestamps:
        entry_ts = tuple(str(ts) for ts in signals.index[signal == 1])
        exit_ts = tuple(str(ts) for ts in signals.index[signal == -1])

    return StrategyDiagnostics(
        bars=bars,
        warmup_bars=warmup_bars,
        raw_entry_events=raw_entries,
        filtered_entry_events=filtered_entries,
        raw_exit_events=raw_exits,
        filtered_exit_events=filtered_exits,
        entry_signals=int((signal == 1).sum()),
        exit_signals=int((signal == -1).sum()),
        bars_held_long=bars_long,
        bars_held_short=bars_short,
        pct_time_invested=pct_invested,
        avg_holding_period_bars=round(avg_hold, 2),
        turnover=turnover,
        rejected_by_reason=reject_reasons,
        nan_position_bars=int(position.isna().sum()),
        entry_signal_timestamps=entry_ts,
        exit_signal_timestamps=exit_ts,
        extra=extra or {},
    )


def assert_exit_contract(
    signals: pd.DataFrame,
    *,
    raw_exit_col: str,
    allow_same_bar_reentry: bool = False,
) -> None:
    """Exit invariant: raw exit while long must flatten position unless re-entry allowed."""
    if signals.empty or raw_exit_col not in signals.columns:
        return

    position = signals["position"]
    raw_exit = signals[raw_exit_col].fillna(False)
    signal = signals["signal"] if "signal" in signals.columns else position.diff().fillna(0)

    for i in range(1, len(signals)):
        if not raw_exit.iloc[i] or position.iloc[i - 1] != 1:
            continue
        if allow_same_bar_reentry and signal.iloc[i] == 1:
            continue
        if position.iloc[i] != 0:
            raise AssertionError(
                f"Exit contract violated at {signals.index[i]}: "
                f"raw exit while long but position={position.iloc[i]}"
            )
