import json

import pandas as pd
import pytest

from research.liquidation_passive import EventBook
from research.raw_liquidation_replay import TAKER_SCENARIOS, parse_slice, taker_replay
from research_scout.run_raw_liquidation_20260930 import available_reports, native_events


def message(quantity="2", last="0.1", average="100", status="FILLED"):
    return ("2024-07-01T00:02:00.0000010Z " + json.dumps({"stream": "btcusdt@forceOrder",
        "data": {"e": "forceOrder", "E": 1719792120000,
                 "o": {"s": "BTCUSDT", "S": "BUY", "q": quantity, "z": quantity,
                       "l": last, "ap": average, "p": "110", "X": status,
                       "f": "IOC", "T": 1719792120000}}}) + "\n").encode()


def events():
    return pd.DataFrame([{"date": "2024-07-01", "event_id": 0, "received_us": 120_000_000,
                          "forced_side": 1, "reported_notional": 100000.}])


def book():
    rows = []
    # Price at the signal's exact capture time must not be visible to the signal.
    for exchange, local, bid in [(119_990_000, 119_990_000, 100.),
                                 (119_999_000, 120_000_000, 100.004),
                                 (121_240_000, 121_400_000, 100.002),
                                 (153_240_000, 153_400_000, 100.100)]:
        row = {"exchange_us": exchange, "local_us": local}
        for level in range(5):
            row.update({f"bids[{level}].price": bid - level * .001,
                        f"asks[{level}].price": bid + .001 + level * .001,
                        f"bids[{level}].amount": 20., f"asks[{level}].amount": 20.})
        rows.append(row)
    return pd.DataFrame(rows)


def run(frame=None):
    return taker_replay("2024-07-01", EventBook(book() if frame is None else frame), events(),
                        "follow", 30, TAKER_SCENARIOS["base"], tick_size=.001, quantity_step=.1)


def test_native_fields_use_cumulative_executed_size_and_not_limit_or_last_fill():
    rows, markers = parse_slice(message(), "2024-07-01", 0)
    assert markers == 0
    assert rows[0]["executed_notional"] == 200.
    assert rows[0]["legacy_proxy"] == 11.
    chosen = native_events(pd.DataFrame(rows), "2024-07-01", 190.)
    assert len(chosen) == 1 and chosen.iloc[0].reported_notional == 200.
    assert chosen.iloc[0].received_us == 120000001


def test_native_parser_rejects_wrong_slice_and_inconsistent_fills():
    with pytest.raises(ValueError, match="out-of-slice"):
        parse_slice(message(), "2024-07-01", 10)
    with pytest.raises(ValueError, match="Inconsistent"):
        parse_slice(message(last="3"), "2024-07-01", 0)
    with pytest.raises(ValueError, match="Invalid raw"):
        parse_slice(message(average="nan"), "2024-07-01", 0)


def test_disconnect_markers_are_retained_and_nonfilled_orders_do_not_trigger():
    rows, markers = parse_slice(message(status="EXPIRED") + b"\n", "2024-07-01", 0)
    assert markers == 1
    assert native_events(pd.DataFrame(rows), "2024-07-01", 1.).empty


def test_capture_signal_physical_execution_ack_timing_and_cash_units():
    result = run()
    row = result["attempts"][0]
    assert result["complete"] and row["status"] == "priced"
    assert row["signal_local_us"] == 119990000
    assert row["entry_exchange_us"] == 121240000
    assert row["entry_ack_us"] == 122250000 and row["exit_us"] == 153250000
    assert row["quantity"] == pytest.approx(2.)
    expected = 2 * (100.100 - 100.003) - 2 * (100.100 + 100.003) * .0007
    assert row["pnl"] == pytest.approx(expected)
    assert row["closed_quantity"] == row["quantity"]


def test_known_fok_rejection_is_flat_and_unknown_submitted_entry_is_not_zero():
    frame = book()
    price_columns = [name for name in frame if name.endswith(".price")]
    frame.loc[2, price_columns] += 1.
    result = run(frame)
    assert result["complete"] and result["attempts"][0]["status"] == "rejected_fok"
    unknown = run(book().drop(index=2))
    assert not unknown["complete"] and unknown["net_dollars"] is None
    assert unknown["attempts"][0]["status"] == "unresolved_entry"


def test_unknown_exit_preserves_inventory_and_invalidates_day():
    result = run(book().drop(index=3))
    row = result["attempts"][0]
    assert not result["complete"] and result["net_dollars"] is None
    assert row["status"] == "unresolved_exit" and row["open_quantity"] == 2.


def test_recovery_cooldown_preserves_earlier_signals_and_excludes_only_known_warmup():
    start = pd.Timestamp("2024-07-01", tz="UTC").value // 1000
    frame = pd.DataFrame({"date": ["2024-07-01"] * 6,
                          "local_timestamp": [start + t for t in (299999999, 300000000, 599999999, 600000000, 899999999, 900000000)]})
    recovery = [{"recovery_local_timestamp": start + 600000000,
                 "warmup_end_local_timestamp": start + 900000000}]
    assert (available_reports(frame, recovery).local_timestamp - start).tolist() == [300000000, 599999999, 900000000]
