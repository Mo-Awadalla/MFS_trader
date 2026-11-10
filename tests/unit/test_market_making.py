from __future__ import annotations

from research.market_making import passive_markout_bps, touch_fill_side


def test_touch_fill_requires_aggressor_to_reach_quote() -> None:
    assert touch_fill_side(99.0, True, 99.0, 101.0) == 1
    assert touch_fill_side(101.0, False, 99.0, 101.0) == -1
    assert touch_fill_side(100.0, True, 99.0, 101.0) == 0


def test_passive_markout_has_correct_side_sign() -> None:
    assert passive_markout_bps(99.0, 100.0, 1) > 0
    assert passive_markout_bps(101.0, 100.0, -1) > 0
    assert passive_markout_bps(99.0, 98.0, 1) < 0
