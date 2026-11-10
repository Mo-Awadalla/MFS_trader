from __future__ import annotations

import numpy as np

from research.multiscale_liquidity import (
    haar_energy_ratio,
    multifractal_width,
    norm_ratios,
    normalized_profile,
    power_law_fit,
)


def test_norm_ratios_increase_with_p_for_concentrated_field() -> None:
    ratios = norm_ratios(np.array([1.0, 1.0, 1.0, 10.0]))
    assert ratios["l4_l2"] < ratios["l8_l2"] < ratios["l16_l2"] < ratios["linf_l2"]


def test_profile_is_width_and_amplitude_normalized() -> None:
    first = normalized_profile(np.array([-2.0, -1.0, 1.0, 2.0]), np.ones(4))
    second = normalized_profile(np.array([-4.0, -2.0, 2.0, 4.0]), np.ones(4) * 5.0)
    np.testing.assert_allclose(first, second)


def test_power_law_fit_identifies_acceleration() -> None:
    age = np.arange(29, -1, -1) * 10.0
    values = 2.0 * (30.0 + age) ** -0.7
    fitted = power_law_fit(values)
    assert fitted["power_alpha"] > 0.5
    assert fitted["power_r2"] > 0.99
    assert fitted["critical_seconds"] == 30.0


def test_multiscale_helpers_are_finite() -> None:
    values = np.sin(np.linspace(0, 8 * np.pi, 64))
    assert np.isfinite(haar_energy_ratio(values))
    assert np.isfinite(multifractal_width(np.tile(values, 5)))
