from __future__ import annotations

from data.alpaca_l1 import normalize_trades
from storage.microstructure_io import microstructure_path, read_events, write_events


def test_microstructure_round_trip_preserves_same_timestamp_events(tmp_path):
    trades = normalize_trades(
        [
            {"t": "2026-07-08T13:30:00.123456789Z", "i": 1, "x": "V", "p": 100, "s": 10, "c": [], "z": "C"},
            {"t": "2026-07-08T13:30:00.123456789Z", "i": 2, "x": "V", "p": 101, "s": 20, "c": [], "z": "C"},
        ],
        "AAPL",
    )
    path = microstructure_path(
        tmp_path,
        provider_feed="alpaca_iex",
        symbol="AAPL",
        session_date="2026-07-08",
        event_type="trades",
    )

    metadata = write_events(trades, path)
    restored = read_events(path)

    assert metadata["rows"] == 2
    assert len(restored) == 2
    assert restored["timestamp"].nunique() == 1
    assert restored["trade_id"].tolist() == ["1", "2"]
    assert restored["exchange"].tolist() == ["V", "V"]
    assert restored["tape"].tolist() == ["C", "C"]
    assert restored.iloc[0]["timestamp"].nanosecond == 789
