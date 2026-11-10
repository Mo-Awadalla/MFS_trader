"""Returns-blind audit for SH-to-SPXU leverage escalation latency v28."""

from __future__ import annotations

import json
from datetime import time
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_upro_spxu_signed_inventory_flux as flux
from research_scout import test_upro_sh_sensor_actuator as shdata
from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "research_scout"
    / "sh_spxu_leverage_escalation_latency_returns_blind_audit_v28.json"
)


def events(quotes: pd.DataFrame, symbol: str) -> list[dict[str, Any]]:
    fresh = flux.fresh_rows(quotes, "09:31", "10:30")
    output: list[dict[str, Any]] = []
    for interval_end, row in fresh.iterrows():
        stamp = pd.Timestamp(row.ts_event)
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        stamp = stamp.tz_convert(interval_end.tz)
        aggressor = 1 if str(row.side) == "B" else -1
        output.append(
            {
                "stamp": stamp,
                "sign": -aggressor,
                "symbol": symbol,
            }
        )
    return output


def matched_latencies(
    sh_events: list[dict[str, Any]],
    spxu_events: list[dict[str, Any]],
) -> dict[int, list[float]]:
    pending: dict[int, list[pd.Timestamp]] = {1: [], -1: []}
    combined = sorted(
        sh_events + spxu_events,
        key=lambda row: (row["stamp"], row["symbol"]),
    )
    latencies: dict[int, list[float]] = {1: [], -1: []}
    for event in combined:
        sign = int(event["sign"])
        if event["symbol"] == "SH":
            pending[sign].append(event["stamp"])
            continue
        if pending[sign]:
            prior = pending[sign].pop()
            seconds = (event["stamp"] - prior).total_seconds()
            if seconds > 0:
                latencies[sign].append(seconds)
    return latencies


def session_signal(
    sh_quotes: pd.DataFrame | None,
    spxu_quotes: pd.DataFrame | None,
) -> dict[str, Any] | None:
    if sh_quotes is None or spxu_quotes is None:
        return None
    latencies = matched_latencies(
        events(sh_quotes, "SH"),
        events(spxu_quotes, "SPXU"),
    )
    if min(len(latencies[1]), len(latencies[-1])) < 3:
        return None
    bullish = float(pd.Series(latencies[1]).median())
    bearish = float(pd.Series(latencies[-1]).median())
    direction = int(bullish < bearish) - int(bullish > bearish)
    return {
        "direction": direction,
        "bullish_matches": len(latencies[1]),
        "bearish_matches": len(latencies[-1]),
        "bullish_median_seconds": bullish,
        "bearish_median_seconds": bearish,
    }


def main() -> None:
    _, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    arca_sh = shdata.sh_sessions(shdata.SH_ARCA)
    equs_sh = shdata.sh_sessions(shdata.SH_EQUS)
    eligible = [
        day
        for day in sorted(set(arca).intersection(arca_sh))
        if day not in arca_excluded
        and v16.START <= day <= v16.DEVELOPMENT_END
    ]
    rows: list[dict[str, Any]] = []
    valid = 0
    for day in eligible:
        state = session_signal(
            arca_sh.get(day),
            arca[day].get("SPXU"),
        )
        if state is None:
            continue
        valid += 1
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
                "available": available,
                **state,
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
    median_matches = {
        "bullish": float(executable.bullish_matches.median()),
        "bearish": float(executable.bearish_matches.median()),
    }
    common = sorted(
        set(arca).intersection(equs).intersection(arca_sh).intersection(equs_sh)
        - arca_excluded
        - equs_excluded
    )
    overlap = both = same = actions = 0
    for day in common:
        if not pd.Timestamp("2023-03-28") <= day <= v16.HOLDOUT_END:
            continue
        left = session_signal(arca_sh.get(day), arca[day].get("SPXU"))
        right = session_signal(equs_sh.get(day), equs[day].get("SPXU"))
        la = 0 if left is None else int(left["direction"])
        ra = 0 if right is None else int(right["direction"])
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
        "valid_measurement_coverage_at_least_90_percent": coverage >= 0.90,
        "at_least_two_entries_per_week": frequency >= 2.0,
        "every_year_at_least_100_entries": all(v >= 100 for v in years.values()),
        "minority_direction_at_least_20_percent": minority >= 0.20,
        "median_matches_at_least_five_each_direction": all(
            value >= 5 for value in median_matches.values()
        ),
        "cross_feed_direction_agreement_at_least_65_percent": (
            direction_agreement >= 0.65
        ),
        "cross_feed_action_agreement_at_least_55_percent": (
            action_agreement >= 0.55
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
        "median_matched_transitions": median_matches,
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
