from research.futures_etf_budget import budget


def quote(bid=400, ask=400.01, size=10000):
    return {"bid_price": bid, "ask_price": ask, "bid_size": size, "ask_size": size}


def test_etf_that_already_caught_up_has_no_budget():
    event = {"current_price": 4002, "reference_price": 4000}
    row = budget(quote(400.2, 400.21), quote(), event)
    assert not row["eligible"] and row["remaining_budget"] < 0


def test_minimum_commissions_and_adverse_cost_are_both_included():
    event = {"current_price": 4010, "reference_price": 4000}
    row = budget(quote(), quote(), event)
    assert row["quantity"] == 24 and row["commission_cost"] == 2 and row["adverse_cost"] > 1.9
    assert row["borrow_cost"] == 0 and row["eligible"]


def test_short_residual_direction_and_one_day_borrow_charge():
    event = {"current_price": 3990, "reference_price": 4000}
    row = budget(quote(), quote(), event)
    assert not row["long"] and row["signed_residual_bps"] == 25 and row["borrow_cost"] > 1.3


def test_known_depth_limits_quantity_without_future_resizing():
    event = {"current_price": 4010, "reference_price": 4000}
    row = budget(quote(size=5), quote(), event)
    assert row["quantity"] == 0 and not row["eligible"]
