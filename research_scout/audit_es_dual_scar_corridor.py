"""Returns-blind feasibility audit for ES dual-scar corridor completion."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from research_scout import test_es_scar_to_leveraged_etf as v20
from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "es_dual_scar_corridor_returns_blind_audit_v21.json"


def adverse_levels(state: dict[str, object]) -> tuple[float, float]:
    side = int(state["side"])
    center = float(state["center"])
    anchor = float(state["anchor"])
    stop_raw = center - side * v20.scar.TICK_SIZE
    target_raw = 2.0 * center - anchor
    if side > 0:
        stop = math.floor(stop_raw / v20.scar.TICK_SIZE) * v20.scar.TICK_SIZE
        target = math.ceil(target_raw / v20.scar.TICK_SIZE) * v20.scar.TICK_SIZE
    else:
        stop = math.ceil(stop_raw / v20.scar.TICK_SIZE) * v20.scar.TICK_SIZE
        target = math.floor(target_raw / v20.scar.TICK_SIZE) * v20.scar.TICK_SIZE
    return stop, target


def build_states() -> dict[pd.Timestamp, dict[str, object]]:
    sessions = v20.scar.load_sessions()
    scars = {day: v20.scar.closing_scar(day) for day, _ in sessions}
    result: dict[pd.Timestamp, dict[str, object]] = {}
    for index in range(1, len(sessions)):
        day, bars = sessions[index]
        prior = scars.get(sessions[index - 1][0])
        if prior is None:
            continue
        anchor, instrument = prior
        ids = pd.unique(bars.iloc[:30].instrument_id)
        if len(ids) != 1 or int(ids[0]) != instrument:
            continue
        center = v20.scar.center(bars.iloc[:30])
        close = float(bars.iloc[29].close)
        side = 1 if center > anchor and close > anchor else -1 if center < anchor and close < anchor else 0
        if not side:
            continue
        state: dict[str, object] = {
            "side": side,
            "center": center,
            "anchor": anchor,
            "bars": bars,
        }
        stop, target = adverse_levels(state)
        dead = bars.iloc[30]
        stop_hit = float(dead.low) <= stop if side > 0 else float(dead.high) >= stop
        target_hit = float(dead.high) >= target if side > 0 else float(dead.low) <= target
        if not stop_hit and not target_hit:
            result[day] = state
    return result


def main() -> None:
    states = build_states()
    _, arca, _, excluded, _ = v16.load_old()
    rows = []
    for day, state in sorted(states.items()):
        if day in excluded or not v16.START <= day <= v16.DEVELOPMENT_END:
            continue
        symbol = "UPRO" if int(state["side"]) > 0 else "SPXU"
        quotes = arca.get(day, {}).get(symbol)
        available = False
        if quotes is not None:
            stamp = v16.stamp(day, v20.time(10, 1), quotes.index.tz)
            available = base.quote_at(quotes, stamp, 0) is not None
        rows.append({"date": day, "side": int(state["side"]), "available": available})
    frame = pd.DataFrame(rows)
    available = frame[frame.available]
    weeks = 156.0
    frequency = len(available) / weeks
    minority = float(
        min((available.side > 0).sum(), (available.side < 0).sum())
        / max(len(available), 1)
    )
    availability = float(frame.available.mean()) if len(frame) else 0.0
    year_counts = {str(year): int((available.date.dt.year == year).sum()) for year in [2021, 2022, 2023]}
    gates = {
        "at_least_two_entries_per_week": frequency >= 2.0,
        "minority_direction_at_least_20_percent": minority >= 0.20,
        "every_development_year_at_least_50_entries": all(value >= 50 for value in year_counts.values()),
        "entry_quote_availability_at_least_95_percent": availability >= 0.95,
    }
    payload = {
        "status": "returns_blind_no_post_entry_prices_or_pnl_read",
        "candidate_sessions": len(frame),
        "available_entries": len(available),
        "entries_per_week": frequency,
        "direction_counts": {
            "UPRO": int((available.side > 0).sum()),
            "SPXU": int((available.side < 0).sum()),
        },
        "minority_fraction": float(minority),
        "entry_quote_availability": availability,
        "year_counts": year_counts,
        "gates": gates,
        "feasibility_passed": all(gates.values()),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
