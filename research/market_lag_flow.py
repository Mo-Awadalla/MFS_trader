"""Apply the distinct, predeclared leader-direction and target-activity gates."""

from decimal import Decimal as D


def joint_confirmation(event, parts):
    expected = {"BTCUSDT", "ETHUSDT", event["symbol"]}
    result = {"source_integrity_ok": False, "leader_activity_gate": False,
              "leader_direction_gate": False, "target_activity_gate": False, "selected": False}
    if (len(expected) != 3 or len(parts) != 3 or {r["symbol"] for r in parts} != expected
            or any(any(r[k] != event[k] for k in ("date", "offset_minutes", "decision_ns", "direction")) for r in parts)):
        return {**result, "reason": "role_or_event_mismatch"}
    indexed = {r["symbol"]: r for r in parts}
    leading = [indexed[s] for s in ("BTCUSDT", "ETHUSDT")]
    target = indexed[event["symbol"]]
    integrity = all(r["source_integrity_ok"] for r in parts)
    activity = all(r["native_market_trade_count"] >= 5 and D(r["total_notional_usdt"]) >= 5000 for r in leading)
    direction = all(4 * D(r["aligned_notional_usdt"]) >= 3 * D(r["total_notional_usdt"]) for r in leading)
    target_activity = target["native_market_trade_count"] >= 5 and D(target["total_notional_usdt"]) >= 5000
    selected = integrity and activity and direction and target_activity
    reason = ("source_integrity_unknown" if not integrity else "insufficient_leader_activity" if not activity
              else "insufficient_aligned_leader_activity" if not direction else "insufficient_target_activity" if not target_activity
              else "requires_response_replay")
    return {"source_integrity_ok": integrity, "leader_activity_gate": activity,
            "leader_direction_gate": direction, "target_activity_gate": target_activity,
            "selected": selected, "reason": reason}
