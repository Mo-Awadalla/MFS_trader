from __future__ import annotations

import numpy as np
import pandas as pd

from research.impact_regimes import impact_features, log_impact_fit


def test_log_impact_fit_recovers_exponent_and_convexity() -> None:
    x = np.linspace(-1.0, 1.0, 40)
    y = 0.3 + 0.6 * x + 0.2 * x**2
    exponent, convexity = log_impact_fit(x, y)
    assert exponent > 0
    assert np.isclose(convexity, 0.2)


def test_permanence_feature_is_delayed_until_outcome_is_known() -> None:
    index = pd.date_range("2020-01-01", periods=50, freq="10s", tz="UTC")
    midpoint = pd.Series(np.exp(np.linspace(0, 0.01, 50)), index=index)
    signed = pd.Series(np.ones(50), index=index)
    gross = pd.Series(np.ones(50) * 2, index=index)
    stress = pd.Series(np.ones(50), index=index)
    result = impact_features(midpoint, signed, gross, stress, window=10, horizon=2)
    assert result["known_permanence_5m"].iloc[:11].isna().all()
    assert result["known_permanence_5m"].iloc[20:].notna().all()
