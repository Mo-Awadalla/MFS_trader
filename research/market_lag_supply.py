"""Coherent leaders and explicitly conditional catch-up budgets."""

from decimal import Decimal as D


def quality(row):
    return (row is not None and row["valid_endpoints"]
            and max(D(row["anchor_spread_bps"]), D(row["current_spread_bps"])) <= 5
            and D(row["minimum_touch_usdt"]) >= 2000)


def leaders(btc, eth):
    output = {"leader_supply": False, "direction": 0, "common_move_bps": None}
    if not quality(btc) or not quality(eth):
        return {**output, "reason": "leader_endpoint_spread_or_depth"}
    moves = [D(row[k]) for row in (btc, eth) for k in ("bid_return_bps", "ask_return_bps")]
    direction = 1 if min(moves) >= 20 else -1 if max(moves) <= -20 else 0
    output.update(minimum_return_bps=str(min(moves)), maximum_return_bps=str(max(moves)))
    if not direction:
        return {**output, "reason": "no_coherent_major_move"}
    common = min(direction * value for value in moves)
    return {**output, "leader_supply": True, "direction": direction,
            "common_move_bps": str(common), "reason": "check_target_lags"}


def lag(leader, target):
    output = {"target_supply": False}
    if not leader["leader_supply"]:
        return {**output, "reason": "no_leader_supply"}
    if not quality(target):
        return {**output, "reason": "target_endpoint_spread_or_depth"}
    signed = [leader["direction"] * D(target[k]) for k in ("bid_return_bps", "ask_return_bps")]
    gap = D(leader["common_move_bps"]) - max(signed)
    budget = gap - 14 - D(target["anchor_spread_bps"]) - D(target["current_spread_bps"])
    output.update(gap_bps=str(gap), budget_bps=str(budget), minimum_signed_target_return_bps=str(min(signed)))
    if min(signed) < -5:
        return {**output, "reason": "large_opposite_target_move"}
    if gap < 20 or budget <= 2:
        return {**output, "reason": "insufficient_hypothesis_budget"}
    return {**output, "target_supply": True, "reason": "requires_native_trade_confirmation"}
