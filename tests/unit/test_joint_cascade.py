import numpy as np
import pandas as pd

from research_scout.test_joint_cascade_v10 import add_future_outcomes, robust_z


def test_robust_z_uses_frozen_location_and_scale() -> None:
    values = pd.Series([1.0, 3.0, 5.0])

    assert robust_z(values, median=3.0, iqr=2.0).tolist() == [-1.0, 0.0, 1.0]


def test_future_outcomes_are_strictly_forward() -> None:
    index = pd.date_range("2024-01-01", periods=8, freq="10s", tz="UTC")
    frame = pd.DataFrame(
        {
            "depth_mean_60s": [100.0, 90.0, 80.0, 70.0, 60.0, 50.0, 40.0, 30.0],
            "spread_mean": [1.0, 2.0, 1.0, 3.0, 1.0, 2.0, 4.0, 5.0],
            "midpoint": np.exp(np.arange(8) / 10_000.0) * 100.0,
            "pressure_linf_l2_60s": np.ones(8),
        },
        index=index,
    )

    result = add_future_outcomes(frame)

    assert result.iloc[0]["future_max_spread_widening_bps"] == 3.0
    assert result.iloc[0]["future_max_touch_depth_depletion"] == 0.6
    assert np.isclose(result.iloc[0]["future_signed_return_bps"], 6.0)
    assert np.isnan(result.iloc[2]["future_signed_return_bps"])
