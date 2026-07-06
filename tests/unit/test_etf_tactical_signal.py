"""Unit tests for ETF tactical momentum signals."""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.etf_tactical.signal import (
    ETFTacticalParams,
    generate_signals,
    params_from_dict,
    params_to_dict,
)

SYMBOLS = ("SPY", "QQQ", "IWM", "IEF", "GLD", "SHY", "DBC")


def _make_panel(n: int = 360, *, risk_off: bool = False) -> pd.DataFrame:
    index = pd.date_range("2021-01-01", periods=n, freq="B", tz="UTC")
    frames: dict[str, pd.DataFrame] = {}
    for i, symbol in enumerate(SYMBOLS):
        if symbol == "SPY" and risk_off:
            returns = np.full(n, -0.0009)
        elif symbol in {"IEF", "GLD", "SHY"} and risk_off:
            returns = np.full(n, 0.0003 + i * 0.00003)
        else:
            returns = np.full(n, 0.0002 + i * 0.00004)
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


def _params() -> ETFTacticalParams:
    return ETFTacticalParams(
        short_lookback_days=63,
        long_lookback_days=126,
        trend_ma_days=100,
        vol_lookback_days=42,
        min_history_days=126,
        min_median_dollar_volume=1.0,
        min_eligible_symbols=4,
        top_n=3,
        defensive_top_n=2,
        max_symbol_weight=0.60,
    )


def test_etf_tactical_is_long_only_and_limited_to_top_n():
    signals = generate_signals(_make_panel(), _params())
    weights = signals.xs("weight", axis=1, level="field").astype(float)

    assert float(weights.min().min()) >= 0.0
    assert int((weights > 0).sum(axis=1).max()) <= 3
    assert float(weights.abs().sum(axis=1).max()) <= 1.000001


def test_etf_tactical_risk_off_uses_defensive_assets_only():
    signals = generate_signals(_make_panel(risk_off=True), _params())
    weights = signals.xs("weight", axis=1, level="field").astype(float)
    active = weights[weights.abs().sum(axis=1) > 0]

    assert not active.empty
    assert float(active[["SPY", "QQQ", "IWM"]].abs().sum().sum()) == 0.0
    assert float(active[["IEF", "GLD", "SHY"]].abs().sum().sum()) > 0.0


def test_etf_tactical_params_round_trip():
    params = ETFTacticalParams(short_lookback_days=84, top_n=2)

    assert params_from_dict(params_to_dict(params)) == params
