from __future__ import annotations

import numpy as np
import pandas as pd

from research.navier_stokes_liquidity import (
    concentration_features,
    future_jump_outcomes,
    second_snapshots,
)


def _snapshots(periods: int = 120) -> pd.DataFrame:
    index = pd.date_range("2025-01-02 14:25:00+00:00", periods=periods, freq="s")
    midpoint = 100.0 + np.linspace(0.0, 0.02, periods)
    return pd.DataFrame(
        {
            "bid_px_00": midpoint - 0.005,
            "ask_px_00": midpoint + 0.005,
            "bid_sz_00": 1_000.0,
            "ask_sz_00": 900.0,
        },
        index=index,
    )


def test_concentration_ratio_rises_for_localized_flow() -> None:
    snapshots = _snapshots()
    spread = pd.DataFrame(
        {
            "ts_recv": snapshots.index[::10],
            "side": ["B", "A"] * 6,
            "size": [100.0] * 12,
        }
    )
    localized = pd.DataFrame(
        {
            "ts_recv": [snapshots.index[30], snapshots.index[30]],
            "side": ["B", "B"],
            "size": [600.0, 600.0],
        }
    )
    broad = concentration_features(snapshots, spread, event_count=100, duration_seconds=120)
    concentrated = concentration_features(
        snapshots, localized, event_count=100, duration_seconds=120
    )
    assert concentrated["u_linf_l2"] > broad["u_linf_l2"]
    assert concentrated["u_core_fraction"] < broad["u_core_fraction"]


def test_second_snapshots_never_use_end_or_later_records() -> None:
    raw = _snapshots(4).reset_index(names="ts_recv")
    start = pd.Timestamp("2025-01-02 14:25:01+00:00")
    end = pd.Timestamp("2025-01-02 14:25:03+00:00")
    result = second_snapshots(raw, start=start, end=end)
    assert list(result.index) == [start, start + pd.Timedelta(seconds=1)]
    assert result.iloc[-1]["bid_px_00"] == raw.iloc[2]["bid_px_00"]


def test_future_jump_uses_first_midpoint_as_origin() -> None:
    snapshots = _snapshots(3)
    outcome = future_jump_outcomes(snapshots)
    expected = 10_000.0 * np.log(100.02 / 100.0)
    assert np.isclose(outcome["future_abs_return_bps"], expected)
    assert np.isclose(outcome["future_max_excursion_bps"], expected)
