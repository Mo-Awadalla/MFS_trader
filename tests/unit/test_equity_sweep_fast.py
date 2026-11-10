from copy import deepcopy

import numpy as np

from research.equity_sweep_fast import MS, NS, admit, quote, replay, select

T = 1680096610000000000


def sample():
    times = np.array([T - MS, T, T + 10 * MS, T + 1000 * MS, T + 2000 * MS])
    bid = np.array([100 * NS] * 5)
    ask = bid + 10000000
    sizes = np.array([5000] * 5)
    return times, times - 500000, bid, ask, sizes.copy(), sizes.copy(), np.ones(5, dtype=bool), np.arange(5)


def group():
    return {"burst_receive_ns": T, "burst_last_source": 1, "direction": 1,
            "pre_bid_int": 99980000000, "pre_ask_int": 99990000000,
            "burst_quantity": 1000, "burst_pre_quantity": 100, "burst_notional_int": 100000 * NS}


def event():
    r, reason = admit(sample(), group(), T - 10 * NS)
    assert reason is None
    return {**r, "date": "2023-03-29", "symbol": "SPY"}


def test_strict_cutoff_after_completed_sweep_and_fixed_size():
    e = event()
    assert e["decision_ns"] == T + 2 * MS and e["cutoff_ns"] == T + MS
    assert e["quantity"] == 98 and e["quantity"] * e["entry_limit_int"] <= 10000 * NS


def test_future_native_signal_is_rejected():
    p = sample()
    p[1][1] = T + 2 * MS
    assert admit(p, group(), T - 10 * NS)[1] == "signal_age_or_clock"


def test_signal_cannot_fall_back_from_latest_invalid_book():
    p = sample()
    p[6][1] = False
    assert admit(p, group(), T - 10 * NS)[1] == "invalid_or_incomplete_signal_book"


def test_fill_reference_on_exact_capture_boundary_is_unknown():
    assert quote(sample(), T + 10 * MS)[1] == "equal_capture_clock_boundary"


def test_future_size_caps_fills_but_does_not_resize_order():
    p, e = sample(), event()
    p[5][1] = 30
    r = replay(e, p, 1000, {"name": "base", "delay_ms": 1, "fee_multiple": 1, "adverse_multiple": 1})
    assert r["outcome"] == "conditional_priced" and r["requested_quantity"] == 98 and r["filled_quantity"] == 30
    assert r["cash"]["commissions"] == "2"


def test_exit_lacks_depth_and_open_inventory_is_not_zero_cash():
    p, e = sample(), event()
    p[4][3] = 20
    r = replay(e, p, 1000, {"name": "base", "delay_ms": 1, "fee_multiple": 1, "adverse_multiple": 1})
    assert r["outcome"] == "unknown_exit_depth_residual_inventory" and r["net_usd"] is None


def test_limit_and_cost_scenarios_do_not_change_admitted_size():
    p, e = sample(), event()
    p[3][1] = e["entry_limit_int"] + 10000000
    r = replay(e, p, 1000, {"name": "base", "delay_ms": 1, "fee_multiple": 2, "adverse_multiple": 1})
    assert r["outcome"] == "conditional_limit_no_entry" and r["requested_quantity"] == e["quantity"]


def test_cross_symbol_selection_and_cooldown():
    e = event()
    other = {**deepcopy(e), "symbol": "SSO", "burst_quantity": 2000}
    later = {**e, "decision_ns": e["decision_ns"] + 6 * NS}
    repeated = {**other, "decision_ns": e["decision_ns"] + 12 * NS}
    assert [r["symbol"] for r in select([e, other, later, repeated])] == ["SSO", "SPY"]
