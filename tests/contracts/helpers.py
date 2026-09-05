"""Reusable strategy contract test helpers.

Import and call from per-strategy test modules or the parametrized suite.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from research.universes.global_dual_momentum_v1 import SYMBOLS as GLOBAL_DUAL_MOMENTUM_SYMBOLS
from strategies.contract import StrategyTemplate, assert_exit_contract
from strategies.registry import RAW_EXIT_COLUMNS


def oscillating_ohlcv(n: int = 400, base: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="1D", tz="UTC")
    close = base + 12.0 * np.sin(np.linspace(0, 24 * np.pi, n))
    return pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": [10_000.0] * n,
        },
        index=idx,
    )


def funding_event_ohlcv(n: int = 400) -> pd.DataFrame:
    df = oscillating_ohlcv(n)
    df.index = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC")
    defaults: dict[str, float | bool] = {
        "funding_settlement": False,
        "funding_rate": 0.0,
        "oi_change_z": 0.0,
        "perp_discount_z": 0.0,
        "perp_taker_sell_ratio": 0.0,
        "spot_taker_buy_ratio": 0.0,
        "btc_return_60m": 0.0,
        "perp_price_window_start": 100.0,
        "spot_close": 100.0,
        "spot_vwap_60m": 100.0,
        "spot_atr_14": 1.0,
        "perp_atr_14": 1.0,
    }
    return df.assign(**defaults)


def trending_ohlcv(n: int = 300) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="1D", tz="UTC")
    close = [100.0 + 0.1 * i for i in range(n)]
    return pd.DataFrame(
        {
            "open": [c - 0.5 for c in close],
            "high": [c + 1.0 for c in close],
            "low": [c - 1.0 for c in close],
            "close": close,
            "volume": [10_000.0] * n,
        },
        index=idx,
    )


def cross_sectional_ohlcv(n_days: int = 90, n_symbols: int = 120) -> pd.DataFrame:
    idx = pd.bdate_range("2024-01-02", periods=n_days, tz="UTC")
    symbols = GLOBAL_DUAL_MOMENTUM_SYMBOLS + tuple(f"S{i:03d}" for i in range(n_symbols))
    columns = pd.MultiIndex.from_product(
        [symbols, ("open", "high", "low", "close", "volume", "fundamental_event")],
        names=["symbol", "field"],
    )
    df = pd.DataFrame(index=idx, columns=columns, dtype=float)
    for i, symbol in enumerate(symbols):
        base = 20.0 + i
        close = np.full(n_days, base)
        close[55:] = base * (1.0 + ((i - n_symbols / 2) / n_symbols) * 0.20)
        df[(symbol, "open")] = close
        df[(symbol, "high")] = close * 1.01
        df[(symbol, "low")] = close * 0.99
        df[(symbol, "close")] = close
        df[(symbol, "volume")] = 2_000_000.0
        df[(symbol, "fundamental_event")] = 0.0
    return df


def assert_metadata_complete(strategy: StrategyTemplate[Any]) -> None:
    meta = strategy.metadata()
    assert meta["name"] == strategy.name
    assert meta["template_version"] == strategy.template_version
    assert meta.get("strategy_template_version") == strategy.strategy_template_version


def assert_required_surface(strategy: StrategyTemplate[Any]) -> None:
    assert strategy.name
    assert strategy.template_version
    params = strategy.default_params()
    assert strategy.sweep_grid()
    assert strategy.compact_sweep_grid()
    assert strategy.required_columns()
    assert strategy.warmup_bars(params) >= 1
    assert isinstance(strategy.supports_long(), bool)
    assert isinstance(strategy.supports_short(), bool)
    assert_metadata_complete(strategy)


def assert_validate_inputs_enforced(strategy: StrategyTemplate[Any]) -> None:
    if str(strategy.metadata().get("data_shape", "")).startswith("cross_sectional"):
        bad = pd.DataFrame({"close": [1.0, 2.0]}, index=pd.date_range("2024-01-01", periods=2))
    else:
        bad = pd.DataFrame({"close": [1.0, 2.0]})
    try:
        strategy.validate_inputs(bad)
        raise AssertionError("expected ValueError for missing columns")
    except ValueError:
        pass


def assert_deterministic_output(
    strategy: StrategyTemplate[Any],
    df: pd.DataFrame | None = None,
) -> None:
    df = oscillating_ohlcv() if df is None else df
    params = strategy.default_params()
    a = strategy.generate_signals(df, params)
    b = strategy.generate_signals(df, params)
    pd.testing.assert_frame_equal(a, b)


def assert_no_lookahead(
    strategy: StrategyTemplate[Any],
    df: pd.DataFrame | None = None,
) -> None:
    df = oscillating_ohlcv(300) if df is None else df
    params = strategy.default_params()
    signals = strategy.generate_signals(df, params)
    if signals.empty:
        return

    df_modified = df.copy()
    df_modified.iloc[150:, df_modified.columns.get_loc("close")] *= 3.0
    signals_modified = strategy.generate_signals(df_modified, params)
    common = signals.index[:150]
    pd.testing.assert_series_equal(
        signals.loc[common, "position"],
        signals_modified.loc[common, "position"],
        check_names=False,
    )


def assert_signal_is_position_diff(
    strategy: StrategyTemplate[Any],
    df: pd.DataFrame | None = None,
) -> None:
    df = oscillating_ohlcv() if df is None else df
    signals = strategy.generate_signals(df, strategy.default_params())
    if signals.empty:
        return
    expected = signals["position"].diff().fillna(0).astype(int)
    pd.testing.assert_series_equal(signals["signal"], expected, check_names=False)


def assert_warmup_handled(strategy: StrategyTemplate[Any]) -> None:
    params = strategy.default_params()
    warmup = strategy.warmup_bars(params)
    short = oscillating_ohlcv(max(warmup - 1, 5))
    signals = strategy.generate_signals(short, params)
    if len(short) < warmup:
        assert signals["position"].isna().all() or (signals["position"] == 0).all()


def assert_exit_exits(
    strategy: StrategyTemplate[Any],
    df: pd.DataFrame | None = None,
) -> None:
    df = oscillating_ohlcv(500) if df is None else df
    signals = strategy.generate_signals(df, strategy.default_params())
    raw_exit_col = RAW_EXIT_COLUMNS[strategy.name]
    assert_exit_contract(signals, raw_exit_col=raw_exit_col)

    position = signals["position"]
    signal = signals["signal"]
    raw_exit = signals[raw_exit_col]
    exits_while_long = 0
    signaled = 0
    for i in range(1, len(signals)):
        if raw_exit.iloc[i] and position.iloc[i - 1] == 1:
            exits_while_long += 1
            if signal.iloc[i] == -1:
                signaled += 1
    if exits_while_long > 0:
        assert signaled > 0, f"{strategy.name}: exits while long produced no exit signals"


def assert_diagnostics_consistent(
    strategy: StrategyTemplate[Any],
    df: pd.DataFrame | None = None,
) -> None:
    df = oscillating_ohlcv() if df is None else df
    params = strategy.default_params()
    diag = strategy.diagnose_signals(df, params)
    assert diag.bars == len(df)
    assert diag.warmup_bars == strategy.warmup_bars(params)
    assert diag.raw_entry_events >= diag.filtered_entry_events
    assert diag.entry_signals <= diag.filtered_entry_events + 1
    assert diag.exit_signals <= diag.raw_exit_events
    assert 0.0 <= diag.pct_time_invested <= 100.0
    assert diag.execution_mode == "next_bar_open"
    assert len(diag.entry_signal_timestamps) == diag.entry_signals
    assert len(diag.exit_signal_timestamps) == diag.exit_signals


def assert_params_roundtrip_bb(strategy: StrategyTemplate[Any]) -> None:
    if strategy.name != "bollinger_bands":
        return
    from strategies.bb.strategy import BollingerBandsStrategy

    assert isinstance(strategy, BollingerBandsStrategy)
    params = strategy.default_params()
    restored = BollingerBandsStrategy.params_from_dict(BollingerBandsStrategy.params_to_dict(params))
    assert restored == params


def assert_cross_sectional_contract(strategy: StrategyTemplate[Any]) -> None:
    assert_required_surface(strategy)
    assert_validate_inputs_enforced(strategy)

    df = cross_sectional_ohlcv()
    params = strategy.default_params()
    a = strategy.generate_signals(df, params)
    b = strategy.generate_signals(df, params)
    pd.testing.assert_frame_equal(a, b)

    assert isinstance(a.columns, pd.MultiIndex)
    assert ("portfolio", "is_rebalance") in a.columns
    assert a.xs("weight", axis=1, level="field").abs().sum(axis=1).max() <= 2.0 + 1e-9

    modified = df.copy()
    modified.loc["2024-04-02":, ("S000", "close")] *= 100.0
    changed = strategy.generate_signals(modified, params)
    pd.testing.assert_frame_equal(a.loc[:"2024-04-01"], changed.loc[:"2024-04-01"])

    short = cross_sectional_ohlcv(n_days=max(strategy.warmup_bars(params) - 1, 5))
    short_signals = strategy.generate_signals(short, params)
    assert short_signals.xs("weight", axis=1, level="field").abs().sum().sum() == 0

    diag = strategy.diagnose_signals(df, params)
    assert diag.bars == len(df)
    assert diag.warmup_bars == strategy.warmup_bars(params)
    assert diag.filtered_entry_events <= diag.raw_entry_events
    assert str(diag.extra["data_shape"]).startswith("cross_sectional")


def run_contract_suite(strategy: StrategyTemplate[Any]) -> None:
    """Run all reusable contract assertions for one strategy."""
    if str(strategy.metadata().get("data_shape", "")).startswith("cross_sectional"):
        assert_cross_sectional_contract(strategy)
        return

    fixture = funding_event_ohlcv() if strategy.metadata().get("data_shape") == "single_asset_funding_event" else None

    assert_required_surface(strategy)
    assert_validate_inputs_enforced(strategy)
    assert_deterministic_output(strategy, fixture)
    assert_no_lookahead(strategy, fixture)
    assert_signal_is_position_diff(strategy, fixture)
    if fixture is None:
        assert_warmup_handled(strategy)
    assert_exit_exits(strategy, fixture)
    assert_diagnostics_consistent(strategy, fixture)
    assert_params_roundtrip_bb(strategy)
