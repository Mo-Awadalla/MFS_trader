"""Completed price-level sweep identity and strictly fixed admission time."""

import numpy as np

from research.equity_resilience import arrays
from research.equity_sweep import admit, sweep_groups

BASE = 100_000_000_000
DTYPE = [("ts_recv", "u8"), ("ts_event", "u8"), ("action", "S1"), ("side", "S1"),
         ("price", "i8"), ("size", "u4"), ("flags", "u1"), ("bid_px_00", "i8"),
         ("ask_px_00", "i8"), ("bid_sz_00", "u4"), ("ask_sz_00", "u4")]


def sample(sell=False):
    rows = [(BASE + t, BASE + t - 1_000_000, b"A", b"B", 100_000_000_000, 100, 128,
             100_000_000_000, 100_010_000_000, 100, 100) for t in range(0, 8_100_000_000, 100_000_000)]
    r = BASE + 5_150_000_000
    prices = [100_000_000_000, 99_990_000_000] if sell else [100_010_000_000, 100_020_000_000]
    rows.extend((r, r - 1_000_000, b"T", b"A" if sell else b"B", p, 1000, f,
                 100_000_000_000, 100_010_000_000, 100, 100) for p, f in zip(prices, (0, 128), strict=True))
    raw = np.array(sorted(rows, key=lambda x: x[0]), dtype=DTYPE)
    mask = raw["ts_recv"] >= BASE + 5_400_000_000
    raw["bid_px_00"][mask] += -20_000_000 if sell else 20_000_000
    raw["ask_px_00"][mask] += -20_000_000 if sell else 20_000_000
    return raw


def accepted(raw):
    prepared = arrays(raw)
    groups, _, _ = sweep_groups(raw, prepared)
    assert len(groups) == 1
    return prepared, groups[0]


def test_fixed_first_grid_and_both_long_only_mechanisms():
    for sell, name in ((False, "buy_sweep_continuation_long"), (True, "sell_sweep_reversal_long")):
        prepared, group = accepted(sample(sell))
        event, reason = admit(prepared, group, BASE)
        assert reason is None and event["decision_ns"] == BASE + 5_700_000_000
        assert event["rule"] == name


def test_different_native_clocks_are_not_merged():
    raw = sample()
    raw["ts_event"][np.flatnonzero(raw["action"] == b"T")[0]] -= 1
    assert not sweep_groups(raw, arrays(raw))[0]


def test_monotonic_distinct_prices_and_known_direction_required():
    for field, value in (("price", 100_030_000_000), ("side", b"N")):
        raw = sample()
        raw[field][np.flatnonzero(raw["action"] == b"T")[0]] = value
        assert not sweep_groups(raw, arrays(raw))[0]


def test_burst_must_clear_exact_notional_and_immediate_size_gates():
    raw = sample()
    raw["size"][raw["action"] == b"T"] = 100
    assert not sweep_groups(raw, arrays(raw))[0]
    raw = sample()
    raw["ask_sz_00"][raw["ts_recv"] == BASE + 5_100_000_000] = 3000
    assert not sweep_groups(raw, arrays(raw))[0]


def test_no_resampling_after_invalid_first_signal():
    raw = sample()
    raw["bid_px_00"][raw["ts_recv"] == BASE + 5_400_000_000] = 0
    prepared, group = accepted(raw)
    event, reason = admit(prepared, group, BASE)
    assert event is None and reason == "invalid_latest_signal_quote"


def test_signal_cannot_claim_postburst_survival_from_future_quote():
    raw = sample()
    raw = raw[raw["ts_recv"] != BASE + 5_400_000_000]
    prepared, group = accepted(raw)
    event, reason = admit(prepared, group, BASE)
    assert event is None and reason == "missing_postburst_quarter_second"


def test_only_one_side_displaced_is_not_an_admission():
    raw = sample()
    mask = raw["ts_recv"] >= BASE + 5_400_000_000
    raw["bid_px_00"][mask] = 100_005_000_000
    raw["ask_px_00"][mask] = 100_010_000_000
    prepared, group = accepted(raw)
    assert admit(prepared, group, BASE)[1] == "both_sides_not_displaced"


def test_locked_completion_cannot_replace_valid_later_signal():
    raw = sample()
    raw["bid_px_00"][raw["action"] == b"T"] = raw["ask_px_00"][raw["action"] == b"T"]
    prepared, group = accepted(raw)
    assert admit(prepared, group, BASE)[0] is not None
