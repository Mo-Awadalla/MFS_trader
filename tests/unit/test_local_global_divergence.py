import numpy as np
import pytest

from research_scout.test_h1_local_global_divergence_v9 import rolling_at_decisions


def test_rolling_pressure_statistics_land_on_ten_second_decisions() -> None:
    values = np.ones(70)

    maximum = rolling_at_decisions(values, "max")
    rms = rolling_at_decisions(values, "rms")
    total = rolling_at_decisions(values, "sum")

    assert np.isnan(maximum[:2]).all()
    assert maximum[2:].tolist() == [1.0] * 5
    assert rms[2:].tolist() == [1.0] * 5
    assert total[2:].tolist() == [30.0, 40.0, 50.0, 60.0, 60.0]


def test_rolling_pressure_rejects_unknown_operation() -> None:
    with pytest.raises(ValueError, match="unknown rolling operation"):
        rolling_at_decisions(np.ones(60), "median")
