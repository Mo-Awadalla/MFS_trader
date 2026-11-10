from research.perp_shock_flow import confirm

EVENT = {"date": "2024-01-01", "offset_minutes": 0, "symbol": "ABCUSDT", "decision_ns": 10_000_000_000, "direction": 1}


def trade(uid, time_ms, quantity="10", maker=False, **fields):
    return {"source_line": uid, "symbol": "ABCUSDT", "receive_ns": (time_ms + 1) * 1_000_000,
            "raw": {"e": "trade", "s": "ABCUSDT", "t": uid, "T": time_ms, "E": time_ms,
                    "p": "100", "q": quantity, "m": maker, "X": "MARKET", **fields}}


def enough():
    return [trade(i, 9000 + i * 10) for i in range(5)]


def test_exact_count_notional_threshold_and_aggressor_direction():
    result, _ = confirm(enough(), [], EVENT)
    assert result["selected"] and result["total_notional_usdt"] == "5000" and result["aligned_fraction"] == "1"
    assert not confirm(enough(), [], {**EVENT, "direction": -1})[0]["selected"]


def test_count_total_and_alignment_are_separate_requirements():
    variants = [enough()[:4], [trade(i, 9000 + i, quantity="9") for i in range(5)],
                [trade(i, 9000 + i, maker=i < 2) for i in range(5)]]
    assert all(not confirm(rows, [], EVENT)[0]["selected"] for rows in variants)


def test_strict_capture_cutoff_and_matching_interval_boundaries():
    rows = [trade(0, 8749), trade(1, 8750), trade(2, 9748), trade(3, 9749), trade(4, 9750)]
    result, _ = confirm(rows, [], EVENT)
    assert result["native_market_trade_count"] == 2


def test_duplicates_are_not_additional_executions():
    duplicated = [r for t in enough() for r in (t, t)]
    result, _ = confirm(duplicated, [], EVENT)
    assert result["selected"] and result["native_market_trade_count"] == 5


def test_conflicting_and_gapped_ids_make_the_event_unknown():
    for extra, fault in ((trade(4, 9060), "conflicting_trade_id"), (trade(6, 9060), "interior_trade_id_gap")):
        result, _ = confirm(enough() + [extra], [], EVENT)
        assert not result["selected"] and fault in result["integrity_problems"]


def test_adl_and_insurance_executions_do_not_confirm_market_demand():
    result, _ = confirm([trade(i, 9000 + i, X="ADL") for i in range(5)], [], EVENT)
    assert not result["selected"] and result["native_market_trade_count"] == 0


def test_post_cutoff_bad_records_and_disconnects_cannot_change_past_selection():
    result, _ = confirm(enough() + [trade(100, 9800, quantity="NaN")], [9_900_000_000], EVENT)
    assert result["selected"]
    assert not confirm(enough(), [9_500_000_000], EVENT)[0]["selected"]


def test_delayed_or_future_clock_trade_is_unknown_not_zero_loss():
    for extra in (trade(5, 9050, E=9100), {**trade(5, 9050), "receive_ns": 9_400_000_000}):
        result, _ = confirm(enough() + [extra], [], EVENT)
        assert result["flow_gate"] and not result["selected"]
        assert result["reason"] == "source_integrity_unknown"
