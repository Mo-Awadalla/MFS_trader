import numpy as np
import pandas as pd
import pytest

from research.bitcoin_5m_exchange_validation import (
    assess_admission,
    replay_trades,
    summarize_trades,
)


def prices():
    t = pd.date_range("2025-01-01", periods=5, freq="5min", tz="UTC")
    p = np.array([100, 110, 105, 120, 115], dtype=float)
    b = pd.DataFrame(
        {
            "open_time": t,
            "open": p,
            "high": p,
            "low": p,
            "close": p,
            "volume": 10,
            "trade_count": 5,
            "taker_buy_base_volume": 5,
        }
    )
    return b, t


def test_replay_charges_entry_exit_notionals_and_funding_with_correct_sign():
    b, t = prices()
    decisions = pd.DataFrame({"open_time": t[:1]})
    f = pd.DataFrame(
        {"calc_time": [t[0] + pd.Timedelta(milliseconds=5)], "last_funding_rate": [0.001]}
    )
    long = replay_trades(decisions, b, f, np.array([1]))
    short = replay_trades(decisions, b, f, np.array([-1]))
    assert long.gross_return.iloc[0] == pytest.approx(0.1)
    assert short.gross_return.iloc[0] == pytest.approx(-0.1)
    assert long.funding_return.iloc[0] == pytest.approx(-0.001)
    assert short.funding_return.iloc[0] == pytest.approx(0.001)
    assert long.net_6bps.iloc[0] == pytest.approx(0.1 - 0.001 - 0.0006 * 1.05)
    assert short.net_6bps.iloc[0] == pytest.approx(-0.1 + 0.001 - 0.0006 * 1.05)


def test_missing_price_and_unavailable_future_prevent_fills():
    b, t = prices()
    d = pd.DataFrame({"open_time": t})
    f = pd.DataFrame()
    first = replay_trades(d, b.drop(index=1), f, np.ones(5, dtype=int))
    assert not first.entry_time.isin([t[0], t[1], t[4]]).any()
    delayed = replay_trades(d, b.drop(index=1), f, np.ones(5, dtype=int), delay_bars=1)
    assert not delayed.decision_time.isin([t[0], t[1], t[3], t[4]]).any()
    assert replay_trades(d, b, f, np.zeros(5, dtype=int)).empty


def test_admission_requires_independent_sample_and_positive_cost_adjusted_lower_bound():
    good = {"trades": 100, "active_days": 20, "net_ci95_bps": {"6": [0.1, 5]}}
    assert assess_admission(good)["admitted"]
    for bad in [
        dict(good, trades=99),
        dict(good, active_days=19),
        dict(good, net_ci95_bps={"6": [-0.1, 5]}),
        dict(good, net_ci95_bps={"6": None}),
        {},
    ]:
        assert not assess_admission(bad)["admitted"]


def test_no_trade_summary_cannot_qualify():
    stats = summarize_trades(
        pd.DataFrame(), pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2025-02-01", tz="UTC")
    )
    assert stats["trades"] == 0
    assert stats["calendar_days"] == 31
    assert stats["net_bps"]["6"] is None
    assert not assess_admission(stats)["admitted"]


def test_summary_fee_scenarios_and_uncertainty_reconcile():
    b, t = prices()
    trades = replay_trades(pd.DataFrame({"open_time": t[:1]}), b, pd.DataFrame(), np.array([1]))
    s = summarize_trades(trades, t[0], t[0] + pd.Timedelta(days=1))
    assert s["gross_bps"] == pytest.approx(1000)
    assert s["net_bps"]["4"] == pytest.approx(995.8)
    np.testing.assert_allclose(s["net_ci95_bps"]["4"], [995.8, 995.8])
    assert not assess_admission(s)["admitted"]
