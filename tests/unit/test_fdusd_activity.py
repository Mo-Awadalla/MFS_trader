import json

from research.fdusd_activity import screen

DAY, SYMBOL, MS = "2024-01-01", "ABCDFDUSD", 1704067200000


def trade(uid, second, maker=False, quantity="2", price="100", received_ns=200_000_000, **updates):
    raw = {"e": "trade", "s": SYMBOL, "t": uid, "T": MS + second * 1000,
           "E": MS + second * 1000, "p": price, "q": quantity, "m": maker}
    raw.update(updates)
    stamp = f"{DAY}T00:00:{second:02d}.{received_ns:09d}Z"
    return stamp + " " + json.dumps({"stream": SYMBOL.lower() + "@trade", "data": raw}) + "\n"


def enough():
    return [trade(i, i + 10, i % 2 == 0) for i in range(20)]


def outcome(lines):
    return screen(lines, DAY, 0, [SYMBOL])


def test_two_sides_and_exact_threshold_with_native_units():
    rows, ledger, _ = outcome(enough())
    assert rows[0]["selected"]
    assert rows[0]["buy_count"] == rows[0]["sell_count"] == 10
    assert rows[0]["buy_notional_fdusd"] == rows[0]["sell_notional_fdusd"] == "2000"
    assert ledger[0]["aggressor"] == "sell"


def test_one_sided_flow_cannot_be_netted_to_meet_gate():
    row = outcome([trade(i, 10 + i) for i in range(20)])[0][0]
    assert not row["selected"] and row["buy_count"] == 20 and row["sell_count"] == 0


def test_trade_count_and_notional_are_separate_requirements():
    for lines in ([trade(i, 10 + i, i % 2 == 0, quantity="100") for i in range(18)],
                  [trade(i, 10 + i, i % 2 == 0, quantity="1.999") for i in range(20)]):
        assert not outcome(lines)[0][0]["selected"]


def test_availability_cutoff_is_strict_and_warmup_is_not_counted():
    lines = [trade(0, 9), trade(1, 10), trade(2, 59, received_ns=749_999_999),
             trade(3, 59, received_ns=750_000_000)]
    row, ledger, _ = outcome(lines)
    assert row[0]["buy_count"] == 2
    assert ledger[0]["reason"] == "before_counting_interval"
    assert ledger[-1]["reason"] == "unavailable_at_cutoff"


def test_duplicates_never_double_activity():
    lines = [item for line in enough() for item in (line, line)]
    rows, _, counts = outcome(lines)
    assert rows[0]["buy_count"] == 10 and rows[0]["selected"]
    assert counts["exact_duplicate_trades"] == 20


def test_conflicting_id_invalidates_window():
    lines = enough() + [trade(19, 30, quantity="9")]
    row = outcome(lines)[0][0]
    assert row["activity_gate"] and not row["selected"]
    assert "conflicting_trade_id" in row["integrity_problems"]


def test_missing_or_regressing_trade_ids_invalidate_window():
    for uid, expected in ((21, "interior_trade_id_gap"), (-1, "regressing_trade_id")):
        row = outcome(enough() + [trade(uid, 30)])[0][0]
        assert not row["selected"] and expected in row["integrity_problems"]


def test_disconnect_invalidates_even_when_activity_would_pass():
    row = outcome(enough() + ["\n"])[0][0]
    assert row["activity_gate"] and not row["selected"]
    assert row["integrity_problems"] == "disconnect_before_cutoff"


def test_clock_order_and_staleness_cannot_create_activity():
    for updates in ({"E": MS + 29_999}, {"E": MS + 30_202}, {"T": MS + 28_999}):
        row = outcome(enough() + [trade(20, 30, **updates)])[0][0]
        assert "invalid_or_stale_trade_clock" in row["integrity_problems"] and not row["selected"]


def test_information_after_cutoff_cannot_change_past_eligibility():
    row = outcome(enough() + [trade(100, 59, received_ns=800_000_000), "\n"])[0][0]
    assert row["selected"] and row["buy_count"] == 10


def test_nonfinite_trade_is_not_zero_volume_or_a_valid_candidate():
    row = outcome(enough() + [trade(20, 30, price="NaN")])[0][0]
    assert not row["selected"] and row["integrity_problems"] == "invalid_trade_fields"
