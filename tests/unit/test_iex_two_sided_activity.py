from research.iex_two_sided_activity import admit

CUTOFF = 1_700_000_100_000_000_000


def fixture():
    candidate = {"symbol": "TEST", "quantity": 10, "quote": {"bid_price": 100000, "ask_price": 100200}}
    rows = []
    for i, price in enumerate((100000, 99900, 100000, 100200, 100300, 100200)):
        t = CUTOFF - (6 - i) * 1_000_000_000
        rows.append({"symbol": "TEST", "type": "T", "flags": 0, "event_ns": t,
                     "send_ns": t + 500, "capture_ns": t + 1000, "price": price,
                     "size": (20, 20, 10)[i % 3], "trade_id": i})
    return candidate, rows


def test_distinct_times_and_volume_at_both_limits_qualify_at_exact_threshold():
    candidate, rows = fixture()
    result = admit(candidate, rows, CUTOFF)
    assert result["qualified"] and result["buy_limit_print_volume"] == result["sell_limit_print_volume"] == 50


def test_late_received_print_does_not_complete_past_activity():
    candidate, rows = fixture()
    rows[-1]["capture_ns"] = CUTOFF
    result = admit(candidate, rows, CUTOFF)
    assert not result["qualified"] and result["sell_limit_timestamps"] == 2


def test_old_native_trade_with_recent_capture_does_not_enter_window():
    candidate, rows = fixture()
    rows[0]["event_ns"] = CUTOFF - 30_000_000_001
    result = admit(candidate, rows, CUTOFF)
    assert not result["qualified"] and result["buy_limit_timestamps"] == 2


def test_many_reports_from_one_native_event_do_not_count_as_repeated_activity():
    candidate, rows = fixture()
    rows[0]["event_ns"] = rows[1]["event_ns"] = rows[2]["event_ns"]
    result = admit(candidate, rows, CUTOFF)
    assert not result["qualified"] and result["buy_limit_timestamps"] == 1


def test_causally_known_break_removes_quantity_and_time_evidence():
    candidate, rows = fixture()
    rows.append({**rows[0], "type": "B", "event_ns": CUTOFF - 5000,
                 "send_ns": CUTOFF - 4000, "capture_ns": CUTOFF - 3000})
    result = admit(candidate, rows, CUTOFF)
    assert not result["qualified"] and result["buy_limit_print_volume"] == 30


def test_three_times_without_required_volume_on_one_side_does_not_qualify():
    candidate, rows = fixture()
    rows[-1]["size"] = 9
    result = admit(candidate, rows, CUTOFF)
    assert result["sell_limit_timestamps"] == 3 and result["sell_limit_print_volume"] == 49
    assert not result["qualified"]
