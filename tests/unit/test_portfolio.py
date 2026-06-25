"""Tests for portfolio sizing and target position construction."""

from __future__ import annotations

import pytest

from config.schema import PortfolioConfig
from portfolio.sizing import (
    PortfolioState,
    TargetPosition,
    compute_position_delta,
    compute_target_positions,
)


@pytest.fixture
def state() -> PortfolioState:
    return PortfolioState(
        cash=5000.0,
        equity=10000.0,
        high_water_mark=10000.0,
        positions={},
    )


@pytest.fixture
def config() -> PortfolioConfig:
    return PortfolioConfig(
        sizing_method="fixed_fraction",
        per_position_risk_pct=0.01,
        dollar_neutral=False,
        equal_weight=True,
        rebalance_frequency="daily",
    )


class TestComputeTargetPositions:
    def test_long_exposure_produces_long_position(self, state, config):
        exposures = {"AAPL": 1.0}
        prices = {"AAPL": 100.0}
        targets = compute_target_positions(exposures, prices, state, config)
        assert len(targets) == 1
        assert targets[0].side == "long"
        assert targets[0].target_qty > 0
        assert targets[0].target_notional > 0

    def test_short_exposure_produces_short_position(self, state, config):
        exposures = {"AAPL": -1.0}
        prices = {"AAPL": 100.0}
        targets = compute_target_positions(exposures, prices, state, config)
        assert targets[0].side == "short"
        assert targets[0].target_qty < 0

    def test_flat_exposure_produces_zero_position(self, state, config):
        exposures = {"AAPL": 0.0}
        prices = {"AAPL": 100.0}
        targets = compute_target_positions(exposures, prices, state, config)
        assert targets[0].is_flat
        assert targets[0].target_qty == 0.0

    def test_zero_price_produces_flat(self, state, config):
        exposures = {"AAPL": 1.0}
        prices = {"AAPL": 0.0}
        targets = compute_target_positions(exposures, prices, state, config)
        assert targets[0].is_flat

    def test_fractional_exposure_scales_size(self, state, config):
        full = compute_target_positions({"AAPL": 1.0}, {"AAPL": 100.0}, state, config)[0]
        half = compute_target_positions({"AAPL": 0.5}, {"AAPL": 100.0}, state, config)[0]
        assert half.target_qty < full.target_qty

    def test_risk_pct_limits_position_size(self, state):
        config_1pct = PortfolioConfig(per_position_risk_pct=0.01)
        config_2pct = PortfolioConfig(per_position_risk_pct=0.02)
        t1 = compute_target_positions({"AAPL": 1.0}, {"AAPL": 100.0}, state, config_1pct)[0]
        t2 = compute_target_positions({"AAPL": 1.0}, {"AAPL": 100.0}, state, config_2pct)[0]
        assert t2.target_qty > t1.target_qty  # more risk = bigger position

    def test_stop_price_affects_sizing(self, state, config):
        prices = {"AAPL": 100.0}
        tight_stop = compute_target_positions(
            {"AAPL": 1.0}, prices, state, config, stop_prices={"AAPL": 98.0}
        )[0]
        wide_stop = compute_target_positions(
            {"AAPL": 1.0}, prices, state, config, stop_prices={"AAPL": 90.0}
        )[0]
        # Tighter stop = more shares (same risk budget, smaller per-unit risk)
        assert tight_stop.target_qty > wide_stop.target_qty

    def test_dollar_neutral_balances_long_short(self):
        state = PortfolioState(cash=10000, equity=10000, high_water_mark=10000)
        config = PortfolioConfig(
            sizing_method="fixed_fraction",
            per_position_risk_pct=0.01,
            dollar_neutral=True,
        )
        targets = compute_target_positions(
            {"AAPL": 1.0, "MSFT": -1.0},
            {"AAPL": 100.0, "MSFT": 200.0},
            state,
            config,
        )
        long_notional = sum(t.target_notional for t in targets if t.side == "long")
        short_notional = sum(t.target_notional for t in targets if t.side == "short")
        assert abs(long_notional - short_notional) < 0.01

    def test_multiple_symbols(self, state, config):
        exposures = {"AAPL": 1.0, "MSFT": 1.0, "GOOGL": -1.0}
        prices = {"AAPL": 100.0, "MSFT": 200.0, "GOOGL": 150.0}
        targets = compute_target_positions(exposures, prices, state, config)
        assert len(targets) == 3

    def test_vol_target_sizing(self, state):
        config = PortfolioConfig(
            sizing_method="vol_target",
            per_position_risk_pct=0.01,
        )
        targets = compute_target_positions(
            {"AAPL": 1.0},
            {"AAPL": 100.0},
            state,
            config,
            volatilities={"AAPL": 0.30},
        )
        assert targets[0].target_qty > 0


