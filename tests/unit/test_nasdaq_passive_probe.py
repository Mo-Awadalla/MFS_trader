"""Queue position, partial fills, cancel races and cash risks of passive replay."""

from decimal import Decimal as D

import pytest

from research.nasdaq_mbo_book import Book
from research.nasdaq_passive_probe import CASES, Case, Passive, Unknown, cash, schedule, simulate

P = 1000000000
T = 1758029503610000000
EVENT = {"decision_ns": T, "bid_price_int": 100 * P, "ask_price_int": 101 * P, "quantity": 4}


def rec(time, action, side="N", oid=0, price=None, size=0, row=0):
    return {"ts_event": time, "action": action, "side": side, "order_id": oid,
            "price": price, "size": size, "source_row": row}


def book():
    state = Book()
    state.apply("R", "N", 0, None, 0, 0)
    state.apply("A", "B", 1, 100 * P, 100, 1)
    state.apply("A", "A", 2, 101 * P, 100, 2)
    return state


def apply(order, state, row):
    order.on_record(row, state)
    state.apply(row["action"], row["side"], row["order_id"], row["price"], row["size"], row["source_row"])


def source(extra):
    rows = [rec(T - 100, "R"), rec(T - 90, "A", "B", 1, 100 * P, 100),
            rec(T - 80, "A", "A", 2, 101 * P, 100), *extra, rec(T + 6 * P, "N")]
    rows.sort(key=lambda r: r["ts_event"])
    return [{**r, "source_row": i} for i, r in enumerate(rows)]


def entry(quantity=2, at=3000000):
    return [rec(T + 2000000, "C", "B", 1, 100 * P, 100),
            rec(T + 2000001, "A", "B", 3, 100 * P, 100),
            rec(T + at, "F", "B", 3, 100 * P, quantity),
            rec(T + at, "C", "B", 3, 100 * P, quantity)]


def test_queue_fill_not_removed_twice_and_cancellations_do_not_fill_us():
    state = book()
    order = Passive("bid", "B", 100 * P, 4, state, T, [])
    apply(order, state, rec(T + 1, "F", "B", 1, 100 * P, 40))
    assert order.ahead == {1: 100} and not order.fills
    apply(order, state, rec(T + 2, "C", "B", 1, 100 * P, 40))
    apply(order, state, rec(T + 3, "C", "B", 1, 100 * P, 60))
    assert not order.ahead and not order.fills
    apply(order, state, rec(T + 4, "A", "B", 3, 100 * P, 100))
    apply(order, state, rec(T + 5, "F", "B", 3, 100 * P, 2))
    assert order.remaining == 2 and order.fills[0]["quantity"] == 2


def test_hidden_trade_and_touch_never_supply_a_fill():
    state = book()
    order = Passive("bid", "B", 100 * P, 4, state, T, [])
    apply(order, state, rec(T + 1, "C", "B", 1, 100 * P, 100))
    apply(order, state, rec(T + 2, "T", "N", 0, 99 * P, 1000))
    apply(order, state, rec(T + 3, "A", "A", 3, 100 * P, 100))
    assert not order.fills and order.remaining == 4


def test_modification_increase_requeues_but_reduction_retains_priority():
    state = book()
    order = Passive("bid", "B", 100 * P, 4, state, T, [])
    apply(order, state, rec(T + 1, "M", "B", 1, 100 * P, 50))
    assert order.ahead == {1: 50}
    apply(order, state, rec(T + 2, "M", "B", 1, 100 * P, 60))
    assert not order.ahead
    apply(order, state, rec(T + 3, "F", "B", 1, 100 * P, 10))
    assert order.remaining == 0 and order.fills[0]["quantity"] == 4


