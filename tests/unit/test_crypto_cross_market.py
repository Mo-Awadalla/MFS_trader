import numpy as np
import pandas as pd
import pytest

from research.crypto_cross_market import replay, roll_events, states, symbol_features
from research.crypto_passive_replay import DAY_MS, STEP_MS


def book():
    n = DAY_MS // STEP_MS
    return {"bid": np.full(n, 2000.0), "ask": np.full(n, 2000.1),
            "bid_qty": np.full(n, 100.0), "ask_qty": np.full(n, 100.0),
            "event_ms": np.arange(n) * STEP_MS + STEP_MS - 1}


def row():
    return {"date": "synthetic", "decision_ms": 120000, "eligible": True, "ETH_spread_bps": .5,
                "bid": 2000., "ask": 2000.1, "bid_qty": 100., "ask_qty": 100.,
                "entry_1000_ask": 2000.3, "entry_1000_ask_qty": 100.,
                "entry_1000_bid": 2000., "entry_1000_bid_qty": 100.,
                "exit_1000_30_bid": 2003., "exit_1000_30_bid_qty": 100.,
                "exit_1000_30_ask": 1997., "exit_1000_30_ask_qty": 100.}


def test_event_window_excludes_current_and_future_trade():
    times = np.array([1, 5, 9, 10, 11])
    values = np.array([1, 2, 3, 100, 1000])
    assert roll_events(times, values, np.array([10]), 5)[0] == 5


def test_invalid_latest_quote_does_not_resurrect_previous_book():
    b = book()
    b["bid"][1] = 2100
    assert np.isnan(states(b, [500])).all()
    assert states(b, [250])[0, 0] == 2000


def test_future_book_and_trade_changes_do_not_change_features():
    b = book()
    trades = {"time": np.array([100000, 120000]), "price": np.array([2000., 2000.]),
                  "quantity": np.array([1., 1.]), "buyer_maker": np.array([True, False])}
    before, _ = symbol_features(b, trades, np.array([119750]))
    b["bid"][119750 // STEP_MS:] = 90000
    b["ask"][119750 // STEP_MS:] = 90001
    trades["quantity"][1] = 1000000
    after, _ = symbol_features(b, trades, np.array([119750]))
    for key in before:
        assert before[key] == pytest.approx(after[key], nan_ok=True)


def test_ioc_entry_accounts_for_submitted_quantity_and_both_side_costs():
    r = row()
    ledger, daily = replay(pd.DataFrame([r]), np.array([20.]), 30)
    trade = ledger.iloc[0]
    assert trade.quantity == pytest.approx(.499)
    assert trade.fees == pytest.approx(.499 * (2000.3 + 2003) * .0005)
    assert trade.slippage_dollars == pytest.approx(.499 * (2000.3 + 2003) * .0001)
    assert daily.complete.all()


def test_ioc_needing_unknown_deeper_liquidity_is_unresolved():
    r = row()
    r["entry_1000_ask_qty"] = .02
    ledger, daily = replay(pd.DataFrame([r]), np.array([20.]), 30)
    assert ledger.iloc[0].status == "unresolved_entry_depth"
    assert not daily.complete.all()
    assert daily.iloc[0].rejected_entries == 0


def test_submitted_order_with_missing_arrival_is_unresolved_not_rejected():
    r = row()
    r["entry_1000_ask"] = np.nan
    ledger, daily = replay(pd.DataFrame([r]), np.array([20.]), 30)
    assert ledger.iloc[0].status == "unresolved_entry"
    assert not daily.complete.all()


def test_short_costs_and_causal_ioc_collar():
    r = row()
    ledger, daily = replay(pd.DataFrame([r]), np.array([-20.]), 30)
    trade = ledger.iloc[0]
    assert trade.gross_dollars == pytest.approx(trade.quantity * 3.)
    assert trade.pnl == pytest.approx(trade.gross_dollars - trade.fees - trade.slippage_dollars)
    r["entry_1000_bid"] = 1998.
    ledger, daily = replay(pd.DataFrame([r]), np.array([-20.]), 30)
    assert ledger.empty
    assert daily.iloc[0].rejected_entries == 1
