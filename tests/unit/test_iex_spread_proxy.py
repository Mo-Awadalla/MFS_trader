from decimal import Decimal

import pytest

from research.iex_spread_proxy import Tape, cash, evaluate

SECOND = 1_000_000_000


def fixture():
    rows = [{"type": "H", "event_ns": 0, "flags": 84}, {"type": "O", "event_ns": 0, "flags": 78}]
    for t in (0, 30 * SECOND):
        rows.append({"type": "Q", "event_ns": t, "flags": 0, "bid_price": 1_000_000,
                     "ask_price": 1_001_000, "bid_size": 1000, "ask_size": 1000})
    event = {"date": "synthetic", "symbol": "TEST", "decision_ns": 0, "quantity": 20,
             "quote": {"bid_price": 1_000_000, "ask_price": 1_001_000}}
    case = {"name": "base", "latency_ns": SECOND, "fee_factor": 1, "adverse_factor": 1}
    return rows, event, case


def trade(t, price, qty, identity):
    return {"type": "T", "event_ns": int(t * SECOND), "flags": 0, "price": price,
            "size": qty, "trade_id": identity}


def test_partial_entry_and_partial_target_leave_real_forced_inventory():
    rows, event, case = fixture()
    rows += [trade(2, 1_000_000, 7, 1), trade(9, 1_001_000, 3, 2)]
    r = evaluate(event, Tape(rows), case, "touch")
    assert r["bought_quantity"] == 7 and r["target_quantity"] == 3 and r["forced_quantity"] == 4
    assert [o["quantity"] for o in r["orders"]] == [7, 3, 4]
    assert Decimal(r["commission_usd"]) == 3
    assert Decimal(r["gross_usd"]) == Decimal("0.3")
    assert Decimal(r["net_usd"]) == Decimal("-2.862201")


def test_exact_touch_does_not_fill_strict_trade_through_case():
    rows, event, case = fixture()
    rows.append(trade(2, 1_000_000, 100, 1))
    r = evaluate(event, Tape(rows), case, "strict_trade_through")
    assert r["outcome"] == "conditional_no_entry"


def test_invalid_latest_quote_does_not_use_old_valid_for_forced_exit():
    rows, event, case = fixture()
    rows.insert(3, {"type": "Q", "event_ns": 17 * SECOND, "flags": 0, "bid_price": 0,
                    "ask_price": 0, "bid_size": 0, "ask_size": 0})
    rows.append(trade(2, 999_900, 7, 1))
    r = evaluate(event, Tape(rows), case, "touch")
    assert r["outcome"] == "unknown_forced_exit_with_inventory" and r["net_usd"] is None
    assert r["residual_quantity"] == 7


def test_trade_at_cancel_boundary_is_unknown_not_assigned_zero():
    rows, event, case = fixture()
    rows.append(trade(6, 999_900, 10, 1))
    r = evaluate(event, Tape(rows), case, "touch")
    assert r["net_usd"] is None and "boundary" in r["outcome"]


def test_no_same_order_future_size_resizing():
    rows, event, case = fixture()
    rows.append(trade(2, 999_900, 10000, 1))
    r = evaluate(event, Tape(rows), case, "touch")
    assert r["bought_quantity"] == event["quantity"] == 20


def test_used_trade_break_remains_unknown():
    rows, event, case = fixture()
    rows += [trade(2, 999_900, 10, 1), {"type": "B", "event_ns": 22 * SECOND, "trade_id": 1}]
    r = evaluate(event, Tape(rows), case, "touch")
    assert r["net_usd"] is None and "broken" in r["outcome"]


def test_cash_refuses_to_silently_mark_open_inventory_flat():
    with pytest.raises(ValueError, match="Open inventory"):
        cash([{"side": "buy", "quantity": 1, "price": 1_000_000}])


def test_quote_at_order_arrival_is_unknown_without_venue_order_sequence():
    rows, event, case = fixture()
    rows.insert(3, {**rows[2], "event_ns": 1_050_000_000})
    r = evaluate(event, Tape(rows), case, "touch")
    assert r["outcome"] == "unknown_entry_state" and r["net_usd"] is None
