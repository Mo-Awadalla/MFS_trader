import struct
from collections import Counter

import pytest

from research.iex_native_prefix import decode_message, packets, segment


def block(kind, body):
    n = 12 + len(body)
    assert n % 4 == 0
    return struct.pack("<II", kind, n) + body + struct.pack("<I", n)


def capture(timestamp=1_673_445_000_000_000_123):
    shb = block(0x0A0D0D0A, struct.pack("<IHHq", 0x1A2B3C4D, 1, 0, -1))
    idb = block(1, struct.pack("<HHI", 1, 0, 65535) + b"\x09\x00\x01\x00\x09\x00\x00\x00\x00\x00\x00\x00")
    epb = block(6, struct.pack("<IIIII", 0, timestamp >> 32, timestamp & 0xFFFFFFFF, 4, 4) + b"abcd")
    return shb + idb + epb


def test_capture_nanoseconds_never_round_via_float():
    rows = list(packets(capture(), Counter()))
    assert rows == [(1_673_445_000_000_000_123, b"abcd")]


def test_partial_tail_is_explicit_and_not_a_complete_packet():
    stats = Counter()
    assert list(packets(capture()[:-2], stats, allow_partial=True)) == []
    assert stats["trailing_partial_bytes"] > 0
    with pytest.raises(ValueError, match="Partial final"):
        list(packets(capture()[:-2], Counter()))


def test_corrupt_block_trailer_rejected_even_for_prefix():
    raw = capture()[:-4] + b"\x00\x00\x00\x00"
    with pytest.raises(ValueError, match="trailing block"):
        list(packets(raw, Counter(), allow_partial=True))


def test_exact_quote_units_and_original_event_clock():
    raw = b"Q\x00" + struct.pack("<q", 1_673_445_000_000_000_123) + b"SPY     "
    raw += struct.pack("<IqqI", 133, 3_990_000, 3_990_100, 987)
    row = decode_message(raw)
    assert row["bid_size"] == 133 and row["ask_size"] == 987
    assert row["bid_price"] == 3_990_000 and row["event_ns"] == 1_673_445_000_000_000_123


def test_transport_message_count_and_byte_length_both_checked():
    message = b"SO" + struct.pack("<q", 123)
    body = struct.pack("<H", len(message)) + message
    raw = struct.pack("<BBHIIHHqqq", 1, 0, 0x8003, 1, 4, len(body), 1, 0, 1, 567) + body
    assert segment(raw)[-1] == [message]
    broken = bytearray(raw)
    struct.pack_into("<H", broken, 14, 2)
    with pytest.raises(ValueError, match="Missing message length"):
        segment(broken)
