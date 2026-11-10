"""Returns-blind audit for cross-inverse signed-impact asymmetry."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from research_scout import (
    audit_upro_spxu_cross_inverse_aggressor_relay as relay,
)
from research_scout import test_upro_spxu_creative_hypotheses as base

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "research_scout"
    / "upro_spxu_signed_impact_asymmetry_returns_blind_audit_v18.json"
)
START = "09:31"
END = "10:13"
MINIMUM_CELL_EVENTS = 3


def event_impacts(symbol: str, quotes: pd.DataFrame) -> dict[int, list[float]]:
    window = base.between(quotes, START, "10:14")
    leverage = 3.0 if symbol == "UPRO" else -3.0
    impacts: dict[int, list[float]] = {1: [], -1: []}
    for interval_end, row in base.between(quotes, START, END).iterrows():
        event_stamp = row.ts_event
        side = str(row.side)
        if pd.isna(event_stamp) or side not in {"A", "B"}:
            continue
        event_stamp = pd.Timestamp(event_stamp)
        if event_stamp.tzinfo is None:
            event_stamp = event_stamp.tz_localize("UTC")
        event_stamp = event_stamp.tz_convert(interval_end.tz)
        if not interval_end - pd.Timedelta(minutes=1) < event_stamp <= interval_end:
            continue
        current = base.exact_row(window, interval_end)
        following = base.exact_row(
            window,
            interval_end + pd.Timedelta(minutes=1),
        )
        if not base.valid_quote(current) or not base.valid_quote(following):
            continue
        current_mid = base.midpoint(current)
        following_mid = base.midpoint(following)
        if min(current_mid, following_mid) <= 0:
            continue
        wrapper_trade_sign = 1 if side == "B" else -1
        underlying_sign = wrapper_trade_sign * int(math.copysign(1, leverage))
        projected_return = math.log(following_mid / current_mid) / leverage
        impacts[underlying_sign].append(underlying_sign * projected_return)
    return impacts


def session_signal(pair: dict[str, pd.DataFrame]) -> dict[str, object] | None:
    if not {"UPRO", "SPXU"}.issubset(pair):
        return None
    by_symbol = {
        symbol: event_impacts(symbol, pair[symbol])
        for symbol in ["UPRO", "SPXU"]
    }
    cell_counts = [
        len(by_symbol[symbol][direction])
        for symbol in ["UPRO", "SPXU"]
        for direction in [1, -1]
    ]
    if min(cell_counts) < MINIMUM_CELL_EVENTS:
        return None
    directional_impact: dict[int, float] = {}
    for direction in [1, -1]:
        directional_impact[direction] = float(
            np.mean(
                [
                    np.mean(by_symbol[symbol][direction])
                    for symbol in ["UPRO", "SPXU"]
                ]
            )
        )
    score = directional_impact[1] - directional_impact[-1]
    return {
        "direction": int(score > 0) - int(score < 0),
        "score": score,
        "bullish_impact": directional_impact[1],
        "bearish_impact": directional_impact[-1],
        "minimum_cell_events": min(cell_counts),
    }


def signal_frame(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for day in sorted(sessions):
        if day in excluded or not 2021 <= day.year <= 2025:
            continue
        state = session_signal(sessions[day])
        if state is not None:
            rows.append({"date": day, **state})
    return pd.DataFrame(rows)


def counts(frame: pd.DataFrame, column: str = "direction") -> dict[str, int]:
    values = frame[column]
    return {
        "UPRO": int((values > 0).sum()),
        "SPXU": int((values < 0).sum()),
        "NO_TRADE": int((values == 0).sum()),
    }


def main() -> None:
    arca_sessions = relay.sessions(relay.ARCA_PATH)
    equs_sessions = relay.sessions(relay.EQUS_PATH)
    arca_excluded = relay.degraded(relay.ARCA_CONDITIONS)
    equs_excluded = relay.degraded(relay.EQUS_CONDITIONS)
    arca = signal_frame(arca_sessions, arca_excluded)
    equs = signal_frame(equs_sessions, equs_excluded)
    eligible = relay.eligible_feed_sessions(arca_sessions, arca_excluded)
    coverage = len(arca) / max(eligible, 1)
    nonzero = arca[arca.direction != 0]
    weeks = (
        (arca.date.max() - arca.date.min()).days / 7.0
        if len(arca) > 1
        else 0.0
    )
    signals_per_week = len(nonzero) / weeks if weeks > 0 else 0.0
    minority_fraction = (
        min(
            int((nonzero.direction > 0).sum()),
            int((nonzero.direction < 0).sum()),
        )
        / len(nonzero)
        if not nonzero.empty
        else 0.0
    )
    overlap = arca.merge(equs, on="date", suffixes=("_arca", "_equs"))
    both = overlap[
        (overlap.direction_arca != 0) & (overlap.direction_equs != 0)
    ]
    conditional_agreement = (
        float((both.direction_arca == both.direction_equs).mean())
        if not both.empty
        else 0.0
    )
    action_agreement = (
        float((overlap.direction_arca == overlap.direction_equs).mean())
        if not overlap.empty
        else 0.0
    )
    median_cell_events = (
        float(arca.minimum_cell_events.median()) if not arca.empty else 0.0
    )
    gates = {
        "valid_paired_states_at_least_90_percent": coverage >= 0.90,
        "at_least_two_nonzero_signals_per_week": signals_per_week >= 2.0,
        "minority_direction_at_least_20_percent": minority_fraction >= 0.20,
        "median_minimum_cell_events_at_least_ten": (
            median_cell_events >= 10.0
        ),
        "conditional_cross_feed_direction_agreement_at_least_60_percent": (
            conditional_agreement >= 0.60
        ),
        "all_date_cross_feed_action_agreement_at_least_50_percent": (
            action_agreement >= 0.50
        ),
    }
    payload = {
        "status": "returns_blind_no_post_signal_prices_or_pnl_read",
        "definition": {
            "fresh_trade_window": f"{START}-{END} ET",
            "response": "next BBO-minute midpoint log return",
            "underlying_projection": (
                "UPRO wrapper return divided by +3; SPXU divided by -3"
            ),
            "score": (
                "equally weighted wrapper mean own-direction impact for bullish "
                "events minus the equivalent bearish-event impact"
            ),
            "minimum_events_per_wrapper_direction_cell": MINIMUM_CELL_EVENTS,
        },
        "arca_2021_2025": {
            "eligible_feed_session_dates": eligible,
            "valid_state_sessions": int(len(arca)),
            "coverage_fraction": coverage,
            "nonzero_signal_sessions": int(len(nonzero)),
            "signals_per_calendar_week": signals_per_week,
            "direction_counts": counts(arca),
            "minority_direction_fraction": minority_fraction,
            "median_minimum_cell_events": median_cell_events,
            "year_signal_counts": {
                str(year): int(
                    ((arca.date.dt.year == year) & (arca.direction != 0)).sum()
                )
                for year in sorted(arca.date.dt.year.unique())
            },
        },
        "cross_feed_overlap_2023_2025": {
            "overlap_sessions": int(len(overlap)),
            "both_signal_sessions": int(len(both)),
            "conditional_direction_agreement": conditional_agreement,
            "all_date_action_agreement": action_agreement,
            "arca_direction_counts": counts(overlap, "direction_arca"),
            "equs_direction_counts": counts(overlap, "direction_equs"),
            "score_correlation": (
                float(
                    np.corrcoef(
                        overlap.score_arca.astype(float),
                        overlap.score_equs.astype(float),
                    )[0, 1]
                )
                if len(overlap) > 1
                else 0.0
            ),
        },
        "predeclared_feasibility_gates": gates,
        "feasibility_passed": all(gates.values()),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
