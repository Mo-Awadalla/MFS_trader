"""Tests for the risk engine — circuit breakers, exposure, kill switches."""

from __future__ import annotations

import pytest

from config.schema import RiskLimits
from portfolio.sizing import PortfolioState, TargetPosition
from risk.engine import (
    DrawdownState,
    ExceptionSeverity,
    RiskDecision,
    RiskEngine,
    classify_exception,
    determine_emergency_action,
)


@pytest.fixture
def limits() -> RiskLimits:
    return RiskLimits(
        per_position_pct=0.01,
        max_daily_loss_pct=0.03,
        block_new_at_daily_loss_pct=0.02,
        max_weekly_loss_pct=0.06,
        max_monthly_loss_pct=0.15,
        max_gross_exposure_pct=1.5,
        max_net_exposure_pct=0.10,
        max_sector_gross_pct=0.35,
        max_sector_net_pct=0.10,
        max_correlated_cluster_gross_pct=0.35,
        max_correlated_cluster_risk_pct=0.03,
        correlation_threshold=0.70,
        max_open_positions=10,
    )


@pytest.fixture
def state() -> PortfolioState:
    return PortfolioState(cash=10000, equity=10000, high_water_mark=10000)


@pytest.fixture
def engine(limits) -> RiskEngine:
    return RiskEngine(limits)


def _make_target(symbol="AAPL", side="long", qty=50, price=100, notional=None):
    return TargetPosition(
        symbol=symbol,
        asset_class="equity",
        side=side,
        target_qty=qty,
        target_notional=notional or abs(qty) * price,
        current_price=price,
    )


class TestKillSwitch:
    def test_kill_switch_blocks_all(self, engine, state):
        engine.activate_kill_switch("manual_halt")
        targets = [_make_target()]
        dd = DrawdownState(high_water_mark=10000, current_equity=10000)
        result = engine.evaluate(targets, state, dd)
        assert result.is_rejected
        assert "kill_switch" in result.rejection_reasons[0]

    def test_kill_switch_cleared_allows_trading(self, engine, state):
        engine.activate_kill_switch("test")
        engine.deactivate_kill_switch()
        targets = [_make_target()]
        dd = DrawdownState(high_water_mark=10000, current_equity=10000)
        result = engine.evaluate(targets, state, dd)
        assert not result.is_rejected

    def test_strategy_halt_blocks_only_that_strategy(self, engine, state):
        engine.halt_strategy("ma", "max_consecutive_losses")
        targets = [_make_target()]
        dd = DrawdownState(high_water_mark=10000, current_equity=10000)
        result = engine.evaluate(targets, state, dd, strategy_name="ma")
        assert result.is_rejected
        # Other strategy should be fine
        result2 = engine.evaluate(targets, state, dd, strategy_name="bb")
        assert not result2.is_rejected


class TestDrawdownLimits:
    def test_daily_loss_block_new_entries(self, engine, state):
        # -2.5% daily loss → block new (allow exits)
        dd = DrawdownState(
            daily_pnl=-250, high_water_mark=10000, current_equity=9750
        )
        targets = [_make_target("AAPL", "long", 50)]
        result = engine.evaluate(targets, state, dd)
        # New entry blocked — only flat targets allowed
        assert any("daily_loss" in r for r in result.rejection_reasons)

    def test_daily_loss_allows_exits(self, engine, state):
        dd = DrawdownState(daily_pnl=-250, high_water_mark=10000, current_equity=9750)
        # Flat target = exit
        targets = [_make_target("AAPL", "flat", 0)]
        result = engine.evaluate(targets, state, dd)
        # Exits should be allowed
        assert result.final_decision != RiskDecision.REJECTED or all(t.is_flat for t in result.adjusted_targets)

    def test_daily_loss_halt_flattens(self, engine, state):
        # -3.5% daily loss → flatten all
        dd = DrawdownState(daily_pnl=-350, high_water_mark=10000, current_equity=9650)
        targets = [_make_target("AAPL", "long", 50)]
        result = engine.evaluate(targets, state, dd)
        assert all(t.is_flat for t in result.adjusted_targets)

    def test_weekly_loss_blocks_new(self, engine, state):
        dd = DrawdownState(weekly_pnl=-600, high_water_mark=10000, current_equity=9400)
        targets = [_make_target("AAPL", "long", 50)]
        result = engine.evaluate(targets, state, dd)
        assert any("weekly" in r for r in result.rejection_reasons)

    def test_monthly_halt_is_hard_halt(self, engine, state):
        dd = DrawdownState(monthly_pnl=-1600, high_water_mark=10000, current_equity=8400)
        targets = [_make_target("AAPL", "long", 50)]
        result = engine.evaluate(targets, state, dd)
        assert result.is_rejected
        assert any("monthly" in r for r in result.rejection_reasons)


