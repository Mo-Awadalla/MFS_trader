import pandas as pd
import pytest

from research.alpaca_quote_units import sip_sizes_in_shares
from research_scout.audit_sip_quote_units_20260930 import strict_execution_status


def source():
    return pd.DataFrame({"timestamp": pd.to_datetime(["2025-10-31T15:00:00Z", "2025-11-03T15:00:00Z"]),
                         "ask_size": [2, 200], "bid_size": [1, 100]})


def test_historical_transition_preserves_economically_identical_sizes():
    raw = source()
    result = sip_sizes_in_shares(raw, legacy_round_lot_shares=100, feed="sip")
    assert result.ask_size.tolist() == [200, 200]
    assert result.bid_size.tolist() == [100, 100]
    assert result.source_ask_size.tolist() == [2, 200]
    assert raw.ask_size.tolist() == [2, 200]


def test_wrong_feed_and_double_conversion_fail():
    with pytest.raises(ValueError, match="only for Alpaca SIP"):
        sip_sizes_in_shares(source(), legacy_round_lot_shares=100, feed="databento")
    result = sip_sizes_in_shares(source(), legacy_round_lot_shares=100, feed="sip")
    with pytest.raises(ValueError, match="already been normalized"):
        sip_sizes_in_shares(result, legacy_round_lot_shares=100, feed="sip")


def test_historical_lot_size_must_be_explicit_and_valid():
    with pytest.raises(ValueError, match="explicit positive"):
        sip_sizes_in_shares(source(), legacy_round_lot_shares=0, feed="sip")


def test_latest_locked_quote_cannot_be_replaced_by_older_valid_quote():
    times = pd.to_datetime(["2025-01-08T16:00:00.000Z", "2025-01-08T16:00:00.100Z"])
    quotes = pd.DataFrame({"timestamp": times, "ask_price": [100.01, 100.0],
                           "bid_price": [100.0, 100.0], "ask_size": [100, 100],
                           "bid_size": [100, 100], "conditions": ['["R"]', '["R"]']})
    entries = pd.DataFrame({"entry_time": [times[1] + pd.Timedelta(milliseconds=1)],
                            "exit_time": [times[1] + pd.Timedelta(milliseconds=2)]})
    assert strict_execution_status(quotes, entries, 100) == ["entry_invalid_latest_quote"]
