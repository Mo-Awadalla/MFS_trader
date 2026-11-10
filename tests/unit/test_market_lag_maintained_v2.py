"""Causal acquisition boundaries and non-promotion of old displayed quotes."""

from research.market_lag_maintained_v2 import clue, point_error

DECISION = 10_000_000_000
LEADER = {"leader_supply": True, "direction": -1, "common_move_bps": "25"}


def quote(cutoff, age=1_000_000_000):
    return {"receive_ns": cutoff - age, "transaction_ns": cutoff - age,
            "publication_ns": cutoff - age, "update_id": 50, "epoch": 0,
            "sequence_ok": True, "transaction_order_ok": True,
            "bid": "100", "ask": "100.01", "bid_quantity": "50", "ask_quantity": "50"}


def pair(age=1_000_000_000):
    return quote(DECISION - 1_250_000_000, age), quote(DECISION - 250_000_000, age)


def test_old_quote_is_only_a_clue_never_an_order():
    result = clue(*pair(), LEADER, DECISION)
    assert result["acquisition_candidate"] and not result["original_freshness_passed"]
    assert not result["trade_eligible"] and not result["depth_confirmed"]


def test_keep_original_fresh_candidate_regardless_of_known_outcome():
    result = clue(*pair(100_000_000), LEADER, DECISION)
    assert result["acquisition_candidate"] and result["original_freshness_passed"]


def test_exact_age_boundary_and_strict_information_cutoff():
    cutoff = DECISION - 250_000_000
    assert point_error(quote(cutoff, 5_000_000_000), cutoff) is None
    assert point_error(quote(cutoff, 5_000_000_001), cutoff) == "outside_acquisition_age"
    assert point_error(quote(cutoff, 0), cutoff) == "outside_acquisition_age"


def test_clock_conflict_cannot_be_relabelled_as_age():
    cutoff = DECISION - 250_000_000
    row = quote(cutoff)
    row["transaction_ns"] += 2_000_000
    assert point_error(row, cutoff) == "inconsistent_native_clocks"


def test_disconnect_and_regressing_quote_rejected():
    anchor, current = pair()
    current["epoch"] = 1
    assert not clue(anchor, current, LEADER, DECISION)["acquisition_candidate"]
    current["epoch"], current["sequence_ok"] = 0, False
    assert not clue(anchor, current, LEADER, DECISION)["acquisition_candidate"]


def test_existing_economics_and_opposite_move_gates_still_bind():
    anchor, current = pair()
    current.update(bid="100.1", ask="100.11")
    assert clue(anchor, current, LEADER, DECISION)["reason"] == "large_opposite_target_move"
    current = quote(DECISION - 250_000_000)
    current["bid_quantity"] = "19"
    assert clue(anchor, current, LEADER, DECISION)["reason"] == "target_endpoint_spread_or_depth"


def test_nullable_metadata_representation_preserves_valid_candidate():
    anchor, current = pair(100_000_000)
    for row in (anchor, current):
        row.update(epoch=0.0, update_id=5442120811884.0)
    result = clue(anchor, current, LEADER, DECISION)
    assert result["acquisition_candidate"] and result["original_freshness_passed"]


def test_metadata_repair_never_accepts_fractional_or_rounded_clocks():
    cutoff = DECISION - 250_000_000
    for bad in (0.5, float("nan"), float("inf"), float(2**53)):
        row = quote(cutoff)
        row["update_id"] = bad
        assert point_error(row, cutoff) == "missing_native_identity"
    row = quote(cutoff)
    row["receive_ns"] = float(row["receive_ns"])
    assert point_error(row, cutoff) == "missing_native_identity"
