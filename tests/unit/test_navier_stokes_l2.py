from __future__ import annotations

import numpy as np

from research.navier_stokes_l2 import L2Book


def _book() -> L2Book:
    book = L2Book()
    for side, prices in (("bid", [99.99, 99.98, 99.97]), ("ask", [100.01, 100.02, 100.03])):
        for price in prices:
            book.apply(
                side=side,
                price=price,
                amount=10.0,
                is_snapshot=True,
                timestamp_us=0,
                bin_start_us=0,
                bin_seconds=10,
            )
    return book


def test_absolute_updates_and_zero_remove_levels() -> None:
    book = _book()
    book.apply(
        side="bid", price=99.99, amount=15.0, is_snapshot=False,
        timestamp_us=1_000_000, bin_start_us=0, bin_seconds=10,
    )
    book.apply(
        side="ask", price=100.01, amount=0.0, is_snapshot=False,
        timestamp_us=2_000_000, bin_start_us=0, bin_seconds=10,
    )
    assert book.bids[99.99] == 15.0
    assert 100.01 not in book.asks
    assert book.additions == 5.0
    assert book.removals == 10.0


def test_feature_snapshot_is_finite_and_window_reset_preserves_book() -> None:
    book = _book()
    book.apply(
        side="bid", price=99.99, amount=12.0, is_snapshot=False,
        timestamp_us=1_000_000, bin_start_us=0, bin_seconds=10,
    )
    features = book.features(levels=3, bin_seconds=10)
    assert features["midpoint"] == 100.0
    assert all(np.isfinite(value) for value in features.values())
    book.reset_window()
    assert book.event_count == 0
    assert book.bids[99.99] == 12.0
