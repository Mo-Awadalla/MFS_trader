import json
from decimal import Decimal as D

from research.conversion_cycle_supply import cash_cycle, evaluate, sample
from research.spot_perp_supply import NS, midnight_ns

DAY = "2024-01-01"
START = midnight_ns(DAY)


def book(bid="99", ask="100", size="100000"):
    return {"bid": bid, "ask": ask, "bid_quantity": size, "ask_quantity": size,
            "receive_ns": START + 9_700_000_000, "sequence_ok": True, "venue": "spot"}


def line(symbol, second, bid, ask, uid=1, fraction="700000000"):
    raw = {"s": symbol, "u": uid, "b": bid, "a": ask, "B": "100000", "A": "100000"}
    return f"{DAY}T00:00:{second:02d}.{fraction}Z " + json.dumps({"stream": symbol.lower() + "@bookTicker", "data": raw}) + "\n"


def test_cost_is_charged_on_each_leg_in_received_asset():
    books = [book(), book("1.02", "1.03"), book("100", "101")]
    final, depth, legs = cash_cycle(books, "base_first")
    expected = D(200) / D("100.01") * D(".999") * D("1.02") * D(".9999") * D(".999") * D(100) * D(".9999") * D(".999")
    assert abs(final - expected) < D("1e-23") and depth and len(legs) == 3
    assert evaluate(books, START + 10 * NS, "base_first")["supply"]


def test_reverse_route_uses_other_sides_in_reverse_conversion_order():
    books = [book("105", "106"), book("1", "1.01"), book("99", "100")]
    final, _, legs = cash_cycle(books, "bridge_first", fee=D(0), adverse=D(0))
    assert abs(final - D(200) / 100 / D("1.01") * 105) < D("1e-23")
    assert [r["side"] for r in legs] == ["buy", "buy", "sell"]


def test_parity_and_wider_costs_cannot_create_a_profit():
    books = [book(), book("1", "1.01"), book("100", "101")]
    result = evaluate(books, START + 10 * NS, "base_first")
    assert not result["supply"] and D(result["gross_budget_bps"]) == 0
    assert D(result["double_fee_budget_bps"]) < D(result["base_budget_bps"]) < 0
    assert D(result["double_adverse_budget_bps"]) < D(result["base_budget_bps"])


def test_each_leg_depth_matters_in_its_own_base_units():
    books = [book(), book("1.02", "1.03"), book("100", "101", size="10")]
    result = evaluate(books, START + 10 * NS, "base_first")
    assert result["price_gate"] and not result["depth_gate"] and not result["supply"]


def test_missing_stale_and_conflicting_books_are_not_prices():
    good = [book(), book("1.02", "1.03"), book("100", "101")]
    for broken in (None, {**good[0], "sequence_ok": False}, {**good[0], "receive_ns": START + 8 * NS}):
        result = evaluate([broken, *good[1:]], START + 10 * NS, "base_first")
        assert not result["valid_books"] and not result["supply"]


def test_strict_causal_cutoff_and_two_observation_confirmation():
    lines = []
    for second in (9, 10):
        for symbol, bid, ask in (("XUSDT", "99", "100"), ("XBTC", "1.02", "1.03"), ("BTCUSDT", "100", "101")):
            lines.append(line(symbol, second, bid, ask, uid=second))
    rows, quotes, _, route_count = sample(lines, DAY, 0)
    selected = [r for r in rows if r["selected"]]
    assert route_count == 1 and len(selected) == 1 and selected[0]["decision_ns"] == START + 11 * NS
    assert all(r.get("receive_ns", 0) < r["decision_ns"] - 250_000_000 for r in quotes)
    changed = [s.replace(".700000000Z", ".750000000Z") for s in lines]
    assert not any(r["selected"] for r in sample(changed, DAY, 0)[0])


def test_duplicate_update_does_not_refresh_age_and_disconnect_clears_state():
    lines = [line("XUSDT", 9, "99", "100"), line("XBTC", 9, "1.02", "1.03"), line("BTCUSDT", 9, "100", "101")]
    duplicates = lines + [s.replace(":09.", ":10.") for s in lines]
    assert not any(r["selected"] for r in sample(duplicates, DAY, 0)[0])
    assert not any(r["selected"] for r in sample(lines + ["\n"], DAY, 0)[0])
