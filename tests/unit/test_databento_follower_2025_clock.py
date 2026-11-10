"""Audit capture-clock failures must stay unknown with exact native timestamps."""

import numpy as np
import pytest

from research_scout.audit_databento_follower_2025_20261003 import clock_failure


@pytest.mark.parametrize(
    "times, flags, expected",
    [
        ([1740000000000000001, 1740000000000000002], [128, 128], None),
        ([1740000000000000002, 1740000000000000001], [128, 128], "Unusable capture clock"),
        ([1740000000000000002, 1740000000000000001], [136, 128], "Unusable capture clock"),
        ([1740000000000000001, (1 << 64) - 1], [128, 128], "Unusable capture clock"),
        ([1740000000000000001, 1740000000000000002], [128, 136], "BAD_TS_RECV record: no removal or timestamp repair"),
    ],
)
def test_native_clock_quality(times, flags, expected):
    raw = np.zeros(2, dtype=[("ts_recv", "<u8"), ("flags", "u1")])
    raw["ts_recv"], raw["flags"] = times, flags
    assert clock_failure(raw) == expected
