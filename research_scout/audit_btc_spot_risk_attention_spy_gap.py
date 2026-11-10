"""Returns-blind audit for BTC Spot Risk-Attention Gate × SPY Gap v32."""

from __future__ import annotations

import json
from datetime import time
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_btc_spot_flow_baton_to_leveraged_etf as btc_v26
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as audit
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
    / "btc_spot_risk_attention_spy_gap_returns_blind_audit_v32.json"
)


def gap_directions(
    sessions: dict[pd.Timestamp, pd.DataFrame],
) -> dict[pd.Timestamp, int]:
    ordered = sorted(sessions)
    directions: dict[pd.Timestamp, int] = {}
    for index in range(1, len(ordered)):
        day = ordered[index]
        prior_day = ordered[index - 1]
        prior_close = sessions[prior_day].between_time("15:59", "15:59")
        current_open = sessions[day].between_time("09:30", "09:30")
        if len(prior_close) != 1 or len(current_open) != 1:
            continue
        gap = float(current_open.iloc[0].open) - float(
            prior_close.iloc[0].close
        )
        directions[day] = 1 if gap > 0 else -1 if gap < 0 else 0
    return directions


def main() -> None:
    btc = btc_v26.load_btc()
    spy, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    equs_spy = base.split_sessions(base.load_dbn(EQUS_SPY, "SPY"))
    equs_spy_excluded = audit.degraded(audit.EQUS_CONDITIONS)
    arca_gap = gap_directions(spy)
    equs_gap = gap_directions(equs_spy)

    eligible = [
        day
        for day in sorted(spy)
        if day not in arca_excluded
        and v16.START <= day <= v16.DEVELOPMENT_END
    ]
    measured = 0
    rows: list[dict[str, Any]] = []
    for day in eligible:
        state = btc_v26.signal_for(btc, day)
        if state is None:
            continue
        measured += 1
        attention = int(state["direction"]) != 0
        direction = arca_gap.get(day, 0) if attention else 0
        if direction == 0:
            continue
        symbol = "UPRO" if direction > 0 else "SPXU"
        quotes = arca.get(day, {}).get(symbol)
        arca_entry = False
        if quotes is not None:
            stamp = v16.stamp(day, time(9, 31), quotes.index.tz)
            arca_entry = base.quote_at(quotes, stamp, 0) is not None
        eq_quotes = (
            equs.get(day, {}).get(symbol)
            if day not in equs_excluded
            else None
        )
        equs_entry = False
        if eq_quotes is not None:
            eq_stamp = v16.stamp(day, time(9, 31), eq_quotes.index.tz)
            equs_entry = base.quote_at(eq_quotes, eq_stamp, 0) is not None
        rows.append(
            {
                "date": day,
                "direction": direction,
                "symbol": symbol,
                "arca_entry": arca_entry,
                "equs_entry": equs_entry,
            }
        )

    frame = pd.DataFrame(rows)
    executable = (
        frame.copy() if frame.empty else frame[frame.arca_entry].copy()
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
    overlap_start = pd.Timestamp("2023-03-28")
    overlap_end = v16.HOLDOUT_END
    overlap_dates = both_signal = same_direction = same_action = 0
    for day in sorted(set(arca_gap).intersection(equs_gap)):
        if (
            day in arca_excluded
            or day in equs_spy_excluded
            or not overlap_start <= day <= overlap_end
        ):
            continue
        state = btc_v26.signal_for(btc, day)
        attention = state is not None and int(state["direction"]) != 0
        left = arca_gap[day] if attention else 0
        right = equs_gap[day] if attention else 0
        overlap_dates += 1
        same_action += int(left == right)
        if left and right:
            both_signal += 1
            same_direction += int(left == right)

    measurement_coverage = measured / max(len(eligible), 1)
    arca_availability = (
        float(frame.arca_entry.mean()) if len(frame) else 0.0
    )
    overlap_frame = (
        executable[executable.date >= overlap_start]
        if len(executable)
        else executable
    )
    equs_availability = (
        float(overlap_frame.equs_entry.mean()) if len(overlap_frame) else 0.0
    )
    direction_agreement = same_direction / max(both_signal, 1)
    action_agreement = same_action / max(overlap_dates, 1)
    gates = {
        "btc_measurement_coverage_at_least_98_percent": (
            measurement_coverage >= 0.98
        ),
        "at_least_two_entries_per_week": frequency >= 2.0,
        "every_development_year_at_least_100_entries": all(
            count >= 100 for count in years.values()
        ),
        "minority_direction_at_least_20_percent": minority >= 0.20,
        "arca_entry_availability_at_least_95_percent": (
            arca_availability >= 0.95
        ),
        "equs_entry_availability_at_least_95_percent": (
            equs_availability >= 0.95
        ),
        "cross_feed_direction_agreement_at_least_95_percent": (
            direction_agreement >= 0.95
        ),
        "cross_feed_action_agreement_at_least_90_percent": (
            action_agreement >= 0.90
        ),
    }
    payload = {
        "status": "returns_blind_no_post_entry_etf_prices_or_pnl_read",
        "eligible_development_sessions": len(eligible),
        "complete_btc_measurements": measured,
        "btc_measurement_coverage": measurement_coverage,
        "candidate_entries": int(len(frame)),
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
        "arca_entry_availability": arca_availability,
        "equs_overlap_entry_availability": equs_availability,
        "cross_feed": {
            "overlap_dates": overlap_dates,
            "both_signal_dates": both_signal,
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
