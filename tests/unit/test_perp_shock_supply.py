import json

from research.perp_shock_supply import evaluate, sample
from research.spot_perp_supply import NS, midnight_ns

DAY, SYMBOL = "2024-01-01", "ABCUSDT"
START = midnight_ns(DAY)


def quote(second, bid, ask, size="100", epoch=0):
    stamp = START + int(second * NS)
    return {"receive_ns": stamp, "transaction_ns": stamp - 1_000_000,
            "publication_ns": stamp, "sequence_ok": True, "transaction_order_ok": True,
            "bid": bid, "ask": ask, "bid_quantity": size, "ask_quantity": size, "epoch": epoch}


def line(second, bid, ask, uid, transaction=None, fraction="700000000"):
    millis = START // 1_000_000 + second * 1000 + int(fraction) // 1_000_000
    raw = {"s": SYMBOL, "u": uid, "T": millis - 1 if transaction is None else transaction,
           "E": millis, "b": bid, "a": ask, "B": "100", "A": "100"}
    return f"{DAY}T00:00:{second:02d}.{fraction}Z " + json.dumps({"stream": SYMBOL.lower() + "@bookTicker", "data": raw}) + "\n"


def test_both_quote_sides_must_move_in_the_same_direction():
    before = quote(.7, "100", "100.01")
    result = evaluate(before, quote(1.7, "100.4", "100.41"), START + 2 * NS)
    assert result["supply"] and result["direction"] == 1
    result = evaluate(before, quote(1.7, "99.6", "99.61"), START + 2 * NS)
    assert result["supply"] and result["direction"] == -1
    assert not evaluate(before, quote(1.7, "100", "100.5"), START + 2 * NS)["supply"]


def test_current_and_anchor_depth_and_spread_are_required():
    before, now = quote(.7, "100", "100.01"), quote(1.7, "100.4", "100.41")
    for pair in (({**before, "bid_quantity": "1"}, now), (before, {**now, "ask_quantity": "1"}),
                 (quote(.7, "100", "100.2"), quote(1.7, "101", "101.3"))):
        result = evaluate(*pair, START + 2 * NS)
        assert not result["supply"] and result["direction"] != 0


def test_endpoint_cutoff_is_strict_and_clock_delay_is_checked():
    before, now = quote(.7, "100", "100.01"), quote(1.7, "100.4", "100.41")
    for field, value in (("receive_ns", START + 1_750_000_000),
                         ("transaction_ns", START + NS), ("publication_ns", START + 1_702_000_000)):
        result = evaluate(before, {**now, field: value}, START + 2 * NS)
        assert not result["valid_endpoints"] and not result["supply"]


def test_disconnect_generations_cannot_be_joined():
    result = evaluate(quote(.7, "100", "100.01", epoch=0), quote(1.7, "100.4", "100.41", epoch=1), START + 2 * NS)
    assert result["reason"] == "disconnect_between_endpoints" and not result["supply"]


def test_quarter_second_universe_rows_and_no_future_quote_selection():
    lines = [line(0, "100", "100.01", 1), line(1, "100.4", "100.41", 2)]
    rows, quotes, _, symbols = sample(lines, DAY, 0)
    assert symbols == 1 and len(rows) == 228 and len(quotes) == 232
    selected = [r for r in rows if r["selected"]]
    assert len(selected) == 1 and selected[0]["decision_ns"] == START + 2 * NS
    later = [s.replace(".700000000Z", ".750000000Z") for s in lines]
    assert not sample(later, DAY, 0)[0][0]["selected"]


def test_equal_id_duplicates_cannot_refresh_signal_freshness():
    first = line(0, "100", "100.01", 1)
    duplicate = first.replace(":00.700000000Z", ":01.700000000Z")
    rows, _, counts, _ = sample([first, duplicate], DAY, 0)
    assert counts["exact_duplicate_books"] == 1 and not any(r["selected"] for r in rows)


def test_matching_clock_regression_is_not_repaired_by_capture_order():
    lines = [line(0, "100", "100.01", 1), line(1, "100.4", "100.41", 2, transaction=START // 1_000_000 + 600)]
    rows, _, counts, _ = sample(lines, DAY, 0)
    assert counts["regressing_matching_clocks"] == 1
    assert rows[0]["reason"] == "current_regressing_matching_clock" and not rows[0]["selected"]


def test_conflicting_latest_quote_is_retained_as_invalid():
    lines = [line(0, "100", "100.01", 1), line(1, "100.4", "100.41", 1)]
    rows, _, counts, _ = sample(lines, DAY, 0)
    assert counts["conflicting_or_regressing_books"] == 1
    assert rows[0]["reason"] == "current_conflicting_or_regressing_id"


def test_same_symbol_cooldown_preserves_all_raw_events():
    lines = []
    for second in range(40):
        bid = 100 if second % 2 == 0 else 101
        lines.append(line(second, str(bid), str(bid + .01), second + 1))
    rows, _, _, _ = sample(lines, DAY, 0)
    assert sum(r["supply"] for r in rows) > 2
    chosen = [r["decision_ns"] for r in rows if r["selected"]]
    assert chosen == [START + 2 * NS, START + 32 * NS]
