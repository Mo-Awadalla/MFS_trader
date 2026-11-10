import json
from decimal import Decimal as D

from research.fdusd_maker_supply import budgets, evaluate, sample
from research.spot_perp_supply import midnight_ns

DAY = "2024-01-01"
START = midnight_ns(DAY)


def book(capture=0, bid="100", ask="100.1", quantity="100"):
    return {"receive_ns": START + capture, "bid": bid, "ask": ask,
            "bid_quantity": quantity, "ask_quantity": quantity, "sequence_ok": True}


def line(second, uid=1, bid="100", ask="100.1"):
    data = {"s": "NEWFDUSD", "u": uid, "b": bid, "a": ask, "B": "100", "A": "100"}
    return f"{DAY}T00:00:{second:02d}.0000000Z " + json.dumps({"stream": "newfdusd@bookTicker", "data": data})


def test_fee_reserve_and_adverse_stresses_charge_both_sides():
    result = budgets("100", "100.1")
    assert D(result["passive_budget_bps"]) == D("5.998")
    assert D(result["double_fee_reserve_budget_bps"]) == D("3.997")
    assert result["double_fee_reserve_budget_bps"] == result["double_adverse_budget_bps"]
    assert D(result["flat_forced_exit_bps"]) == -13
    assert D(result["simplified_required_passive_exit_fraction"]) == D(13) / D("18.998")


def test_zero_spread_does_not_create_free_fee_profit():
    result = budgets("100", "100")
    assert D(result["passive_budget_bps"]) == -4
    assert result["simplified_required_passive_exit_fraction"] is None


def test_both_touch_depths_and_full_spread_gate_are_required():
    assert evaluate(book(), START + 1_000_000_000)["supply"]
    thin = book()
    thin["ask_quantity"] = "1"
    assert not evaluate(thin, START + 1_000_000_000)["supply"]
    assert not evaluate(book(ask="100.01"), START + 1_000_000_000)["supply"]


def test_exact_information_cutoff_and_stale_quotes_do_not_qualify():
    assert not evaluate(book(capture=750_000_000), START + 1_000_000_000)["valid"]
    assert not evaluate(book(), START + 6_000_000_000)["valid"]


def test_symbols_discovered_later_cannot_get_earlier_grid_prices():
    rows, summaries, _, _ = sample([line(20)], DAY, 0)
    assert summaries[0]["symbol"] == "NEWFDUSD"
    assert all(not r["valid"] for r in rows[:11])
    assert rows[11]["valid"] and rows[11]["decision_ns"] == START + 21_000_000_000


def test_duplicate_books_do_not_extend_freshness_and_disconnects_clear():
    rows, _, _, counts = sample([line(10), line(14), "\n", line(18, uid=2)], DAY, 0)
    assert counts["exact_duplicate_books"] == counts["disconnects"] == 1
    assert not next(r for r in rows if r["decision_ns"] == START + 17_000_000_000)["valid"]


def test_fx_keeps_observed_usdt_quote_without_par_or_maker_cost_assumption():
    fx_line = line(10, bid="0.995", ask="0.996").replace("NEWFDUSD", "FDUSDUSDT").replace("newfdusd", "fdusdusdt")
    rows, _, fx, _ = sample([fx_line], DAY, 0)
    assert not rows and fx[1]["valid"]
    assert fx[1]["quote_currency"] == "USDT" and fx[1]["bid"] == "0.995"
    assert "passive_budget_bps" not in fx[1] and "minimum_touch_fdusd" not in fx[1]
