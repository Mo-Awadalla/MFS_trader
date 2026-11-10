from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from research.iex_stock_hft_scout import find_signals, simulate_crossing


def test_offer_shock_uses_prior_quote_and_execution_uses_asof_quotes():
    spec = json.loads(Path("research_scout/sip_stock_hft_v1.json").read_text())
    stamps = [
        "2025-01-08 11:00:10.400",  # previous offer
        "2025-01-08 11:00:10.500",  # signal
        "2025-01-08 11:00:11.400",  # known at one-second arrival
        "2025-01-08 11:00:11.600",  # future quote cannot set entry
        "2025-01-08 11:00:21.400",  # known at ten-second exit
        "2025-01-08 11:00:21.600",  # future quote cannot set exit
    ]
    quotes = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(stamps).tz_localize("America/New_York").tz_convert("UTC"),
            "ask_price": [100.02, 100.02, 100.02, 100.50, 100.06, 100.01],
            "ask_size": [200, 50, 50, 50, 50, 50],
            "bid_price": [100.00, 100.00, 100.00, 100.00, 100.04, 99.99],
            "bid_size": [200, 200, 200, 200, 200, 200],
            "conditions": ['["R"]'] * 6,
        }
    )
    signals = find_signals(quotes, spec)
    assert len(signals) == 1
    result = simulate_crossing(quotes, signals, spec)
    assert result.iloc[0]["execution_status"] == "crossing_proxy"
    assert result.iloc[0]["entry_ask"] == 100.02
    assert result.iloc[0]["exit_bid"] == 100.04
    assert result.iloc[0]["net_bps"] < 0  # spread crossing, commissions and friction


def test_stale_quote_prevents_executable_proxy():
    spec = json.loads(Path("research_scout/sip_stock_hft_v1.json").read_text())
    stamps = pd.to_datetime(["2025-01-08 11:00:10.400", "2025-01-08 11:00:10.500"])
    quotes = pd.DataFrame(
        {
            "timestamp": stamps.tz_localize("America/New_York").tz_convert("UTC"),
            "ask_price": [100.02, 100.02], "ask_size": [200, 50],
            "bid_price": [100.00, 100.00], "bid_size": [200, 200],
            "conditions": ['["R"]', '["R"]'],
        }
    )
    result = simulate_crossing(quotes, find_signals(quotes, spec), spec)
    assert result.iloc[0]["execution_status"] == "missing_or_stale_quote"
    assert pd.isna(result.iloc[0]["net_bps"])
