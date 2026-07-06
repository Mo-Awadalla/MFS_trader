"""Tests for frozen VS-ICSM v1 signal construction."""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.vs_icsm.signal import (
    VSICSMParams,
    _vs_icsm_score,
    generate_signals,
    params_from_dict,
    params_to_dict,
)


def vs_icsm_panel(
    *,
    n_days: int = 90,
    n_symbols: int = 25,
    bars_per_day: int = 7,
    start: str = "2024-01-02",
) -> pd.DataFrame:
    sessions = pd.bdate_range(start, periods=n_days, tz="UTC")
    timestamps = []
    for session in sessions:
        open_anchor = session + pd.Timedelta(hours=14, minutes=30)
        timestamps.extend(open_anchor + pd.Timedelta(hours=i) for i in range(bars_per_day))
    idx = pd.DatetimeIndex(timestamps)
    symbols = tuple(f"S{i:03d}" for i in range(n_symbols))
    fields = ("open", "high", "low", "close", "volume")
    columns = pd.MultiIndex.from_product([symbols, fields], names=["symbol", "field"])
    df = pd.DataFrame(index=idx, columns=columns, dtype=float)

    steps = np.arange(len(idx))
    for i, symbol in enumerate(symbols):
        base = 20.0 + i
        drift = (i - n_symbols / 2) / n_symbols * 0.0008
        wave = np.sin(steps / 5.0 + i) * 0.00015
        close = base * np.exp(np.cumsum(drift + wave))
        open_ = np.r_[close[0], close[:-1]]
        df[(symbol, "open")] = open_
        df[(symbol, "high")] = np.maximum(open_, close) * 1.002
        df[(symbol, "low")] = np.minimum(open_, close) * 0.998
        df[(symbol, "close")] = close
        df[(symbol, "volume")] = 50_000.0 + i * 1_000.0
    return df


def test_vs_icsm_score_is_trailing_momentum_divided_by_realized_vol() -> None:
    idx = pd.date_range("2024-01-01", periods=20, freq="h", tz="UTC")
    close = pd.DataFrame({"AAA": np.exp(np.arange(20) * 0.01)}, index=idx)
    params = VSICSMParams(momentum_lookback_bars=6, volatility_lookback_bars=13)

    score = _vs_icsm_score(close, params)
    returns = np.log(close / close.shift(1))
    expected = returns.rolling(6).sum() / returns.rolling(13).std(ddof=1)

    pd.testing.assert_frame_equal(score, expected)


def test_generates_long_only_top_k_inverse_atr_weights() -> None:
    df = vs_icsm_panel()
    params = VSICSMParams(
        universe_size=25,
        transition_buffer_rank=25,
        liquidity_lookback_sessions=20,
        min_history_sessions=20,
        min_eligible_symbols=15,
        top_k=15,
    )

    signals = generate_signals(df, params)
    weights = signals.xs("weight", axis=1, level="field").astype(float)
    active = weights[weights.abs().sum(axis=1) > 0].iloc[0]

    assert (active > 0).sum() == 15
    assert (active < 0).sum() == 0
    assert active.sum() <= 0.98 + 1e-9
    assert active.max() <= 0.15 + 1e-9
    assert "S024" in set(active[active > 0].index)


def test_uses_only_data_available_at_signal_bar() -> None:
    df = vs_icsm_panel()
    params = VSICSMParams(
        universe_size=25,
        transition_buffer_rank=25,
        liquidity_lookback_sessions=20,
        min_history_sessions=20,
        min_eligible_symbols=15,
        top_k=15,
    )
    original = generate_signals(df, params)

    cutoff = df.index[260]
    modified = df.copy()
    modified.loc[df.index[df.index > cutoff], ("S000", "close")] *= 25.0
    changed = generate_signals(modified, params)

    pd.testing.assert_frame_equal(original.loc[:cutoff], changed.loc[:cutoff])


def test_time_stop_forces_liquidation_without_parameter_tuning() -> None:
    df = vs_icsm_panel(n_days=35, n_symbols=10)
    params = VSICSMParams(
        universe_size=10,
        transition_buffer_rank=10,
        liquidity_lookback_sessions=5,
        min_history_sessions=5,
        min_eligible_symbols=3,
        top_k=3,
        max_holding_bars=3,
    )

    signals = generate_signals(df, params)
    trades = signals.xs("trade", axis=1, level="field").astype(float)

    assert int((trades > 0).sum().sum()) > 0
    assert int((trades < 0).sum().sum()) > 0


def test_time_stop_liquidates_even_when_replacement_universe_is_insufficient() -> None:
    df = vs_icsm_panel(n_days=25, n_symbols=3)
    params = VSICSMParams(
        momentum_lookback_bars=2,
        volatility_lookback_bars=3,
        atr_lookback_bars=3,
        universe_size=3,
        transition_buffer_rank=3,
        liquidity_lookback_sessions=2,
        min_history_sessions=2,
        min_eligible_symbols=3,
        top_k=3,
        max_holding_bars=1,
    )

    signals = generate_signals(df, params)
    weights = signals.xs("weight", axis=1, level="field").astype(float)
    trades = signals.xs("trade", axis=1, level="field").astype(float)
    skipped = signals[("portfolio", "rebalance_skipped")].astype(bool)
    skip_reason = signals[("portfolio", "skip_reason")]
    liquidation_rows = skipped & (skip_reason == "insufficient_eligible_universe") & (trades < 0.0).any(axis=1)

    assert liquidation_rows.any()
    first_liquidation = liquidation_rows[liquidation_rows].index[0]
    assert float(weights.loc[first_liquidation].abs().sum()) == 0.0
    assert float(trades.loc[first_liquidation].sum()) < 0.0


def test_params_roundtrip() -> None:
    params = VSICSMParams(top_k=12, gross_exposure=0.75)

    assert params_from_dict(params_to_dict(params)) == params
