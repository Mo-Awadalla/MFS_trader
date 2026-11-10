import numpy as np
import pytest

from research.market_lag_coverage import sample


def test_exact_cutoff_and_future_price_do_not_change_first_candidate():
    times = np.array([700_000, 1_700_000, 1_750_000, 2_000_000], dtype=np.int64)
    bid, ask = np.array([100, 100.2, 1, 200.0]), np.array([100.01, 100.21, 1.01, 201.0])
    result = sample(times, bid, ask, 0, 1)
    assert result["candidate"][0] and result["anchor_row"][0] == 0 and result["current_row"][0] == 1
    assert result["decision_us"][0] == 2_000_000


def test_missing_old_snapshot_and_stale_snapshot_cannot_form_candidate():
    times = np.array([1_700_000], dtype=np.int64)
    result = sample(times, np.array([100.0]), np.array([100.1]), 0, 1)
    assert not result["valid"][0] and not result["candidate"].any()
    assert not result["valid"][-1]


def test_both_sides_must_move_and_crossed_quotes_are_invalid():
    times = np.array([700_000, 1_700_000], dtype=np.int64)
    result = sample(times, np.array([100, 100.2]), np.array([100.01, 100.21]), 0, 1)
    assert result["direction"][0] == 1
    result = sample(times, np.array([100, 99.9]), np.array([100.01, 100.21]), 0, 1)
    assert result["direction"][0] == 0
    result = sample(times, np.array([100, 100.3]), np.array([100.01, 100.21]), 0, 1)
    assert not result["valid"][0]


def test_downward_boundary_is_queued_for_exact_check():
    times = np.array([700_000, 1_700_000], dtype=np.int64)
    result = sample(times, np.array([100, 99.85]), np.array([200, 199.7]), 0, 1)
    assert result["near_boundary"][0]


def test_capture_regression_is_rejected_and_duplicate_cutoff_is_excluded():
    with pytest.raises(AssertionError):
        sample(np.array([2, 1], dtype=np.int64), np.array([100, 101]), np.array([101, 102]), 0, 1)
    result = sample(np.array([700_000, 1_750_000, 1_750_000], dtype=np.int64),
                    np.array([100, 101, 102]), np.array([100.1, 101.1, 102.1]), 0, 1)
    assert result["current_row"][0] == 0 and not result["candidate"][0]
