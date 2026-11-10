import numpy as np
import pandas as pd
import pytest

from research.absorption_hft import SCENARIOS, detect_events, replay, targets
from research.liquidation_event_replay import FIELDS


def tapes():
    clock = np.arange(1, 2001, dtype=np.int64) * 100000
    book = {"bid": np.full(2000, 100.), "ask": np.full(2000, 100.01),
            "bid_qty": np.full(2000, 10.), "ask_qty": np.full(2000, 100.),
            "local_us": clock - 1000, "exchange_us": clock - 2000}
    trades = {"local_us": np.array([59000000], np.int64), "exchange_us": np.array([58999000], np.int64),
              "price": np.array([100.]), "amount": np.array([120.]), "sell": np.array([True])}
    return book, trades


def quote_panel(events):
    panel = targets(events)
    for col in FIELDS:
        side, level = col.split("[")
        level = int(level[0])
        panel[col] = (100. + (.01 if side == "asks" else 0.) + (1 if side == "asks" else -1) * .01 * level) if col.endswith("price") else 100.
    panel["quote_local_us"] = panel.target_us - 1000
    panel["quote_exchange_us"] = panel.target_us - 2000
    panel["clock_kind"] = np.where(panel.label.eq("signal"), "capture", "exchange")
    panel["exchange_age_us"] = 2000
    panel["quote_age_us"] = 2000
    panel["source_delay_us"] = 1000
    panel["exchange_clock_ambiguous"] = False
    return panel


def test_defended_bid_then_observed_break_has_correct_direction_and_parent():
    book, trades = tapes()
    book["bid"][609:] = 99.99
    events = detect_events(book, trades, .01)
    assert events.mechanism.tolist() == ["hold_fade", "break_follow"]
    assert events.direction.tolist() == [1, -1]
    assert events.received_us.tolist() == [60000000, 61000000]
    assert events.parent_us.tolist() == [60000000, 60000000]
    assert events.volume_multiple.tolist() == [12., 12.]


def test_received_at_decision_trade_does_not_trigger_earlier_signal():
    book, trades = tapes()
    trades["local_us"][:] = 60000000
    trades["exchange_us"][:] = 59999000
    events = detect_events(book, trades, .01)
    assert not events.received_us.eq(60000000).any()
    assert events.iloc[0].received_us == 61000000


def test_depth_coverage_and_flow_dominance_are_actual_conditions():
    book, trades = tapes()
    book["bid_qty"][:] = 100.
    assert detect_events(book, trades, .01).empty
    book, trades = tapes()
    trades = {key: np.r_[value, value] for key, value in trades.items()}
    trades["sell"][1] = False
    trades["price"][1] = 100.01
    assert detect_events(book, trades, .01).empty


def test_stale_signal_window_and_future_event_clocks_cannot_trigger():
    book, trades = tapes()
    book["local_us"][580:650] -= 1000000
    assert detect_events(book, trades, .01).empty
    book, trades = tapes()
    trades["exchange_us"][:] = 60000001
    assert detect_events(book, trades, .01).empty


def test_break_after_ten_second_watch_is_not_an_event():
    book, trades = tapes()
    book["bid"][719:] = 99.99
    assert detect_events(book, trades, .01).mechanism.tolist() == ["hold_fade"]


def test_realized_fees_ack_holding_and_fixed_stress_quantity():
    events = detect_events(*tapes(), .01)
    panel = quote_panel(events)
    base = replay(events, panel, "hold_fade", 15, SCENARIOS["base"], .01, 1.)[0]
    fees = replay(events, panel, "hold_fade", 15, SCENARIOS["double_fees"], .01, 1.)[0]
    assert base["status"] == fees["status"] == "priced"
    assert base["quantity"] == fees["quantity"] == 9
    assert base["entry_us"] == 60500000 and base["entry_ack_us"] == 60750000
    assert base["exit_us"] == 76000000 and base["exit_ack_us"] == 76250000
    assert base["pnl"] == pytest.approx(9 * (100. - 100.01) - 9 * (100. + 100.01) * .0007)
    assert fees["pnl"] == pytest.approx(base["pnl"] - base["fees"])


def test_unknown_exit_retains_inventory_and_halts_later_orders():
    events = detect_events(*tapes(), .01)
    later = events.copy()
    later["received_us"] += 60000000
    later["parent_us"] += 60000000
    later["event_id"] += 1
    events = pd.concat([events, later], ignore_index=True)
    panel = quote_panel(events)
    panel.loc[panel.event_id.eq(0) & panel.label.eq("exit_250000_15"), "exchange_age_us"] = 1000000
    rows = replay(events, panel, "hold_fade", 15, SCENARIOS["base"], .01, 1.)
    assert rows[0]["status"] == "unresolved_exit" and rows[0]["open_quantity"] == 9
    assert rows[1]["status"] == "skipped_unresolved_inventory"
    assert rows[0]["pnl"] is rows[1]["pnl"] is None
