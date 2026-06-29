"""Unit tests for ETF time-series momentum signals."""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.etf_time_series_momentum.signal import (
    ETFTimeSeriesMomentumParams,
    generate_signals,
    params_from_dict,
    params_to_dict,
)

SYMBOLS = ("SPY", "QQQ", "IWM", "IEF", "GLD", "SHY", "DBC")


def _make_panel(n: int = 380, *, all_negative: bool = False) -> pd.DataFrame:
    index = pd.date_range("2021-01-01", periods=n, freq="B", tz="UTC")
    frames: dict[str, pd.DataFrame] = {}
    for i, symbol in enumerate(SYMBOLS):
        if all_negative and symbol != "SHY":
            returns = np.full(n, -0.0002 - i * 0.00001)
        elif all_negative and symbol == "SHY":
            returns = np.full(n, -0.00001)
        else:
            returns = np.full(n, 0.0001 + i * 0.00003)
        close = 100.0 * np.cumprod(1.0 + returns)
        frames[symbol] = pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.003,
                "low": close * 0.997,
                "close": close,
                "volume": np.full(n, 1_000_000.0),
            },
            index=index,
        )
    panel = pd.concat(frames, axis=1)
    panel.columns = pd.MultiIndex.from_tuples(
        [(str(symbol), str(field)) for symbol, field in panel.columns],
        names=["symbol", "field"],
    )
    return panel


def _params() -> ETFTimeSeriesMomentumParams:
    return ETFTimeSeriesMomentumParams(
        momentum_lookback_days=126,
        vol_lookback_days=42,
        min_history_days=126,
        min_median_dollar_volume=1.0,
        top_n=3,
        max_symbol_weight=0.50,
    )


def test_etf_tsm_is_long_only_top_n_and_capped():
    signals = generate_signals(_make_panel(), _params())
    weights = signals.xs("weight", axis=1, level="field").astype(float)
    active = weights[weights.abs().sum(axis=1) > 0]

    assert not active.empty
    assert float(weights.min().min()) >= 0.0
    assert int((weights > 0).sum(axis=1).max()) <= 3
    assert float(weights.max().max()) <= 0.500001
    assert float(weights.abs().sum(axis=1).max()) <= 1.000001


def test_etf_tsm_falls_back_to_shy_when_no_positive_momentum():
    signals = generate_signals(_make_panel(all_negative=True), _params())
    weights = signals.xs("weight", axis=1, level="field").astype(float)
    active = weights[weights.abs().sum(axis=1) > 0]

    assert not active.empty
    assert float(active.drop(columns=["SHY"]).abs().sum().sum()) == 0.0
    assert float(active["SHY"].sum()) > 0.0


def test_etf_tsm_params_round_trip():
    params = ETFTimeSeriesMomentumParams(momentum_lookback_days=189, top_n=2)

    assert params_from_dict(params_to_dict(params)) == params
