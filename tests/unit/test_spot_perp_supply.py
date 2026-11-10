import json
from collections import Counter
from decimal import Decimal

import pytest

from research.spot_perp_supply import (
    capture_ns,
    evaluate_grid,
    gap_budget,
    midnight_ns,
    sample_native,
    screen_pair,
    update_book,
    valid_book,
)

DAY = "2024-01-01"
START = midnight_ns(DAY) + 9 * 3600 * 1_000_000_000


def payload(uid=1, bid="100", ask="100.01"):
    return {"s": "BTCUSDT", "u": uid, "b": bid, "a": ask, "B": "100", "A": "100"}


def line(second, microseconds, raw):
    return (f"{DAY}T09:00:{second:02d}.{microseconds:06d}0Z "
            + json.dumps({"stream": "btcusdt@bookTicker", "data": raw}) + "\n")


def test_capture_preserves_submicrosecond_clock():
    assert capture_ns(DAY + "T09:00:00.0005615Z", midnight_ns(DAY)) == START + 561_500


def test_strict_feed_cutoff_excludes_equal_timestamp_and_complete_tie():
    data = sample_native([line(0, 500000, payload()), line(0, 750000, payload(2, "101", "101.01")),
                          line(0, 750000, payload(3, "102", "102.01"))], DAY, "spot")
    assert data["samples"][1]["BTCUSDT"]["bid"] == "100"
    assert data["samples"][2]["BTCUSDT"]["bid"] == "102"


def test_duplicate_does_not_refresh_quote_and_conflict_stays_poisoned():
    states, ids, counts = {}, {}, Counter()
    update_book(payload(), START, 0, "spot", states, ids, counts)
    update_book(payload(), START + 900_000_000, 1, "spot", states, ids, counts)
    assert states["BTCUSDT"]["receive_ns"] == START
    update_book(payload(bid="99"), START + 910_000_000, 2, "spot", states, ids, counts)
    update_book(payload(), START + 920_000_000, 3, "spot", states, ids, counts)
    assert not states["BTCUSDT"]["sequence_ok"]
    update_book(payload(2), START + 930_000_000, 4, "spot", states, ids, counts)
    assert states["BTCUSDT"]["sequence_ok"]


def test_disconnect_erases_pre_disconnect_state():
    data = sample_native([line(0, 500000, payload()), "\n", line(1, 500000, payload(2))], DAY, "spot")
    assert "BTCUSDT" not in data["samples"][1]
    assert data["samples"][2]["BTCUSDT"]["update_id"] == 2


def test_reject_backwards_capture_instead_of_sorting():
    with pytest.raises(ValueError, match="Capture order"):
        sample_native([line(1, 0, payload()), line(0, 0, payload(2))], DAY, "spot")


def test_spot_clock_is_not_invented_and_perpetual_time_is_checked():
    states, ids, counts = {}, {}, Counter()
    update_book(payload(), START, 0, "spot", states, ids, counts)
    assert valid_book(states["BTCUSDT"], START + 500_000_000) is None
    raw = {**payload(2), "T": START // 1_000_000 + 10, "E": START // 1_000_000}
    update_book(raw, START, 1, "perpetual", states, ids, counts)
    assert valid_book(states["BTCUSDT"], START + 500_000_000) == "perpetual_clock_gate"


@pytest.mark.parametrize("bid,ask,expected", [("101", "101.02", -1), ("99", "99.02", 1)])
def test_cost_budget_charges_both_executions_and_full_spread(bid, ask, expected):
    spot = {"bid": "99.99", "ask": "100.01"}
    perpetual = {"bid": bid, "ask": ask}
    result = gap_budget(spot, perpetual, Decimal(1))
    assert result["direction"] == expected
    entry = Decimal(bid if expected < 0 else ask)
    exit_price = Decimal("100.01" if expected < 0 else "99.99")
    exact = (expected * (exit_price - entry) - Decimal("0.0007") * (entry + exit_price)) / entry * 10000
    assert Decimal(result["projected_budget_bps"]) == exact


def paired_fixture():
    result = []
    for venue in ("spot", "perpetual"):
        data = {"grids": [START + i * 1_000_000_000 for i in range(60)],
                "symbols": {"BTCUSDT"}, "samples": []}
        for i, decision in enumerate(data["grids"]):
            stamp = decision - 500_000_000
            state = {"receive_ns": stamp, "source_line": i, "update_id": i,
                     "bid": "99.99", "ask": "100.01", "bid_quantity": "100",
                     "ask_quantity": "100", "sequence_ok": True, "venue": venue}
            if venue == "perpetual":
                state.update(transaction_ns=stamp, publication_ns=stamp)
                if i in (10, 11, 12):
                    state.update(bid="100.99", ask="101.01")
            data["samples"].append({"BTCUSDT": state})
        result.append(data)
    return result


def test_anchor_excludes_current_and_future_observations():
    spot, perpetual = paired_fixture()
    row = evaluate_grid(spot, perpetual, "BTCUSDT", 10)
    assert Decimal(row["reference_ratio"]) == 1
    assert Decimal(row["gap_bps"]) == 100
    assert row["raw_eligible"]
    perpetual["samples"][59]["BTCUSDT"]["bid"] = "100000"
    assert row == evaluate_grid(spot, perpetual, "BTCUSDT", 10)


def test_confirmation_requires_two_consecutive_grids_and_selects_once():
    spot, perpetual = paired_fixture()
    rows = screen_pair(spot, perpetual, DAY)
    assert [r["second"] for r in rows if r["selected"]] == [11]
    assert rows[2]["reason"] == "one_event_per_symbol_date"