class TestExposureLimits:
    def test_gross_exposure_reduces(self, engine, state):
        # 10 positions * 2000 notional = 20000 > 15000 (1.5x equity)
        targets = [_make_target(f"SYM{i}", "long", 20, 100, 2000) for i in range(10)]
        dd = DrawdownState(high_water_mark=10000, current_equity=10000)
        result = engine.evaluate(targets, state, dd)
        assert result.final_decision == RiskDecision.REDUCED
        assert any("gross" in r for r in result.reduction_reasons)

    def test_max_open_positions_rejects_new(self, engine, state):
        # 8 current + 5 new = 13 > 10
        current = {f"CUR{i}": {"qty": 10, "avg_price": 100} for i in range(8)}
        targets = [_make_target(f"NEW{i}", "long", 50) for i in range(5)]
        dd = DrawdownState(high_water_mark=10000, current_equity=10000)
        result = engine.evaluate(targets, state, dd, current_positions=current)
        assert any("max_open" in r for r in result.rejection_reasons)

    def test_per_position_risk_reduces(self, engine, state):
        # Huge position — risk >> 1% of equity
        target = _make_target("AAPL", "long", 1000, 100, 100000)
        dd = DrawdownState(high_water_mark=10000, current_equity=10000)
        result = engine.evaluate([target], state, dd)
        assert result.final_decision == RiskDecision.REDUCED
        # Position should be smaller
        assert result.adjusted_targets[0].target_notional < 100000


class TestSectorExposure:
    def test_sector_gross_reduces(self, engine, state):
        sector_map = {"AAPL": "tech", "MSFT": "tech", "GOOGL": "tech", "AMZN": "tech"}
        # 4 tech stocks * 1500 = 6000 > 3500 (35% of 10000)
        targets = [_make_target(s, "long", 15, 100, 1500) for s in sector_map]
        dd = DrawdownState(high_water_mark=10000, current_equity=10000)
        result = engine.evaluate(targets, state, dd, sector_map=sector_map)
        assert any("sector" in r for r in result.reduction_reasons)


class TestCorrelationCluster:
    def test_correlated_cluster_reduces(self, engine, state):
        corr_matrix = {
            "AAPL": {"MSFT": 0.85, "GOOGL": 0.80},
            "MSFT": {"AAPL": 0.85, "GOOGL": 0.75},
            "GOOGL": {"AAPL": 0.80, "MSFT": 0.75},
        }
        # 3 correlated stocks * 1500 = 4500 > 3500 (35% of 10000)
        targets = [_make_target(s, "long", 15, 100, 1500) for s in ["AAPL", "MSFT", "GOOGL"]]
        dd = DrawdownState(high_water_mark=10000, current_equity=10000)
        result = engine.evaluate(targets, state, dd, correlation_matrix=corr_matrix)
        assert any("correlation" in r for r in result.reduction_reasons)

    def test_uncorrelated_not_clustered(self, engine, state):
        corr_matrix = {"AAPL": {"XOM": 0.10}, "XOM": {"AAPL": 0.10}}
        targets = [_make_target("AAPL", "long", 15, 100, 1500), _make_target("XOM", "long", 15, 100, 1500)]
        dd = DrawdownState(high_water_mark=10000, current_equity=10000)
        result = engine.evaluate(targets, state, dd, correlation_matrix=corr_matrix)
        # Should NOT trigger correlation cluster (low correlation)
        assert not any("correlation" in r for r in result.reduction_reasons)


class TestExceptionClassification:
    def test_soft_exception(self):
        assert classify_exception("indicator_calc_error") == ExceptionSeverity.SOFT

    def test_hard_exception(self):
        assert classify_exception("position_mismatch") == ExceptionSeverity.HARD

    def test_catastrophic_exception(self):
        assert classify_exception("internal_position_unknown") == ExceptionSeverity.CATASTROPHIC

    def test_unknown_defaults_to_hard(self):
        assert classify_exception("some_new_error") == ExceptionSeverity.HARD


class TestEmergencyAction:
    def test_soft_disables_strategy(self):
        action = determine_emergency_action(ExceptionSeverity.SOFT, state_known=True, risk_breach=False)
        assert action == "disable_strategy"

    def test_hard_known_state_risk_breach_flattens(self):
        action = determine_emergency_action(ExceptionSeverity.HARD, state_known=True, risk_breach=True)
        assert action == "flatten_if_safe"

    def test_hard_unknown_state_freezes(self):
        action = determine_emergency_action(ExceptionSeverity.HARD, state_known=False, risk_breach=True)
        assert action == "freeze_alert_manual"

    def test_catastrophic_always_freezes(self):
        action = determine_emergency_action(ExceptionSeverity.CATASTROPHIC, state_known=True, risk_breach=True)
        assert action == "freeze_alert_manual"

    def test_hard_no_breach_halts_new(self):
        action = determine_emergency_action(ExceptionSeverity.HARD, state_known=True, risk_breach=False)
        assert action == "halt_new_orders"
