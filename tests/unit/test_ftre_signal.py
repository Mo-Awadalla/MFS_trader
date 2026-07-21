from __future__ import annotations

import pandas as pd
import pytest

from strategies.ftre.signal import (
    default_params,
    dislocation,
    generate_signals,
    spot_failure_stop,
    target_price,
    trigger_mask,
    volatility_stop,
)


def _fixture(bars: int = 24) -> pd.DataFrame:
    index = pd.date_range("2025-01-01 08:00", periods=bars, freq="5min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": 90.0,
            "high": 91.0,
            "low": 89.0,
            "close": 90.0,
            "volume": 10.0,
            "funding_settlement": False,
            "funding_rate": 0.0021,
            "oi_change_z": -2.1,
            "perp_discount_z": -1.6,
            "perp_taker_sell_ratio": 0.56,
            "spot_taker_buy_ratio": 0.50,
            "btc_return_60m": -0.009,
            "perp_price_window_start": 100.0,
            "spot_close": 100.0,
            "spot_vwap_60m": 100.0,
            "spot_atr_14": 2.0,
            "perp_atr_14": 2.0,
        },
        index=index,
    )
    df.loc[index[0], "funding_settlement"] = True
    return df


def test_trigger_requires_every_frozen_condition() -> None:
    baseline = _fixture()
    assert trigger_mask(baseline).iloc[0]
    failures = {
        "funding_rate": 0.002,
        "oi_change_z": -2.0,
        "perp_discount_z": -1.5,
        "perp_taker_sell_ratio": 0.55,
        "spot_taker_buy_ratio": 0.499,
        "btc_return_60m": -0.01,
    }
    for column, value in failures.items():
        candidate = baseline.copy()
        candidate.loc[candidate.index[0], column] = value
        assert not trigger_mask(candidate).iloc[0], column


def test_dislocation_and_target_math() -> None:
    assert dislocation(100.0, 90.0) == 10.0
    assert target_price(100.0, 90.0) == 95.0


def test_spot_and_volatility_stop_boundaries() -> None:
    assert spot_failure_stop(97.99, 100.0, 2.0)
    assert not spot_failure_stop(98.0, 100.0, 2.0)
    assert volatility_stop(87.0, 90.0, 2.0)
    assert not volatility_stop(87.01, 90.0, 2.0)


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ({"high": 95.0}, "target"),
        ({"spot_close": 97.0}, "spot_failure"),
        ({"low": 86.0}, "vol_stop"),
    ],
)
def test_each_price_stop(mutation: dict[str, float], expected_reason: str) -> None:
    df = _fixture()
    for column, value in mutation.items():
        df.loc[df.index[1], column] = value
    signals = generate_signals(df)
    assert signals.loc[df.index[1], "exit_reason"] == expected_reason


def test_time_stop_is_90_minutes_and_entry_is_next_open() -> None:
    df = _fixture()
    df.loc[df.index[1], "open"] = 88.0
    signals = generate_signals(df, default_params())
    assert signals.loc[df.index[0], "entry_price"] == 88.0
    assert signals.loc[df.index[18], "exit_reason"] == "time_stop"


def test_market_filter_blocks_entry() -> None:
    df = _fixture()
    df.loc[df.index[0], "btc_return_60m"] = -0.02
    assert not (generate_signals(df)["signal"] > 0).any()
