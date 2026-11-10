"""Exact cost hurdle and capture-clock atomicity before passive supply screening."""

from decimal import Decimal

import numpy as np
import pytest

from research.nasdaq_spread_supply import CASH_SCALE, budget_units, size_at_quote, snapshot_indices


@pytest.mark.parametrize("quantity", [1, 200, 1000])
def test_integer_cash_matches_independent_decimal_identity(quantity):
    bid, ask = 177030000000, 177150000000
    entry = Decimal(quantity) * Decimal("177.03")
    sale = Decimal(quantity) * Decimal("177.15")
    expected = sale - entry - 2 * max(Decimal(1), Decimal("0.005") * quantity)
    expected -= Decimal("0.0001") * (entry + sale) + Decimal("0.00003") * sale + Decimal("0.000166") * quantity
    assert Decimal(int(budget_units(bid, ask, quantity))) / CASH_SCALE == expected


def test_snapshot_uses_last_row_of_prior_capture_and_excludes_equal_cutoff():
    base = 1758029400000000000
    receive = np.array([base - 2, base - 1, base - 1, base], dtype=np.int64)
    result = snapshot_indices(receive, np.array([base + 1000000], dtype=np.int64))
    assert result.tolist() == [2]


def test_quantity_uses_both_current_touches_and_rounded_up_collar():
    assert size_at_quote(1000, 20, 177030000000) == 2
    assert size_at_quote(10000, 10000, 177030000000) == 55
