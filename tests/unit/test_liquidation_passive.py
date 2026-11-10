import numpy as np
import pandas as pd
import pytest

from research.liquidation_passive import SCENARIOS, EventBook, entry_fills, replay, window_mask


def raw_book():
    rows = []
    for clock, bid in [(119_999_999, 10000.), (121_249_999, 10000.), (158_249_999, 10010.)]:
        row = {"exchange_us": clock, "local_us": clock}
        for level in range(5):
            row.update({f"bids[{level}].price": bid - level * .1, f"asks[{level}].price": bid + .1 + level * .1,
                        f"bids[{level}].amount": 2., f"asks[{level}].amount": 2.})
        rows.append(row)
    return pd.DataFrame(rows)


def tape(times, amounts, prices=None):
    return {"exchange_us": np.array(times), "id": np.arange(len(times)), "price": np.array(prices or [9990.] * len(times)),
            "sell": np.ones(len(times), dtype=bool), "amount": np.array(amounts)}


def events():
    return pd.DataFrame([{"date": "2024-07-01", "event_id": 0, "received_us": 120_000_000,
                          "forced_side": 1, "quiet_2s": True, "reported_notional": 100000.}])


def test_strict_through_volume_excludes_boundaries_touch_and_wrong_aggressor():
    trades = tape([100, 101, 102, 103, 104, 105], [.2] * 6, [99., 100., 99., 99., 99., 99.])
    trades["sell"][3] = False
    fills = entry_fills(trades, 100, 105, 1, 100., 1., "through_partial")
    assert [f["source_id"] for f in fills] == [2, 4]
    assert sum(f["quantity"] for f in fills) == pytest.approx(.4)
    touch = entry_fills(trades, 100, 105, 1, 100., 1., "touch_partial")
    assert sum(f["quantity"] for f in touch) == pytest.approx(.6)


def test_partial_inventory_survives_cancel_ack_and_pays_actual_fill_costs():
    trades = tape([122_000_000, 126_249_999], [.02, .03])
    result = replay("2024-07-01", EventBook(raw_book()), trades, events(), "follow", 8, 30, SCENARIOS["base"])
    trade = result["attempts"][0]
    assert result["complete"] and trade["status"] == "priced"
    assert trade["quantity"] == pytest.approx(.05) and trade["partial_entry"]
    assert trade["cancel_arrival_us"] == 126_250_000
    assert trade["cancel_ack_us"] == 127_250_000
    assert trade["exit_send_us"] == 157_250_000
    assert trade["exit_us"] == 158_250_000
    assert trade["closed_quantity"] == pytest.approx(.05)
    assert trade["pnl"] == pytest.approx(.05 * (10010 - 9992) - .05 * 9992 * .0003 - .05 * 10010 * .0007)


def test_unknown_submitted_book_is_not_converted_to_no_fill():
    frame = raw_book()
    frame = frame.drop(index=1)
    result = replay("2024-07-01", EventBook(frame), tape([], []), events(), "follow", 8, 30, SCENARIOS["base"])
    assert not result["complete"]
    assert result["attempts"][0]["status"] == "unresolved_post_only"
    assert result["net_dollars"] is None


def test_unknown_exit_preserves_open_partial_inventory():
    frame = raw_book()
    frame.loc[2, ["exchange_us", "local_us"]] -= 1_000_000
    trades = tape([122_000_000], [.02])
    result = replay("2024-07-01", EventBook(frame), trades, events(), "follow", 8, 30, SCENARIOS["base"])
    assert not result["complete"]
    assert result["attempts"][0]["status"] == "unresolved_exit"
    assert result["attempts"][0]["open_quantity"] == pytest.approx(.02)


def test_full_first_print_is_explicit_sensitivity_and_not_partial_baseline():
    trades = tape([122_000_000], [.02])
    baseline = replay("2024-07-01", EventBook(raw_book()), trades, events(), "follow", 8, 30, SCENARIOS["base"])
    stress = replay("2024-07-01", EventBook(raw_book()), trades, events(), "follow", 8, 30, SCENARIOS["first_through_full"])
    assert baseline["attempts"][0]["quantity"] == pytest.approx(.02)
    assert stress["attempts"][0]["quantity"] == pytest.approx(.1)


def test_event_windows_do_not_depend_on_future_returns_or_order_fill():
    times = np.array([84_999_999, 85_000_000, 120_000_000, 290_000_000, 290_000_001])
    assert window_mask(times, np.array([120_000_000])).tolist() == [False, True, True, True, False]


def test_explicit_instrument_grid_preserves_dollars_and_native_quantity():
    frame = raw_book()
    for column in frame.columns:
        if column.endswith(".price"):
            frame[column] /= 100
        elif column.endswith(".amount"):
            frame[column] *= 100
    trades = tape([122_000_000], [2.], [99.90])
    result = replay("2024-07-01", EventBook(frame), trades, events(), "follow", 8, 30, SCENARIOS["base"],
                    tick_size=.001, quantity_step=.1)
    trade = result["attempts"][0]
    assert result["complete"]
    assert trade["quantity"] == pytest.approx(2.)
    assert trade["intended_quantity"] == pytest.approx(10.)
    assert trade["entry"] == pytest.approx(99.92)
    assert trade["pnl"] == pytest.approx(2 * (100.10 - 99.92) - 2 * 99.92 * .0003 - 2 * 100.10 * .0007)
