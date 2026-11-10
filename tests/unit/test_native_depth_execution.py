import pandas as pd
import pytest

from research.native_depth_execution import TargetBook, outcomes, replay, walk
from tests.unit.test_standing_depth_audit import case


def test_transaction_before_target_counts_even_if_published_after_target():
    rows, quote = case()
    rows[1].update(T_us=1900, E_us=2100, a=[["101", "3"]])
    target = TargetBook(quote, rows[0], 1.)
    for row in rows[1:]:
        target.advance(row)
    assert target.result["complete"]
    assert outcomes(target.result, 1, 5)[0]["notional"] == 507.


def test_all_same_transaction_time_states_retained():
    rows, quote = case()
    rows[1].update(T_us=2000, a=[["101", "3"]])
    target = TargetBook(quote, rows[0], 1.)
    for row in rows[1:]:
        target.advance(row)
    fills = outcomes(target.result, 1, 5, 101.)
    assert {x["status"] for x in fills} == {"filled", "rejected_fok"}
    assert target.result["timestamp_ties"] == 1


def test_unchanged_book_does_not_expire_by_age():
    rows, quote = case()
    quote["target_us"] = 10000000
    rows[-1]["T_us"] = 10001000
    target = TargetBook(quote, rows[0], 1.)
    for row in rows[1:]:
        target.advance(row)
    assert outcomes(target.result, -1, 3)[0]["notional"] == 300.


@pytest.mark.parametrize("change,reason", [({"pu": 1}, "native_sequence_gap"),
                                           ({"T_us": 800}, "transaction_clock_backtrack"),
                                           ({"disconnect": True}, "disconnect_or_context_gap")])
def test_invalid_native_continuity_cannot_establish_fill(change, reason):
    rows, quote = case()
    rows[1].update(change)
    target = TargetBook(quote, rows[0], 1.)
    target.advance(rows[1])
    assert target.result["reason"] == reason and not target.result["complete"]


def test_initial_normalized_snapshot_must_agree_with_raw_update():
    rows, quote = case()
    rows[0]["a"] = [["101", "9"]]
    assert TargetBook(quote, rows[0], 1.).result["reason"] == "source_snapshot_delta_disagreement"


def test_unknown_deeper_liquidity_is_not_invented_or_called_fok_rejection():
    state = {"a": [[101, 2]], "b": [[100, 2]]}
    boundary = {"a": 105, "b": 96}
    assert walk(state, boundary, 1., 1, 3)["status"] == "unknown_depth"
    assert walk(state, boundary, 1., 1, 3, 106.)["status"] == "unknown_depth"
    assert walk(state, boundary, 1., 1, 3, 105.)["status"] == "rejected_fok"
    assert walk(state, boundary, 1., -1, 3, 95.)["status"] == "unknown_depth"
    assert walk(state, boundary, 1., -1, 3, 96.)["status"] == "rejected_fok"


@pytest.mark.parametrize("direction", [1, -1])
def test_cash_bounds_include_fees_and_optional_rejection(direction):
    _, quote = case()
    quote.update(event_id=0, label="signal", quote_age_us=0, source_delay_us=0)
    event = {"event_id": 0, "received_us": 0, "direction": direction, "mechanism": "hold_fade"}
    events = pd.DataFrame([event])
    buy_fill = {"a": [[10100, 10]], "b": [[10000, 10]]}
    buy_reject = {"a": [[10200, 10]], "b": [[9900, 10]]}
    exit_state = {"a": [[10050, 10]], "b": [[10050, 10]]}
    base = {"complete": True, "tick": .01, "boundary": {"a": 10500, "b": 9600}, "timestamp_ties": 1}
    panels = {500000: {**base, "states": [buy_fill, buy_reject]},
              16000000: {**base, "states": [exit_state]}}
    scenario = {"delay_us": 250000, "taker_bps": 6., "adverse_bps": 1.}
    result = replay(events, pd.DataFrame([quote]), panels, "hold_fade", 15, scenario, .01, 1.)[0]
    entry = 101. if direction > 0 else 100.
    cash = direction * (100.5 - entry) - .0007 * (100.5 + entry)
    assert result["pnl_lower"] == pytest.approx(min(0, cash))
    assert result["pnl_upper"] == pytest.approx(max(0, cash))
    assert result["entry_optional"] and result["exit_us"] == 16000000


def test_unresolved_entry_retains_possible_inventory_and_stops_future_orders():
    _, quote = case()
    quote.update(event_id=0, label="signal", quote_age_us=0, source_delay_us=0)
    events = pd.DataFrame([{"event_id": i, "received_us": i * 60000000,
                            "direction": 1, "mechanism": "hold_fade"} for i in range(2)])
    panel = {500000: {"complete": False, "reason": "native_sequence_gap"}}
    scenario = {"delay_us": 250000, "taker_bps": 6., "adverse_bps": 1.}
    result = replay(events, pd.DataFrame([quote]), panel, "hold_fade", 15, scenario, .01, 1.)
    assert result[0]["possible_open_quantity"] == 1.
    assert result[1]["status"] == "skipped_unresolved_inventory"
