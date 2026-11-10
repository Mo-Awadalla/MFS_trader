import pytest

from research.iex_deep_probe_source import quote_tape


def level(side, event, seq, price, qty, flags=1):
    return {"type": side, "flags": flags, "event_ns": event, "sequence": seq,
            "price": price, "size": qty, "symbol": "TEST", "capture_ns": seq + 100,
            "send_ns": seq + 90}


def test_venue_time_reorders_cross_side_publication_without_future_ask():
    rows = [level("8", 20, 1, 100000, 100), level("5", 10, 2, 100200, 50)]
    q = quote_tape(rows)
    assert [r["event_ns"] for r in q] == [10, 20]
    assert q[0]["bid_price"] == 0 and q[1]["bid_price"] == 100000
    assert q[1]["ask_levels"] == [[100200, 50]]


def test_atomic_transition_does_not_publish_nonexistent_intermediate_quote():
    rows = [level("8", 1, 1, 100000, 100), level("5", 2, 2, 100200, 50),
            level("5", 3, 3, 100200, 0, 0), level("5", 3, 4, 100300, 80)]
    q = quote_tape(rows)
    assert len(q) == 3 and q[-1]["ask_price"] == 100300
    assert q[-1]["native_final_update"]["sequence"] == 4


def test_incomplete_final_atomic_update_remains_unknown():
    with pytest.raises(ValueError, match="within an atomic"):
        quote_tape([level("8", 1, 1, 100000, 100, 0)])


def test_equal_timestamp_states_collapse_and_original_trades_stay_exact():
    trade = {"type": "T", "event_ns": 1673447459705599932, "size": 7, "price": 100100}
    rows = [level("8", 1, 1, 100000, 100), level("5", 1, 2, 100200, 50), trade]
    q = quote_tape(rows)
    assert q[0] == trade and len(q) == 2
    assert q[1]["bid_price"] == 100000 and q[1]["ask_price"] == 100200
