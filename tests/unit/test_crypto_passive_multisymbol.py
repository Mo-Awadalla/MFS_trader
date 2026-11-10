import numpy as np
import pytest

from research.crypto_passive_multisymbol import PartialRule, replay_partial_day
from research.crypto_passive_partial import PartialRule as OldRule
from research.crypto_passive_partial import replay_partial_day as old_replay
from research.crypto_passive_replay import DAY_MS, STEP_MS


def book(bid, ask):
    n = DAY_MS // STEP_MS
    return {"bid": np.full(n, bid), "ask": np.full(n, ask), "bid_qty": np.full(n, 100.),
            "ask_qty": np.full(n, 10.), "event_ms": np.arange(n) * STEP_MS + STEP_MS - 1}


def tape(prices):
    return {"time": np.array([120501, 121501]), "price": np.array(prices),
            "quantity": np.array([1., 1.]), "buyer_maker": np.array([True, False])}


def test_default_btc_contract_preserves_frozen_engine():
    b, t = book(30000., 30000.1), tape([29975.9, 30000.2])
    assert replay_partial_day(b, t, PartialRule("imbalance", 8), "synthetic") == old_replay(b, t, OldRule("imbalance", 8), "synthetic")


def test_eth_contract_keeps_cent_ticks_and_actual_notional():
    b, t = book(2000., 2000.1), tape([1998.43, 2000.06])
    trade = replay_partial_day(b, t, PartialRule("imbalance", 8, tick_size=.01), "synthetic")["trades"][0]
    assert trade["entry"] == pytest.approx(1998.44)
    assert trade["target"] == pytest.approx(2000.05)
    assert trade["quantity"] == pytest.approx(.5)
    assert trade["pnl"] == pytest.approx(.5 * (2000.05 - 1998.44) - .5 * (2000.05 + 1998.44) * .0002)


def test_bad_contract_increment_fails_before_trading():
    with pytest.raises(ValueError, match="increments"):
        replay_partial_day(book(2000., 2000.1), tape([1998.43, 2000.06]),
                           PartialRule("imbalance", 8, tick_size=0), "synthetic")
