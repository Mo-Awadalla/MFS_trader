"""Causal passive-spread feasibility only; no future fills or strategy returns."""

import numpy as np

CENT = 10000000
USD = 1000000000
CASH_SCALE = 100000000000000


def snapshot_indices(receive_ns, decisions_ns):
    """Last record at a capture clock strictly before the one-ms information cutoff."""
    times = np.asarray(receive_ns, dtype=np.int64)
    decisions = np.asarray(decisions_ns, dtype=np.int64)
    return np.searchsorted(times, decisions - np.int64(1000000), side="left") - 1


def size_at_quote(bid_size, ask_size, ask_price):
    collar = ((ask_price // CENT * 102 + 99) // 100) * CENT
    return np.minimum(np.minimum(bid_size // 10, ask_size // 10), 10000 * USD // collar)


def budget_units(bid, ask, quantity):
    """Exact cash in 1e-14 USD: buy bid, sell ask, two fees, adverse costs and sales levy."""
    commission = np.maximum(CASH_SCALE, 500000000000 * quantity)
    return quantity * ((ask - bid) * 100000 - 10 * (bid + ask) - 3 * ask - 16600000000) - 2 * commission


def profitable_budget(bid, ask, quantity):
    return budget_units(bid, ask, quantity) >= 20 * quantity * bid
