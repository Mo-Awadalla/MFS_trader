import json
from decimal import Decimal as D

from research.spot_perp_response import Tape, cash, compatible, parse, plan, replay
from research.spot_perp_supply import midnight_ns

NS = 1_000_000_000
DAY = "2024-09-01"
MIDNIGHT = midnight_ns(DAY)
DECISION = MIDNIGHT + 16 * NS
EVENT = {"decision_ns": DECISION, "direction": -1}
BASE = {"delay_ms": 1000, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 1}


def book(second, bid="0.2368", ask="0.2369", size="10000", source_line=0):
    stamp = MIDNIGHT + int(second * NS)
    return {"receive_ns": stamp, "transaction_ns": stamp, "publication_ns": stamp,
            "source_line": source_line, "valid": True, "update_id": source_line + 1,
            "bid": D(bid), "ask": D(ask), "bid_quantity": D(size), "ask_quantity": D(size)}


def tape():
    books = [book(t, source_line=i) for i, t in enumerate((15.5, 16.2, 17.0, 17.1, 31.8, 32.0, 34.0, 34.2, 40.0, 40.2))]
    mark = {"receive_ns": DECISION - NS, "publication_ns": DECISION - NS,
            "next_funding_ns": MIDNIGHT + 14400 * NS, "valid": True, "source_line": 0}
    return Tape(books, [mark], [])


def test_signal_quantity_is_frozen_and_limit_rounds_inward():
    data = tape()
    intent = plan(data, EVENT, "fade_basis")
    assert intent["eligible"] and not intent["long"]
    assert intent["quantity"] == 800 and intent["limit"] == D("0.2366")
    data.books[3]["bid_quantity"] = D("1")
    assert plan(data, EVENT, "fade_basis") == intent


def test_funding_update_after_information_cutoff_cannot_authorize_trade():
    data = tape()
    data.marks[0]["receive_ns"] = DECISION - 250_000_000
    assert plan(data, EVENT, "fade_basis")["reason"] == "funding_cycle_not_proven_clear"


def test_upcoming_funding_inside_stress_exit_blocks_order():
    data = tape()
    data.marks[0]["next_funding_ns"] = DECISION + 20 * NS
    assert not plan(data, EVENT, "fade_basis")["eligible"]


def test_native_transaction_time_is_distinct_from_publication():
    raw = {"u": 1, "s": "ENAUSDT", "b": "0.2368", "a": "0.2369", "B": "10000", "A": "10000",
           "T": MIDNIGHT // 1_000_000 + 500, "E": MIDNIGHT // 1_000_000 + 900}
    message = f"{DAY}T00:00:01.0000000Z " + json.dumps({"stream": "enausdt@bookTicker", "data": raw})
    data, _ = parse([message], DAY)
    assert data.books[0]["transaction_ns"] == MIDNIGHT + 500_000_000
    assert data.books[0]["publication_ns"] == MIDNIGHT + 900_000_000
    assert data.books[0]["receive_ns"] == MIDNIGHT + NS


def test_entire_predecessor_tie_group_is_in_the_execution_envelope():
    data = Tape([book(17, size="1"), book(17, size="10000"), book(17.2)], [], [])
    envelope = compatible(data, MIDNIGHT + 17_050_000_000, 1_000_000, True)
    assert envelope["known"] and envelope["minimum_touch_quantity"] == 1


def test_unknown_entry_and_exit_never_become_zero_profit():
    data = tape()
    intent = plan(data, EVENT, "fade_basis")
    data.books[2]["bid_quantity"] = D(1)
    result = replay(data, EVENT, intent, BASE)
    assert result["status"] == "unknown_entry" and "lower" not in result
    data.books[2]["bid_quantity"] = D(10000)
    data.books[6]["ask_quantity"] = D(1)
    result = replay(data, EVENT, intent, BASE)
    assert result["status"] == "unknown_exit" and "lower" not in result


def test_regression_is_unknown_and_three_second_latency_respects_holding_limit():
    data = tape()
    intent = plan(data, EVENT, "fade_basis")
    data.physical_ordered = False
    result = replay(data, EVENT, intent, {**BASE, "delay_ms": 3000})
    assert result["status"] == "unknown_entry"
    assert result["inventory_schedule_upper_ns"] == 21_052_000_000


def test_cash_charges_entry_and_exit_notional_and_stress_multipliers():
    result = cash(800, False, D("0.2368"), D("0.2361"), {**BASE, "fee_multiple": 2})
    assert result["gross"] == D("0.56")
    assert result["fees"] == D("0.453984")
    assert result["adverse"] == D("0.037832")
    assert result["net"] == D("0.068184")
