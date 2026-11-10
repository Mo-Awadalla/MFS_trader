import numpy as np
import pytest

from research.cross_venue_gate import basis_gap, freshness, screen_day, visible_quantity


def book(bid, ask, n=1000):
    clock = np.arange(1, n + 1) * 100000
    return {"bid": np.full(n, bid), "ask": np.full(n, ask),
            "bid_qty": np.full(n, 10.), "ask_qty": np.full(n, 10.),
            "local_us": clock - 1, "exchange_us": clock - 1001}


def test_gap_cost_units_use_one_leg_mean_not_total_gross_exposure():
    assert basis_gap(np.array([100.]), np.array([100.33]))[0] == pytest.approx(32.9456396945)


def test_size_uses_both_venues_and_equal_btc_amounts():
    a, b = book(100., 100.1), book(100.5, 100.6)
    b["bid_qty"][:] = .123
    assert visible_quantity(a, b)[0] == pytest.approx(.012)


def test_stale_or_crossed_latest_book_cannot_generate_an_opportunity():
    a, b = book(100., 100.1), book(101., 101.1)
    clock = np.arange(1, 1001) * 100000
    b["local_us"][:] = clock - 250001
    b["exchange_us"][:] = b["local_us"] - 1000
    assert not freshness(b, clock, 250000).any()
    result = screen_day(a, b, "synthetic")
    assert not result["opportunities"]
    b["local_us"][:] = clock - 1
    b["exchange_us"][:] = clock - 1001
    b["ask"][:] = 100.9
    assert not freshness(b, clock, 250000).any()


def test_disappearing_future_gap_does_not_erase_initial_opportunity():
    a, b = book(100., 100.1), book(100.2, 100.3)
    b["bid"][650] = 100.6
    b["ask"][650] = 100.7
    result = screen_day(a, b, "synthetic")
    assert len(result["opportunities"]) == 1
    event = result["opportunities"][0]
    assert event["opening_gap_bps"] > 33
    assert event["gap_after_200ms_bps"] < 28
