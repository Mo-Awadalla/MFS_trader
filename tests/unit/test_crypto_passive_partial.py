import numpy as np
import pytest

from research.crypto_passive_partial import PartialRule, replay_partial_day, through_fills
from research.crypto_passive_replay import DAY_MS, STEP_MS


def book():
    n = DAY_MS // STEP_MS
    return {"bid": np.full(n, 30000.0), "ask": np.full(n, 30000.1),
            "bid_qty": np.full(n, 100.0), "ask_qty": np.full(n, 10.0),
            "event_ms": np.arange(n) * STEP_MS + STEP_MS - 1}


def tape(times, prices, quantities, makers):
    return {"time": np.array(times), "price": np.array(prices),
            "quantity": np.array(quantities), "buyer_maker": np.array(makers, dtype=bool)}


def test_partial_fills_accumulate_and_do_not_consume_later_excess_volume():
    t = tape([100, 101, 102, 103, 104, 105], [99, 100, 99, 99, 99, 99],
             [1, 1, 1, .01, .03, 1], [True, True, False, True, True, True])
    fills = through_fills(t, 100, 105, 1, 100, .025)
    assert [f["time"] for f in fills] == [103, 104]
    assert [f["quantity"] for f in fills] == pytest.approx([.01, .015])
    assert through_fills(t, 100, 103, 1, 100, .025) == []


def test_small_entry_waits_for_cancel_ack_and_closes_exact_inventory():
    t = tape([120501, 121501, 126001], [29975.9, 30000.2, 30000.2], [.002, 1, 1], [True, False, False])
    result = replay_partial_day(book(), t, PartialRule("imbalance", 8), "synthetic")
    trade = result["trades"][0]
    assert result["complete"]
    assert trade["partial_entry"]
    assert trade["quantity"] == pytest.approx(.002)
    assert trade["closed_quantity"] == pytest.approx(.002)
    assert trade["exit_activation_ms"] == 125750
    assert trade["exit_ms"] == 126001  # Earlier target print precedes cancel acknowledgement.
    assert trade["fees"] == pytest.approx(.002 * (trade["entry"] + trade["exit"]) * .0002)


def test_partial_exit_flattens_only_remainder_after_cancel_ack():
    t = tape([120501, 121501], [29975.9, 30000.2], [1, .01], [True, False])
    result = replay_partial_day(book(), t, PartialRule("imbalance", 8), "synthetic")
    trade = result["trades"][0]
    assert result["complete"]
    assert trade["maker_exit_quantity"] == pytest.approx(.01)
    assert trade["taker_exit_quantity"] == pytest.approx(trade["quantity"] - .01)
    assert trade["forced_arrival_ms"] == trade["cancel_arrival_ms"] + 500
    assert trade["exit_ms"] == 241500
    assert sum(f["quantity"] for f in trade["exit_fills"]) == pytest.approx(trade["quantity"])
    assert trade["slippage_dollars"] == pytest.approx(trade["taker_exit_quantity"] * 30000 * .0001)


def test_missing_forced_exit_keeps_unresolved_partial_inventory():
    b = book()
    b["bid"][241500 // STEP_MS - 1] = np.nan
    t = tape([120501, 121501], [29975.9, 30000.2], [1, .01], [True, False])
    result = replay_partial_day(b, t, PartialRule("imbalance", 8), "synthetic")
    assert not result["complete"]
    assert result["cash"] is None
    assert result["trades"][0]["remaining_quantity"] == pytest.approx(.023)
    assert result["trades"][0]["status"] == "unresolved_exit"


def test_entry_size_uses_visible_depth_and_cannot_skip_on_arrival_depth():
    b = book()
    b["bid_qty"][120250 // STEP_MS - 1] = .01
    t = tape([120501, 121501], [29975.9, 30000.2], [1, 1], [True, False])
    trade = replay_partial_day(b, t, PartialRule("imbalance", 8), "synthetic")["trades"][0]
    assert trade["quantity"] == pytest.approx(.033)
    assert trade["arrival_depth_fraction"] == pytest.approx(3.3)


def test_short_prints_and_fee_accounting_are_symmetric():
    b = book()
    b["ask_qty"][:] = 1000
    t = tape([120501, 121501], [30024.2, 29999.9], [1, 1], [False, True])
    trade = replay_partial_day(b, t, PartialRule("imbalance", 8), "synthetic")["trades"][0]
    assert trade["direction"] == -1
    expected = trade["quantity"] * (trade["entry"] - trade["exit"]) - trade["fees"]
    assert trade["pnl"] == pytest.approx(expected)
    assert trade["exit_ms"] == 121501
