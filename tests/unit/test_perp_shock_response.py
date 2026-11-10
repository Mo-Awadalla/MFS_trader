import json
from decimal import Decimal as D

import pytest

from research.perp_shock_response import episode, parse, plan
from research.spot_perp_response import Tape, cash, compatible, replay
from research.spot_perp_supply import midnight_ns

NS = 10**9
DAY = "2024-09-01"
START = midnight_ns(DAY) + 360 * 60 * NS
EVENT = {"date": DAY, "symbol": "BAKEUSDT", "decision_ns": START + 46 * NS, "direction": -1}
BASE = {"name": "base", "delay_ms": 1000, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 1}
TICK = D("0.0001")


def book(second, size="10000", bid="0.2500", ask="0.2501", line=0):
    stamp = START + int(D(str(second)) * NS)
    return {"receive_ns": stamp, "transaction_ns": stamp, "publication_ns": stamp,
            "source_line": line, "update_id": line + 1, "valid": True,
            "bid": D(bid), "ask": D(ask), "bid_quantity": D(size), "ask_quantity": D(size)}


def tape():
    books = [book(t, line=i) for i, t in enumerate((45.6, 46.2, 47.0, 47.1, 64.0, 64.2, 70.0, 70.2))]
    mark = {"receive_ns": START + 45 * NS, "publication_ns": START + 45 * NS,
            "next_funding_ns": START + 7200 * NS, "valid": True, "source_line": 0}
    return Tape(books, [mark], [])


def line(second="01.0000001", uid=1, match_ms=500, event_ms=900, **extra):
    raw = {"u": uid, "s": "BAKEUSDT", "b": "0.2500", "a": "0.2501", "B": "10000", "A": "10000",
           "T": START // 10**6 + match_ms, "E": START // 10**6 + event_ms, **extra}
    return f"{DAY}T06:00:{second}Z " + json.dumps({"stream": "bakeusdt@bookTicker", "data": raw})


@pytest.mark.parametrize("direction,rule,expected_long", [
    (-1, "follow_shock", False), (-1, "fade_shock", True),
    (1, "follow_shock", True), (1, "fade_shock", False)])
def test_direction_controls_do_not_depend_on_future_returns(direction, rule, expected_long):
    data = tape()
    intent = plan(data, {**EVENT, "direction": direction}, rule, TICK)
    assert intent["eligible"] and intent["long"] == expected_long and intent["quantity"] == 790
    data.books[-1]["bid"] = D("0.9")
    data.books[-1]["ask_quantity"] = D("1")
    assert plan(data, {**EVENT, "direction": direction}, rule, TICK) == intent
    assert intent["limit"] <= D("0.2501") * D("1.001") if expected_long else intent["limit"] >= D("0.2500") * D("0.999")


def test_signal_at_cutoff_is_not_available_and_old_native_clock_fails():
    data = tape()
    data.books[0]["receive_ns"] = EVENT["decision_ns"] - 250_000_000
    assert not plan(data, EVENT, "follow_shock", TICK)["eligible"]
    data = tape()
    data.books[0]["transaction_ns"] = START + 45 * NS
    assert not plan(data, EVENT, "follow_shock", TICK)["eligible"]


def test_funding_after_cutoff_or_inside_stressed_exit_does_not_authorize_order():
    data = tape()
    data.marks[0]["receive_ns"] = EVENT["decision_ns"] - 250_000_000
    assert plan(data, EVENT, "follow_shock", TICK)["reason"] == "funding_cycle_not_proven_clear"
    data = tape()
    data.marks[0]["next_funding_ns"] = EVENT["decision_ns"] + 25_200_000_000
    assert not plan(data, EVENT, "follow_shock", TICK)["eligible"]


def test_offset_two_minute_parser_preserves_all_three_clocks_exactly():
    data, counts = parse([line()], DAY, 360, "BAKEUSDT", TICK)
    assert counts["native_messages"] == 1
    assert data.books[0]["receive_ns"] == START + NS + 100
    assert data.books[0]["transaction_ns"] == START + 500_000_000
    assert data.books[0]["publication_ns"] == START + 900_000_000


def test_duplicate_does_not_refresh_signal_and_conflict_poison_is_unknown():
    data, counts = parse([line(), line(second="02.0000000"), line(second="03.0000000", b="0.2499")], DAY, 360, "BAKEUSDT", TICK)
    assert counts["exact_duplicate_books"] == 1 and len(data.books) == 2
    assert data.books[0]["receive_ns"] == START + NS + 100
    assert not data.physical_ordered and not data.books[-1]["valid"]


def test_grid_violation_and_transaction_regression_do_not_prove_execution():
    data, counts = parse([line(), line(second="02.0000000", uid=2, match_ms=400, b="0.24999")], DAY, 360, "BAKEUSDT", TICK)
    assert counts["transaction_clock_regressions"] == 1
    assert not data.books[-1]["valid"] and not data.physical_ordered


def test_all_predecessor_ties_and_disconnect_overlap_remain_uncertain():
    data = Tape([book(47, size="1"), book(47), book(47.1)], [], [])
    bounds = compatible(data, START + 47_050_000_000, 1_000_000, True)
    assert bounds["known"] and bounds["minimum_touch_quantity"] == 1
    data.disconnects = [(START + 47 * NS, START + 47_100_000_000)]
    assert not compatible(data, START + 47_050_000_000, 1_000_000, True)["known"]


def test_unknown_submitted_position_halts_later_event_and_full_net_is_null():
    data = tape()
    intent = plan(data, EVENT, "follow_shock", TICK)
    data.books[2]["bid_quantity"] = D(1)
    later = {**EVENT, "symbol": "ZROUSDT", "decision_ns": EVENT["decision_ns"] + 3600 * NS}
    key = (DAY, "BAKEUSDT", EVENT["decision_ns"])
    result = episode([EVENT, later], {key: data}, {key: {"follow_shock": intent}}, "follow_shock", BASE)
    assert not result["complete"] and result["net_lower"] is None
    assert result["rows"][0]["result"]["status"] == "unknown_entry"
    assert result["rows"][1]["result"]["status"] == "halted_after_unknown_inventory"


def test_known_round_trip_crosses_minute_boundary_and_costs_both_legs():
    data = tape()
    intent = plan(data, EVENT, "follow_shock", TICK)
    result = replay(data, EVENT, intent, BASE)
    assert result["status"] == "conditional_complete"
    assert result["exit_arrival_ns"] == START + 64_100_000_000
    expected = cash(790, False, D("0.2500"), D("0.2501"), BASE)
    assert result["lower"] == expected and expected["net"] < 0


def test_fixed_quantity_is_not_resized_to_future_exit_depth():
    data = tape()
    intent = plan(data, EVENT, "follow_shock", TICK)
    data.books[4]["ask_quantity"] = D(1)
    result = replay(data, EVENT, intent, BASE)
    assert result["status"] == "unknown_exit" and result["quantity"] == 790 and "lower" not in result


def test_max_latency_stress_still_has_sub_30_second_planned_inventory():
    data = tape()
    result = replay(data, EVENT, plan(data, EVENT, "follow_shock", TICK), {**BASE, "delay_ms": 3000, "clock_ms": 100})
    assert result["inventory_schedule_upper_ns"] == 21_250_000_000
