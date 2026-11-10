"""Returns-blind audit for the frozen ES three-clock ETF transport."""

from __future__ import annotations

import json
from datetime import time
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import test_es_opening_dual_engine_robustness as dual
from research_scout import test_es_three_engine_stress as three
from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "research_scout"
    / "es_three_clock_to_leveraged_etf_returns_blind_audit_v22.json"
)


def clock(index: int) -> time:
    stamp = pd.Timestamp("2000-01-01 09:30") + pd.Timedelta(minutes=index)
    return stamp.time()


def frozen_first_signals(
    sessions: list[tuple[pd.Timestamp, pd.DataFrame]],
) -> pd.DataFrame:
    session_map = dict(sessions)
    signals = three.build_three_engine_signals(sessions)
    eligible: list[dict[str, Any]] = []
    for signal in signals.itertuples(index=False):
        bars = session_map[signal.date]
        side = int(signal.side)
        entry_index = int(signal.base_entry_idx)
        entry = float(bars.iloc[entry_index].open) + side * three.TICK_SIZE
        stop = float(signal.stop_reference - side * three.TICK_SIZE)
        if (side > 0 and stop >= entry) or (side < 0 and stop <= entry):
            continue
        eligible.append(
            {
                "date": signal.date,
                "engine": str(signal.engine),
                "side": side,
                "base_entry_idx": entry_index,
                "time_exit_idx": int(signal.time_exit_idx),
                "stop_reference": float(signal.stop_reference),
                "risk_usd": abs(entry - stop) * three.POINT_VALUE
                + three.COMMISSION,
            }
        )
    frame = pd.DataFrame(eligible)
    selected = (
        frame.sort_values(
            ["date", "base_entry_idx", "risk_usd", "engine"],
            ascending=True,
        )
        .drop_duplicates("date", keep="first")
        .reset_index(drop=True)
    )
    if not selected.date.is_unique:
        raise AssertionError("frozen first-signal selection must be unique by day")
    return selected


def stop_trigger(signal: pd.Series) -> float:
    if signal.engine == "convexity":
        return float(signal.stop_reference)
    return float(signal.stop_reference - signal.side * three.TICK_SIZE)


def main() -> None:
    sessions = dual.load_sessions()
    session_map = dict(sessions)
    signals = frozen_first_signals(sessions)
    _, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    candidates: list[dict[str, Any]] = []
    for signal in signals.itertuples(index=False):
        day = signal.date
        if not v16.START <= day <= v16.DEVELOPMENT_END:
            continue
        if day in arca_excluded:
            continue
        side = int(signal.side)
        bars = session_map[day]
        trigger = (
            float(signal.stop_reference)
            if signal.engine == "convexity"
            else float(signal.stop_reference - side * three.TICK_SIZE)
        )
        dead_bar = bars.iloc[int(signal.base_entry_idx)]
        invalidated = (
            float(dead_bar.low) <= trigger
            if side > 0
            else float(dead_bar.high) >= trigger
        )
        if invalidated:
            continue
        symbol = "UPRO" if side > 0 else "SPXU"
        entry_index = int(signal.base_entry_idx) + 1
        pair = arca.get(day, {})
        quotes = pair.get(symbol)
        arca_entry = False
        if quotes is not None:
            entry_stamp = v16.stamp(day, clock(entry_index), quotes.index.tz)
            arca_entry = base.quote_at(quotes, entry_stamp, 0) is not None
        eq_pair = equs.get(day, {}) if day not in equs_excluded else {}
        eq_quotes = eq_pair.get(symbol)
        equs_entry = False
        if eq_quotes is not None:
            eq_stamp = v16.stamp(day, clock(entry_index), eq_quotes.index.tz)
            equs_entry = base.quote_at(eq_quotes, eq_stamp, 0) is not None
        candidates.append(
            {
                "date": day,
                "engine": signal.engine,
                "side": side,
                "symbol": symbol,
                "entry_index": entry_index,
                "arca_entry": arca_entry,
                "equs_entry": equs_entry,
            }
        )
    frame = pd.DataFrame(candidates)
    executable = frame[frame.arca_entry].copy()
    frequency = len(executable) / (3 * 52)
    minority = (
        min(
            int((executable.side > 0).sum()),
            int((executable.side < 0).sum()),
        )
        / max(len(executable), 1)
    )
    availability = float(frame.arca_entry.mean()) if len(frame) else 0.0
    year_counts = {
        str(year): int((executable.date.dt.year == year).sum())
        for year in [2021, 2022, 2023]
    }
    engine_counts = {
        str(engine): int(count)
        for engine, count in executable.engine.value_counts().items()
    }
    overlap = executable[executable.date >= pd.Timestamp("2023-03-28")]
    overlap_equs_availability = (
        float(overlap.equs_entry.mean()) if len(overlap) else 0.0
    )
    gates = {
        "at_least_two_entries_per_week": frequency >= 2.0,
        "arca_entry_quote_availability_at_least_95_percent": availability
        >= 0.95,
        "minority_direction_at_least_20_percent": minority >= 0.20,
        "every_development_year_at_least_150_entries": all(
            count >= 150 for count in year_counts.values()
        ),
        "every_engine_at_least_25_entries": all(
            engine_counts.get(engine, 0) >= 25
            for engine in ["center", "convexity", "reload"]
        ),
    }
    payload = {
        "status": "returns_blind_no_post_entry_etf_prices_or_pnl_read",
        "frozen_first_signal_days": int(len(signals)),
        "development_candidates_after_dead_minute_cancellation": int(len(frame)),
        "executable_entries": int(len(executable)),
        "entries_per_week": frequency,
        "direction_counts": {
            "UPRO": int((executable.side > 0).sum()),
            "SPXU": int((executable.side < 0).sum()),
        },
        "minority_direction_fraction": minority,
        "engine_counts": engine_counts,
        "year_counts": year_counts,
        "arca_entry_quote_availability": availability,
        "equs_overlap_entry_quote_availability": overlap_equs_availability,
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
