"""Returns-blind feasibility audit for ES scar polarity flip v23."""

from __future__ import annotations

import json
import math
from datetime import time
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import test_es_scar_to_leveraged_etf as v20
from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "research_scout"
    / "es_scar_polarity_flip_returns_blind_audit_v23.json"
)
CONTACT_START = 30
CONTACT_END_EXCLUSIVE = 240


def clock(index: int) -> time:
    stamp = pd.Timestamp("2000-01-01 09:30") + pd.Timedelta(minutes=index)
    return stamp.time()


def adverse_center(center: float, side: int) -> float:
    tick = v20.scar.TICK_SIZE
    if side > 0:
        return math.floor(center / tick) * tick
    return math.ceil(center / tick) * tick


def event_for(state: dict[str, Any]) -> dict[str, Any] | None:
    bars = state["bars"]
    side = int(state["side"])
    anchor = float(state["anchor"])
    target = adverse_center(float(state["center"]), side)
    stop = anchor - side * v20.scar.TICK_SIZE
    if side > 0 and target <= anchor:
        return None
    if side < 0 and target >= anchor:
        return None
    contact_index = None
    for index in range(CONTACT_START, CONTACT_END_EXCLUSIVE):
        bar = bars.iloc[index]
        touched = float(bar.low) <= anchor if side > 0 else float(bar.high) >= anchor
        if touched:
            contact_index = index
            break
    if contact_index is None or contact_index + 1 >= len(bars):
        return None
    contact = bars.iloc[contact_index]
    rejected = (
        float(contact.close) > anchor
        and float(contact.low) > stop
        and float(contact.high) < target
        if side > 0
        else float(contact.close) < anchor
        and float(contact.high) < stop
        and float(contact.low) > target
    )
    if not rejected:
        return None
    dead = bars.iloc[contact_index + 1]
    invalidated = (
        float(dead.low) <= stop or float(dead.high) >= target
        if side > 0
        else float(dead.high) >= stop or float(dead.low) <= target
    )
    if invalidated:
        return None
    return {
        "side": side,
        "entry_index": contact_index + 2,
        "contact_index": contact_index,
        "anchor": anchor,
        "target": target,
        "stop": stop,
        "reward_risk": abs(target - anchor) / v20.scar.TICK_SIZE,
    }


def main() -> None:
    states = v20.states()
    _, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    candidates: list[dict[str, Any]] = []
    for day, state in sorted(states.items()):
        if day in arca_excluded or not v16.START <= day <= v16.DEVELOPMENT_END:
            continue
        event = event_for(state)
        if event is None:
            continue
        side = int(event["side"])
        symbol = "UPRO" if side > 0 else "SPXU"
        quotes = arca.get(day, {}).get(symbol)
        arca_entry = False
        if quotes is not None:
            stamp = v16.stamp(
                day,
                clock(int(event["entry_index"])),
                quotes.index.tz,
            )
            arca_entry = base.quote_at(quotes, stamp, 0) is not None
        eq_quotes = (
            equs.get(day, {}).get(symbol)
            if day not in equs_excluded
            else None
        )
        equs_entry = False
        if eq_quotes is not None:
            eq_stamp = v16.stamp(
                day,
                clock(int(event["entry_index"])),
                eq_quotes.index.tz,
            )
            equs_entry = base.quote_at(eq_quotes, eq_stamp, 0) is not None
        candidates.append(
            {
                "date": day,
                "side": side,
                "symbol": symbol,
                "entry_index": int(event["entry_index"]),
                "reward_risk": float(event["reward_risk"]),
                "arca_entry": arca_entry,
                "equs_entry": equs_entry,
            }
        )
    frame = pd.DataFrame(candidates)
    executable = frame[frame.arca_entry].copy()
    frequency = len(executable) / (3 * 52)
    availability = float(frame.arca_entry.mean()) if len(frame) else 0.0
    minority = (
        min(
            int((executable.side > 0).sum()),
            int((executable.side < 0).sum()),
        )
        / max(len(executable), 1)
    )
    year_counts = {
        str(year): int((executable.date.dt.year == year).sum())
        for year in [2021, 2022, 2023]
    }
    median_geometry = (
        float(executable.reward_risk.median()) if len(executable) else 0.0
    )
    overlap = executable[executable.date >= pd.Timestamp("2023-03-28")]
    gates = {
        "at_least_two_entries_per_week": frequency >= 2.0,
        "arca_entry_quote_availability_at_least_95_percent": availability
        >= 0.95,
        "minority_direction_at_least_20_percent": minority >= 0.20,
        "every_development_year_at_least_75_entries": all(
            value >= 75 for value in year_counts.values()
        ),
        "median_structural_reward_risk_at_least_four": median_geometry >= 4.0,
    }
    payload = {
        "status": "returns_blind_no_post_entry_etf_prices_or_pnl_read",
        "candidate_events": int(len(frame)),
        "executable_entries": int(len(executable)),
        "entries_per_week": frequency,
        "direction_counts": {
            "UPRO": int((executable.side > 0).sum()),
            "SPXU": int((executable.side < 0).sum()),
        },
        "minority_direction_fraction": minority,
        "year_counts": year_counts,
        "arca_entry_quote_availability": availability,
        "equs_overlap_entry_quote_availability": (
            float(overlap.equs_entry.mean()) if len(overlap) else 0.0
        ),
        "median_structural_reward_risk": median_geometry,
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
