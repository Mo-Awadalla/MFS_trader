from __future__ import annotations

import numpy as np
import pandas as pd

from research.bitcoin_5m_probability_model import (
    FEATURE_COLUMNS,
    CalibratedLogisticProbabilityModel,
    build_dataset,
)


def _synthetic_inputs(rows: int = 380) -> tuple[pd.DataFrame, pd.DataFrame]:
    times = pd.date_range("2025-01-01", periods=rows, freq="5min", tz="UTC")
    phase = np.arange(rows, dtype=float)
    open_price = 100.0 * np.exp(0.0001 * phase)
    close_price = open_price * (1.0 + 0.0005 * np.where((phase.astype(int) % 3) == 0, 1.0, -1.0))
    bars = pd.DataFrame(
        {
            "open_time": times,
            "open": open_price,
            "high": np.maximum(open_price, close_price) * 1.0002,
            "low": np.minimum(open_price, close_price) * 0.9998,
            "close": close_price,
            "volume": 100.0 + phase,
            "trade_count": 20.0 + phase,
            "taker_buy_base_volume": (100.0 + phase) * 0.52,
        }
    )
    metrics = pd.DataFrame(
        {
            "create_time": times,
            "sum_open_interest": 10_000.0 + phase,
            "count_toptrader_long_short_ratio": 1.1 + phase / 10_000.0,
            "sum_toptrader_long_short_ratio": 1.2 + phase / 10_000.0,
            "count_long_short_ratio": 1.3 + phase / 10_000.0,
            "sum_taker_long_short_vol_ratio": 0.9 + phase / 10_000.0,
        }
    )
    return bars, metrics


def test_build_dataset_is_lagged_and_model_returns_probabilities():
    bars, metrics = _synthetic_inputs()
    dataset = build_dataset(bars, metrics)

    assert len(dataset) > 40
    assert dataset["open_time"].min() >= bars["open_time"].iloc[0] + pd.Timedelta(hours=24)
    assert set(dataset["label"].unique()) == {0, 1}
    assert dataset.loc[:, list(FEATURE_COLUMNS)].notna().all().all()

    split = len(dataset) // 2
    model = CalibratedLogisticProbabilityModel(C=0.1).fit(
        dataset.iloc[:split], dataset.iloc[split:]
    )
    probabilities = model.predict_proba(dataset.iloc[split:])
    assert np.isfinite(probabilities).all()
    assert ((probabilities > 0.0) & (probabilities < 1.0)).all()
