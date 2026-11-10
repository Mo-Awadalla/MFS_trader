"""Returns-blind audit for SPY Auction Value/Price Phase-Lag v29."""

from __future__ import annotations

import json
from datetime import time
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as xfeed
from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16

ROOT = Path(__file__).resolve().parents[1]
EQUS_SPY = (
    ROOT
    / "external_artifacts"
    / "databento_fractional_etf"
    / "EQUS.MINI"
    / "bars"
    / "spy_sh_ohlcv_1m_2023-03-28_2026-01-01.dbn.zst"
)
OUTPUT = (
    ROOT
    / "research_scout"
    / "spy_auction_value_price_phase_lag_returns_blind_audit_v29.json"
)


def block_state(block: pd.DataFrame) -> tuple[float, float]:
    typical = (block.high + block.low + block.close) / 3.0
    center = float((typical * block.volume).sum() / block.volume.sum())
    return center, float(block.iloc[-1].close)


def signal(bars: pd.DataFrame) -> int | None:
    first = bars.between_time("09:30", "09:59")
    second = bars.between_time("10:00", "10:29")
    dead = bars.between_time("10:30", "10:30")
    if len(first) != 30 or len(second) != 30 or len(dead) != 1:
        return None
    first_center, first_close = block_state(first)
    second_center, second_close = block_state(second)
    residual = (second_center - second_close) - (
        first_center - first_close
    )
    return int(residual > 0) - int(residual < 0)


def main() -> None:
    spy, arca, _, arca_excluded, _ = v16.load_old()
    equs_spy = base.split_sessions(base.load_dbn(EQUS_SPY, "SPY"))
    equs_excluded = xfeed.degraded(xfeed.EQUS_CONDITIONS)
    eligible = [
        day
        for day in sorted(spy)
        if day not in arca_excluded
        and v16.START <= day <= v16.DEVELOPMENT_END
    ]
    rows: list[dict[str, Any]] = []
    valid = 0
    for day in eligible:
        direction = signal(spy[day])
        if direction is None:
            continue
        valid += 1
        if direction == 0:
            continue
        symbol = "UPRO" if direction > 0 else "SPXU"
        quotes = arca.get(day, {}).get(symbol)
        available = False
        if quotes is not None:
            stamp = v16.stamp(day, time(10, 31), quotes.index.tz)
            available = base.quote_at(quotes, stamp, 0) is not None
        rows.append(
            {
                "date": day,
                "direction": direction,
                "available": available,
            }
        )
    frame = pd.DataFrame(rows)
    executable = frame[frame.available].copy()
    frequency = len(executable) / (3 * 52)
    minority = (
        min(
            int((executable.direction > 0).sum()),
            int((executable.direction < 0).sum()),
        )
        / max(len(executable), 1)
    )
    years = {
        str(year): int((executable.date.dt.year == year).sum())
        for year in [2021, 2022, 2023]
    }
    common = sorted(
        set(spy).intersection(equs_spy) - arca_excluded - equs_excluded
    )
    overlap = both = same = actions = 0
    for day in common:
        if not pd.Timestamp("2023-03-28") <= day <= v16.HOLDOUT_END:
            continue
        left = signal(spy[day])
        right = signal(equs_spy[day])
        la = 0 if left is None else left
        ra = 0 if right is None else right
        overlap += 1
        actions += int(la == ra)
        if la and ra:
            both += 1
            same += int(la == ra)
    direction_agreement = same / max(both, 1)
    action_agreement = actions / max(overlap, 1)
    coverage = valid / max(len(eligible), 1)
    availability = float(frame.available.mean()) if len(frame) else 0.0
    gates = {
        "measurement_coverage_at_least_98_percent": coverage >= 0.98,
        "at_least_four_entries_per_week": frequency >= 4.0,
        "every_year_at_least_150_entries": all(v >= 150 for v in years.values()),
        "minority_direction_at_least_30_percent": minority >= 0.30,
        "cross_feed_direction_agreement_at_least_85_percent": (
            direction_agreement >= 0.85
        ),
        "cross_feed_action_agreement_at_least_80_percent": (
            action_agreement >= 0.80
        ),
        "entry_quote_availability_at_least_95_percent": availability >= 0.95,
    }
    payload = {
        "status": "returns_blind_no_post_entry_prices_or_pnl_read",
        "eligible_sessions": len(eligible),
        "valid_measurements": valid,
        "measurement_coverage": coverage,
        "executable_entries": int(len(executable)),
        "entries_per_week": frequency,
        "direction_counts": {
            "UPRO": int((executable.direction > 0).sum()),
            "SPXU": int((executable.direction < 0).sum()),
        },
        "minority_direction_fraction": minority,
        "year_counts": years,
        "entry_quote_availability": availability,
        "cross_feed": {
            "overlap_dates": overlap,
            "both_signal_dates": both,
            "same_direction_fraction": direction_agreement,
            "same_action_fraction": action_agreement,
        },
        "gates": gates,
        "feasibility_passed": all(gates.values()),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
