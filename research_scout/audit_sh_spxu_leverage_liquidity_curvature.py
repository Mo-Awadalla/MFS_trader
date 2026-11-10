"""Returns-blind audit for SH/SPXU leverage-liquidity curvature v33."""

from __future__ import annotations

import json
from datetime import time
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import test_upro_sh_sensor_actuator as shdata
from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "research_scout"
    / "sh_spxu_leverage_liquidity_curvature_returns_blind_audit_v33.json"
)


def block_spread(
    quotes: pd.DataFrame,
    start: str,
    end: str,
) -> dict[str, float] | None:
    block = quotes.between_time(start, end).copy()
    midpoint = (block.bid_px_00 + block.ask_px_00) / 2.0
    valid = block[
        (block.bid_px_00 > 0)
        & (block.ask_px_00 >= block.bid_px_00)
        & (midpoint > 0)
    ].copy()
    if len(valid) < 12:
        return None
    valid_midpoint = (valid.bid_px_00 + valid.ask_px_00) / 2.0
    spread = (valid.ask_px_00 - valid.bid_px_00) / valid_midpoint
    median = float(spread.median())
    if median <= 0:
        return None
    return {"median": median, "rows": float(len(valid))}


def session_signal(
    sh_quotes: pd.DataFrame | None,
    spxu_quotes: pd.DataFrame | None,
) -> dict[str, Any] | None:
    if sh_quotes is None or spxu_quotes is None:
        return None
    sh_first = block_spread(sh_quotes, "09:45", "09:59")
    sh_second = block_spread(sh_quotes, "10:00", "10:14")
    spxu_first = block_spread(spxu_quotes, "09:45", "09:59")
    spxu_second = block_spread(spxu_quotes, "10:00", "10:14")
    blocks = [sh_first, sh_second, spxu_first, spxu_second]
    if any(block is None for block in blocks):
        return None
    assert sh_first is not None
    assert sh_second is not None
    assert spxu_first is not None
    assert spxu_second is not None
    first = spxu_first["median"] / sh_first["median"]
    second = spxu_second["median"] / sh_second["median"]
    direction = 1 if second < first else -1 if second > first else 0
    return {
        "direction": direction,
        "first_surcharge": first,
        "second_surcharge": second,
        "sh_first_spread": sh_first["median"],
        "sh_second_spread": sh_second["median"],
        "spxu_first_spread": spxu_first["median"],
        "spxu_second_spread": spxu_second["median"],
        "minimum_valid_rows": min(block["rows"] for block in blocks),
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
    valid_measurements = 0
    minimum_rows: list[float] = []
    for day in eligible:
        state = session_signal(
            arca_sh.get(day),
            arca[day].get("SPXU"),
        )
        if state is None:
            continue
        valid_measurements += 1
        minimum_rows.append(float(state["minimum_valid_rows"]))
        direction = int(state["direction"])
        if direction == 0:
            continue
        symbol = "UPRO" if direction > 0 else "SPXU"
        quotes = arca[day].get(symbol)
        available = False
        if quotes is not None:
            stamp = v16.stamp(day, time(10, 16), quotes.index.tz)
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
    executable = (
        frame.copy() if frame.empty else frame[frame.available].copy()
    )
    frequency = len(executable) / (3 * 52)
    minority = (
        min(
            int((executable.direction > 0).sum()),
            int((executable.direction < 0).sum()),
        )
        / max(len(executable), 1)
        if len(executable)
        else 0.0
    )
    years = {
        str(year): int((executable.date.dt.year == year).sum())
        if len(executable)
        else 0
        for year in [2021, 2022, 2023]
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
    coverage = valid_measurements / max(len(eligible), 1)
    availability = float(frame.available.mean()) if len(frame) else 0.0
    minimum_observed_rows = min(minimum_rows) if minimum_rows else 0.0
    gates = {
        "valid_measurement_coverage_at_least_95_percent": coverage >= 0.95,
        "at_least_twelve_rows_each_block": minimum_observed_rows >= 12,
        "at_least_two_entries_per_week": frequency >= 2.0,
        "every_year_at_least_100_entries": all(v >= 100 for v in years.values()),
        "minority_direction_at_least_20_percent": minority >= 0.20,
        "cross_feed_direction_agreement_at_least_75_percent": (
            direction_agreement >= 0.75
        ),
        "cross_feed_action_agreement_at_least_65_percent": (
            action_agreement >= 0.65
        ),
        "entry_quote_availability_at_least_95_percent": availability >= 0.95,
    }
    payload = {
        "status": "returns_blind_no_post_entry_prices_or_pnl_read",
        "eligible_sessions": len(eligible),
        "valid_measurements": valid_measurements,
        "measurement_coverage": coverage,
        "minimum_valid_rows_in_any_accepted_block": minimum_observed_rows,
        "executable_entries": int(len(executable)),
        "entries_per_week": frequency,
        "direction_counts": {
            "UPRO": int((executable.direction > 0).sum())
            if len(executable)
            else 0,
            "SPXU": int((executable.direction < 0).sum())
            if len(executable)
            else 0,
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