class TestPositionDelta:
    def test_no_change_is_hold(self):
        target = TargetPosition("AAPL", "equity", "long", 100.0, 10000.0, 100.0)
        delta = compute_position_delta(target, current_qty=100.0)
        assert delta["action"] == "hold"
        assert delta["delta_qty"] == 0.0

    def test_signal_transition_holds_same_side_even_if_target_qty_drifts(self):
        target = TargetPosition("AAPL", "equity", "long", 101.0, 10100.0, 100.0)
        delta = compute_position_delta(
            target,
            current_qty=100.0,
            execution_mode="signal_transition",
        )
        assert delta["action"] == "hold"
        assert delta["delta_qty"] == 0.0

    def test_signal_transition_flattens_on_side_change(self):
        target = TargetPosition("AAPL", "equity", "flat", 0.0, 0.0, 100.0)
        delta = compute_position_delta(
            target,
            current_qty=100.0,
            execution_mode="signal_transition",
        )
        assert delta["action"] == "sell"
        assert delta["delta_qty"] == -100.0

    def test_continuous_rebalance_suppresses_small_deltas(self):
        target = TargetPosition("AAPL", "equity", "long", 101.0, 10100.0, 100.0)
        delta = compute_position_delta(
            target,
            current_qty=100.0,
            execution_mode="continuous_rebalance",
            min_notional_delta=25.0,
            min_qty_delta=0.01,
            min_pct_position_delta=0.05,
        )
        assert delta["action"] == "hold"

    def test_continuous_rebalance_allows_meaningful_deltas(self):
        target = TargetPosition("AAPL", "equity", "long", 120.0, 12000.0, 100.0)
        delta = compute_position_delta(
            target,
            current_qty=100.0,
            execution_mode="continuous_rebalance",
            min_notional_delta=25.0,
            min_qty_delta=0.01,
            min_pct_position_delta=0.05,
        )
        assert delta["action"] == "buy"
        assert delta["delta_qty"] == 20.0

    def test_increase_is_buy(self):
        target = TargetPosition("AAPL", "equity", "long", 150.0, 15000.0, 100.0)
        delta = compute_position_delta(target, current_qty=100.0, execution_mode="continuous_rebalance")
        assert delta["action"] == "buy"
        assert delta["delta_qty"] == 50.0
        assert delta["delta_notional"] == 5000.0

    def test_decrease_is_sell(self):
        target = TargetPosition("AAPL", "equity", "long", 50.0, 5000.0, 100.0)
        delta = compute_position_delta(target, current_qty=100.0, execution_mode="continuous_rebalance")
        assert delta["action"] == "sell"
        assert delta["delta_qty"] == -50.0

    def test_flatten_is_sell(self):
        target = TargetPosition("AAPL", "equity", "flat", 0.0, 0.0, 100.0)
        delta = compute_position_delta(target, current_qty=100.0)
        assert delta["action"] == "sell"
        assert delta["delta_qty"] == -100.0


class TestPortfolioState:
    def test_gross_exposure(self):
        state = PortfolioState(
            cash=5000,
            equity=10000,
            high_water_mark=10000,
            positions={
                "AAPL": {"qty": 50, "avg_price": 100, "side": "long"},
                "MSFT": {"qty": -20, "avg_price": 200, "side": "short"},
            },
        )
        # gross = 50*100 + 20*200 = 5000 + 4000 = 9000
        assert state.gross_exposure == 9000

    def test_net_exposure(self):
        state = PortfolioState(
            cash=5000,
            equity=10000,
            high_water_mark=10000,
            positions={
                "AAPL": {"qty": 50, "avg_price": 100, "side": "long"},
                "MSFT": {"qty": -20, "avg_price": 200, "side": "short"},
            },
        )
        # net = 50*100 + (-20)*200 = 5000 - 4000 = 1000
        assert state.net_exposure == 1000
