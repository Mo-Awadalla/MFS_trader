from decimal import Decimal as D

import pandas as pd

from research.futures_response_hft import Account, Tape, cash, compatible, fok, plan, replay


def frame(times=None):
    times = times or [0, 1_000_000_000, 2_000_000_000, 3_000_000_000]
    return pd.DataFrame({"timestamp": pd.to_datetime(times, utc=True), "bid_price": [400.]*len(times),
                         "ask_price": [400.01]*len(times), "bid_size": [1.]*len(times), "ask_size": [1.]*len(times),
                         "conditions": ['["R"]']*len(times), "bid_exchange": ["P"]*len(times), "ask_exchange": ["P"]*len(times)})


def test_complete_tied_predecessor_group_is_preserved_for_execution():
    data = frame([0, 1_000_000_000, 1_000_000_000, 3_000_000_000])
    data.loc[1, "ask_price"] = 400.02
    quotes = compatible(Tape(data), 2_000_000_000, 1_000_000, True)
    assert quotes["known"] and quotes["first_index"] == 1 and quotes["stop_index"] == 3
    assert quotes["price_lower"] == D("400.01") and quotes["price_upper"] == D("400.02")


def test_signal_rejects_conflicting_same_timestamp_state():
    data = frame([0, 1_000_000_000, 1_000_000_000, 3_000_000_000])
    data.loc[1, "ask_price"] = 400.02
    event = {"signal_cutoff_ns": 2_000_000_000, "return_bps": 5}
    assert not plan(Tape(data), event, "follow_impulse")["eligible"]


def test_fok_mixed_price_or_unknown_depth_preserves_inventory_uncertainty():
    values = {"known": True, "prices": [D(10), D(11)], "sizes": [D(100), D(100)]}
    assert fok(values, 10, True, D("10.5")) == "unknown"
    values["prices"] = [D(10), D(10)]
    values["sizes"] = [D(100), D(5)]
    assert fok(values, 10, True, D(11)) == "unknown"


def test_nonmarketable_fok_has_no_fill_even_when_depth_is_small():
    values = {"known": True, "prices": [D(11), D(12)], "sizes": [D(1), D(1)]}
    assert fok(values, 10, True, D(10)) == "no_fill"


def test_unknown_inventory_halts_account_and_is_not_booked_as_zero_profit():
    account = Account()
    account.book({"status": "unknown_entry"})
    assert account.halted and account.lower == 10000 and account.upper == 10000


def test_both_minimum_commissions_and_full_day_short_borrow_are_charged():
    scenario = {"fee_multiple": 1, "adverse_multiple": 1}
    long = cash(10, True, D(400), D(401), scenario)
    short = cash(10, False, D(401), D(400), scenario)
    assert long["gross"] == short["gross"] == 10 and long["commissions"] == short["commissions"] == 2
    assert long["borrow"] == 0 and short["borrow"] > 0 and short["net"] < long["net"]


def test_no_quote_successor_makes_fill_unresolved():
    quote = compatible(Tape(frame()), 4_000_000_000, 1_000_000, True)
    assert not quote["known"] and quote["reason"] == "unbracketed_quote_window"


def test_latency_stress_delays_frozen_signal_without_future_quote_resizing():
    tape = Tape(frame(list(range(0, 33_000_000_000, 1_000_000_000))))
    event = {"decision_ns": 2_100_000_000, "signal_cutoff_ns": 2_000_000_000, "return_bps": 5}
    intent = plan(tape, event, "follow_impulse")
    scenario = {"feed_ms": 1000, "outbound_ms": 1000, "ack_ms": 1000, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 1}
    result = replay(tape, event, intent, scenario)
    assert result["status"] == "conditional_complete" and result["quantity"] == intent["quantity"]
    assert result["entry_arrival_ns"] == 4_050_000_000 and result["exit_arrival_ns"] == 21_100_000_000
    assert result["inventory_schedule_upper_ns"] == 17_052_000_000 and result["upper"]["net"] < 0
