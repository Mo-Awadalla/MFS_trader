from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.bitcoin_5m_exchange_model import (
    PayoffAwareBitcoinModel,
    actionable_signals,
    attach_targets,
    build_decisions,
    chronological_partition,
    fit_windows,
    propose_trades,
    validate_bars,
)


def inputs(rows=1000):
    times = pd.date_range("2025-01-01", periods=rows, freq="5min", tz="UTC")
    z = np.arange(rows, dtype=float)
    op = 100 * np.exp(0.0001 * z + 0.001 * np.sin(z))
    cl = op * (1 + 0.0003 * np.where(z % 3 == 0, 1, -1))
    volume = 100 + z
    b = pd.DataFrame(
        {
            "open_time": times,
            "open": op,
            "close": cl,
            "high": np.maximum(op, cl) * 1.0002,
            "low": np.minimum(op, cl) * 0.9998,
            "volume": volume,
            "trade_count": 20 + z,
            "taker_buy_base_volume": volume * 0.52,
        }
    )
    m = pd.DataFrame({"create_time": times, "sum_open_interest": 10000 + z})
    return b, m


def test_features_need_only_completed_bars_and_retain_tie_decisions():
    b, m = inputs()
    t = b.open_time.iloc[500]
    before = build_decisions(b, m).set_index("open_time")
    tied = b.copy()
    tied.loc[500, "close"] = tied.loc[500, "open"]
    after = build_decisions(tied, m).set_index("open_time")
    pd.testing.assert_series_equal(before.loc[t], after.loc[t])
    truncated = build_decisions(b.loc[b.open_time < t], m).set_index("open_time")
    pd.testing.assert_series_equal(before.loc[t], truncated.loc[t])
    assert truncated.index.max() == t


def test_future_price_and_metric_changes_do_not_change_current_features():
    b, m = inputs()
    t = b.open_time.iloc[500]
    expected = build_decisions(b, m).set_index("open_time")
    changed = b.copy()
    changed.loc[500:, ["open", "high", "low", "close", "volume", "taker_buy_base_volume"]] *= 2
    changed_m = m.copy()
    changed_m.loc[500:, "sum_open_interest"] *= 3
    actual = build_decisions(changed, changed_m).set_index("open_time")
    pd.testing.assert_frame_equal(expected.loc[:t], actual.loc[:t])


def test_optional_missing_derivatives_do_not_remove_price_decisions():
    b, m = inputs()
    with_oi = build_decisions(b, m)
    without = build_decisions(b, None)
    pd.testing.assert_series_equal(with_oi.open_time, without.open_time)
    assert without.oi_12_missing.eq(1).all()
    assert without.oi_48_missing.eq(1).all()
    assert without.open_interest_log_change_12_bars.isna().all()
    missing = m.copy()
    missing["sum_open_interest"] = np.nan
    pd.testing.assert_frame_equal(without, build_decisions(b, missing))


def test_long_lookback_gap_requires_full_history_recovery():
    b, m = inputs()
    missing_time = b.open_time.iloc[400]
    decisions = build_decisions(b.drop(index=400), m).open_time
    assert not decisions.between(
        missing_time + pd.Timedelta(minutes=5), missing_time + pd.Timedelta(minutes=289 * 5)
    ).any()
    assert (missing_time + pd.Timedelta(minutes=290 * 5)) in set(decisions)


@pytest.mark.parametrize(
    "column,value",
    [
        ("open", np.nan),
        ("close", np.inf),
        ("low", 0),
        ("high", 1),
        ("taker_buy_base_volume", 2000),
        ("taker_buy_base_volume", -1),
        ("trade_count", 1.5),
    ],
)
def test_bad_market_inputs_are_rejected(column, value):
    b, _ = inputs()
    b.loc[500, column] = value
    with pytest.raises(ValueError):
        validate_bars(b)


def test_missing_price_does_not_create_longer_than_five_minute_target():
    b, m = inputs()
    b = b.drop(index=500)
    panel = attach_targets(build_decisions(b, m), b).set_index("open_time")
    assert pd.isna(panel.loc[pd.Timestamp("2025-01-02 17:35", tz="UTC"), "target_return"])
    assert pd.isna(panel.loc[pd.Timestamp("2025-01-02 17:40", tz="UTC"), "target_return"])


