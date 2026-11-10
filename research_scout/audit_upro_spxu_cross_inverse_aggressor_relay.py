"""Returns-blind audit for the cross-inverse aggressor relay hypothesis."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from research_scout import test_upro_spxu_creative_hypotheses as base

ROOT = Path(__file__).resolve().parents[1]
ARCA_PATH = (
    ROOT
    / "external_artifacts"
    / "databento_leveraged_etf"
    / "ARCX.PILLAR"
    / "bbo"
    / "upro_spxu_bbo_1m_2021-01-01_2026-01-01.dbn.zst"
)
EQUS_PATH = (
    ROOT
    / "external_artifacts"
    / "databento_leveraged_etf"
    / "EQUS.MINI"
    / "bbo"
    / "upro_spxu_bbo_1m_2023-03-28_2026-01-01.dbn.zst"
)
ARCA_CONDITIONS = (
    ROOT
    / "external_artifacts"
    / "databento_fractional_etf"
    / "ARCX.PILLAR"
    / "dataset_condition_2021_2025.json"
)
EQUS_CONDITIONS = (
    ROOT
    / "external_artifacts"
    / "databento_fractional_etf"
    / "EQUS.MINI"
    / "dataset_condition_2023_2025.json"
)
OUTPUT = (
    ROOT
    / "research_scout"
    / "upro_spxu_cross_inverse_aggressor_relay_returns_blind_audit_v16.json"
)
START_CLOCK = "09:45"
END_CLOCK = "10:14"
MAX_RELAY_SECONDS = 120.0


@dataclass(frozen=True)
class Event:
    stamp: pd.Timestamp
    symbol: str
    underlying_sign: int


def degraded(path: Path) -> set[pd.Timestamp]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        pd.Timestamp(row["date"])
        for row in payload["conditions"]
        if row["condition"] == "degraded"
    }


def sessions(path: Path) -> dict[pd.Timestamp, dict[str, pd.DataFrame]]:
    frame = base.load_dbn(path)
    result: dict[pd.Timestamp, dict[str, pd.DataFrame]] = {}
    for symbol in ["UPRO", "SPXU"]:
        selected = frame[frame.symbol == symbol]
        for day, quotes in base.split_sessions(selected).items():
            result.setdefault(day, {})[symbol] = quotes
    return result


def fresh_events(symbol: str, quotes: pd.DataFrame) -> list[Event]:
    window = base.between(quotes, START_CLOCK, END_CLOCK)
    events: list[Event] = []
    wrapper_sign = 1 if symbol == "UPRO" else -1
    for interval_end, row in window.iterrows():
        event_stamp = row.ts_event
        if pd.isna(event_stamp) or str(row.side) not in {"A", "B"}:
            continue
        event_stamp = pd.Timestamp(event_stamp)
        if event_stamp.tzinfo is None:
            event_stamp = event_stamp.tz_localize("UTC")
        event_stamp = event_stamp.tz_convert(interval_end.tz)
        interval_start = interval_end - pd.Timedelta(minutes=1)
        if not interval_start < event_stamp <= interval_end:
            continue
        aggressor_sign = 1 if str(row.side) == "B" else -1
        events.append(
            Event(
                stamp=event_stamp,
                symbol=symbol,
                underlying_sign=wrapper_sign * aggressor_sign,
            )
        )
    return events


def session_signal(pair: dict[str, pd.DataFrame]) -> dict[str, object] | None:
    if not {"UPRO", "SPXU"}.issubset(pair):
        return None
    events = fresh_events("UPRO", pair["UPRO"])
    events.extend(fresh_events("SPXU", pair["SPXU"]))
    events.sort(key=lambda event: (event.stamp, event.symbol))
    relays: list[Event] = []
    for previous, current in zip(events, events[1:], strict=False):
        separation = (current.stamp - previous.stamp).total_seconds()
        if (
            current.symbol != previous.symbol
            and 0.0 < separation <= MAX_RELAY_SECONDS
            and current.underlying_sign == previous.underlying_sign
        ):
            relays.append(current)
    score = int(sum(event.underlying_sign for event in relays))
    return {
        "events": len(events),
        "relays": len(relays),
        "score": score,
        "direction": int(score > 0) - int(score < 0),
    }


def frame_for(
    feed: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for day in sorted(feed):
        if day in excluded or not 2021 <= day.year <= 2025:
            continue
        signal = session_signal(feed[day])
        if signal is not None:
            rows.append({"date": day, **signal})
    return pd.DataFrame(rows)


def eligible_feed_sessions(
    feed: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
) -> int:
    return sum(
        day not in excluded and 2021 <= day.year <= 2025 for day in feed
    )


def direction_counts(frame: pd.DataFrame) -> dict[str, int]:
    return {
        "UPRO": int((frame.direction > 0).sum()),
        "SPXU": int((frame.direction < 0).sum()),
        "NO_TRADE": int((frame.direction == 0).sum()),
    }


def main() -> None:
    arca_sessions = sessions(ARCA_PATH)
    equs_sessions = sessions(EQUS_PATH)
    arca_excluded = degraded(ARCA_CONDITIONS)
    equs_excluded = degraded(EQUS_CONDITIONS)
    arca = frame_for(arca_sessions, arca_excluded)
    equs = frame_for(equs_sessions, equs_excluded)
    nonzero = arca[arca.direction != 0]
    calendar_weeks = (
        (arca.date.max() - arca.date.min()).days / 7.0
        if len(arca) > 1
        else 0.0
    )
    overlap = arca.merge(equs, on="date", suffixes=("_arca", "_equs"))
    both_signal = overlap[
        (overlap.direction_arca != 0) & (overlap.direction_equs != 0)
    ]
    conditional_agreement = (
        float((both_signal.direction_arca == both_signal.direction_equs).mean())
        if not both_signal.empty
        else 0.0
    )
    action_agreement = (
        float((overlap.direction_arca == overlap.direction_equs).mean())
        if not overlap.empty
        else 0.0
    )
    arca_eligible_sessions = eligible_feed_sessions(
        arca_sessions,
        arca_excluded,
    )
    coverage_fraction = len(arca) / max(arca_eligible_sessions, 1)
    minority_fraction = (
        min(
            int((nonzero.direction > 0).sum()),
            int((nonzero.direction < 0).sum()),
        )
        / len(nonzero)
        if not nonzero.empty
        else 0.0
    )
    signals_per_week = (
        len(nonzero) / calendar_weeks if calendar_weeks > 0 else 0.0
    )
    gates = {
        "paired_session_coverage_at_least_95_percent": (
            coverage_fraction >= 0.95
        ),
        "at_least_two_nonzero_signals_per_week": signals_per_week >= 2.0,
        "minority_direction_at_least_20_percent": minority_fraction >= 0.20,
        "median_relays_at_least_ten": float(arca.relays.median()) >= 10.0,
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
            "window": f"{START_CLOCK}-{END_CLOCK} ET",
            "fresh_trade": (
                "ts_event must lie strictly after interval_end minus one minute "
                "and no later than interval_end"
            ),
            "side_mapping": (
                "B=buy aggressor, A=sell aggressor; multiply SPXU by -1"
            ),
            "relay": (
                "adjacent fresh events from different wrappers, same projected "
                "underlying sign, no more than 120 seconds apart"
            ),
            "score": "sum of projected signs across relays",
        },
        "arca_2021_2025": {
            "eligible_feed_session_dates": arca_eligible_sessions,
            "eligible_sessions": int(len(arca)),
            "coverage_fraction_of_feed_sessions": coverage_fraction,
            "nonzero_signal_sessions": int(len(nonzero)),
            "signals_per_calendar_week": signals_per_week,
            "direction_counts": direction_counts(arca),
            "minority_direction_fraction": minority_fraction,
            "median_fresh_events": float(arca.events.median()),
            "median_relays": float(arca.relays.median()),
            "relay_quantiles": {
                str(q): float(arca.relays.quantile(q))
                for q in [0.05, 0.25, 0.50, 0.75, 0.95]
            },
            "year_signal_counts": {
                str(year): int(
                    ((arca.date.dt.year == year) & (arca.direction != 0)).sum()
                )
                for year in sorted(arca.date.dt.year.unique())
            },
        },
        "cross_feed_overlap_2023_2025": {
            "overlap_sessions": int(len(overlap)),
            "both_signal_sessions": int(len(both_signal)),
            "conditional_direction_agreement": conditional_agreement,
            "all_date_action_agreement": action_agreement,
            "arca_direction_counts": direction_counts(
                overlap.rename(columns={"direction_arca": "direction"})
            ),
            "equs_direction_counts": direction_counts(
                overlap.rename(columns={"direction_equs": "direction"})
            ),
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
