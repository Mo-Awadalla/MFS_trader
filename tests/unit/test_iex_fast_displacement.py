from copy import deepcopy

import pytest

from research.iex_fast_displacement import NS, State, admission, choose, fresh

C = 1673447459000000000


def case():
    def trade(t, p, identity):
        return {"type": "T", "flags": 0, "event_ns": t - 500_000, "capture_ns": t,
                "send_ns": t - 100_000, "price": p, "size": 100, "trade_id": identity}

    def state(t, p, identity):
        return {"quote": {"bid_price": p - 100, "ask_price": p + 100, "bid_size": 3000,
                          "ask_size": 3000, "event_ns": t - 500_000, "capture_ns": t,
                          "send_ns": t - 100_000}, "pending": False, "h": 84, "o": 78,
                "test": False, "trade": trade(t, p, identity)}
    now, old = state(C - 10_000_000, 503000, 10), state(C - NS - 10_000_000, 500000, 1)
    flow = [trade(C - (i + 1) * 10_000_000, 503000, 10 - i) for i in range(5)][::-1]
    return now, old, flow


def admit(args, broken=()):
    return admission("TEST", *args, set(broken), C)


def test_causal_rise_sets_fixed_quantity_and_cost():
    reason, r = admit(case())
    assert reason == "candidate" and r["rule"] == "follow_rise" and r["move_bp"] == "60"
    assert r["quantity"] * r["entry_limit"] <= 10000 * 10000
    assert r["quantity"] == 194 and r["entry_limit"] == 513200


def test_fall_is_long_fade_not_unfunded_short():
    now, old, flow = case()
    for row in [now["trade"], *flow]:
        row["price"] = 497000
        row["size"] = 110
    now["quote"].update(bid_price=496900, ask_price=497100)
    assert admit((now, old, flow))[1]["rule"] == "fade_fall"


def test_capture_boundary_native_future_and_staleness_are_rejected():
    row = {"capture_ns": C, "event_ns": C - 1, "send_ns": C - 1}
    assert not fresh(row, C, NS)
    row.update(capture_ns=C - 1, event_ns=C + 1)
    assert not fresh(row, C, NS)
    now, old, flow = case()
    now["trade"]["event_ns"] = C - 100_000_001
    assert admit((now, old, flow))[0] == "trade_age"


def test_atomic_incomplete_quote_is_not_used():
    args = case()
    args[0]["pending"] = True
    assert admit(args)[0] == "atomic_event_pending"


def test_known_break_invalidates_reference():
    assert admit(case(), [("TEST", 1)])[0] == "broken_anchor_or_current_trade"


def test_multiple_reports_at_one_native_time_are_not_five_events():
    args = case()
    for row in args[2]:
        row["event_ns"] = C - 10_000_000
    assert admit(args)[0] == "one_second_activity"


def test_duplicate_unbroken_id_fails():
    args = case()
    args[2][0]["trade_id"] = args[2][1]["trade_id"]
    with pytest.raises(ValueError, match="Repeated"):
        admit(args)


def test_conservative_commission_and_depth_reject_tiny_orders():
    args = case()
    args[0]["quote"].update(bid_size=100, ask_size=100)
    assert admit(args)[0] == "causal_cost_hurdle"


def test_ranking_and_two_cooldowns_do_not_use_future_returns():
    candidate = admit(case())[1]
    other = {**deepcopy(candidate), "symbol": "AAAA"}
    state = {}
    assert choose([candidate, other], state)[0]["symbol"] == "AAAA"
    assert not choose([{**candidate, "decision_ns": candidate["decision_ns"] + 5 * NS}], state)
    assert choose([{**candidate, "decision_ns": candidate["decision_ns"] + 6 * NS}], state)
    assert not choose([{**candidate, "decision_ns": candidate["decision_ns"] + 12 * NS}], state)


def test_grid_excludes_packet_at_cutoff_and_checks_native_clock():
    state = State(C + 1_000_000, C + 1_000_000)
    state.advance(C)
    assert state.grids == 1 and state.messages == 0
    state = State(C + 1_000_000, C + 1_000_000)
    state.max_clock = C + 1
    with pytest.raises(ValueError, match="crosses"):
        state.advance(C)
