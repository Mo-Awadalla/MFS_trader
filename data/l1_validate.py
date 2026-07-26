"""Quality gates for irregular Level-1 trade and quote event data."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from data.validate import QualityResult, ValidationIssue

_INGESTION_COLUMNS = {"ingestion_run_id", "page_index", "row_index"}

TRADE_COLUMNS = {
    "symbol",
    "timestamp",
    "raw_timestamp",
    "trade_id",
    "exchange",
    "price",
    "size",
    "conditions",
    "tape",
}
QUOTE_COLUMNS = {
    "symbol",
    "timestamp",
    "raw_timestamp",
    "ask_exchange",
    "ask_price",
    "ask_size",
    "bid_exchange",
    "bid_price",
    "bid_size",
    "conditions",
    "tape",
}


@dataclass
class L1ValidationReport:
    """Event-specific validation result with JSON-safe statistics."""

    symbol: str
    source: str
    event_type: str
    result: QualityResult = QualityResult.PASS
    events_checked: int = 0
    issues: list[ValidationIssue] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def add(
        self,
        check: str,
        severity: QualityResult,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        issue = ValidationIssue(check, severity, message, details or {})
        self.issues.append(issue)
        if severity == QualityResult.FAIL:
            self.result = QualityResult.FAIL
        elif severity == QualityResult.WARN and self.result == QualityResult.PASS:
            self.result = QualityResult.WARN

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "source": self.source,
            "event_type": self.event_type,
            "result": self.result.value,
            "events_checked": self.events_checked,
            "stats": self.stats,
            "issues": [
                {
                    "check": issue.check,
                    "severity": issue.severity.value,
                    "message": issue.message,
                    "details": issue.details,
                }
                for issue in self.issues
            ],
        }


def validate_trades(
    frame: pd.DataFrame,
    *,
    symbol: str,
    source: str = "alpaca_iex",
    pagination_complete: bool = True,
    requested_start: str | pd.Timestamp | None = None,
    requested_end: str | pd.Timestamp | None = None,
) -> L1ValidationReport:
    report = L1ValidationReport(symbol, source, "trades", events_checked=len(frame))
    if not _check_common(frame, TRADE_COLUMNS, report, pagination_complete):
        return report
    _check_bounds(frame, report, requested_start, requested_end)

    bad_price = frame["price"].isna() | (frame["price"] <= 0)
    bad_size = frame["size"].isna() | (frame["size"] <= 0)
    invalid_count = int((bad_price | bad_size).sum())
    missing_identity = int(frame[["trade_id", "exchange", "tape"]].isna().any(axis=1).sum())
    report.stats.update(
        {"invalid_price_or_size": invalid_count, "missing_trade_identity_rows": missing_identity}
    )
    if invalid_count:
        report.add(
            "trade_values",
            QualityResult.FAIL,
            f"{invalid_count} trades have nonpositive or missing price/size",
            {"invalid_rows": invalid_count},
        )
    if missing_identity:
        report.add(
            "trade_identity",
            QualityResult.FAIL,
            f"{missing_identity} trades are missing vendor ID, exchange, or tape",
            {"missing_identity_rows": missing_identity},
        )

    identified = frame[frame["trade_id"].notna()].copy()
    identified["trading_date"] = identified["timestamp"].dt.date
    identity_columns = ["symbol", "trading_date", "exchange", "trade_id"]
    duplicate_ids = int(identified.duplicated(identity_columns, keep=False).sum())
    content_columns = [column for column in frame if column not in _INGESTION_COLUMNS]
    exact_duplicates = int(frame.duplicated(content_columns, keep=False).sum())
    report.stats.update(
        {"duplicate_trade_id_rows": duplicate_ids, "exact_duplicate_rows": exact_duplicates}
    )
    if duplicate_ids:
        report.add(
            "trade_identity",
            QualityResult.FAIL,
            f"{duplicate_ids} rows reuse a scoped vendor trade ID",
            {"duplicate_trade_id_rows": duplicate_ids},
        )
    elif exact_duplicates:
        report.add(
            "duplicates",
            QualityResult.WARN,
            f"{exact_duplicates} exact duplicate trade rows",
            {"exact_duplicate_rows": exact_duplicates},
        )
    return report


def validate_quotes(
    frame: pd.DataFrame,
    *,
    symbol: str,
    source: str = "alpaca_iex",
    pagination_complete: bool = True,
    requested_start: str | pd.Timestamp | None = None,
    requested_end: str | pd.Timestamp | None = None,
) -> L1ValidationReport:
    report = L1ValidationReport(symbol, source, "quotes", events_checked=len(frame))
    if not _check_common(frame, QUOTE_COLUMNS, report, pagination_complete):
        return report
    _check_bounds(frame, report, requested_start, requested_end)

    numeric_columns = ["ask_price", "ask_size", "bid_price", "bid_size"]
    missing_numeric = frame[numeric_columns].isna().any(axis=1)
    negative = (frame[numeric_columns] < 0).any(axis=1)
    ask_incoherent = (frame["ask_size"] > 0) & (frame["ask_price"] <= 0)
    bid_incoherent = (frame["bid_size"] > 0) & (frame["bid_price"] <= 0)
    invalid = missing_numeric | negative | ask_incoherent | bid_incoherent
    invalid_count = int(invalid.sum())
    missing_identity = frame["tape"].isna()
    missing_identity |= (frame["ask_size"] > 0) & frame["ask_exchange"].isna()
    missing_identity |= (frame["bid_size"] > 0) & frame["bid_exchange"].isna()
    missing_identity_count = int(missing_identity.sum())
    report.stats.update(
        {
            "invalid_quote_rows": invalid_count,
            "missing_quote_identity_rows": missing_identity_count,
        }
    )
    if invalid_count:
        report.add(
            "quote_values",
            QualityResult.FAIL,
            f"{invalid_count} quotes have missing, negative, or incoherent values",
            {"invalid_rows": invalid_count},
        )
    if missing_identity_count:
        report.add(
            "quote_identity",
            QualityResult.FAIL,
            f"{missing_identity_count} quotes are missing active-side exchange or tape",
            {"missing_identity_rows": missing_identity_count},
        )

    two_sided = (frame["ask_price"] > 0) & (frame["bid_price"] > 0)
    one_sided = ~two_sided & ~invalid
    locked = two_sided & (frame["ask_price"] == frame["bid_price"])
    crossed = two_sided & (frame["ask_price"] < frame["bid_price"])
    locked_count = int(locked.sum())
    crossed_count = int(crossed.sum())
    content_columns = [column for column in frame if column not in _INGESTION_COLUMNS]
    exact_duplicates = int(frame.duplicated(content_columns, keep=False).sum())
    report.stats.update(
        {
            "two_sided_quotes": int(two_sided.sum()),
            "one_sided_quotes": int(one_sided.sum()),
            "locked_quotes": locked_count,
            "crossed_quotes": crossed_count,
            "exact_duplicate_rows": exact_duplicates,
        }
    )
    if locked_count or crossed_count:
        report.add(
            "quote_market_state",
            QualityResult.WARN,
            f"Observed {locked_count} locked and {crossed_count} crossed IEX quotes",
            {"locked": locked_count, "crossed": crossed_count},
        )
    if exact_duplicates:
        report.add(
            "duplicates",
            QualityResult.WARN,
            f"{exact_duplicates} exact duplicate quote rows",
            {"exact_duplicate_rows": exact_duplicates},
        )
    return report


def _check_bounds(
    frame: pd.DataFrame,
    report: L1ValidationReport,
    requested_start: str | pd.Timestamp | None,
    requested_end: str | pd.Timestamp | None,
) -> None:
    if requested_start is None or requested_end is None:
        return
    start = pd.Timestamp(requested_start)
    end = pd.Timestamp(requested_end)
    start = start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
    end = end.tz_localize("UTC") if end.tzinfo is None else end.tz_convert("UTC")
    outside = (frame["timestamp"] < start) | (frame["timestamp"] > end)
    outside_count = int(outside.sum())
    report.stats["outside_requested_interval"] = outside_count
    if outside_count:
        report.add(
            "requested_interval",
            QualityResult.FAIL,
            f"{outside_count} events fall outside the inclusive requested interval",
            {"outside_requested_interval": outside_count},
        )


def _check_common(
    frame: pd.DataFrame,
    required: set[str],
    report: L1ValidationReport,
    pagination_complete: bool,
) -> bool:
    if not pagination_complete:
        report.add(
            "pagination",
            QualityResult.FAIL,
            "Download stopped before the final API page",
        )
    missing = required.difference(frame.columns)
    if missing:
        report.add(
            "schema",
            QualityResult.FAIL,
            f"Missing required columns: {sorted(missing)}",
            {"missing": sorted(missing)},
        )
        return False
    if frame.empty:
        report.add("completeness", QualityResult.FAIL, "Event frame is empty")
        return False

    timestamps = frame["timestamp"]
    if not isinstance(timestamps.dtype, pd.DatetimeTZDtype) or str(timestamps.dt.tz) != "UTC":
        report.add("timestamp", QualityResult.FAIL, "timestamp must be timezone-aware UTC")
        return False
    missing_timestamps = int(timestamps.isna().sum())
    out_of_order = int((timestamps.diff().dropna() < pd.Timedelta(0)).sum())
    report.stats.update(
        {
            "missing_timestamps": missing_timestamps,
            "out_of_order_events": out_of_order,
            "first_timestamp": timestamps.iloc[0].isoformat(),
            "last_timestamp": timestamps.iloc[-1].isoformat(),
        }
    )
    if missing_timestamps:
        report.add(
            "timestamp",
            QualityResult.FAIL,
            f"{missing_timestamps} events have missing timestamps",
        )
    if out_of_order:
        report.add(
            "ordering",
            QualityResult.FAIL,
            f"{out_of_order} events are out of timestamp order",
        )
    return True
