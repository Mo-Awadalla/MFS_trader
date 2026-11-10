from research.market_lag_supply import lag, leaders


def row(bid="30", ask="31", spread="2", depth="3000", valid=True):
    return {"bid_return_bps": bid, "ask_return_bps": ask, "anchor_spread_bps": spread,
            "current_spread_bps": spread, "minimum_touch_usdt": depth, "valid_endpoints": valid}


def test_both_leaders_and_both_quote_sides_must_confirm_the_direction():
    assert leaders(row(), row(bid="22", ask="23"))["common_move_bps"] == "22"
    assert not leaders(row(), row(bid="19", ask="23"))["leader_supply"]
    assert not leaders(row(), row(bid="-22", ask="-23"))["leader_supply"]


def test_downward_move_uses_smallest_absolute_confirmed_move():
    actual = leaders(row(bid="-25", ask="-26"), row(bid="-22", ask="-23"))
    assert actual["direction"] == -1 and actual["common_move_bps"] == "22"


def test_invalid_stale_wide_or_shallow_leader_never_supplies_target_signal():
    for bad in (None, row(valid=False), row(spread="5.0001"), row(depth="1999.9")):
        assert not leaders(row(), bad)["leader_supply"]


def test_target_gap_budget_charges_both_spreads_and_round_trip_costs():
    leader = leaders(row(), row())
    value = lag(leader, row(bid="0", ask="1"))
    assert value["target_supply"] and value["budget_bps"] == "11"
    assert not lag(leader, row(bid="9", ask="10", spread="2"))["target_supply"]


def test_opposite_idiosyncratic_move_is_not_called_a_lag():
    leader = leaders(row(), row())
    assert not lag(leader, row(bid="-5.001", ask="-4"))["target_supply"]
    assert lag(leader, row(bid="-5", ask="-4"))["target_supply"]


def test_missing_leader_or_invalid_target_is_rejected_before_numeric_fields():
    assert lag({"leader_supply": False}, None)["reason"] == "no_leader_supply"
    assert not lag(leaders(row(), row()), row(valid=False))["target_supply"]
