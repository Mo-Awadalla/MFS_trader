import json

import pytest

from research.spot_perp_clock_supply import sample_native_at
from research.spot_perp_supply import midnight_ns, valid_book


@pytest.mark.parametrize("minute", [0, 1080])
def test_midnight_and_evening_preserve_physical_and_capture_clocks(minute):
    day = "2024-03-01"
    stamp = midnight_ns(day) + minute * 60 * 1_000_000_000 + 500_000_000
    raw = {"s": "BTCUSDT", "u": 1, "b": "100", "B": "100", "a": "100.01", "A": "100",
           "T": stamp // 1_000_000, "E": stamp // 1_000_000}
    line = f"{day}T{minute // 60:02d}:00:00.5000000Z " + json.dumps({"stream": "btcusdt@bookTicker", "data": raw})
    samples = sample_native_at([line], day, "perpetual", minute)
    book = samples["samples"][1]["BTCUSDT"]
    assert book["receive_ns"] == book["transaction_ns"] == stamp
    assert valid_book(book, samples["grids"][1]) is None


def test_reader_rejects_wrong_clock_window_instead_of_retiming_data():
    line = '2024-03-01T09:00:00.5000000Z {"stream":"other"}'
    with pytest.raises(ValueError, match="boundary"):
        sample_native_at([line], "2024-03-01", "spot", 0)
