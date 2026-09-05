from __future__ import annotations

import pandas as pd

from validation.mc.engine import cluster_bootstrap_returns, run_monte_carlo


def test_cluster_bootstrap_keeps_same_settlement_symbols_adjacent() -> None:
    index = pd.Index(["a-btc", "a-eth", "b-btc", "b-eth"])
    returns = pd.Series([1.0, 2.0, 10.0, 20.0], index=index)
    labels = pd.Series(["a", "a", "b", "b"], index=index)
    paths = cluster_bootstrap_returns(returns, labels, num_paths=20, seed=7)
    for path in paths:
        assert tuple(path[:2]) in {(1.0, 2.0), (10.0, 20.0)}
        assert tuple(path[2:]) in {(1.0, 2.0), (10.0, 20.0)}


def test_event_monte_carlo_accepts_realized_events_per_year() -> None:
    index = pd.Index([f"event-{i}" for i in range(6)])
    returns = pd.Series([0.01, -0.005, 0.02, -0.002, 0.01, 0.003], index=index)
    labels = pd.Series([f"settlement-{i // 2}" for i in range(6)], index=index)
    result = run_monte_carlo(returns, num_paths=20, cluster_labels=labels,
                             annualization_factor=1095.0, seed=42)
    assert result.num_paths == 20
