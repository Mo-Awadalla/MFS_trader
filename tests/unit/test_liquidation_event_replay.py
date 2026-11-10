import numpy as np
import pandas as pd
import pytest

from research.liquidation_event_replay import (
    events_for_day,
    extract_quotes,
    quote_targets,
    simulate,
    sweep,
)


def snapshot(bid=30000., ask=30000.1, quantity=1.):
    row = {"quote_age_us": 1, "source_delay_us": 1000}
    for level in range(5):
        row.update({f"bids[{level}].price": bid - .1 * level, f"asks[{level}].price": ask + .1 * level,
                    f"bids[{level}].amount": quantity, f"asks[{level}].amount": quantity})
    return row


def test_five_level_fills_use_weighted_price():
    row = snapshot(100., 100.1, .1)
    assert sweep(row, 1, .25, 100.5)["price"] == pytest.approx(100.18)
    assert sweep(row, -1, .25, 99.5)["price"] == pytest.approx(99.92)


def test_fok_rejects_known_outside_limit_but_does_not_invent_sixth_level():
    row = snapshot(100., 100.1, .1)
    assert sweep(row, 1, .25, 100.2)["status"] == "rejected_fok"
    assert sweep(row, 1, 1., 105.)["status"] == "unknown_deeper_liquidity"
    row["quote_age_us"] = 1000001
    assert sweep(row, 1, .01, 105.)["status"] == "unknown_snapshot"


def test_event_refractory_uses_first_report_and_quiet_wait_is_causal():
    start = pd.Timestamp("2024-01-01", tz="UTC").value // 1000
    data = pd.DataFrame({"local_timestamp": start + np.array([120, 121, 150, 500]) * 1_000_000,
                         "price": [100.] * 4, "amount": [1000., 1., 2000., 1000.],
                         "side": ["sell", "sell", "buy", "buy"]})
    events = events_for_day(data, "2024-01-01", 100000)
    assert events.event_id.tolist() == [0, 3]
    assert events.quiet_2s.tolist() == [False, True]
    assert events.forced_side.tolist() == [-1, 1]


def test_capture_asof_excludes_equal_time_and_keeps_latest_invalid_state(tmp_path):
    day = "2024-01-01"
    start = pd.Timestamp(day, tz="UTC").value // 1000
    rows = []
    for stamp, bid, ask in [(100, 100., 100.1), (200, 101., 101.1), (300, 200., 101.1)]:
        rows.append({**snapshot(bid, ask), "timestamp": start + stamp - 1, "local_timestamp": start + stamp})
    path = tmp_path / "book.csv.gz"
    pd.DataFrame(rows).to_csv(path, index=False, compression="gzip")
    targets = pd.DataFrame({"target_us": [200, 201, 301]})
    result, _ = extract_quotes(path, day, targets)
    assert result["bids[0].price"].tolist() == [100., 101., 200.]
    assert sweep(result.iloc[-1], 1, .01)["status"] == "unknown_snapshot"


def panel():
    events = pd.DataFrame([{"date": "synthetic", "event_id": 0, "received_us": 120_000_000,
                            "reported_notional": 100000., "forced_side": 1, "quiet_2s": True}])
    targets = quote_targets(events)
    rows = []
    for target in targets.to_dict("records"):
        state = snapshot(30050., 30050.1) if target["label"].startswith("exit") else snapshot()
        rows.append({**target, **state})
    return pd.DataFrame(rows)


def test_event_replay_pays_both_taker_fees_and_slippage():
    trades, daily = simulate(panel(), "follow", "immediate", 30)
    t = trades.iloc[0]
    assert daily.complete.all()
    assert t.quantity == pytest.approx(.033)
    assert t.pnl == pytest.approx(.033 * (30050 - 30000.1) - .033 * (30050 + 30000.1) * .0006)


def test_missing_submitted_order_snapshot_blocks_result():
    p = panel()
    p.loc[p.label.eq("entry_1000"), "quote_age_us"] = 2_000_000
    trades, daily = simulate(p, "follow", "immediate", 30)
    assert not daily.complete.all()
    assert trades.iloc[0].status == "unresolved_entry"
