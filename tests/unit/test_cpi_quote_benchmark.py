import pandas as pd
import pytest

from research.cpi_quote_benchmark import known_order, replay
from research.halt_hft import NS


def quotes():
    t = [0, .5, 2, 3, 4, 10, 20, 21, 29, 30, 40, 50, 60]
    return pd.DataFrame({"timestamp": pd.to_datetime([int(v*NS) for v in t], unit="ns", utc=True),
                         "ask_price": 100.01, "bid_price": 100., "ask_size": 1000., "bid_size": 1000.,
                         "conditions": '["R"]', "bid_exchange": "Q", "ask_exchange": "Q"})


def test_news_source_delay_ack_and_hold_clocks_are_separate():
    row, _ = replay(quotes(), 0, 15)
    assert row["decision_ns"] == 2*NS
    assert row["source_cutoff_ns"] == NS
    assert row["entry_ns"] == 3250000000 and row["ack_ns"] == 4250000000
    assert row["exit_ns"] == 20500000000
    delayed, _ = replay(quotes(), 0, 30, delay_seconds=3, news_seconds=10)
    assert delayed["entry_ns"] == 13250000000 and delayed["exit_ns"] == 49500000000


def test_future_depth_cannot_resize_the_order():
    frame = quotes()
    before = known_order(frame, 0)
    frame.loc[frame.timestamp.astype('int64') > NS, "ask_size"] = 1.
    result, _ = replay(frame, 0, 15)
    assert result["quantity"] == before["quantity"]
    assert result["status"] == "unknown_entry" and result["net_lower"] is None


def test_closed_trade_cashflow_has_real_spread_and_both_sided_fees():
    row, _ = replay(quotes(), 0, 15)
    assert row["status"] == "conditional_round_trip"
    assert row["quantity"] == 99
    expected = 99*(100-100.01)-2-99*100*.00003-99*.0002-99*(100+100.01)*.0001
    assert row["net_lower"] == pytest.approx(expected)


def test_expired_observation_is_not_automatically_expired_standing_quote():
    frame = quotes().iloc[[0, 1, 12]].copy()
    row, _ = replay(frame, 0, 15)
    assert row["status"] == "conditional_round_trip"


def test_future_price_cannot_change_signal_and_rejection_has_zero_exposure():
    frame = quotes()
    order = known_order(frame, 0)
    frame.loc[frame.timestamp.astype('int64') >= 2*NS, ["ask_price", "bid_price"]] = [102., 101.99]
    assert known_order(frame, 0) == order
    row, _ = replay(frame, 0, 15)
    assert row["status"] == "fok_price_reject" and row["net_lower"] == 0


def test_conflicting_tied_predecessor_cannot_choose_optimistic_depth():
    frame = quotes()
    shallow = frame.iloc[[3]].copy()
    shallow["ask_size"] = 1.
    frame = pd.concat([frame.iloc[:3], shallow, frame.iloc[3:]], ignore_index=True)
    row, trace = replay(frame, 0, 15)
    assert row["status"] == "unknown_entry" and row["net_lower"] is None
    assert trace[0]["states"] == 2
