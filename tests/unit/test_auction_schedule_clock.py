import pandas as pd
import pytest

from research_scout.correct_close_auction_clock_20260930 import scheduled_time


@pytest.mark.parametrize("day,utc_hour", [("2024-01-02", 21), ("2024-07-01", 20)])
def test_legacy_wall_clock_repair_obeys_historical_dst(day, utc_hour):
    legacy = pd.Timestamp(day + " 16:00", tz="UTC").value
    close = pd.Timestamp(day + " 16:00", tz="America/New_York").value
    repaired, mode = scheduled_time(legacy, day, "C", close)
    assert pd.Timestamp(repaired, tz="UTC").hour == utc_hour
    assert mode == "legacy_new_york_wall_time_encoded_as_utc"
    assert scheduled_time(close, day, "C", close) == (close, "already_utc")


def test_unexpected_auction_time_cannot_be_shifted_into_a_valid_close():
    day = "2024-07-01"
    raw = pd.Timestamp(day + " 16:01", tz="UTC").value
    close = pd.Timestamp(day + " 16:00", tz="America/New_York").value
    assert scheduled_time(raw, day, "C", close) == (raw, "unrecognized_no_repair")
    assert scheduled_time(raw, day, "H", close) == (raw, "unsupported_auction_type")
