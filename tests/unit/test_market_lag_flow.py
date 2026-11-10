from research.market_lag_flow import joint_confirmation

EVENT = {"date": "2024-10-01", "offset_minutes": 987, "decision_ns": 1727800077500000000, "direction": -1, "symbol": "TRXUSDT"}


def part(symbol, aligned="4000", total="5000", count=5, integrity=True):
    return {**EVENT, "symbol": symbol, "aligned_notional_usdt": aligned, "total_notional_usdt": total,
            "native_market_trade_count": count, "source_integrity_ok": integrity}


def test_target_activity_does_not_require_the_leaders_directional_imbalance():
    parts = [part("BTCUSDT"), part("ETHUSDT"), part("TRXUSDT", aligned="0")]
    assert joint_confirmation(EVENT, parts)["selected"]


def test_either_leader_failing_direction_prevents_confirmation():
    parts = [part("BTCUSDT"), part("ETHUSDT", aligned="3749.99"), part("TRXUSDT")]
    assert joint_confirmation(EVENT, parts)["reason"] == "insufficient_aligned_leader_activity"


def test_source_fault_or_insufficient_target_volume_cannot_be_masked_by_leaders():
    parts = [part("BTCUSDT"), part("ETHUSDT"), part("TRXUSDT", integrity=False)]
    assert joint_confirmation(EVENT, parts)["reason"] == "source_integrity_unknown"
    parts[-1] = part("TRXUSDT", total="4999.99")
    assert joint_confirmation(EVENT, parts)["reason"] == "insufficient_target_activity"


def test_missing_duplicate_or_wrong_decision_role_is_not_a_joint_signal():
    parts = [part("BTCUSDT"), part("ETHUSDT"), part("TRXUSDT")]
    assert not joint_confirmation(EVENT, parts[:-1])["selected"]
    assert not joint_confirmation(EVENT, [parts[0], parts[0], parts[2]])["selected"]
    parts[1]["decision_ns"] += 250_000_000
    assert joint_confirmation(EVENT, parts)["reason"] == "role_or_event_mismatch"
