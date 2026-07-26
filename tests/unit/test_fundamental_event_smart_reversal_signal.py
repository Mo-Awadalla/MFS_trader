"""Tests for frozen FundamentalEventSmartReversal v1 signal construction."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies.fundamental_event_smart_reversal.signal import (
    FundamentalEventSmartReversalParams,
    _complete_liquidity_history,
    _smart_target_weights,
    generate_signals,
)


def _params() -> FundamentalEventSmartReversalParams:
    return FundamentalEventSmartReversalParams(
        liquidity_lookback_days=5,
        min_history_days=8,
        min_price=1.0,
        min_median_dollar_volume=0.0,
        min_eligible_symbols=10,
        max_symbol_weight=0.5,
        benchmark_symbol="SPY",
    )


def _panel(n_days: int = 24, n_symbols: int = 10) -> pd.DataFrame:
    index = pd.bdate_range("2024-01-02", periods=n_days, tz="UTC")
    symbols = ("SPY",) + tuple(f"S{i:02d}" for i in range(n_symbols))
    fields = ("open", "high", "low", "close", "volume", "fundamental_event")
    columns = pd.MultiIndex.from_product([symbols, fields], names=["symbol", "field"])
    frame = pd.DataFrame(index=index, columns=columns, dtype=float)

    for i, symbol in enumerate(symbols):
        base = 100.0 + i
        daily_return = 0.0 if symbol == "SPY" else (i - 5.5) / 1000.0
        close = base * np.cumprod(np.full(n_days, 1.0 + daily_return))
        frame[(symbol, "open")] = close
        frame[(symbol, "high")] = close * 1.01
        frame[(symbol, "low")] = close * 0.99
        frame[(symbol, "close")] = close
        frame[(symbol, "volume")] = 2_000_000.0
        frame[(symbol, "fundamental_event")] = 0.0
    return frame


def test_smart_rank_buffer_retains_until_opposite_half() -> None:
    symbols = tuple(f"S{i}" for i in range(10))
    params = _params()
    initial_scores = pd.Series({symbol: float(i) for i, symbol in enumerate(symbols)})
    empty = pd.Series(0.0, index=symbols)

    initial, _, _ = _smart_target_weights(initial_scores, symbols, empty, params)
    assert set(initial[initial > 0].index) == {"S0", "S1"}
    assert set(initial[initial < 0].index) == {"S8", "S9"}

    moved_but_still_loser_half = pd.Series(
        {"S1": 0.0, "S2": 1.0, "S0": 2.0, "S3": 3.0, "S4": 4.0,
         "S5": 5.0, "S6": 6.0, "S7": 7.0, "S8": 8.0, "S9": 9.0}
    )
    retained, _, _ = _smart_target_weights(
        moved_but_still_loser_half, symbols, initial, params
    )
    assert retained["S0"] > 0

    crossed_median = pd.Series(
        {"S1": 0.0, "S2": 1.0, "S3": 2.0, "S4": 3.0, "S5": 4.0,
         "S0": 5.0, "S6": 6.0, "S7": 7.0, "S8": 8.0, "S9": 9.0}
    )
    exited, _, _ = _smart_target_weights(crossed_median, symbols, retained, params)
    assert exited["S0"] == 0.0
    assert exited["S2"] > 0


def test_universe_shrink_does_not_drop_positions_that_have_not_crossed_median() -> None:
    symbols = tuple(f"S{i:03d}" for i in range(110))
    params = _params()
    initial_scores = pd.Series({symbol: float(i) for i, symbol in enumerate(symbols)})
    initial, _, _ = _smart_target_weights(
        initial_scores,
        symbols,
        pd.Series(0.0, index=symbols),
        params,
    )
    initial_longs = set(initial[initial > 0.0].index)
    assert len(initial_longs) == 22

    retained, _, _ = _smart_target_weights(initial_scores.iloc[:100], symbols, initial, params)

    assert initial_longs <= set(retained[retained > 0.0].index)


def test_liquidity_history_requires_every_session_in_window() -> None:
    formation = _panel().iloc[:10].copy()
    formation.loc[formation.index[-1], ("S00", "volume")] = np.nan

    complete = _complete_liquidity_history(
        formation,
        tuple(str(symbol) for symbol in formation.columns.get_level_values(0).unique()),
        lookback_days=5,
    )

    assert not bool(complete["S00"])
    assert bool(complete["S01"])


def test_material_event_veto_blocks_entry_and_forces_exit() -> None:
    frame = _panel()
    params = _params()
    baseline = generate_signals(frame, params)
    baseline_weights = baseline.xs("weight", axis=1, level="field")

    active_dates = baseline_weights.index[(baseline_weights["S00"] > 0)]
    assert len(active_dates) > 2
    event_date = active_dates[1]
    event_frame = frame.copy()
    event_frame.loc[event_date, ("S00", "fundamental_event")] = 1.0

    changed = generate_signals(event_frame, params)
    changed_weights = changed.xs("weight", axis=1, level="field")
    next_date = event_frame.index[event_frame.index.get_loc(event_date) + 1]

    assert changed_weights.loc[next_date, "S00"] == 0.0
    assert changed.loc[next_date, ("portfolio", "event_forced_exit_count")] >= 1


def test_future_price_and_event_changes_do_not_change_prior_signals() -> None:
    frame = _panel()
    params = _params()
    original = generate_signals(frame, params)

    modified = frame.copy()
    cutoff = frame.index[16]
    modified.loc[cutoff:, ("S00", "close")] *= 10.0
    modified.loc[cutoff:, ("S01", "fundamental_event")] = 1.0
    changed = generate_signals(modified, params)

    prior = frame.index[:16]
    pd.testing.assert_frame_equal(original.loc[prior], changed.loc[prior])


def test_requires_point_in_time_event_field_for_every_symbol() -> None:
    frame = _panel().drop(columns=[("S00", "fundamental_event")])

    with pytest.raises(ValueError, match="fundamental_event"):
        generate_signals(frame, _params())


def test_benchmark_is_never_traded() -> None:
    signals = generate_signals(_panel(), _params())
    weights = signals.xs("weight", axis=1, level="field")
    assert (weights["SPY"] == 0.0).all()
