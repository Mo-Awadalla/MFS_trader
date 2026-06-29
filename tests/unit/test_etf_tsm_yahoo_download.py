"""Tests for Yahoo adjusted ETF TSM daily-bar parser."""

from __future__ import annotations

import pytest

from scripts.download_etf_tsm_yahoo_daily import _parse_yahoo_chart_result


def test_parse_yahoo_chart_result_adjusts_ohlc_to_adj_close():
    result = {
        "timestamp": [1_609_459_200, 1_609_545_600],
        "indicators": {
            "quote": [
                {
                    "open": [100.0, 110.0],
                    "high": [102.0, 112.0],
                    "low": [99.0, 109.0],
                    "close": [101.0, 111.0],
                    "volume": [1000, 2000],
                }
            ],
            "adjclose": [{"adjclose": [50.5, 111.0]}],
        },
    }

    df = _parse_yahoo_chart_result(result, "SPY")

    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 2
    assert df.index.tz is not None
    assert df.iloc[0]["open"] == pytest.approx(50.0)
    assert df.iloc[0]["high"] == pytest.approx(51.0)
    assert df.iloc[0]["low"] == pytest.approx(49.5)
    assert df.iloc[0]["close"] == pytest.approx(50.5)
    assert df.iloc[1]["open"] == pytest.approx(110.0)
    assert df.iloc[1]["close"] == pytest.approx(111.0)
