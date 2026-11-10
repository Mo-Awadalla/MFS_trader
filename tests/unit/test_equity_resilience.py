"""Execution-cost and causal event-boundary tests for the optimistic screen."""

from decimal import Decimal as D

import numpy as np

from research.equity_resilience import causal_quantity, detect, favorable_quotes, optimistic_cash


def fixture(side=-1):
    qt = np.arange(0, 5_100_000_000, 100_000_000, dtype=np.int64)
    n = len(qt)
    price = 100_000_000_000 if side == -1 else 100_010_000_000
    tt = np.array([3_000_000_000, 3_100_000_000, 3_200_000_000, 3_300_000_000, 3_400_000_000])
    return [qt, qt.copy(), np.full(n, 100_000_000_000), np.full(n, 100_010_000_000),
            np.full(n, 100), np.full(n, 100), np.ones(n, dtype=bool), np.arange(n) * 10,
            tt, tt.copy(), np.full(5, price), np.full(5, 100), np.full(5, side), np.ones(5, dtype=bool),
            np.searchsorted(qt, tt) * 10 - 1, np.array([4_000_000_000])]


def test_resilience_uses_only_completed_causal_trades():
    a = fixture()
    assert len(detect(*a)) == 1
    a[14][-1] = 10000
    assert not detect(*a)


def test_trade_at_cutoff_is_excluded_and_fragments_do_not_inflate_count():
    a = fixture()
    a[8][-1] = a[9][-1] = 3_750_000_000
    assert not detect(*a)
    a = fixture()
    a[8][:] = a[9][:] = 3_000_000_000
    assert not detect(*a)


def test_unknown_trade_side_counts_against_dominance():
    a = fixture()
    a[12][-1] = 0
    a[11][-1] = 500
    assert not detect(*a)


def test_temporary_price_break_and_invalid_book_cancel_resilience():
    a = fixture()
    a[2][25] -= 10_000_000
    assert not detect(*a)
    a = fixture()
    a[6][25] = False
    assert not detect(*a)


def test_ask_resilience_requires_a_later_causal_break():
    a = fixture(1)
    assert not detect(*a)
    a[15] = np.array([4_000_000_000, 4_500_000_000])
    a[3][41:] += 10_000_000
    rows = detect(*a)
    assert len(rows) == 1 and rows[0][0] == 4_500_000_000 and rows[0][1] == 1


def test_quantity_is_frozen_from_signal_depth_and_cash():
    assert causal_quantity(100_000_000_000, 100) == 10
    assert causal_quantity(100_000_000_000, 10000) == 98


def test_minimum_commission_and_adverse_allowance_on_both_legs():
    cash = optimistic_cash(100_000_000_000, 100_100_000_000, 10)
    assert D(cash["gross"]) == 1
    assert D(cash["commissions"]) == 2
    assert D(cash["net"]) == D("-1.23179")
    doubled = optimistic_cash(100_000_000_000, 100_100_000_000, 10, fee_multiple=2)
    assert D(doubled["net"]) < D(cash["net"])


def test_favorable_price_is_explicitly_future_aware_and_rejects_unknown():
    a = fixture()
    a[3][34] -= 1_000_000
    result = favorable_quotes(a, 3_100_000_000, 3_500_000_000, "buy")
    assert result["known"] and result["source_receive_ns"] == 3_400_000_000
    a[6][33] = False
    assert not favorable_quotes(a, 3_100_000_000, 3_500_000_000, "buy")["known"]
