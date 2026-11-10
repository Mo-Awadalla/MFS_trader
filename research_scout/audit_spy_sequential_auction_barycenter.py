"""Returns-blind audit for Sequential Auction Barycenter Lease v24."""

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
    / "spy_sequential_auction_barycenter_returns_blind_audit_v24.json"
)


def exact_block(
    bars: pd.DataFrame,
    start: str,
    end: str,
    expected: int,
) -> pd.DataFrame | None:
    block = bars.between_time(start, end)
    return block if len(block) == expected else None


def center(block: pd.DataFrame) -> float:
    typical = (block.high + block.low + block.close) / 3.0
    return float((typical * block.volume).sum() / block.volume.sum())


def signal(bars: pd.DataFrame) -> dict[str, Any] | None:
    first = exact_block(bars, "09:30", "09:59", 30)
    second = exact_block(bars, "10:00", "10:29", 30)
    dead = exact_block(bars, "10:30", "10:30", 1)
    if first is None or second is None or dead is None:
        return None
    first_center = center(first)
    second_center = center(second)
    cash_open = float(first.iloc[0].open)
    terminal = float(second.iloc[-1].close)
    side = 0
    if first_center > cash_open and second_center > first_center and terminal > second_center:
        side = 1
    elif first_center < cash_open and second_center < first_center and terminal < second_center:
        side = -1
    if side == 0:
        return {"side": 0, "invalidated": False}
    dead_bar = dead.iloc[0]
    invalidated = (
        float(dead_bar.low) <= first_center
        if side > 0
        else float(dead_bar.high) >= first_center
    )
    return {
        "side": side,
        "invalidated": invalidated,
        "first_center": first_center,
        "second_center": second_center,
    }


def main() -> None:
    spy, arca, _, arca_excluded, _ = v16.load_old()
    equs_frame = base.load_dbn(EQUS_SPY, "SPY")
    equs_spy = base.split_sessions(equs_frame)
    equs_excluded = audit.degraded(audit.EQUS_CONDITIONS)
    rows: list[dict[str, Any]] = []
    for day, bars in sorted(spy.items()):
        if day in arca_excluded or not v16.START <= day <= v16.DEVELOPMENT_END:
            continue
        state = signal(bars)
        if state is None or int(state["side"]) == 0 or bool(state["invalidated"]):
            continue
        side = int(state["side"])
        symbol = "UPRO" if side > 0 else "SPXU"
        quotes = arca.get(day, {}).get(symbol)
        entry_available = False
        if quotes is not None:
            stamp = v16.stamp(day, time(10, 31), quotes.index.tz)
            entry_available = base.quote_at(quotes, stamp, 0) is not None
        rows.append(
            {
                "date": day,
                "side": side,
                "symbol": symbol,
                "entry_available": entry_available,
            }
        )
    frame = pd.DataFrame(rows)
    executable = frame[frame.entry_available].copy()
    frequency = len(executable) / (3 * 52)
    availability = float(frame.entry_available.mean()) if len(frame) else 0.0
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

    overlap_start = pd.Timestamp("2023-03-28")
    overlap_end = v16.HOLDOUT_END
    common_dates = sorted(
        set(spy).intersection(equs_spy) - arca_excluded - equs_excluded
    )
    both_signal = 0
    same_direction = 0
    same_action = 0
    overlap_dates = 0
    for day in common_dates:
        if not overlap_start <= day <= overlap_end:
            continue
        left = signal(spy[day])
        right = signal(equs_spy[day])
        left_action = (
            0
            if left is None or bool(left.get("invalidated", False))
            else int(left["side"])
        )
        right_action = (
            0
            if right is None or bool(right.get("invalidated", False))
            else int(right["side"])
        )
        overlap_dates += 1
        same_action += int(left_action == right_action)
        if left_action != 0 and right_action != 0:
            both_signal += 1
            same_direction += int(left_action == right_action)
    direction_agreement = same_direction / max(both_signal, 1)
    action_agreement = same_action / max(overlap_dates, 1)
    gates = {
        "at_least_two_entries_per_week": frequency >= 2.0,
        "entry_quote_availability_at_least_95_percent": availability >= 0.95,
        "minority_direction_at_least_20_percent": minority >= 0.20,
        "every_development_year_at_least_100_entries": all(
            count >= 100 for count in year_counts.values()
        ),
        "cross_feed_direction_agreement_at_least_85_percent": (
            direction_agreement >= 0.85
        ),
        "cross_feed_action_agreement_at_least_75_percent": action_agreement
        >= 0.75,
    }
    payload = {
        "status": "returns_blind_no_post_entry_prices_or_pnl_read",
        "development_candidate_signals": int(len(frame)),
        "executable_entries": int(len(executable)),
        "entries_per_week": frequency,
        "direction_counts": {
            "UPRO": int((executable.side > 0).sum()),
            "SPXU": int((executable.side < 0).sum()),
        },
        "minority_direction_fraction": minority,
        "year_counts": year_counts,
        "entry_quote_availability": availability,
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
