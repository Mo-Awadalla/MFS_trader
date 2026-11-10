import struct

import pytest

from research.iex_deep_supply import Book, deep_message, deep_segment


def row(side, price, size, t, flags=1):
    return {"type": side, "flags": flags, "price": price, "size": size, "event_ns": t,
            "symbol": "TEST", "capture_ns": t + 1, "send_ns": t + 1, "sequence": t}


def test_incomplete_atomic_event_preserves_prior_committed_quote():
    b = Book()
    b.update(row("8", 1_000_000, 100, 1))
    b.update(row("5", 1_001_000, 100, 2))
    prior = b.quote.copy()
    assert b.update(row("5", 1_001_000, 0, 3, 0)) is None
    assert b.quote == prior and b.pending_event_ns == 3
    assert b.protected() is None
    b.update(row("5", 1_002_000, 100, 3))
    assert b.quote["ask_price"] == 1_002_000 and b.pending_event_ns is None


def test_better_odd_lots_are_in_deep_and_aggregate_at_lower_protected_bid():
    b = Book()
    b.update(row("8", 100200, 90, 1))
    b.update(row("8", 100100, 30, 2))
    assert (b.quote["bid_price"], b.quote["bid_size"]) == (100200, 90)
    assert b.protected()["bid"] == {"price": 100100, "size": 120}


def test_last_side_deleted_is_invalid_empty_book_not_stale_quote():
    b = Book()
    b.update(row("8", 100000, 100, 1))
    b.update(row("8", 100000, 0, 2))
    assert b.quote["bid_price"] == b.quote["bid_size"] == 0


def test_native_clock_order_is_only_guaranteed_within_message_type():
    b = Book()
    b.update(row("8", 100000, 100, 20))
    b.update(row("5", 100100, 100, 10))
    assert b.quote["ask_price"] == 100100
    with pytest.raises(ValueError, match="clock reversal"):
        b.update(row("8", 100000, 100, 19))


def test_missing_atomic_completion_or_unknown_deletion_fails():
    b = Book()
    b.update(row("8", 100000, 100, 1, 0))
    with pytest.raises(ValueError, match="Incomplete atomic"):
        b.update(row("8", 100100, 100, 2))
    with pytest.raises(ValueError, match="Deletion without"):
        Book().update(row("8", 100000, 0, 1))


def test_native_decode_preserves_large_integer_timestamp_and_quantity():
    timestamp = 1673447459705599932
    message = struct.pack("<BBq8sIq", ord("8"), 1, timestamp, b"TEST    ", 123, 100200)
    r = deep_message(message)
    assert r["event_ns"] == timestamp and r["size"] == 123 and r["price"] == 100200
    with pytest.raises(ValueError, match="Invalid DEEP"):
        deep_message(bytes([ord("8"), 2]) + message[2:])


def test_top_of_book_protocol_is_not_silently_accepted_as_depth():
    header = struct.pack("<BBHIIHHqqq", 1, 0, 0x8003, 1, 42, 0, 0, 0, 1, 100)
    with pytest.raises(ValueError, match="Wrong DEEP"):
        deep_segment(header)
    header = struct.pack("<BBHIIHHqqq", 1, 0, 0x8004, 1, 42, 0, 0, 0, 1, 100)
    assert deep_segment(header)[0] == (0x8004, 1, 42)
