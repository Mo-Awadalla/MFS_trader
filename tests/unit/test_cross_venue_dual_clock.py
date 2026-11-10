import pandas as pd
import pytest

from research.cross_venue_dual_clock import extract_dual_clock, physical_fill


def state(exchange, local, bid):
    start = pd.Timestamp("2024-07-01", tz="UTC").value // 1000
    row = {"timestamp": start + exchange, "local_timestamp": start + local}
    for level in range(5):
        row.update({f"bids[{level}].price": bid - level * .1,
                    f"asks[{level}].price": bid + .1 + level * .1,
                    f"bids[{level}].amount": 1., f"asks[{level}].amount": 1.})
    return row


def test_late_capture_changes_execution_without_leaking_into_signal(tmp_path):
    path = tmp_path / "book.csv.gz"
    pd.DataFrame([state(900_000, 1_000_000, 100.), state(1_900_000, 4_000_000, 110.)]).to_csv(path, index=False)
    targets = pd.DataFrame({"label": ["signal", "entry"], "target_us": [2_000_000, 2_000_000]})
    q, audit = extract_dual_clock(path, "2024-07-01", targets)
    assert q["bids[0].price"].tolist() == [100., 110.]
    assert audit["signals_captured_after_target"] == 0
    assert audit["execution_snapshots_captured_after_target"] == 1
    assert q.iloc[1].source_delay_us == 2_100_000
    assert physical_fill(q.iloc[1], 1, .1, 100.2)["status"] == "rejected_fok"
    assert physical_fill(q.iloc[1], 1, .1, 110.2)["price"] == pytest.approx(110.1)


def test_exchange_backtrack_is_flagged_locally_instead_of_hidden_by_sort(tmp_path):
    path = tmp_path / "book.csv.gz"
    rows = [state(1_000_000, 1_010_000, 100.), state(2_000_000, 2_010_000, 110.),
            state(1_800_000, 2_020_000, 105.), state(3_000_000, 3_010_000, 120.)]
    pd.DataFrame(rows).to_csv(path, index=False)
    targets = pd.DataFrame({"label": ["entry", "entry"], "target_us": [1_900_000, 3_000_001]})
    q, audit = extract_dual_clock(path, "2024-07-01", targets)
    assert audit["exchange_backtracks"] == 1
    assert q.exchange_clock_ambiguous.tolist() == [True, False]
    assert physical_fill(q.iloc[0], 1, .1)["status"] == "unknown_exchange_clock"
    assert physical_fill(q.iloc[1], 1, .1)["price"] == pytest.approx(120.1)


def test_exchange_asof_excludes_equal_timestamps_and_retains_invalid_latest(tmp_path):
    path = tmp_path / "book.csv.gz"
    rows = [state(1_000_000, 1_010_000, 100.), state(2_000_000, 2_010_000, 110.)]
    rows[-1]["asks[0].price"] = 90.
    pd.DataFrame(rows).to_csv(path, index=False)
    targets = pd.DataFrame({"label": ["entry", "entry"], "target_us": [2_000_000, 2_000_001]})
    q, _ = extract_dual_clock(path, "2024-07-01", targets)
    assert q["bids[0].price"].tolist() == [100., 110.]
    assert physical_fill(q.iloc[-1], 1, .1)["status"] == "unknown_snapshot"
