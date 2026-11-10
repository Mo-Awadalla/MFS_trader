import pandas as pd
import pytest

from research_scout.benchmark_close_auction_20260930 import SCENARIOS, benchmark, targets


def example():
    signal = {"date": "2024-07-01", "quantity": 20, "limit": 500.}
    auction = {"valid": True, "price": 499., "quantity": 100000,
               "event_ns": 20000000000, "receive_ns": 20100000000}
    quote = {"target_ns": 37250000000, "receive_ns": 37300000000, "event_ns": 37299999000,
             "bid": 500., "ask": 500.01, "bid_qty": 100, "ask_qty": 100, "flags": 128}
    return signal, auction, quote


def test_conditional_cash_deducts_all_costs_without_claiming_execution():
    signal, auction, quote = example()
    r = benchmark(signal, auction, quote, 15, SCENARIOS["base"])
    assert r["conditional_pnl"] == pytest.approx(20 - 2 - .304 - 1.998)
    assert r["conditional_complete"] and not r["strategy_execution_verified"]


def test_outside_price_limit_has_no_reference_fill():
    signal, auction, quote = example()
    auction["price"] = 500.01
    r = benchmark(signal, auction, None, 15, SCENARIOS["base"])
    assert r["status"] == "outside_limit_no_reference_fill" and r["conditional_pnl"] == 0


def test_insufficient_exit_depth_keeps_inventory_and_never_resizes():
    signal, auction, quote = example()
    quote["bid_qty"] = 19
    r = benchmark(signal, auction, quote, 15, SCENARIOS["base"])
    assert not r["conditional_complete"] and r["possible_open_quantity"] == 20
    assert "conditional_pnl" not in r


def test_exit_targets_include_return_ack_hold_processing_and_outbound():
    signal, auction, quote = example()
    frame = targets(pd.DataFrame([signal]), pd.DataFrame([{**auction, "date": signal["date"]}]))
    expected = {(1, 15): 37250000000, (1, 30): 52250000000, (3, 15): 41250000000, (3, 30): 56250000000}
    assert {(r.delay_s, r.hold_s): r.target_ns for r in frame.itertuples()} == expected
