"""Tests for Pairs v1 discovery and spread diagnostics."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies.pairs.discovery import (
    PairCandidate,
    PairsParams,
    compute_spread,
    discover_pair_relationships,
    fit_pair_relationship,
    generate_pair_candidates,
    rolling_zscore,
    select_candidate_symbols,
)


def _pairs_panel(n_days: int = 280, n_symbols: int = 8) -> pd.DataFrame:
    idx = pd.bdate_range("2023-01-03", periods=n_days, tz="UTC")
    symbols = tuple(f"S{i:03d}" for i in range(n_symbols))
    columns = pd.MultiIndex.from_product(
        [symbols, ("open", "high", "low", "close", "volume")],
        names=["symbol", "field"],
    )
    df = pd.DataFrame(index=idx, columns=columns, dtype=float)

    rng = np.random.default_rng(42)
    log_base = np.log(50.0) + np.cumsum(rng.normal(0.0, 0.01, n_days))
    base_trend = np.exp(log_base)
    for i, symbol in enumerate(symbols):
        if symbol == "S000":
            close = base_trend
        elif symbol == "S001":
            close = np.exp(log_base + 0.04 + rng.normal(0.0, 0.002, n_days))
        else:
            close = 20.0 + i + np.cumsum(np.sin(np.arange(n_days) / (7.0 + i)) * 0.08 + 0.03 * i)
        volume = np.full(n_days, 20_000_000.0 - i * 2_000_000.0)
        df[(symbol, "open")] = close
        df[(symbol, "high")] = close * 1.01
        df[(symbol, "low")] = close * 0.99
        df[(symbol, "close")] = close
        df[(symbol, "volume")] = volume
    return df


def test_select_candidate_symbols_uses_top_median_dollar_volume() -> None:
    df = _pairs_panel(n_symbols=8)
    params = PairsParams(candidate_pool_size=3, formation_window_days=252, min_eligible_universe=3)

    symbols = select_candidate_symbols(df, params)

    formation = df.tail(params.formation_window_days)
    close = formation.xs("close", axis=1, level=1)
    volume = formation.xs("volume", axis=1, level=1)
    expected = tuple(
        (close * volume)
        .tail(params.liquidity_lookback_days)
        .median()
        .sort_values(ascending=False)
        .head(3)
        .index
    )
    assert symbols == expected


def test_generate_pair_candidates_all_vs_all_without_sector_data() -> None:
    df = _pairs_panel(n_symbols=4)
    params = PairsParams(candidate_pool_size=4, formation_window_days=252, min_eligible_universe=4)

    candidates = generate_pair_candidates(df, params)

    assert len(candidates) == 6
    assert (candidates[0].y_symbol, candidates[0].x_symbol) == ("S000", "S001")
    assert {candidate.sector for candidate in candidates} == {None}


def test_generate_pair_candidates_can_filter_same_sector_when_available() -> None:
    df = _pairs_panel(n_symbols=4)
    params = PairsParams(candidate_pool_size=4, formation_window_days=252, min_eligible_universe=4)
    sectors = {"S000": "tech", "S001": "tech", "S002": "bank", "S003": "bank"}

    candidates = generate_pair_candidates(df, params, sectors=sectors)

    assert [(candidate.y_symbol, candidate.x_symbol, candidate.sector) for candidate in candidates] == [
        ("S000", "S001", "tech"),
        ("S002", "S003", "bank"),
    ]


def test_fit_pair_relationship_selects_cointegrated_pair() -> None:
    df = _pairs_panel(n_symbols=4)
    params = PairsParams(formation_window_days=252, min_eligible_universe=2)
    candidate = PairCandidate(
        y_symbol="S000",
        x_symbol="S001",
        y_median_dollar_volume=1.0,
        x_median_dollar_volume=1.0,
    )

    relationship = fit_pair_relationship(df.tail(252), candidate, params)

    assert relationship is not None
    assert relationship.y_symbol == "S000"
    assert relationship.x_symbol == "S001"
    assert relationship.cointegration_pvalue <= params.coint_pvalue_threshold
    assert relationship.diagnostics.observations == 252
    assert relationship.diagnostics.spread_std > 0


def test_discover_pair_relationships_returns_deterministic_top_pairs() -> None:
    df = _pairs_panel(n_symbols=5)
    params = PairsParams(
        candidate_pool_size=5,
        formation_window_days=252,
        max_active_pairs=3,
        min_eligible_universe=5,
    )

    first = discover_pair_relationships(df, params)
    second = discover_pair_relationships(df, params)

    assert first == second
    assert len(first) <= 3
    assert ("S000", "S001") in [relationship.symbols for relationship in first]


def test_compute_spread_and_rolling_zscore() -> None:
    idx = pd.bdate_range("2024-01-01", periods=30, tz="UTC")
    x = pd.Series(np.linspace(1.0, 2.0, len(idx)), index=idx)
    y = 2.0 * x + 0.5

    spread = compute_spread(y, x, beta=2.0, intercept=0.5)
    zscore = rolling_zscore(spread, window=20)

    assert spread.abs().max() == pytest.approx(0.0)
    assert zscore.dropna().fillna(0.0).abs().max() == pytest.approx(0.0)
