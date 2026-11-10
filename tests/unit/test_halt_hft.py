import pandas as pd
import pytest

from research.halt_hft import (
    NS,
    asof_quote,
    cashflow,
    entry_state,
    halt_intersection,
    quote_window,
    signal,
)


def frame(times, **changes):
    d = {"timestamp": pd.to_datetime(times, unit="ns", utc=True), "bid_price": 10., "ask_price": 10.01,
         "bid_size": 100., "ask_size": 100., "conditions": '["R"]', "bid_exchange": "Q", "ask_exchange": "Q"}
    d.update(changes)
    return pd.DataFrame(d)


def test_signal_cutoff_is_strict_and_invalid_latest_is_not_replaced():
    q = frame([NS, 2*NS, 3*NS], bid_price=[10., 0., 10.])
    assert asof_quote(q, 2*NS, NS)["source_ns"] == NS
    assert asof_quote(q, 3*NS, NS) is None


def test_conflicting_same_timestamp_signal_states_are_unknown():
    q = frame([NS, NS], ask_size=[100., 200.])
    assert asof_quote(q, 2*NS, NS) is None


def test_quote_window_keeps_predecessor_all_ties_and_requires_successor():
    q = frame([0, NS, NS, 2*NS])
    rows, indices = quote_window(q, NS, 0)
    assert len(rows) == 3 and indices["first_index"] == 0
    assert quote_window(q, 2*NS, 0)[0] is None


def test_fok_mixed_paths_and_shallow_book_not_made_into_no_fill():
    r = frame([0, NS], ask_price=[10.01, 10.02]).to_dict("records")
    assert entry_state(r, 10, 10.01) == "unknown_entry"
    assert entry_state(r, 10, 10.00) == "fok_price_reject"
    assert entry_state(r, 1000, 10.03) == "unknown_entry"
    assert entry_state(r, 10, 10.03) == "conditional_fill"


def test_standing_quote_not_arbitrarily_expired_and_bad_state_not_skipped():
    q = frame([0, 100*NS], bid_price=[0., 10.])
    rows, _ = quote_window(q, 50*NS, NS)
    assert rows is not None and entry_state(rows, 1, 11) == "unknown_entry"


def test_halt_precision_envelope_includes_boundary_and_open_inventory():
    assert halt_intersection([(10*NS, 310*NS)], 9*NS, 9*NS)
    assert halt_intersection([(10*NS, 310*NS)], 0, 15*NS)
    assert not halt_intersection([(10*NS, 310*NS)], 0, 8*NS)


def test_exact_costs_include_two_minimum_commissions_and_both_adverse_sides():
    r = cashflow(10, 10, 10.1)
    assert r["gross"] == pytest.approx(1)
    assert r["fees"] == pytest.approx(2+101*.00003+10*.0002)
    assert r["adverse"] == pytest.approx(.0201)


@pytest.mark.parametrize("old_bid,family", [(10., "up_continuation"), (12., "down_rebound")])
def test_signal_can_qualify_and_future_quotes_cannot_change_order(old_bid, family):
    event = {"halt_ns": 100*NS, "archive_resume_ns": 400*NS, "exchange": "Nasdaq"}
    quotes = frame([69*NS, 98*NS, 404*NS, 450*NS],
                   bid_price=[old_bid, 11., 11.12, 11.], ask_price=[old_bid+.01, 11.01, 11.13, 11.01],
                   bid_size=10000., ask_size=10000.)
    trades = pd.DataFrame({"timestamp": pd.to_datetime([399*NS, 400*NS], unit="ns", utc=True),
                           "exchange": ["D", "Q"], "price": [50., 11.1], "size": [100, 100],
                           "conditions": ['["@","5","X"]']*2})
    first = signal(event, quotes, trades)
    assert first["eligible"] and first["family"] == family
    assert first["decision_ns"] == 406*NS and first["quote_ns"] == 404*NS
    assert first["reopen_index"] == 1 and first["quantity"] == 889
    quotes.loc[3, ["bid_price", "ask_price", "ask_size"]] = [1., 1000., 0.]
    assert signal(event, quotes, trades) == first