@pytest.mark.parametrize("failure", ["ahead", "better", "off_display"])
def test_unresolved_matching_is_unknown(failure):
    state = book()
    order = Passive("bid", "B", 100 * P, 4, state, T, [])
    if failure != "ahead":
        apply(order, state, rec(T + 1, "C", "B", 1, 100 * P, 100))
    if failure == "better":
        apply(order, state, rec(T + 2, "A", "B", 4, 100 * P + P // 2, 100))
    apply(order, state, rec(T + 3, "A", "B", 3, 100 * P, 100))
    with pytest.raises(Unknown):
        apply(order, state, rec(T + 4, "F", "B", 3, (99 if failure == "off_display" else 100) * P, 10))


def test_marketable_posting_is_unknown_not_fictional_rejection_or_fill():
    with pytest.raises(Unknown, match="marketable_passive"):
        Passive("bid", "B", 101 * P, 4, book(), T, [])


def test_partial_entry_partial_ask_and_forced_remainder_pay_three_minimums():
    rows = source(entry() + [rec(T + 1100000000, "C", "A", 2, 101 * P, 100),
                            rec(T + 1100000001, "A", "A", 4, 101 * P, 100),
                            rec(T + 1200000000, "F", "A", 4, 101 * P, 1),
                            rec(T + 1200000000, "C", "A", 4, 101 * P, 1)])
    result = simulate(rows, EVENT, CASES[0])
    assert result["status"] == "flat" and result["bought"] == result["sold"] == 2
    assert [f["order"] for f in result["fills"]] == ["bid", "ask", "force"]
    assert D(result["cash"]["commissions"]) == 3
    expected = D(1) - D(3) - D(401) / D(10000) - D(201) * D("0.00003") - D(2) * D("0.000166")
    assert D(result["cash"]["net"]) == expected
    assert result["max_inventory_holding_ns"] < 6 * P


@pytest.mark.parametrize("offset, bought", [(-1, 2), (1, 0)])
def test_cancel_race_one_nanosecond_either_side(offset, bought):
    cancel = schedule(T, CASES[0])[1][0] - T
    result = simulate(source(entry(at=cancel + offset)), EVENT, CASES[0])
    assert result["status"] == ("flat" if bought else "no_entry_fill")
    assert result["bought"] == bought


def test_equal_native_clock_is_unknown_with_exact_context():
    post = T + 1050000
    result = simulate(source([rec(post, "N")]), EVENT, CASES[0])
    assert result["unknown_reason"] == "equal_native_clock_at_post_bid"
    assert result["ledger"][-1]["context"]["event_ns"] == post
    assert result["cash"] is None


def test_incomplete_depth_preserves_inventory_and_unknown_profit():
    rows = source(entry() + [rec(T + 4 * P, "C", "B", 3, 100 * P, 98),
                            rec(T + 4 * P + 1, "A", "B", 5, 97 * P, 100)])
    result = simulate(rows, EVENT, CASES[0])
    assert result["unknown_reason"] == "insufficient_forced_exit_depth_inside_collar"
    assert result["residual_known_inventory"] == 2 and result["cash"] is None
    assert D(result["known_cash_component"]["entry_notional"]) == 200


def test_truncated_source_and_active_reset_are_unknown():
    result = simulate(source(entry())[:-1], EVENT, CASES[0])
    assert result["unknown_reason"] == "source_ended_before_order_lifecycle"
    result = simulate(source([rec(T + 4000000, "R")]), EVENT, CASES[0])
    assert result["unknown_reason"] == "book_reset_while_bid_active"


def test_commission_aggregates_partial_fills_per_order_and_stresses_costs():
    fills = [{"order": "bid", "side": "B", "quantity": 100, "price_int": 100 * P},
             {"order": "bid", "side": "B", "quantity": 200, "price_int": 100 * P},
             {"order": "ask", "side": "A", "quantity": 300, "price_int": 101 * P}]
    base = cash(fills, CASES[0])
    fees = cash(fills, Case("fees", 1000000, fee_multiplier=2))
    adverse = cash(fills, Case("adverse", 1000000, adverse_multiplier=2))
    assert D(base["commissions"]) == 3
    assert D(base["net"]) - D(fees["net"]) == 3
    assert D(base["net"]) - D(adverse["net"]) == D("6.03")
