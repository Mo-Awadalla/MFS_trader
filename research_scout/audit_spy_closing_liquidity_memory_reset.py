"""Returns-blind audit for SPY Closing-Liquidity Memory Reset v31."""

from __future__ import annotations

import json
from datetime import time
from pathlib import Path
from typing import Any

import pandas as pd

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
    / "spy_closing_liquidity_memory_reset_returns_blind_audit_v31.json"
)


def center(block: pd.DataFrame) -> float:
    typical = (block.high + block.low + block.close) / 3.0
    return float((typical * block.volume).sum() / block.volume.sum())


def exact_block(
    bars: pd.DataFrame,
    start: str,
    end: str,
    expected: int,
) -> pd.DataFrame | None:
    block = bars.between_time(start, end)
    return block if len(block) == expected else None


def build_signal(
    prior_bars: pd.DataFrame,
    current_bars: pd.DataFrame,
) -> dict[str, Any] | None:
    prior_close = exact_block(prior_bars, "15:00", "15:29", 30)
    current_open = exact_block(current_bars, "09:30", "09:59", 30)
    observation = exact_block(current_bars, "10:00", "13:29", 210)
    dead = exact_block(current_bars, "13:30", "13:30", 1)
    if any(
        block is None
        for block in [prior_close, current_open, observation, dead]
    ):
        return None
    assert prior_close is not None
    assert current_open is not None
    assert observation is not None
    assert dead is not None
    old_anchor = center(prior_close)
    new_anchor = center(current_open)
    if old_anchor == new_anchor:
        return {"side": 0, "reason": "anchor_tie"}
    anchor_values = {"old": old_anchor, "new": new_anchor}
    visits: list[str] = []
    ambiguous = False
    for row in observation.itertuples():
        touched = [
            name
            for name, value in anchor_values.items()
            if float(row.low) <= value <= float(row.high)
        ]
        if len(touched) > 1:
            ambiguous = True
            break
        if len(touched) == 1 and (not visits or visits[-1] != touched[0]):
            visits.append(touched[0])
    if ambiguous:
        return {"side": 0, "reason": "same_bar_dual_touch"}
    if len(visits) != 2 or visits[0] == visits[1]:
        return {"side": 0, "reason": "not_exactly_two_distinct_visits"}
    first_value = anchor_values[visits[0]]
    second_value = anchor_values[visits[1]]
    side = 1 if second_value > first_value else -1
    midpoint = (first_value + second_value) / 2.0
    terminal_close = float(observation.iloc[-1].close)
    terminal_confirmed = (
        terminal_close > midpoint if side > 0 else terminal_close < midpoint
    )
    if not terminal_confirmed:
        return {"side": 0, "reason": "terminal_not_owned"}
    dead_bar = dead.iloc[0]
    dead_revisited_first = float(dead_bar.low) <= first_value <= float(
        dead_bar.high
    )
    if dead_revisited_first:
        return {"side": 0, "reason": "dead_bar_revisited_first"}
    return {
        "side": side,
        "reason": "signal",
        "first_anchor": visits[0],
        "second_anchor": visits[1],
    }


def signals(
    sessions: dict[pd.Timestamp, pd.DataFrame],
) -> dict[pd.Timestamp, dict[str, Any]]:
    ordered = sorted(sessions)
    output: dict[pd.Timestamp, dict[str, Any]] = {}
    for index in range(1, len(ordered)):
        day = ordered[index]
        prior = ordered[index - 1]
        output[day] = build_signal(sessions[prior], sessions[day]) or {
            "side": 0,
            "reason": "missing_blocks",
        }
    return output


def main() -> None:
    spy, arca, _, arca_excluded, _ = v16.load_old()
    equs_spy = base.split_sessions(base.load_dbn(EQUS_SPY, "SPY"))
    equs_excluded = audit.degraded(audit.EQUS_CONDITIONS)
    arca_signals = signals(spy)
    equs_signals = signals(equs_spy)

    rows: list[dict[str, Any]] = []
    reason_counts: dict[str, int] = {}
    for day, state in sorted(arca_signals.items()):
        if day in arca_excluded or not v16.START <= day <= v16.DEVELOPMENT_END:
            continue
        reason = str(state["reason"])
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        side = int(state["side"])
        if side == 0:
            continue
        symbol = "UPRO" if side > 0 else "SPXU"
        quotes = arca.get(day, {}).get(symbol)
        available = False
        if quotes is not None:
            stamp = v16.stamp(day, time(13, 31), quotes.index.tz)
            available = base.quote_at(quotes, stamp, 0) is not None
        rows.append(
            {
                "date": day,
                "side": side,
                "symbol": symbol,
                "entry_available": available,
            }
        )

    frame = pd.DataFrame(rows)
    executable = (
        frame.copy() if frame.empty else frame[frame.entry_available].copy()
    )
    frequency = len(executable) / (3 * 52)
    availability = (
        float(frame.entry_available.mean()) if len(frame) else 0.0
    )
    minority = (
        min(
            int((executable.side > 0).sum()),
            int((executable.side < 0).sum()),
        )
        / max(len(executable), 1)
        if len(executable)
        else 0.0
    )
    year_counts = {
        str(year): int((executable.date.dt.year == year).sum())
        if len(executable)
        else 0
        for year in [2021, 2022, 2023]
    }

    common = sorted(
        set(arca_signals).intersection(equs_signals)
        - arca_excluded
        - equs_excluded
    )
    overlap_dates = both_signal = same_direction = same_action = 0
    for day in common:
        if not pd.Timestamp("2023-03-28") <= day <= v16.HOLDOUT_END:
            continue
        left = int(arca_signals[day]["side"])
        right = int(equs_signals[day]["side"])
        overlap_dates += 1
        same_action += int(left == right)
        if left and right:
            both_signal += 1
            same_direction += int(left == right)
    direction_agreement = same_direction / max(both_signal, 1)
    action_agreement = same_action / max(overlap_dates, 1)
    gates = {
        "at_least_two_entries_per_week": frequency >= 2.0,
        "every_development_year_at_least_100_entries": all(
            count >= 100 for count in year_counts.values()
        ),
        "minority_direction_at_least_20_percent": minority >= 0.20,
        "entry_quote_availability_at_least_95_percent": availability >= 0.95,
        "cross_feed_direction_agreement_at_least_85_percent": (
            direction_agreement >= 0.85
        ),
        "cross_feed_action_agreement_at_least_75_percent": (
            action_agreement >= 0.75
        ),
    }
    payload = {
        "status": "returns_blind_no_post_entry_prices_or_pnl_read",
        "candidate_entries": int(len(frame)),
        "executable_entries": int(len(executable)),
        "entries_per_week": frequency,
        "direction_counts": {
            "UPRO": int((executable.side > 0).sum())
            if len(executable)
            else 0,
            "SPXU": int((executable.side < 0).sum())
            if len(executable)
            else 0,
        },
        "minority_direction_fraction": minority,
        "year_counts": year_counts,
        "entry_quote_availability": availability,
        "signal_state_counts": reason_counts,
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
