from __future__ import annotations

import pandas as pd
import pytest

from data.alpaca_l1 import normalize_quotes
from research.alpaca_iex_l1_features import attach_iex_execution_returns
from research.alpaca_iex_orderflow_scout import evaluate_scout, load_spec


def test_execution_diagnostic_waits_one_second_and_crosses_spread():
    features = pd.DataFrame(
        {"composite_score": [0.5]},
        index=pd.DatetimeIndex(["2026-07-08T13:35:00Z"], name="signal_timestamp"),
    )
    quotes = normalize_quotes(
        [
            {"t": "2026-07-08T13:35:00.5Z", "ax": "V", "ap": 100.1, "as": 10, "bx": "V", "bp": 99.9, "bs": 10, "c": ["R"], "z": "C"},
            {"t": "2026-07-08T13:35:01Z", "ax": "V", "ap": 101.0, "as": 10, "bx": "V", "bp": 100.8, "bs": 10, "c": ["R"], "z": "C"},
            {"t": "2026-07-08T13:40:01Z", "ax": "V", "ap": 102.0, "as": 10, "bx": "V", "bp": 101.8, "bs": 10, "c": ["R"], "z": "C"},
        ],
        "AAPL",
    )

    result = attach_iex_execution_returns(features, quotes)

    expected = 101.8 / 101.0 - 1.0
    assert result.iloc[0]["iex_crossing_return"] == pytest.approx(expected)
    assert result.iloc[0]["iex_crossing_net_return"] == pytest.approx(expected - 0.0002)
    assert result.iloc[0]["entry_quote_timestamp"] == pd.Timestamp("2026-07-08T13:35:01Z")


def test_frozen_evaluator_passes_only_when_all_gates_clear():
    spec = load_spec()
    rows = []
    symbols = ["SPY", "QQQ", "IWM"]
    for session_index in range(12):
        session_date = f"2023-01-{session_index + 1:02d}"
        for symbol in symbols:
            for interval in range(4):
                rows.append(
                    {
                        "symbol": symbol,
                        "session_date": session_date,
                        "signal_timestamp": pd.Timestamp("2023-01-03T14:35:00Z")
                        + pd.Timedelta(minutes=5 * interval),
                        "signed_trade_imbalance": 0.6,
                        "terminal_quote_size_imbalance": 0.4,
                        "composite_score": 0.5,
                        "selected": True,
                        "next_midpoint_return": 0.001,
                        "iex_crossing_return": 0.0006,
                        "iex_crossing_net_return": 0.0004,
                        "excluded_trade_condition_count": 0,
                        "excluded_quote_condition_count": 0,
                        "stale_or_unmatched_trade_count": 0,
                        "locked_quote_count": 0,
                        "crossed_quote_count": 0,
                        "one_sided_quote_count": 0,
                        "invalid_quote_count": 0,
                        "execution_quotes_missing": False,
                    }
                )
    report = evaluate_scout(pd.DataFrame(rows), spec)

    assert report["passed"] is True
    assert report["selected_rows"] == 144
    assert all(report["gates"].values())
