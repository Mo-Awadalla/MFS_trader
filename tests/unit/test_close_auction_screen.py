import pytest

from research_scout.screen_close_auction_20260930 import screen


def states():
    a = {"receive_ns": 9000000000, "event_ns": 8999000000, "auction_time_ns": 75000000000,
         "auction_type": "C", "auction_status": 0, "freeze_status": 0, "ind_match_price": 499.,
         "paired_qty": 100000, "total_imbalance_qty": 10000, "side": "A"}
    q = {"receive_ns": 9950000000, "event_ns": 9949999000, "bid_px_00": 500., "ask_px_00": 500.01,
         "bid_sz_00": 1000, "ask_sz_00": 1000, "flags": 128}
    return a, q


def test_limit_covers_all_costs_and_margin_with_fixed_predecision_size():
    a, q = states()
    r = screen(a, q, 10000000000, 75000000000)
    assert r["eligible"] and r["quantity"] == 19
    limit, qty = r["limit"], r["quantity"]
    fees = 2 * max(1., .0075 * qty) + qty * (.00003 * 500 + .0002)
    gain_after_cost = qty * (500 - limit) - fees - qty * (500 + limit) * .0001
    assert gain_after_cost >= qty * limit * .0002
    higher = limit + .01
    assert qty * (500 - higher) - fees - qty * (500 + higher) * .0001 < qty * higher * .0002


@pytest.mark.parametrize("which,field,value", [("q", "receive_ns", 10000000000),
                                               ("a", "event_ns", 10000000001),
                                               ("q", "receive_ns", 9600000000)])
def test_future_ties_and_stale_quotes_do_not_create_signals(which, field, value):
    a, q = states()
    (q if which == "q" else a)[field] = value
    assert not screen(a, q, 10000000000, 75000000000)["eligible"]


def test_no_admission_for_invalid_or_frozen_market_state():
    a, q = states()
    q["bid_px_00"] = 501.
    assert screen(a, q, 10000000000, 75000000000)["reason"] == "invalid_market_state"
    a, q = states()
    a["freeze_status"] = 1
    assert screen(a, q, 10000000000, 75000000000)["reason"] == "invalid_or_frozen_auction"


def test_indicative_match_is_a_signal_and_must_be_strictly_below_limit():
    a, q = states()
    first = screen(a, q, 10000000000, 75000000000)
    a["ind_match_price"] = first["limit"]
    assert screen(a, q, 10000000000, 75000000000)["reason"] == "discount_below_cost_and_margin_gate"
    a["ind_match_price"] = 500.
    r = screen(a, q, 10000000000, 75000000000)
    assert r["hypothetical_net"] < 0 and not r["eligible"]
