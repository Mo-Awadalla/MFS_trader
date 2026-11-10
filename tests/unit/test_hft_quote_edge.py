import numpy as np
import pandas as pd
import pytest

from research.hft_quote_edge import (
    BOOK_FEATURES,
    asof_state,
    prior_indices,
    replay,
    rolling_sum,
    symbol_panel,
)


def test_equal_time_messages_are_not_available_and_bad_order_fails():
    assert prior_indices(np.array([10, 20, 20, 30]), np.array([10, 20, 21])).tolist() == [-1, 0, 2]
    with pytest.raises(ValueError, match="nonmonotonic"):
        prior_indices(np.array([20, 10]), np.array([30]))


def test_invalid_quote_does_not_resurrect_previous_good_quote():
    times = np.array([1, 2]) * 1_000_000_000
    values = np.array([[100, 101], [np.nan, np.nan]])
    state = asof_state(times, values, np.array([3]) * 1_000_000_000)
    assert np.isnan(state[0, 0])
    assert state[0, -1] == 1


def test_window_has_left_inclusive_right_exclusive_boundaries():
    times = np.array([0, 1, 2, 3]) * 1_000_000_000
    actual = rolling_sum(times, np.array([100, 2, 3, 999]), np.array([3]) * 1_000_000_000, 2)
    assert actual.tolist() == [5]


def sample():
    return pd.DataFrame([{"date": "2025-01-02", "symbol": "SPY", "second": t,
        "eligible": True, "ask": 100.0, "ask_qty": 1000,
        "entry_250_ask": 100.0, "entry_250_ask_qty": 1000, "entry_250_age": 0.1,
        "exit_250_5_bid": 101.0, "exit_250_5_bid_qty": 1000, "exit_250_5_age": 0.1}
        for t in [30, 35, 40]])


def test_capital_nonoverlap_and_integer_shares():
    ledger, daily = replay(sample(), np.repeat(100.0, 3), 5)
    assert ledger.second.tolist() == [30, 40]
    assert (ledger.quantity * ledger.entry <= 10100).all()
    first = ledger.iloc[0]
    expected = first.quantity * (101 * 0.9999 - 100 * 1.0001)
    expected -= first.quantity * 0.010119 + first.quantity * 101 * 0.9999 * 0.0000051
    assert first.pnl == pytest.approx(expected)
    assert daily.cash.iloc[0] == pytest.approx(10000 + ledger.pnl.sum())


def test_missing_exit_blocks_instead_of_silently_removing_loss():
    frame = sample()
    frame.loc[0, "exit_250_5_bid"] = np.nan
    ledger, daily = replay(frame, np.repeat(100.0, 3), 5)
    assert len(ledger) == 1 and ledger.iloc[0].status == "unresolved_exit"
    assert daily.unresolved.sum() == 1


def test_cost_stress_keeps_signal_selection_fixed():
    frame = sample()
    base, _ = replay(frame, np.repeat(10.0, 3), 5)
    stress, _ = replay(frame, np.repeat(10.0, 3), 5, slippage_bps=2)
    assert base.second.tolist() == stress.second.tolist()
    assert stress.pnl.sum() < base.pnl.sum()


def test_fill_size_uses_arrival_liquidity_not_future_exit_liquidity():
    frame = sample()
    frame.loc[0, "exit_250_5_bid_qty"] = 1
    ledger, daily = replay(frame, np.repeat(100.0, 3), 5)
    assert ledger.iloc[0].quantity > 1
    assert daily.unresolved.sum() == 1


def test_future_prices_cannot_change_features_for_any_datetime_resolution():
    start = pd.Timestamp("2025-01-02 09:29:00", tz="America/New_York").tz_convert("UTC")
    times = pd.date_range(start, periods=660, freq="1s") + pd.Timedelta(milliseconds=500)
    frame = pd.DataFrame({"symbol": "SPY", "ts_recv": times, "flags": 128,
                          "bid_px_00": 100.0, "ask_px_00": 100.01,
                          "bid_sz_00": 1000, "ask_sz_00": 2000,
                          "action": "A", "side": "B", "size": 100})
    before = symbol_panel(frame, "2025-01-02", "SPY")
    after_frame = frame.copy()
    future = after_frame.ts_recv > pd.Timestamp("2025-01-02 09:30:30", tz="America/New_York")
    after_frame.loc[future, ["bid_px_00", "ask_px_00"]] += 10
    after = symbol_panel(after_frame, "2025-01-02", "SPY")
    pd.testing.assert_series_equal(before.loc[0, BOOK_FEATURES], after.loc[0, BOOK_FEATURES])
    assert before.loc[0, "target_250_5"] != after.loc[0, "target_250_5"]
    assert before.loc[0, "quote_age_s"] == pytest.approx(0.5)
    frame["ts_recv"] = frame.ts_recv.dt.as_unit("ns")
    ns = symbol_panel(frame, "2025-01-02", "SPY")
    pd.testing.assert_frame_equal(before, ns)
