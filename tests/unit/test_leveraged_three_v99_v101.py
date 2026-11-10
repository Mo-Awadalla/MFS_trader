import numpy as np
import pandas as pd

from research_scout.leveraged_three_v99_v101_20260907 import (
    filing_counts,
    london_times,
    normalized_shock,
    price_window,
    text_scores,
    valid_quote,
)


def test_text_distinguishes_relief_from_collapsing_demand():
    good = text_scores("Demand remains strong. Input costs are easing.")
    bad = text_scores("Demand is weakening. Input costs are easing.")
    assert good["demand"]["score"] == 1
    assert bad["demand"]["score"] == -1
    assert good["cost"]["score"] == bad["cost"]["score"] == -1


def test_text_abstains_on_negation_conflict_and_distant_cues():
    assert text_scores("Demand is not strong.")["demand"]["score"] is None
    assert text_scores("Demand is strong and weakening.")["demand"]["score"] is None
    assert text_scores("Demand " + "neutral " * 9 + "strong.")["demand"]["score"] is None
    assert text_scores("Revenue increased.")["demand"]["score"] is None


def test_text_rejects_customer_order_process_and_client_supply_chain_project():
    assert text_scores("Improved experience in how customers order their food.")["demand"]["score"] is None
    assert text_scores("Our client can improve its supply chain processes.")["cost"]["score"] is None
    assert text_scores("Supply chain costs increased.")["cost"]["score"] == 1
    assert text_scores("Customer traffic increased.")["demand"]["score"] == 1


def test_london_clock_follows_mismatched_daylight_saving():
    assert london_times("2021-03-19")["entry"].tz_convert("America/New_York").strftime("%H:%M") == "12:41"
    assert london_times("2021-04-01")["entry"].tz_convert("America/New_York").strftime("%H:%M") == "11:41"
    assert london_times("2021-11-01")["entry"].tz_convert("America/New_York").strftime("%H:%M") == "12:41"


def test_lagged_normalization_excludes_current_and_propagates_gap():
    history = [{"log_return": (-1)**i * .001, "volume": 100} for i in range(20)]
    current = {"log_return": .10, "volume": 200}
    result = normalized_shock(current, history)
    assert result["price_shock"]
    assert result["sigma"] < .002
    assert normalized_shock(current, [None] + history[1:])["status"] == "missing"
    assert normalized_shock(current, history[:19])["status"] == "warmup"


def test_filing_count_deduplicates_issuer_and_preserves_acceptance_cutoff():
    us = pd.DataFrame({"close": pd.to_datetime(["2021-01-04 21:00Z", "2021-01-05 21:00Z"])}, index=["2021-01-04", "2021-01-05"])
    rows = [
        ["a", "1", "10-Q", "", "2021-01-04 22:00Z"],
        ["b", "1", "8-K", "2.02,9.01", "2021-01-05 15:00Z"],
        ["c", "2", "8-K", "12.02", "2021-01-05 15:00Z"],
        ["d", "3", "10-K", "", "2021-01-05 15:25:01Z"],
        ["e", "4", "10-K/A", "", "2021-01-05 15:00Z"],
        ["f", "5", "8-K", "2.02", "2021-01-05 15:25Z"],
    ]
    f = pd.DataFrame(rows, columns=["accession_number", "cik", "form", "items", "acceptance_datetime"])
    f.acceptance_datetime = pd.to_datetime(f.acceptance_datetime, format="mixed")
    assert filing_counts(f, us)["2021-01-05"]["count"] == 2


def test_price_window_rejects_missing_bar_and_invalid_extrema():
    idx = pd.date_range("2021-01-04 14:30Z", periods=20, freq="1min")
    f = pd.DataFrame({"open": 100., "close": 101., "high": 102., "low": 99., "volume": 100.}, index=idx)
    assert price_window(f, idx[0], idx[-1] + pd.Timedelta(minutes=1)) is not None
    assert price_window(f.iloc[1:], idx[0], idx[-1] + pd.Timedelta(minutes=1)) is None
    f.iloc[0, f.columns.get_loc("high")] = 100.
    assert price_window(f, idx[0], idx[-1] + pd.Timedelta(minutes=1)) is None


def test_quote_validation_checks_size_crossing_and_nan():
    row = pd.Series({"bid_px_00": 10., "ask_px_00": 10.01, "bid_sz_00": 100, "ask_sz_00": 100})
    assert valid_quote(row)
    for key, value in [("ask_sz_00", 0), ("bid_px_00", 11.), ("ask_px_00", np.nan)]:
        bad = row.copy()
        bad[key] = value
        assert not valid_quote(bad)
