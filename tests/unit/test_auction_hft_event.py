import numpy as np
import pandas as pd
import pytest

from research.auction_hft_event import SCENARIOS, costs, extract_quotes, replay_day

DAY = "2024-07-01"
OPEN = pd.Timestamp(DAY + " 09:30", tz="America/New_York").value


def sources():
    rows = []
    for symbol in ("SPY", "SH", "UPRO", "SPXU"):
        for seconds, bid in ((-40.001, 99.99), (-10.001, 100.), (-8.751, 100.01), (8.249, 100.10), (23.249, 100.12)):
            event = OPEN + int(seconds * 1e9)
            # Delayed capture of the execution state must not leak into features.
            receive = event + (300000000 if seconds == -8.751 else 100)
            rows.append({"symbol": symbol, "ts_recv": pd.Timestamp(receive, tz="UTC"),
                "ts_event": pd.Timestamp(event, tz="UTC"), "flags": 128,
                "bid_px_00": bid, "ask_px_00": bid + .01, "bid_sz_00": 10000, "ask_sz_00": 10000})
    return pd.DataFrame(rows).sort_values("ts_recv", kind="stable")


def auctions(indicative=100.20):
    common = {"auction_type": "M", "auction_status": 0, "ref_price": 100.}
    early = {**common, "receive_ns": OPEN - 120001000000, "event_ns": OPEN - 120001000100,
             "ind_match_price": 100.01}
    late = {**common, "receive_ns": OPEN - 10001000000, "event_ns": OPEN - 10001000100,
            "ind_match_price": indicative}
    return early, late


def replay(frame=None, rule="indicative_gap_1x", scenario="base"):
    quotes, _ = extract_quotes(sources() if frame is None else frame, DAY)
    early, late = auctions()
    return replay_day(DAY, quotes, early, late, rule, 15, SCENARIOS[scenario])


def test_dual_clocks_causal_signal_ack_holding_and_exact_cash():
    row = replay()
    assert row["status"] == "priced" and row["complete"]
    assert row["signal_receive_ns"] < row["decision_ns"]
    assert row["entry_source_event_ns"] == OPEN - 8751000000
    assert row["entry_target_ns"] == OPEN - 8750000000
    assert row["entry_ack_ns"] == OPEN - 7750000000
    assert row["exit_target_ns"] == OPEN + 8250000000
    q = row["quantity"]
    expected = q * (100.10 - 100.02) - 2 * max(1., .0075 * q) - q * (100.10 * .00003 + .0002) - q * (100.02 + 100.10) * .0001
    assert row["pnl"] == pytest.approx(expected)
    assert row["closed_quantity"] == q


def test_invalid_latest_state_does_not_resurrect_previous_quote():
    frame = sources()
    row = frame.loc[frame.symbol.eq("SPY")].iloc[1].copy()
    row.ts_recv += pd.Timedelta(microseconds=10)
    row.ts_event += pd.Timedelta(microseconds=10)
    row["flags"] = 132
    frame = pd.concat([frame, pd.DataFrame([row])], ignore_index=True).sort_values("ts_recv", kind="stable")
    assert replay(frame)["status"] == "no_causal_signal"


def test_fok_outside_collar_is_rejected_and_insufficient_depth_is_unknown():
    frame = sources()
    match = frame.symbol.eq("SPY") & frame.ts_event.eq(pd.Timestamp(OPEN - 8751000000, tz="UTC"))
    frame.loc[match, ["bid_px_00", "ask_px_00"]] += .5
    assert replay(frame)["status"] == "rejected_fok"
    frame = sources()
    frame.loc[match, "ask_sz_00"] = 1
    row = replay(frame)
    assert row["status"] == "unresolved_entry_depth" and row["pnl"] is None and not row["complete"]


def test_missing_exit_keeps_open_position_and_fees_do_not_change_signal_selection():
    frame = sources()
    frame = frame.loc[~frame.ts_event.eq(pd.Timestamp(OPEN + 8249000000, tz="UTC"))]
    row = replay(frame)
    assert row["status"] == "unresolved_exit" and row["open_quantity"] == row["quantity"]
    base, stress = replay(), replay(scenario="double_fees")
    assert base["expected_net"] == stress["expected_net"] and base["quantity"] == stress["quantity"]
    assert stress["commission"] == 2 * base["commission"]
    assert stress["adverse"] == base["adverse"]


def test_unknown_entry_is_not_harmless_zero_and_timestamp_ties_are_excluded():
    frame = sources()
    target = pd.Timestamp(OPEN - 8751000000, tz="UTC")
    frame.loc[frame.ts_event.eq(target), "ts_event"] += pd.Timedelta(milliseconds=1)
    row = replay(frame)
    assert row["status"] == "unresolved_entry" and row["pnl"] is None


def test_future_auction_message_cannot_select_order_and_negative_gap_buys_inverse():
    quotes, _ = extract_quotes(sources(), DAY)
    early, late = auctions(99.8)
    row = replay_day(DAY, quotes, early, late, "indicative_gap_1x", 15, SCENARIOS["base"])
    assert row["symbol"] == "SH" and row["status"] == "priced"
    late["receive_ns"] = OPEN - 10000000000
    row = replay_day(DAY, quotes, early, late, "indicative_gap_1x", 15, SCENARIOS["base"])
    assert row["status"] == "no_causal_signal"


def test_source_event_backtrack_quarantines_only_nearby_execution_targets():
    frame = sources()
    row = frame.loc[frame.symbol.eq("SPY")].iloc[2].copy()
    row.ts_recv += pd.Timedelta(milliseconds=1)
    row.ts_event -= pd.Timedelta(milliseconds=1)
    frame = pd.concat([frame, pd.DataFrame([row])], ignore_index=True).sort_values("ts_recv", kind="stable")
    quotes, _ = extract_quotes(frame, DAY)
    selected = quotes.loc[quotes.symbol.eq("SPY")].set_index("label")
    assert selected.loc["entry_1", "ambiguous"]
    assert not selected.loc["signal", "ambiguous"]
    assert replay(frame)["status"] == "unresolved_entry"
    assert np.isfinite(costs(1, 100, 100)).all()
