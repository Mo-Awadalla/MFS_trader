"""Tests for Candidate C12 DispersionGated TSMOM."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.candidate_registry import REGISTRY
from research.etf_tsmom_c12 import (
    CASH_PROXY,
    RISK_ASSETS,
    VARIANTS,
    c12_weekly_signal,
    dispersion_threshold,
    weekly_dispersion,
)

V1 = VARIANTS["C12_v1_hard_cash"]
V2 = VARIANTS["C12_v2_soft_shrink"]
V3 = VARIANTS["C12_v3_8w_hard_cash"]


def _prices(days: int = 700, seed: int = 7, high_dispersion_after: int | None = 380) -> pd.DataFrame:
    """Trending panel: low cross-sectional dispersion early, high later."""
    idx = pd.bdate_range("2021-01-04", periods=days, tz="UTC")
    rng = np.random.default_rng(seed)
    data = {}
    common = rng.normal(0.0004, 0.004, size=days)
    for i, symbol in enumerate(RISK_ASSETS):
        idio_scale = np.full(days, 0.001)
        if high_dispersion_after is not None:
            idio_scale[high_dispersion_after:] = 0.03
        returns = 0.0004 + i * 0.00003 + common + rng.normal(0.0, 1.0, size=days) * idio_scale
        data[symbol] = 100.0 * np.cumprod(1.0 + returns)
    data[CASH_PROXY] = 100.0 * (1.0 + 0.00003) ** np.arange(days)
    return pd.DataFrame(data, index=idx)


def test_no_lookahead_in_threshold_calculation() -> None:
    prices = _prices()
    diag = weekly_dispersion(prices, V1)
    threshold, train_end = dispersion_threshold(diag["smoothed_dispersion"], V1)

    modified = prices.copy()
    modified.loc[modified.index > train_end, list(RISK_ASSETS)] *= np.linspace(
        1.0, 5.0, int((modified.index > train_end).sum())
    )[:, None]
    diag_mod = weekly_dispersion(modified, V1)
    threshold_mod, train_end_mod = dispersion_threshold(diag_mod["smoothed_dispersion"], V1)

    assert threshold == threshold_mod
    assert train_end == train_end_mod


def test_gate_uses_only_information_available_at_rebalance_date() -> None:
    prices = _prices()
    positions, diag = c12_weekly_signal(prices, V1)
    target_week = diag.index[80]
    assert not bool(diag.loc[target_week, "in_train"])

    modified = prices.copy()
    on_or_after = modified.index.normalize() >= target_week.normalize()
    modified.loc[on_or_after, "SPY"] *= 3.0
    positions_mod, diag_mod = c12_weekly_signal(modified, V1)

    assert bool(diag.loc[target_week, "gate_active"]) == bool(diag_mod.loc[target_week, "gate_active"])
    pd.testing.assert_series_equal(positions.loc[target_week], positions_mod.loc[target_week])


def test_gate_active_forces_cash_for_hard_variant() -> None:
    prices = _prices()
    positions, diag = c12_weekly_signal(prices, V1)
    gated = positions.loc[diag["gate_active"]]
    assert not gated.empty, "synthetic regime shift should trigger the gate"
    np.testing.assert_allclose(gated.loc[:, list(RISK_ASSETS)].to_numpy(), 0.0)
    np.testing.assert_allclose(gated[CASH_PROXY].to_numpy(), 1.0)


def test_gate_active_halves_exposure_for_soft_variant() -> None:
    prices = _prices()
    positions_soft, diag = c12_weekly_signal(prices, V2)
    positions_base, _ = c12_weekly_signal(prices, V2, gate_enabled=False)
    gated_weeks = diag.index[diag["gate_active"]]
    assert len(gated_weeks) > 0
    for ts in gated_weeks:
        base_risk = positions_base.loc[ts, list(RISK_ASSETS)]
        soft_risk = positions_soft.loc[ts, list(RISK_ASSETS)]
        np.testing.assert_allclose(soft_risk.to_numpy(), base_risk.to_numpy() * 0.5)
        np.testing.assert_allclose(float(positions_soft.loc[ts].sum()), 1.0)


def test_baseline_unchanged_when_gate_disabled() -> None:
    prices = _prices()
    base_v1, diag_v1 = c12_weekly_signal(prices, V1, gate_enabled=False)
    base_v3, _ = c12_weekly_signal(prices, V3, gate_enabled=False)
    gated_v1, _ = c12_weekly_signal(prices, V1)

    # Gate-disabled output identical across variants (gate params inert).
    pd.testing.assert_frame_equal(base_v1, base_v3)
    assert not diag_v1["gate_active"].any()
    # Ungated weeks match the baseline exactly.
    _, diag_gated = c12_weekly_signal(prices, V1)
    ungated_weeks = diag_gated.index[~diag_gated["gate_active"]]
    pd.testing.assert_frame_equal(gated_v1.loc[ungated_weeks], base_v1.loc[ungated_weeks])


def test_candidate_configs_are_reproducible() -> None:
    # Registry parameters are frozen and match the implementation's variants.
    for variant_id, params in VARIANTS.items():
        spec = REGISTRY[variant_id]
        assert spec.family == "C12_DispersionGated_TSMOM"
        assert spec.parameters["rolling_dispersion_window_weeks"] == params.rolling_dispersion_window_weeks
        assert spec.parameters["threshold_quantile"] == params.threshold_quantile
        assert spec.parameters["threshold_train_weeks"] == params.threshold_train_weeks
        assert spec.parameters["gate_action"] == params.gate_action
    assert set(VARIANTS) == {"C12_v1_hard_cash", "C12_v2_soft_shrink", "C12_v3_8w_hard_cash"}

    # Same inputs produce identical outputs.
    prices = _prices()
    positions_a, diag_a = c12_weekly_signal(prices, V1)
    positions_b, diag_b = c12_weekly_signal(prices, V1)
    pd.testing.assert_frame_equal(positions_a, positions_b)
    pd.testing.assert_frame_equal(diag_a, diag_b)


def test_positions_long_only_fully_invested() -> None:
    prices = _prices()
    for params in VARIANTS.values():
        positions, _ = c12_weekly_signal(prices, params)
        assert float(positions.min().min()) >= 0.0
        np.testing.assert_allclose(positions.sum(axis=1).to_numpy(), 1.0, atol=1e-8)


def test_invalid_gate_action_rejected() -> None:
    from research.etf_tsmom_c12 import C12Params

    with pytest.raises(ValueError):
        C12Params(
            variant_id="bad",
            rolling_dispersion_window_weeks=4,
            threshold_quantile=0.80,
            gate_action="leverage_up",
        )
