import numpy as np
import pytest

from research.crypto_passive_replay import (
    DAY_MS,
    STEP_MS,
    PassiveRule,
    first_trade_through,
    quote_at,
    simulate_day,
)


def book():
    n = DAY_MS // STEP_MS
    return {"bid": np.full(n, 30000.0), "ask": np.full(n, 30000.1),
            "bid_qty": np.full(n, 100.0), "ask_qty": np.full(n, 10.0),
            "event_ms": np.arange(n) * STEP_MS + STEP_MS - 1}


def test_trade_through_requires_strict_price_correct_side_volume_and_live_order():
    trades = {"time": np.array([100, 101, 102, 103, 104, 105]),
              "price": np.array([99, 100, 99, 99, 99, 99]),
              "quantity": np.array([10, 10, 10, .1, 10, 10]),
              "buyer_maker": np.array([True, True, False, True, True, True])}
    assert first_trade_through(trades, 100, 105, 1, 100, 1, 2) == 4
    assert first_trade_through(trades, 100, 104, 1, 100, 1, 2) == -1


def test_quote_cache_cannot_use_later_bin():
    b = book()
    b["bid"][1:] = 90000
    assert quote_at(b, 250)[0] == 30000
    with pytest.raises(ValueError, match="aligned"):
        quote_at(b, 251)


def test_passive_pair_pays_both_maker_fees_and_waits_for_acknowledgement():
    trades = {"time": np.array([120501, 120600, 121501]),
              "price": np.array([29975.9, 30000.2, 30000.2]),
              "quantity": np.array([1.0, 1.0, 1.0]),
              "buyer_maker": np.array([True, False, False])}
    result = simulate_day(book(), trades, PassiveRule("imbalance", 8), "synthetic")
    assert result["complete"]
    assert result["counts"]["maker_exits"] == 1
    t = result["trades"][0]
    assert t["exit_ms"] == 121501  # Earlier print precedes exit-order arrival.
    fees = t["quantity"] * (t["entry"] + t["exit"]) * .0002
    assert t["fees"] == pytest.approx(fees)
    assert t["pnl"] == pytest.approx(t["quantity"] * (t["exit"] - t["entry"]) - fees)


def test_timeout_exits_pay_taker_costs_instead_of_discarding_inventory():
    trades = {"time": np.array([120501]), "price": np.array([29975.9]),
              "quantity": np.array([1.0]), "buyer_maker": np.array([True])}
    result = simulate_day(book(), trades, PassiveRule("imbalance", 8), "synthetic")
    t = result["trades"][0]
    assert t["exit_kind"] == "taker_timeout"
    assert t["exit"] == pytest.approx(30000 * .9999)
    assert t["fees"] == pytest.approx(t["quantity"] * (t["entry"] * .0002 + t["exit"] * .0005))


def test_missing_quote_after_entry_blocks_the_path():
    b = book()
    b["bid"][121250 // STEP_MS - 1] = np.nan
    trades = {"time": np.array([120501]), "price": np.array([29975.9]),
              "quantity": np.array([1.0]), "buyer_maker": np.array([True])}
    result = simulate_day(b, trades, PassiveRule("imbalance", 8), "synthetic")
    assert not result["complete"]
    assert result["counts"]["unresolved_exits"] == 1
