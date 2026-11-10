import numpy as np
import pandas as pd
import pytest

from research_scout.run_crypto_edge_search_20260930 import simulate


def inputs(seconds):
    return pd.DataFrame([{"date": "2024-01-15", "second": s,
                          "current_spread_bps": 1.0, "entry_buy": 100.0,
                          "entry_sell": 99.99, "exit_buy": 101.0,
                          "exit_sell": 101.01} for s in seconds])


def test_both_sides_pay_fees_on_both_notionals():
    for direction in [1, -1]:
        trades, days = simulate(inputs([120]), np.array([direction * 30.0]), margin=0)
        t = trades.iloc[0]
        entry = t.entry * (1 + direction * 0.0001)
        exit_price = t.exit * (1 - direction * 0.0001)
        expected = direction * t.quantity * (exit_price - entry)
        expected -= t.quantity * (entry + exit_price) * 0.0005
        assert t.pnl == pytest.approx(expected)
        assert days.cash.iloc[0] == pytest.approx(10000 + expected)


def test_funding_boundary_and_overlapping_trades_excluded():
    trades, _ = simulate(inputs([120, 180, 240, 28740]), np.repeat(30.0, 4), margin=0)
    assert trades.second.tolist() == [120, 240]


def test_high_fees_do_not_reselect_signals():
    frame = inputs([120, 240])
    trades, _ = simulate(frame, np.repeat(30.0, 2), margin=0)
    stress, _ = simulate(frame, np.repeat(30.0, 2), margin=0, fee_side=10)
    assert trades.second.tolist() == stress.second.tolist()
    assert stress.pnl.sum() < trades.pnl.sum()


def test_cannot_open_with_prediction_below_costs():
    trades, days = simulate(inputs([120, 240]), np.array([5.0, -5.0]), margin=0)
    assert trades.empty
    assert days.cash.iloc[0] == 10000
