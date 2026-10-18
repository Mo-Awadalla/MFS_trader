"""Explicit, timestamped sector and correlation evidence for portfolio risk."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol


@dataclass(frozen=True)
class RiskMetadataSnapshot:
    sectors: dict[str, str]
    correlations: dict[str, dict[str, float]]
    observed_at: datetime
    source: str

    def validate(
        self,
        symbols: Sequence[str],
        *,
        now: datetime | None = None,
        max_age: timedelta = timedelta(seconds=60),
    ) -> None:
        now = now or datetime.now(UTC)
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("risk metadata observation timestamp must be timezone-aware")
        if not self.source.strip():
            raise ValueError("risk metadata source is missing")
        age = now.astimezone(UTC) - self.observed_at.astimezone(UTC)
        if age < timedelta(0) or age > max_age:
            raise ValueError(f"risk metadata is stale or future-dated ({age.total_seconds():.3f}s)")
        required = set(symbols)
        absent_sector = sorted(symbol for symbol in required if not self.sectors.get(symbol, "").strip())
        if absent_sector:
            raise ValueError(f"sector metadata missing for symbols: {', '.join(absent_sector)}")
        absent_rows = sorted(symbol for symbol in required if symbol not in self.correlations)
        if absent_rows:
            raise ValueError(f"correlation rows missing for symbols: {', '.join(absent_rows)}")
        for left in required:
            row = self.correlations[left]
            absent = required - set(row)
            if absent:
                raise ValueError(
                    f"correlation evidence missing {left} vs {', '.join(sorted(absent))}"
                )
            for right in required:
                try:
                    value = float(row[right])
                except (TypeError, ValueError, KeyError) as error:
                    raise ValueError(f"invalid correlation evidence for {left}/{right}") from error
                if not math.isfinite(value) or not -1.0 <= value <= 1.0:
                    raise ValueError(f"invalid correlation value for {left}/{right}")


class RiskMetadataProvider(Protocol):
    def get_risk_metadata(self, symbols: Sequence[str]) -> RiskMetadataSnapshot: ...
