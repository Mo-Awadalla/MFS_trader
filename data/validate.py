"""Data quality validation — PASS / WARN / FAIL gate.

Research data can tolerate flagged gaps if the strategy handles them.
Live data cannot — bad/stale latest bar = no signal = no trade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import pandas as pd


class QualityResult(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class ValidationIssue:
    check: str
    severity: QualityResult
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationReport:
    symbol: str
    source: str
    result: QualityResult
    issues: list[ValidationIssue] = field(default_factory=list)
    bars_checked: int = 0
    bars_failed: int = 0
    latest_bar_timestamp: str | None = None

    @property
    def checks_run(self) -> list[str]:
        return list({i.check for i in self.issues}) or ["all_passed"]

    @property
    def issues_json(self) -> list[dict[str, Any]]:
        return [
            {"check": i.check, "severity": i.severity.value, "message": i.message, "details": i.details}
            for i in self.issues
        ]

    def add(self, issue: ValidationIssue) -> None:
        self.issues.append(issue)
        if issue.severity == QualityResult.FAIL:
            self.result = QualityResult.FAIL
        elif issue.severity == QualityResult.WARN and self.result == QualityResult.PASS:
            self.result = QualityResult.WARN


def validate_ohlcv(
    df: pd.DataFrame,
    symbol: str,
    source: str,
    *,
    frequency: str = "1min",
    expected_interval_seconds: int = 60,
    is_live: bool = False,
    now_ts: pd.Timestamp | None = None,
) -> ValidationReport:
    """Run all quality checks on an OHLCV DataFrame.

    Args:
        df: DataFrame with DatetimeIndex and columns open/high/low/close/volume.
        symbol: Ticker or pair identifier.
        source: Data source tag (alpaca, ccxt_binance, etc.).
        frequency: Bar frequency label for logging.
        expected_interval_seconds: Expected seconds between bars.
        is_live: If True, apply stricter live rules (stale latest bar = FAIL).
        now_ts: Reference timestamp for staleness (defaults to current UTC).
    """
    report = ValidationReport(symbol=symbol, source=source, result=QualityResult.PASS)
    now_ts = now_ts or pd.Timestamp.now(tz="UTC")

    if df.empty:
        report.add(ValidationIssue("completeness", QualityResult.FAIL, "DataFrame is empty"))
        report.bars_checked = 0
        report.bars_failed = 0
        return report

    df = df.sort_index()
    report.bars_checked = len(df)
    report.latest_bar_timestamp = str(df.index[-1])

    _check_completeness(df, expected_interval_seconds, report)
    _check_staleness(df, expected_interval_seconds, now_ts, is_live, report)
    _check_duplicates(df, report)
    _check_ohlcv_sanity(df, report)
    _check_gap_detection(df, expected_interval_seconds, report)
    _check_volume(df, report)

    report.bars_failed = sum(1 for i in report.issues if i.severity == QualityResult.FAIL)
    return report


def _check_completeness(
    df: pd.DataFrame, expected_interval: int, report: ValidationReport
) -> None:
    if len(df) < 10:
        report.add(
            ValidationIssue(
                "completeness",
                QualityResult.WARN,
                f"Very few bars: {len(df)}",
                {"bar_count": len(df)},
            )
        )


def _check_staleness(
    df: pd.DataFrame,
    expected_interval: int,
    now_ts: pd.Timestamp,
    is_live: bool,
    report: ValidationReport,
) -> None:
    if df.empty:
        return
    latest = df.index[-1]
    if latest.tzinfo is None:
        latest = latest.tz_localize("UTC")
    age_seconds = (now_ts - latest).total_seconds()

    if is_live and age_seconds > expected_interval * 2:
        report.add(
            ValidationIssue(
                "staleness",
                QualityResult.FAIL,
                f"Latest bar is {age_seconds:.0f}s old (live threshold: {expected_interval * 2}s)",
                {"age_seconds": age_seconds, "latest": str(latest)},
            )
        )
    elif age_seconds > expected_interval * 100:
        report.add(
            ValidationIssue(
                "staleness",
                QualityResult.WARN,
                f"Latest bar is {age_seconds:.0f}s old",
                {"age_seconds": age_seconds, "latest": str(latest)},
            )
        )


def _check_duplicates(df: pd.DataFrame, report: ValidationReport) -> None:
    dup_mask = df.index.duplicated(keep=False)
    dup_count = dup_mask.sum()
    if dup_count == 0:
        return

    # Check if duplicates have identical values
    dups = df[dup_mask]
    grouped = dups.groupby(dups.index)
    conflicting = 0
    for _, group in grouped:
        if len(group.drop_duplicates()) > 1:
            conflicting += 1

    if conflicting > 0:
        report.add(
            ValidationIssue(
                "duplicates",
                QualityResult.FAIL,
                f"{conflicting} timestamps have conflicting duplicate rows",
                {"conflicting_duplicates": conflicting, "total_duplicate_rows": dup_count},
            )
        )
    else:
        report.add(
            ValidationIssue(
                "duplicates",
                QualityResult.WARN,
                f"{dup_count} exact duplicate rows (safe to dedupe)",
                {"exact_duplicates": dup_count},
            )
        )


def _check_ohlcv_sanity(df: pd.DataFrame, report: ValidationReport) -> None:
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        report.add(
            ValidationIssue(
                "schema",
                QualityResult.FAIL,
                f"Missing required columns: {missing}",
                {"missing": list(missing)},
            )
        )
        return

    # high >= max(open, close, low)
    # low <= min(open, close, high)
    # all prices > 0, volume >= 0
    bad_hl = (df["high"] < df[["open", "close", "low"]].max(axis=1)) | (
        df["low"] > df[["open", "close", "high"]].min(axis=1)
    )
    bad_prices = (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
    bad_volume = df["volume"] < 0

    bad_count = int((bad_hl | bad_prices | bad_volume).sum())
    if bad_count > 0:
        severity = QualityResult.FAIL if bad_count > len(df) * 0.05 else QualityResult.WARN
        report.add(
            ValidationIssue(
                "ohlcv_sanity",
                severity,
                f"{bad_count} bars have invalid OHLCV values",
                {"bad_bars": bad_count, "total": len(df)},
            )
        )
        report.bars_failed = bad_count


def _check_gap_detection(
    df: pd.DataFrame, expected_interval: int, report: ValidationReport
) -> None:
    if len(df) < 2:
        return
    diffs = df.index.to_series().diff().dropna()
    gaps = diffs[diffs > pd.Timedelta(seconds=expected_interval * 1.5)]
    if len(gaps) > 0:
        largest_gap = gaps.max()
        report.add(
            ValidationIssue(
                "gap_detection",
                QualityResult.WARN,
                f"{len(gaps)} gaps detected, largest: {largest_gap}",
                {"gap_count": len(gaps), "largest_gap_seconds": largest_gap.total_seconds()},
            )
        )


def _check_volume(df: pd.DataFrame, report: ValidationReport) -> None:
    if "volume" not in df.columns:
        return
    zero_vol = (df["volume"] == 0).sum()
    if zero_vol == len(df):
        report.add(
            ValidationIssue(
                "volume",
                QualityResult.FAIL,
                "All bars have zero volume",
                {"zero_volume_bars": zero_vol},
            )
        )
    elif zero_vol > len(df) * 0.5:
        report.add(
            ValidationIssue(
                "volume",
                QualityResult.WARN,
                f"{zero_vol} bars have zero volume (>50%)",
                {"zero_volume_bars": zero_vol},
            )
        )
