import numpy as np
import pandas as pd
import pytest

from research.auction_capture_proxy import SCENARIOS, extract_envelopes, replay_day
from research.auction_hft_event import extract_quotes

DAY = "2024-07-01"
OPEN = pd.Timestamp(DAY + " 09:30", tz="America/New_York").value


def source():
    records = []
    for symbol in ("SPY", "SH", "UPRO", "SPXU"):
        for seconds, bid in ((-40.01, 100.), (-10.01, 100.), (-9., 100.01), (8., 100.10), (23., 100.12), (60., 100.)):
            clock = OPEN + int(seconds * 1e9)
            records.append({"symbol": symbol, "ts_recv": pd.Timestamp(clock, tz="UTC"),
                            "ts_event": pd.Timestamp(clock - 100, tz="UTC"), "flags": 128,
                            "bid_px_00": bid, "ask_px_00": bid + .01,
                            "bid_sz_00": 10000, "ask_sz_00": 10000})
    return pd.DataFrame(records).sort_values("ts_recv", kind="stable")


def run(frame=None, scenario="base"):
    frame = source() if frame is None else frame.sort_values("ts_recv", kind="stable")
    signals, _ = extract_quotes(frame, DAY)
    envelopes, _ = extract_envelopes(frame, DAY)
    late = {"auction_type": "M", "auction_status": 0, "ref_price": 100., "ind_match_price": 100.2,
            "receive_ns": OPEN - 10001000000, "event_ns": OPEN - 10001000100}
    return replay_day(DAY, signals, envelopes, None, late, "indicative_gap_1x", 15, SCENARIOS[scenario])


def inject(frame, seconds, ask=100.02, size=10000, flags=128, event_seconds=None):
    row = frame.loc[frame.symbol.eq("SPY")].iloc[2].copy()
    row.ts_recv = pd.Timestamp(OPEN + int(seconds * 1e9), tz="UTC")
    row.ts_event = row.ts_recv - pd.Timedelta(nanoseconds=100) if event_seconds is None else pd.Timestamp(OPEN + int(event_seconds * 1e9), tz="UTC")
    row.ask_px_00, row.bid_px_00, row.ask_sz_00, row["flags"] = ask, ask - .01, size, flags
    return pd.concat([frame, pd.DataFrame([row])], ignore_index=True)


def test_standing_book_does_not_expire_and_acknowledgments_and_cash_are_exact():
    result = run()
    assert result["status"] == "bounded_fill"
    assert result["entry_min"] == result["entry_max"] == pytest.approx(100.02)
    assert result["entry_ack_ns"] == OPEN - 7750000000
    assert result["exit_target_ns"] == OPEN + 8250000000
    q = result["quantity"]
    net = q * (100.10 - 100.02) - 2 * max(1., .0075 * q) - q * (100.10 * .00003 + .0002) - q * (100.02 + 100.10) * .0001
    assert result["pnl_lower"] == pytest.approx(net)
    assert result["pnl_upper"] == pytest.approx(net)


def test_capture_order_keeps_later_state_despite_backward_event_clock():
    frame = inject(source(), -8.8, 100.03, event_seconds=-9.1)
    assert run(frame)["entry_min"] == pytest.approx(100.03)


def test_invalid_latest_state_is_unknown_not_resurrected():
    row = run(inject(source(), -8.8, flags=132))
    assert row["status"] == "unresolved_entry" and row["pnl_lower"] is None


def test_mixed_fok_branch_retains_loss_and_zero_instead_of_deleting_trade():
    frame = inject(source(), -8.7505, ask=100.50)
    frame = inject(frame, -8.7495, ask=100.02)
    frame.loc[frame.ts_recv.eq(pd.Timestamp(OPEN + 8000000000, tz="UTC")), ["bid_px_00", "ask_px_00"]] = [100., 100.01]
    result = run(frame)
    assert result["status"] == "bounded_fill_or_reject"
    assert result["pnl_lower"] < 0 and result["pnl_upper"] == 0
    frame.loc[frame.ts_recv.eq(pd.Timestamp(OPEN + 8000000000, tz="UTC")), ["bid_px_00", "ask_px_00"]] = [101., 101.01]
    result = run(frame)
    assert result["pnl_lower"] == 0 and result["pnl_upper"] > 0


def test_unknown_l1_entry_depth_is_not_a_rejection_or_future_resizing():
    result = run(inject(source(), -8.7505, size=1))
    assert result["status"] == "unresolved_entry_depth"
    assert result["possible_open_quantity"] == result["quantity"] > 1
    assert result["pnl_lower"] is None


def test_unknown_exit_retains_possible_inventory():
    frame = source()
    frame.loc[frame.ts_recv.eq(pd.Timestamp(OPEN + 8000000000, tz="UTC")), "bid_sz_00"] = 1
    result = run(frame)
    assert result["status"] == "unresolved_exit"
    assert result["possible_open_quantity"] == result["quantity"]
    assert not result["complete"]


def test_cost_stress_preserves_signal_and_alignment_enlargement_cannot_improve_lower_bound():
    frame = inject(source(), -8.7, 100.05)
    base, fees, alignment = run(frame), run(frame, "double_fees"), run(frame, "alignment_100ms")
    assert base["quantity"] == fees["quantity"] == alignment["quantity"]
    assert base["expected_net"] == fees["expected_net"] == alignment["expected_net"]
    assert fees["pnl_lower"] < base["pnl_lower"]
    assert alignment["pnl_lower"] <= base["pnl_lower"]
    assert np.isfinite(alignment["pnl_upper"])
