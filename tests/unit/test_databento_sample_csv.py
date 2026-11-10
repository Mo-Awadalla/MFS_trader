"""Public CSV ingestion cannot round clocks, prices, identifiers or missing prices."""

import pyarrow as pa
import pytest

from research.databento_sample_csv import native_batch, reader


def parse(text):
    batches = reader(pa.BufferReader(text.encode()))
    return native_batch(next(batches)).to_pydict()


def test_adjacent_nanoseconds_remain_distinct():
    data = parse("ts_recv,ts_event\n1970-01-01T00:00:01.000000001Z,1970-01-01T00:00:01.000000000Z\n1970-01-01T00:00:01.000000002Z,1970-01-01T00:00:01.000000001Z\n")
    assert data == {"ts_recv": [1000000001, 1000000002], "ts_event": [1000000000, 1000000001]}


def test_fixed_prices_and_missing_quote_are_exact():
    data = parse("price,bid_px_00,ask_px_00\n186.123456789,,186.123456790\n")
    assert data == {"price": [186123456789], "bid_px_00": [None], "ask_px_00": [186123456790]}


def test_native_unsigned_identifier_is_not_a_float():
    data = parse("order_id,sequence\n18446744073709551615,4294967295\n")
    assert data == {"order_id": [(1 << 64) - 1], "sequence": [(1 << 32) - 1]}


def test_excess_price_precision_is_rejected():
    with pytest.raises(pa.ArrowInvalid):
        parse("price\n1.0000000001\n")