def test_zero_return_target_is_retained_and_unavailable_target_stays_null():
    b, m = inputs()
    b.loc[501, "open"] = b.loc[500, "open"]
    b.loc[501, "high"] = max(b.loc[501, ["open", "close", "high"]]) * 1.001
    b.loc[501, "low"] = min(b.loc[501, ["open", "close", "low"]]) * 0.999
    decisions = build_decisions(b, m)
    panel = attach_targets(decisions, b)
    assert len(panel) == len(decisions)
    row = panel.loc[panel.open_time == b.open_time.iloc[500]].iloc[0]
    assert row.target_return == 0 and row.target_up == 0
    assert pd.isna(panel.iloc[-1].target_return)
    assert pd.isna(panel.iloc[-1].target_up)


def test_partition_purges_boundary_labels():
    b, m = inputs()
    panel = attach_targets(build_decisions(b, m), b)
    cutoff = b.open_time.iloc[600]
    training = chronological_partition(panel, panel.open_time.min(), cutoff)
    assert training.target_end.max() < cutoff
    assert not training.open_time.eq(cutoff - pd.Timedelta(minutes=5)).any()


def test_fit_rejects_overlapping_labels_and_uses_training_only_imputation():
    b, _ = inputs(1500)
    panel = attach_targets(build_decisions(b, None), b).dropna(subset=["target_return"])
    cutoff = panel.open_time.iloc[600]
    end = panel.open_time.iloc[950]
    tr = chronological_partition(panel, panel.open_time.min(), cutoff)
    cal = chronological_partition(panel, cutoff, end)
    model = PayoffAwareBitcoinModel().fit(tr, cal)
    assert model.preprocessing.named_steps["simpleimputer"].statistics_[11] == 0
    means = model.preprocessing.named_steps["standardscaler"].mean_.copy()
    future = panel.loc[panel.open_time >= end].copy()
    future["open_interest_log_change_12_bars"] = 100.0
    future["oi_12_missing"] = 0.0
    predictions = model.predict(future)
    np.testing.assert_array_equal(means, model.preprocessing.named_steps["standardscaler"].mean_)
    assert np.isfinite(predictions.expected_return_bps).all()
    with pytest.raises(ValueError, match="overlap"):
        PayoffAwareBitcoinModel().fit(tr, pd.concat([tr.tail(1), cal]))
    with pytest.raises(ValueError, match="after"):
        model.predict(cal)


def test_trade_decisions_use_expected_money_and_default_to_no_admission():
    # All have identical confidence, but only large economic edges justify trades.
    p = pd.DataFrame({"p_up": [0.6, 0.6, 0.6, 0.6], "expected_return_bps": [1, 10, -10, 0]})
    np.testing.assert_array_equal(propose_trades(p), [0, 1, -1, 0])
    np.testing.assert_array_equal(actionable_signals(p), [0, 0, 0, 0])
    np.testing.assert_array_equal(actionable_signals(p, admitted=True), [0, 1, -1, 0])
    p.expected_return_bps = 1
    np.testing.assert_array_equal(
        propose_trades(p, round_trip_cost_bps=1, minimum_net_edge_bps=0), [0, 0, 0, 0]
    )


@pytest.mark.parametrize("cost,edge", [(-1, 2), (6, -1), (np.nan, 2), (6, np.inf)])
def test_bad_cost_assumptions_are_rejected(cost, edge):
    with pytest.raises(ValueError):
        propose_trades(
            pd.DataFrame({"expected_return_bps": [10]}),
            round_trip_cost_bps=cost,
            minimum_net_edge_bps=edge,
        )


def test_quarterly_windows_are_fixed_and_timezone_checked():
    w = fit_windows(pd.Timestamp("2026-01-01", tz="UTC"))
    assert w.training_start == pd.Timestamp("2023-10-01", tz="UTC")
    assert w.calibration_start == pd.Timestamp("2025-10-01", tz="UTC")
    assert w.admission_start == pd.Timestamp("2025-12-01", tz="UTC")
    with pytest.raises(ValueError):
        fit_windows(pd.Timestamp("2026-01-01"))
    with pytest.raises(ValueError):
        fit_windows(pd.Timestamp("2026-02-01", tz="UTC"))
