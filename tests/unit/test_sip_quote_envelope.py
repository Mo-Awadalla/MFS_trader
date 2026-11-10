import pandas as pd

from research.sip_quote_envelope import envelope


def tape():
    return pd.DataFrame({"timestamp": pd.to_datetime([100, 1000, 2000, 3000], unit="ns", utc=True),
                         "bid_price": [99., 100., 101., 102.], "ask_price": [100., 101., 102., 103.],
                         "bid_size": [100, 100, 100, 100], "ask_size": [100, 100, 100, 100],
                         "bid_exchange": ["P"] * 4, "ask_exchange": ["Q"] * 4, "conditions": ['["R"]'] * 4})


def test_envelope_includes_predecessor_and_all_same_time_alternatives():
    r = envelope(tape(), 1500, 20, 500)
    assert r["complete"] and r["bid_lower"] == 99. and r["bid_upper"] == 101.
    assert r["first_index"] == 0 and r["stop_index"] == 3


def test_unknown_latest_quote_cannot_revive_earlier_valid_quote():
    f = tape()
    f.loc[1, "ask_price"] = 99.
    assert not envelope(f, 1500, 20, 100)["complete"]


def test_insufficient_size_in_any_branch_preserves_unknown_inventory():
    f = tape()
    f.loc[2, "bid_size"] = 19
    assert envelope(f, 1500, 20, 500)["reason"] == "unknown_quote_state_or_depth"


def test_unchanged_standing_quote_remains_observed_without_arbitrary_expiry():
    f = tape().iloc[[0, 3]].copy()
    f["timestamp"] = pd.to_datetime([0, 2000000000], unit="ns", utc=True)
    assert envelope(f, 1000000000, 20, 1000000)["complete"]


def test_missing_predecessor_or_successor_is_not_priced():
    assert not envelope(tape(), 100, 20, 50)["complete"]
    assert not envelope(tape(), 3000, 20, 50)["complete"]
