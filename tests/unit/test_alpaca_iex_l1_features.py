from __future__ import annotations

import pandas as pd
import pytest

from data.alpaca_l1 import normalize_quotes, normalize_trades
from research.alpaca_iex_l1_features import build_iex_5min_features


def test_features_use_only_quote_available_at_trade_time_and_next_interval_target():
    quotes = normalize_quotes(
        [
            {"t": "2026-07-08T13:30:00Z", "ax": "V", "ap": 100.1, "as": 10, "bx": "V", "bp": 99.9, "bs": 20, "c": ["R"], "z": "C"},
            {"t": "2026-07-08T13:30:01Z", "ax": "V", "ap": 102.1, "as": 10, "bx": "V", "bp": 101.9, "bs": 20, "c": ["R"], "z": "C"},
            {"t": "2026-07-08T13:30:02Z", "ax": "V", "ap": 102.1, "as": 10, "bx": "V", "bp": 101.9, "bs": 20, "c": ["R"], "z": "C"},
            {"t": "2026-07-08T13:35:00Z", "ax": "V", "ap": 102.1, "as": 10, "bx": "V", "bp": 101.9, "bs": 20, "c": ["R"], "z": "C"},
            {"t": "2026-07-08T13:39:59Z", "ax": "V", "ap": 103.1, "as": 10, "bx": "V", "bp": 102.9, "bs": 20, "c": ["R"], "z": "C"},
        ],
        "AAPL",
    )
    trades = normalize_trades(
        [
            {"t": "2026-07-08T13:30:01Z", "i": 1, "x": "V", "p": 101.0, "s": 10, "c": ["@"], "z": "C"},
            {"t": "2026-07-08T13:35:01Z", "i": 2, "x": "V", "p": 102.2, "s": 20, "c": ["@"], "z": "C"},
        ],
        "AAPL",
    )

    features = build_iex_5min_features(trades, quotes)

    first = features.loc["2026-07-08T13:35:00Z"]
    assert first["signed_volume"] == 10
    assert first["signed_trade_imbalance"] == 1.0
    assert first["quote_match_fraction"] == 1.0
    assert first["maximum_trade_quote_age_ms"] == 1_000.0
    assert first["normal_quote_count"] == 3
    assert first["terminal_midpoint"] == 102.0
    assert first["terminal_quote_age_ms"] == 298_000.0
    assert first["next_midpoint_return"] == pytest.approx(103.0 / 102.0 - 1.0)
    assert pd.isna(features.iloc[-1]["next_midpoint_return"])


def test_feature_builder_refuses_naive_timestamps():
    trades = normalize_trades(
        [{"t": "2026-07-08T13:30:01Z", "i": 1, "x": "V", "p": 101, "s": 10, "c": ["@"], "z": "C"}],
        "AAPL",
    )
    quotes = normalize_quotes(
        [{"t": "2026-07-08T13:30:00Z", "ax": "V", "ap": 101.1, "as": 10, "bx": "V", "bp": 100.9, "bs": 10, "c": ["R"], "z": "C"}],
        "AAPL",
    )
    trades["timestamp"] = trades["timestamp"].dt.tz_localize(None)

    with pytest.raises(ValueError, match="timezone-aware"):
        build_iex_5min_features(trades, quotes)
