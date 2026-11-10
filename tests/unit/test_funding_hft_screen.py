import pandas as pd
import pytest

from research_scout import screen_funding_hft_20260930 as screen


def inspect(monkeypatch, *, future_row=False, source_in_future=False, following_event=False):
    settle = pd.Timestamp("2024-01-01 08:00", tz="UTC").value // 1000
    decision = settle - 30_000_000
    row = {"exchange": "bybit", "symbol": "BTCUSDT", "local_timestamp": decision - 100_000,
           "timestamp": decision + 1 if source_in_future else decision - 120_000,
           "funding_timestamp": settle + 8 * 3600_000_000 if following_event else settle,
           "funding_rate": .0001, "mark_price": 40000.}
    rows = [row]
    if future_row:
        rows.append({**row, "local_timestamp": decision, "timestamp": decision - 1, "funding_rate": .1})
    monkeypatch.setattr(screen, "digest", lambda _: "test_hash")
    monkeypatch.setattr(screen.pd, "read_csv", lambda *args, **kwargs: pd.DataFrame(rows))
    records, _ = screen.causal_snapshots({"date": "2024-01-01", "exchange": "bybit", "symbol": "BTCUSDT", "path": "unused", "sha256": "test_hash"})
    return records[0]


def test_equal_decision_capture_cannot_supply_a_favorable_funding_rate(monkeypatch):
    result = inspect(monkeypatch, future_row=True)
    assert result["usable"] and result["funding_rate"] == pytest.approx(.0001)


def test_future_exchange_time_is_unusable_even_when_capture_is_earlier(monkeypatch):
    assert not inspect(monkeypatch, source_in_future=True)["usable"]


def test_following_cycle_rate_is_not_a_payment_in_the_target_cycle(monkeypatch):
    assert not inspect(monkeypatch, following_event=True)["usable"]
