"""Returns-blind audit for UPRO/SPXU signed inventory-flux persistence."""

from __future__ import annotations

import json
from datetime import time
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "research_scout"
    / "upro_spxu_signed_inventory_flux_returns_blind_audit_v25.json"
)
BLOCKS = {
    "first": ("09:31", "10:00"),
    "second": ("10:01", "10:30"),
}
MIN_EVENTS = 5


def fresh_rows(quotes: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    window = base.between(quotes, start, end).copy()
    valid = []
    for interval_end, row in window.iterrows():
        event_stamp = row.ts_event
        if pd.isna(event_stamp) or str(row.side) not in {"A", "B"}:
            valid.append(False)
            continue
        event_stamp = pd.Timestamp(event_stamp)
        if event_stamp.tzinfo is None:
            event_stamp = event_stamp.tz_localize("UTC")
        event_stamp = event_stamp.tz_convert(interval_end.tz)
        valid.append(interval_end - pd.Timedelta(minutes=1) < event_stamp <= interval_end)
    return window.loc[valid]


def session_signal(
    pair: dict[str, pd.DataFrame],
) -> dict[str, Any] | None:
    if not {"UPRO", "SPXU"}.issubset(pair):
        return None
    scores: dict[str, float] = {}
    counts: dict[str, int] = {}
    for block, (start, end) in BLOCKS.items():
        wrapper_scores = []
        for symbol in ["UPRO", "SPXU"]:
            events = fresh_rows(pair[symbol], start, end)
            counts[f"{symbol}_{block}"] = len(events)
            if len(events) < MIN_EVENTS:
                return None
            signs = events.side.map({"B": 1.0, "A": -1.0})
            sizes = events["size"].astype(float)
            denominator = float(sizes.sum())
            if denominator <= 0:
                return None
            imbalance = float((signs * sizes).sum() / denominator)
            wrapper_scores.append(imbalance if symbol == "UPRO" else -imbalance)
        scores[block] = sum(wrapper_scores) / len(wrapper_scores)
    first = scores["first"]
    second = scores["second"]
    direction = (
        1
        if first > 0 and second > 0
        else -1
        if first < 0 and second < 0
        else 0
    )
    return {
        "direction": direction,
        "scores": scores,
        "counts": counts,
    }


def main() -> None:
    _, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    rows: list[dict[str, Any]] = []
    eligible_dates = [
        day
        for day in sorted(arca)
        if day not in arca_excluded
        and v16.START <= day <= v16.DEVELOPMENT_END
    ]
    valid_measurements = 0
    for day in eligible_dates:
        state = session_signal(arca[day])
        if state is None:
            continue
        valid_measurements += 1
        direction = int(state["direction"])
        if direction == 0:
            continue
        symbol = "UPRO" if direction > 0 else "SPXU"
        quotes = arca[day].get(symbol)
        available = False
        if quotes is not None:
            stamp = v16.stamp(day, time(10, 31), quotes.index.tz)
            available = base.quote_at(quotes, stamp, 0) is not None
        rows.append(
            {
                "date": day,
                "direction": direction,
                "symbol": symbol,
                "available": available,
                **state["counts"],
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
    year_counts = {
        str(year): int((executable.date.dt.year == year).sum())
        for year in [2021, 2022, 2023]
    }
    cell_medians = {
        column: float(executable[column].median())
        for column in [
            "UPRO_first",
            "SPXU_first",
            "UPRO_second",
            "SPXU_second",
        ]
    }

    common_dates = sorted(
        set(arca).intersection(equs) - arca_excluded - equs_excluded
    )
    overlap_dates = 0
    both_signal = 0
    same_direction = 0
    same_action = 0
    for day in common_dates:
        if not pd.Timestamp("2023-03-28") <= day <= v16.HOLDOUT_END:
            continue
        left = session_signal(arca[day])
        right = session_signal(equs[day])
        left_action = 0 if left is None else int(left["direction"])
        right_action = 0 if right is None else int(right["direction"])
        overlap_dates += 1
        same_action += int(left_action == right_action)
        if left_action != 0 and right_action != 0:
            both_signal += 1
            same_direction += int(left_action == right_action)
    direction_agreement = same_direction / max(both_signal, 1)
    action_agreement = same_action / max(overlap_dates, 1)
    measurement_coverage = valid_measurements / max(len(eligible_dates), 1)
    quote_availability = (
        float(frame.available.mean()) if len(frame) else 0.0
    )
    gates = {
        "valid_measurement_coverage_at_least_90_percent": (
            measurement_coverage >= 0.90
        ),
        "at_least_two_entries_per_week": frequency >= 2.0,
        "minority_direction_at_least_20_percent": minority >= 0.20,
        "every_development_year_at_least_100_entries": all(
            value >= 100 for value in year_counts.values()
        ),
        "median_events_at_least_ten_in_every_cell": all(
            value >= 10 for value in cell_medians.values()
        ),
        "cross_feed_direction_agreement_at_least_65_percent": (
            direction_agreement >= 0.65
        ),
        "cross_feed_action_agreement_at_least_55_percent": action_agreement
        >= 0.55,
        "entry_quote_availability_at_least_95_percent": (
            quote_availability >= 0.95
        ),
    }
    payload = {
        "status": "returns_blind_no_post_entry_prices_or_pnl_read",
        "eligible_development_sessions": len(eligible_dates),
        "valid_measurements": valid_measurements,
        "measurement_coverage": measurement_coverage,
        "executable_entries": int(len(executable)),
        "entries_per_week": frequency,
        "direction_counts": {
            "UPRO": int((executable.direction > 0).sum()),
            "SPXU": int((executable.direction < 0).sum()),
        },
        "minority_direction_fraction": minority,
        "year_counts": year_counts,
        "median_fresh_events_by_cell": cell_medians,
        "entry_quote_availability": quote_availability,
        "cross_feed": {
            "overlap_dates": overlap_dates,
            "both_signal_dates": both_signal,
            "same_direction_fraction": direction_agreement,
            "same_action_fraction": action_agreement,
        },
        "gates": gates,
        "feasibility_passed": all(gates.values()),
    }
    OUTPUT.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
