"""Unit tests for Global Dual Momentum signals."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.universes.global_dual_momentum_v1 import DEFENSIVE_ASSETS, RISK_ASSETS, all_symbols
from strategies.global_dual_momentum.signal import (
    GlobalDualMomentumParams,
    generate_signals,
    params_from_dict,
    params_to_dict,
)

SYMBOLS = all_symbols()


def _make_panel(n: int = 380, *, risk_off: bool = False) -> pd.DataFrame:
    index = pd.date_range("2021-01-01", periods=n, freq="B", tz="UTC")
    frames: dict[str, pd.DataFrame] = {}
    for i, symbol in enumerate(SYMBOLS):
        if symbol in RISK_ASSETS and risk_off:
            returns = np.full(n, -0.0002 - i * 0.00001)
        elif symbol in DEFENSIVE_ASSETS and risk_off:
            returns = np.full(n, 0.00005 + i * 0.00002)
        elif symbol in RISK_ASSETS:
            returns = np.full(n, 0.00010 + i * 0.00003)
        else:
            returns = np.full(n, 0.00002)
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


def _params() -> GlobalDualMomentumParams:
    return GlobalDualMomentumParams(
        momentum_lookback_days=126,
        min_history_days=126,
        min_median_dollar_volume=1.0,
    )


def test_global_dual_momentum_risk_on_holds_one_risk_asset():
    signals = generate_signals(_make_panel(), _params())
    weights = signals.xs("weight", axis=1, level="field").astype(float)
    active = weights[weights.abs().sum(axis=1) > 0]

    assert not active.empty
    assert float(weights.min().min()) >= 0.0
    assert int((weights > 0).sum(axis=1).max()) == 1
    assert float(active[list(DEFENSIVE_ASSETS)].abs().sum().sum()) == 0.0
    assert float(active[list(RISK_ASSETS)].abs().sum().sum()) > 0.0


def test_global_dual_momentum_risk_off_uses_defensive_asset():
    signals = generate_signals(_make_panel(risk_off=True), _params())
    weights = signals.xs("weight", axis=1, level="field").astype(float)
    active = weights[weights.abs().sum(axis=1) > 0]

    assert not active.empty
    assert float(active[list(RISK_ASSETS)].abs().sum().sum()) == 0.0
    assert float(active[list(DEFENSIVE_ASSETS)].abs().sum().sum()) > 0.0


def test_global_dual_momentum_params_round_trip():
    params = GlobalDualMomentumParams(momentum_lookback_days=189, top_risk_n=2)

    assert params_from_dict(params_to_dict(params)) == params
