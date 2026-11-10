from copy import deepcopy

import numpy as np

from research.equity_follower_lag import MS, NS, follower, leader, select, snapshot

T = 1680096610000000000


def books(old_bid, new_bid):
    times = np.array([T - NS - MS, T - 100000, T + MS], dtype=np.int64)
    bids = np.array([old_bid, new_bid, new_bid + 10000000], dtype=np.int64)
    sizes = np.array([5000, 5000, 5000])
    return times, times - 100000, bids, bids + 10000000, sizes, sizes, np.ones(3, dtype=bool), np.arange(3)


def setup(down=False):
    raw = books(100 * NS, (99 if down else 101) * NS)
    g = {"burst_receive_ns": T - MS, "burst_last_source": 1, "direction": -1 if down else 1}
    signal, why = leader(raw, g, T - 10 * NS)
    assert why is None
    return signal


def test_long_follower_uses_only_common_anchor_and_current_clocks():
    signal = setup()
    event, why, _ = follower(books(50 * NS, 50 * NS), "UPRO", signal)
    assert why is None and event["multiplier"] == 3 and event["quantity"] == 196
    assert event["projected_exit_int"] > event["follower_current"]["ask_int"]
    assert event["quantity"] * event["entry_limit_int"] <= 10000 * NS


def test_negative_leader_move_can_trigger_a_long_inverse_fund():
    event, why, _ = follower(books(50 * NS, 50 * NS), "SPXU", setup(down=True))
    assert why is None and event["multiplier"] == -3
    assert follower(books(50 * NS, 50 * NS), "UPRO", setup(down=True))[1] == "wrong_long_direction"


def test_already_adjusted_follower_has_no_remaining_budget():
    event, why, _ = follower(books(50 * NS, 52 * NS), "UPRO", setup())
    assert event is None and why == "projected_net_below_2bp"


def test_exact_capture_cutoff_excluded_without_rounding():
    p = books(50 * NS, 51 * NS)
    p[0][1] = T - 36
    assert snapshot(p, T, 250 * MS)[0]["source_index"] == 1
    p[0][1] = T
    assert snapshot(p, T, 250 * MS)[1] == "quote_age_or_native_clock"


def test_latest_invalid_follower_does_not_fall_back():
    p = books(50 * NS, 50 * NS)
    p[6][1] = False
    assert follower(p, "UPRO", setup())[1] == "follower_current_invalid_latest_book"


def test_future_native_clock_invalidates_snapshot():
    p = books(50 * NS, 50 * NS)
    p[1][1] = T + MS
    assert snapshot(p, T, 250 * MS)[1] == "quote_age_or_native_clock"


def test_cost_and_size_gate_cannot_be_rescued_by_large_model_move():
    p = books(50 * NS, 50 * NS)
    p[4][1] = 10
    p[5][1] = 10
    assert follower(p, "UPRO", setup())[1] == "causal_cost_above_12bp"


def test_rank_uses_projected_dollars_then_fixed_cooldowns():
    event = follower(books(50 * NS, 50 * NS), "UPRO", setup())[0]
    other = {**deepcopy(event), "symbol": "SSO", "projected_cash": {"net": "100000"}}
    later = {**event, "decision_ns": event["decision_ns"] + 6 * NS}
    repeat = {**other, "decision_ns": event["decision_ns"] + 12 * NS}
    assert [r["symbol"] for r in select([event, other, later, repeat])] == ["SSO", "UPRO"]
