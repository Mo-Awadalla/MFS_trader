"""No substitution of anchor depth, unknown volume or post-signal evidence."""

import numpy as np

from research.equity_burst_resilience import (
    completed_bursts,
    events_from_seeds,
    prove_seed,
    seed_windows,
)
from research.equity_resilience import arrays

BASE = 100_000_000_000
DTYPE = [("ts_recv", "u8"), ("ts_event", "u8"), ("action", "S1"), ("side", "S1"),
         ("price", "i8"), ("size", "u4"), ("flags", "u1"), ("bid_px_00", "i8"),
         ("ask_px_00", "i8"), ("bid_sz_00", "u4"), ("ask_sz_00", "u4")]


def raw_fixture(buy=False):
    rows = [(BASE + t, BASE + t - 1_000_000, b"A", b"B", 100_000_000_000, 100, 128,
             100_000_000_000, 100_010_000_000, 100, 100) for t in range(0, 5_100_000_000, 100_000_000)]
    r = BASE + 3_150_000_000
    rows += [(r, r - 1_000_000, b"T", b"B" if buy else b"A", 100_010_000_000 if buy else 100_000_000_000,
              300, flag, 100_000_000_000, 100_010_000_000, 100, 100) for flag in (0, 128)]
    return np.array(sorted(rows, key=lambda r: r[0]), dtype=DTYPE)


def one(raw):
    prepared = arrays(raw)
    groups, _ = completed_bursts(raw, prepared)
    assert len(groups) == 1
    return prepared, groups[0]


def test_completed_fragments_form_one_observed_burst():
    prepared, burst = one(raw_fixture())
    assert burst["burst_quantity"] == 600 and burst["burst_trade_records"] == 2
    row, reason = prove_seed(prepared, burst, BASE + 4_000_000_000)
    assert reason is None and row["total_volume"] == 600


def test_different_clocks_or_unknown_side_cannot_be_combined():
    for field, value in (("ts_event", BASE + 3_148_000_000), ("side", b"N")):
        raw = raw_fixture()
        raw[field][np.flatnonzero(raw["action"] == b"T")[0]] = value
        assert not completed_bursts(raw, arrays(raw))[0]


def test_immediate_preburst_depth_cannot_be_replaced_by_smaller_anchor():
    raw = raw_fixture()
    raw["bid_sz_00"][raw["ts_recv"] == BASE + 3_100_000_000] = 200
    assert not completed_bursts(raw, arrays(raw))[0]


def test_requires_postburst_quarter_second_on_both_clocks():
    prepared, burst = one(raw_fixture())
    assert prove_seed(prepared, burst, BASE + 3_600_000_000)[0] is None
    assert prove_seed(prepared, burst, BASE + 4_000_000_000)[0] is not None
    prepared[1][-1] = 0  # Future evidence is irrelevant to the earlier signal.
    assert prove_seed(prepared, burst, BASE + 4_000_000_000)[0] is not None


def test_temporary_price_failure_or_invalid_state_rejects_seed():
    for field, value in (("bid_px_00", 99_990_000_000), ("flags", 132)):
        raw = raw_fixture()
        raw[field][raw["ts_recv"] == BASE + 2_500_000_000] = value
        prepared, burst = one(raw)
        assert prove_seed(prepared, burst, BASE + 4_000_000_000)[0] is None


def test_unknown_side_size_remains_in_total_volume():
    raw = raw_fixture()
    extra = np.array([(BASE + 3_250_000_000, BASE + 3_249_000_000, b"T", b"N", 100_000_000_000,
                       200, 128, 100_000_000_000, 100_010_000_000, 100, 100)], dtype=DTYPE)
    raw = np.sort(np.r_[raw, extra], order="ts_recv", kind="stable")
    prepared, burst = one(raw)
    row, reason = prove_seed(prepared, burst, BASE + 4_000_000_000)
    assert row is None and reason == "burst_not_dominant_in_full_window"


def test_prestate_at_same_capture_clock_is_ambiguous():
    raw = raw_fixture()
    mask = raw["ts_recv"] == BASE + 3_100_000_000
    raw["ts_recv"][mask] = BASE + 3_150_000_000
    assert not completed_bursts(raw, arrays(raw))[0]


def test_ask_seed_does_not_enter_until_later_causal_break():
    raw = raw_fixture(buy=True)
    prepared, burst = one(raw)
    grids = np.array([BASE + 4_000_000_000, BASE + 4_500_000_000])
    seeds, _ = seed_windows(prepared, [burst], grids[:1])
    assert len(seeds) == 1 and not events_from_seeds(prepared, seeds, grids)
    raw["ask_px_00"][raw["ts_recv"] >= BASE + 4_100_000_000] += 10_000_000
    prepared = arrays(raw)
    rows = events_from_seeds(prepared, seeds, grids)
    assert len(rows) == 1 and rows[0]["decision_ns"] == BASE + 4_500_000_000
