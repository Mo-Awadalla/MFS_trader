from research.iex_spread_supply import eligibility


def example():
    quote = {"symbol": "TEST", "flags": 0, "bid_price": 500_000, "ask_price": 501_000,
             "bid_size": 2000, "ask_size": 2000}
    trades = [{"price": 500_500, "size": 100} for _ in range(10)]
    return quote, trades


def test_displayed_budget_includes_minimum_commission_and_causal_quantity():
    q, ts = example()
    reason, row = eligibility(q, ts, ord("T"), ord("N"))
    assert reason == "candidate" and row["quantity"] == 199
    assert row["quoted_net_budget_usd"] == "15.575879"


def test_missing_or_halted_status_is_not_zero_liquidity():
    q, ts = example()
    assert eligibility(q, ts, None, ord("N"))[0] == "trading_status"
    assert eligibility(q, ts, ord("T"), ord("O"))[0] == "trading_status"


def test_past_activity_and_last_price_required_before_candidate():
    q, ts = example()
    assert eligibility(q, ts[:9], ord("T"), ord("N"))[0] == "insufficient_prior_activity"
    ts[-1] = {"price": 501_001, "size": 100}
    assert eligibility(q, ts, ord("T"), ord("N"))[0] == "last_trade_outside_current_quote"


def test_crossed_or_invalid_latest_book_not_replaced_by_old_quote():
    q, ts = example()
    q["ask_price"] = q["bid_price"]
    assert eligibility(q, ts, ord("T"), ord("N"))[0] == "invalid_current_quote"


def test_trade_activity_cannot_offset_insufficient_spread_after_costs():
    q, ts = example()
    q["ask_price"] = 500_100
    for t in ts:
        t["price"] = 500_050
    assert eligibility(q, ts, ord("T"), ord("N"))[0] == "spread_below_cost_plus_2bp"
