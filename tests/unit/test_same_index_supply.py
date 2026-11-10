import numpy as np
import pandas as pd
import pytest

from research.same_index_supply import NS, Quotes, convergence_budget, decision, fixed_size


def frame(price=100):
    return pd.DataFrame({"timestamp": pd.to_datetime(np.arange(0, 181)*NS, unit="ns", utc=True),
                         "bid_price": price-.005, "ask_price": price+.005, "bid_size": 100., "ask_size": 100.,
                         "conditions": '["R"]', "bid_exchange": "Q", "ask_exchange": "Q"})


def test_identical_index_state_cannot_manufacture_free_profit():
    row = decision(Quotes(frame()), Quotes(frame()), 120*NS)
    assert not row["eligible"] and row["net_if_converged"] < 0


def test_real_relative_gap_selects_rich_short_and_cheap_long():
    a = frame()
    a.loc[a.index >= 118, ["bid_price", "ask_price"]] += .50
    row = decision(Quotes(a), Quotes(frame()), 120*NS)
    assert row["eligible"] and row["direction"] == "short_a_long_b"
    assert row["ratio"] == pytest.approx(1.)


def test_future_prices_and_depth_cannot_change_decision():
    a, b = frame(), frame()
    expected = decision(Quotes(a), Quotes(b), 120*NS)
    a.loc[a.index >= 120, ["bid_price", "ask_price", "bid_size", "ask_size"]] *= 10
    b.loc[b.index >= 120, ["bid_price", "ask_price", "bid_size", "ask_size"]] /= 10
    assert decision(Quotes(a), Quotes(b), 120*NS) == expected


def test_tied_conflicting_current_state_forces_explicit_no_order():
    a = frame()
    other = a.iloc[[119]].copy()
    other["bid_size"] = 2
    a = pd.concat([a.iloc[:119], other, a.iloc[119:]], ignore_index=True)
    row = decision(Quotes(a), Quotes(frame()), 120*NS)
    assert not row["eligible"] and row["reason"] == "missing_invalid_or_tied_current_state"


def test_sizing_requires_integer_hedge_and_both_known_depths():
    a = {"bid_price": 200., "ask_price": 200.02, "bid_size": 1000., "ask_size": 1000.}
    b = {"bid_price": 80., "ask_price": 80.02, "bid_size": 100., "ask_size": 100.}
    size = fixed_size(a, b, 2.5, True)
    assert size["quantity_a"] == 4 and size["quantity_b"] == 10
    assert size["hedge_mismatch"] == 0


def test_convergence_budget_charges_four_orders_and_short_borrow():
    a = {"bid_price": 100., "ask_price": 100.02, "bid_size": 1000., "ask_size": 1000.}
    row = convergence_budget(a, a, 1., 0., True)
    q = row["quantity_a"]
    assert q == row["quantity_b"] == 49
    assert row["gross_if_converged"] == pytest.approx(-q*.04)
    assert row["fees_if_converged"] == pytest.approx(4+2*q*100*.00003+2*q*.0002)
    assert row["borrow_if_converged"] == pytest.approx(q*100.02*.05/365)
    assert row["required_margin"] == pytest.approx(row["minimum_leg_notional"]*.0005)


def test_missing_venue_and_size_are_not_usable_quotes():
    a = frame()
    a.loc[119, "ask_exchange"] = None
    b = frame()
    b.loc[119, "ask_size"] = np.nan
    row = decision(Quotes(a), Quotes(b), 120*NS)
    assert not row["eligible"] and row["reason"] == "missing_invalid_or_tied_current_state"
