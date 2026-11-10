"""Check the economic ceiling without fabricating missing-day returns."""

import numpy as np
import pytest

from research_scout.v98_missing_day_bound_20260907 import optimistic_day_factor


def test_ceiling_covers_funded_baskets_including_cash_and_costs():
    rng = np.random.default_rng(98)
    ranges = [{"low": 90.0, "high": 110.0}, {"low": 45.0, "high": 49.0}]
    ceiling = optimistic_day_factor(ranges)
    for _ in range(100):
        weights = rng.dirichlet(np.ones(3))
        cash = 100.0 * weights[2]
        for weight, bounds in zip(weights[:2], ranges, strict=True):
            entry, exit_ = rng.uniform(bounds["low"], bounds["high"], 2)
            shares = (100 * weight) / (entry * 1.0005)
            cash += shares * exit_ * 0.9995
        assert cash <= 100 * ceiling
    assert ceiling >= 1.0


def test_bad_or_absent_extrema_cannot_silently_produce_a_bound():
    for ranges in [
        [],
        [{"low": 0, "high": 10}],
        [{"low": 12, "high": 10}],
        [{"low": float("nan"), "high": 10}],
    ]:
        with pytest.raises(ValueError):
            optimistic_day_factor(ranges)
