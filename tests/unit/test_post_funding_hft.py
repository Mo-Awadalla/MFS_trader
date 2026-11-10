from decimal import Decimal as D

from research.post_funding_hft import cash, entry_plan, possible_quotes, replay, ticker_update

NS = 1_000_000_000


def book(t, bid=10, ask=10.01, quantity=1000, index=1):
    return {"receive_ns": t+10_000_000, "publication_ns": t+1_000_000, "transaction_ns": t,
            "source_index": index, "valid": True, "bid": bid, "ask": ask,
            "bid_quantity": quantity, "ask_quantity": quantity}


def ticker(t, next_ms=100000):
    return {"receive_ns": t+10_000_000, "publication_ns": t, "source_index": t,
            "valid": True, "fields": {"nextFundingTime": str(next_ms)}, "provenance": {"nextFundingTime": t}}


def test_post_settlement_gate_rejects_unknown_and_unadvanced_cycle():
    books = [book(9*NS)]
    assert entry_plan(books, [ticker(9*NS, 0)], 0)["reason"] == "funding_cycle_not_safely_advanced"
    state = ticker(9*NS)
    state["fields"] = {}
    assert entry_plan(books, [state], 0)["reason"] == "funding_cycle_advance_unobserved"
    assert entry_plan(books, [ticker(9*NS)], 0)["eligible"]


def test_capture_equal_to_decision_cutoff_cannot_be_used():
    row = book(9*NS)
    row["receive_ns"] = 9_750_000_000
    assert not entry_plan([row], [ticker(9*NS)], 0)["eligible"]


def test_invalid_funding_time_is_not_treated_as_a_completed_cycle():
    row = ticker(9*NS)
    row["fields"]["nextFundingTime"] = ""
    assert entry_plan([book(9*NS)], [row], 0)["reason"] == "invalid_native_funding_time"


def test_sequence_break_does_not_seed_carried_funding_field():
    message = {"data": {"nextFundingTime": "100000"}, "cs": 2, "type": "delta", "ts": 9000}
    _, state = ticker_update(message, 9*NS, 1, None)
    invalid = {**message, "cs": 1, "data": {"nextFundingTime": "200000"}}
    row, state = ticker_update(invalid, 9*NS+1, 2, state)
    assert not row["valid"] and not state["fields"]
    row, _ = ticker_update({**message, "cs": 3, "data": {"markPrice": "10"}}, 9*NS+2, 3, state)
    assert row["valid"] and "nextFundingTime" not in row["fields"]


def test_clock_envelope_includes_all_tied_predecessors_and_updates():
    rows = [book(10*NS, ask=10.01, index=1), book(10*NS, ask=10.02, index=2),
            book(11*NS, ask=10.03, index=3), book(12*NS, ask=10.04, index=4)]
    result = possible_quotes(rows, 11*NS, 1_000_000, 10, True)
    assert result["known"] and result["source_indices"] == [1, 2, 3]
    assert result["price_min"] == D("10.01") and result["price_max"] == D("10.03")


def test_depth_failure_is_unknown_not_an_assumed_fill_or_zero():
    rows = [book(10*NS, quantity=5), book(12*NS)]
    assert not possible_quotes(rows, 11*NS, 1_000_000, 10, True)["known"]


def test_matching_clock_regression_is_not_sorted_away():
    rows = [book(10*NS), book(9*NS), book(12*NS)]
    assert possible_quotes(rows, 11*NS, 1_000_000, 10, True)["reason"] == "regressing_matching_clock"


def test_book_gap_or_missing_right_boundary_is_unknown():
    assert not possible_quotes([book(10*NS)], 11*NS, 1_000_000, 10, True)["known"]
    rows = [book(10*NS), {"receive_ns": 11*NS, "transaction_ns": None}, book(12*NS)]
    assert not possible_quotes(rows, 11*NS, 1_000_000, 10, True)["known"]


def test_both_long_and_short_cash_charge_both_sides_without_funding_credit():
    long = cash(10, True, "10", "10.1", 6, 1)
    short = cash(10, False, "10.1", "10", 6, 1)
    assert long == short == {"gross": D("1.0"), "fees": D("0.1206"), "adverse": D("0.0201"), "net": D("0.8593")}


def test_late_funding_time_change_preserves_unknown_after_entry():
    books = [book(t*NS, index=t) for t in range(8, 30)]
    tickers = [ticker(t*NS) for t in range(8, 30)]
    plan = entry_plan(books, tickers, 0)
    tickers[7]["fields"]["nextFundingTime"] = "20000"
    event = {"settlement_ns": 0, "bybit_funding_rate": -0.003}
    scenario = {"latency_seconds": 1, "clock_ms": 1, "taker_bps": 6, "adverse_bps": 1}
    result = replay(books, tickers, event, plan, "unwind_reversal", scenario)
    assert result["submitted"] and not result["known"] and result["reason"] == "unknown_funding_cash_after_submission"


def test_fixed_horizon_and_direction_are_not_selected_from_returns():
    books = [book(t*NS, index=t) for t in range(8, 32)]
    tickers = [ticker(t*NS) for t in range(8, 32)]
    plan = entry_plan(books, tickers, 0)
    event = {"settlement_ns": 0, "bybit_funding_rate": -0.003}
    scenario = {"latency_seconds": 3, "clock_ms": 100, "taker_bps": 6, "adverse_bps": 1}
    result = replay(books, tickers, event, plan, "unwind_reversal", scenario)
    assert result["known"] and result["long"] and result["entry_arrival_ns"] == 13*NS and result["exit_arrival_ns"] == 28*NS
    assert result["inventory_upper_ns"] == 15_200_000_000 and result["upper"]["net"] < 0
