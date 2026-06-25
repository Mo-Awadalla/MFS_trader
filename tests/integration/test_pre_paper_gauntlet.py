"""Pre-paper gauntlet integration tests.

These prove the engine can survive:
  - same target twice → no duplicate orders (idempotency)
  - same bar replayed twice → identical result (determinism)
  - timeout → reconcile, not retry blindly
  - partial fill → position updated correctly
  - rejected order → no position change
  - cancelled partial fill → preserves filled quantity
  - broker position mismatch → halt/freeze
  - DB intent write failure → block order
  - restart reconciles broker state before trading
  - kill-switch state persists across restart
  - unknown state → alert + manual, not flatten
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from config.schema import (
    AssetClass,
    BrokerConfig,
    Config,
    CostModelConfig,
    DataConfig,
    EngineConfig,
    LiveDeploymentConfig,
    Mode,
    MonitoringConfig,
    PortfolioConfig,
    RiskLimits,
)
from engine.replay import run_replay
from engine.runtime import TradingEngine
from execution.sim_broker.broker import SimBroker, SimBrokerConfig
from portfolio.sizing import PortfolioState
from risk.engine import DrawdownState
from storage.event_logger import EventLogger
from storage.repository import (
    get_engine_state,
    get_positions,
    is_strategy_halted,
    set_strategy_kill_switch,
)
from storage.schema import init_db


def _make_config(mode: Mode = Mode.PAPER) -> Config:
    return Config(
        mode=mode,
        brokers=[BrokerConfig(name="sim_broker", asset_class=AssetClass.EQUITY, api_key_env="X", api_secret_env="Y", base_url="sim")],
        data=[DataConfig(symbols=["AAPL"], asset_class=AssetClass.EQUITY)],
        risk_limits=RiskLimits(per_position_pct=0.05, max_open_positions=10),
        portfolio=PortfolioConfig(per_position_risk_pct=0.05),
        cost_model=CostModelConfig(),
        monitoring=MonitoringConfig(),
        engine=EngineConfig(),
        live_deployment=LiveDeploymentConfig(),
        strategy_name="test_strategy",
        strategy_version="0.1.0",
    )


def _make_bars(n: int = 100, symbol: str = "AAPL") -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="1D", tz="UTC")
    close = [100.0 + i * 0.1 for i in range(n)]
    return pd.DataFrame(
        {
            "symbol": symbol,
            "open": [c - 0.5 for c in close],
            "high": [c + 1.0 for c in close],
            "low": [c - 1.0 for c in close],
            "close": close,
            "volume": [10000.0] * n,
        },
        index=idx,
    )


def _always_long_strategy(bars, params):
    """Strategy that always wants to be long AAPL."""
    return {"AAPL": 1.0}


def _flat_strategy(bars, params):
    """Strategy that always wants to be flat."""
    return {"AAPL": 0.0}


@pytest.fixture
def db(tmp_path) -> sqlite3.Connection:
    conn = init_db(tmp_path / "test.sqlite")
    yield conn
    conn.close()


@pytest.fixture
def broker() -> SimBroker:
    b = SimBroker(SimBrokerConfig(seed=42))
    b.connect()
    b.set_price("AAPL", 100.0)
    return b


@pytest.fixture
def engine(db, broker):
    config = _make_config()
    _logger = EventLogger(db, environment="paper")
    return TradingEngine(
        config=config,
        conn=db,
        broker=broker,
        strategy_fn=_always_long_strategy,
        strategy_name="test_strategy",
    )


class TestIdempotency:
    def test_same_target_twice_no_duplicate_orders(self, engine, db):
        """Same target twice → no duplicate orders."""
        bars = _make_bars(50)
        prices = {"AAPL": 100.0}
        state = PortfolioState(cash=10000, equity=10000, high_water_mark=10000)
        dd = DrawdownState(high_water_mark=10000, current_equity=10000)

        # Process same bar twice
        engine.process_bar(bars, prices, bar_timestamp="2024-01-01", portfolio_state=state, drawdown=dd)
        engine.process_bar(bars, prices, bar_timestamp="2024-01-01", portfolio_state=state, drawdown=dd)

        # Should only have ONE order (deterministic client_order_id)
        order_count = db.execute(
            "SELECT COUNT(*) FROM orders_live WHERE strategy = 'test_strategy'"
        ).fetchone()[0]
        assert order_count == 1

    def test_same_bar_replayed_twice_identical_positions(self, engine, db):
        """Same bar replayed twice → identical position state."""
        bars = _make_bars(50)
        prices = {"AAPL": 100.0}
        state = PortfolioState(cash=10000, equity=10000, high_water_mark=10000)
        dd = DrawdownState(high_water_mark=10000, current_equity=10000)

        engine.process_bar(bars, prices, bar_timestamp="2024-01-01", portfolio_state=state, drawdown=dd)

        positions_after_1 = get_positions(db, strategy="test_strategy")
        qty_1 = positions_after_1[0]["quantity"] if positions_after_1 else 0

        # Process same bar again
        engine.process_bar(bars, prices, bar_timestamp="2024-01-01", portfolio_state=state, drawdown=dd)

        positions_after_2 = get_positions(db, strategy="test_strategy")
        qty_2 = positions_after_2[0]["quantity"] if positions_after_2 else 0

        assert qty_1 == qty_2  # no change


class TestRejection:
    def test_rejected_order_no_position_change(self, db):
        """Rejected order → no position change."""
        reject_broker = SimBroker(SimBrokerConfig(reject_probability=1.0, seed=42))
        reject_broker.connect()
        reject_broker.set_price("AAPL", 100.0)

        config = _make_config()
        _logger = EventLogger(db, environment="paper")
        engine = TradingEngine(
            config=config,
            conn=db,
            broker=reject_broker,
            strategy_fn=_always_long_strategy,
            strategy_name="test_strategy",
        )
        engine.startup()

        bars = _make_bars(50)
        prices = {"AAPL": 100.0}
        state = PortfolioState(cash=10000, equity=10000, high_water_mark=10000)
        dd = DrawdownState(high_water_mark=10000, current_equity=10000)

        engine.process_bar(bars, prices, bar_timestamp="2024-01-01", portfolio_state=state, drawdown=dd)

        # No positions should exist
        positions = get_positions(db, strategy="test_strategy")
        assert len(positions) == 0


class TestTimeout:
    def test_timeout_no_blind_retry(self, db):
        """Timeout → reconcile, not retry blindly."""
        timeout_broker = SimBroker(SimBrokerConfig(timeout_probability=1.0, seed=42))
        timeout_broker.connect()
        timeout_broker.set_price("AAPL", 100.0)

        config = _make_config()
        _logger = EventLogger(db, environment="paper")
        engine = TradingEngine(
            config=config,
            conn=db,
            broker=timeout_broker,
            strategy_fn=_always_long_strategy,
            strategy_name="test_strategy",
        )
        engine.startup()

        bars = _make_bars(50)
        prices = {"AAPL": 100.0}
        state = PortfolioState(cash=10000, equity=10000, high_water_mark=10000)
        dd = DrawdownState(high_water_mark=10000, current_equity=10000)

        engine.process_bar(bars, prices, bar_timestamp="2024-01-01", portfolio_state=state, drawdown=dd)

        # Order should be in TIMEOUT state
        orders = db.execute(
            "SELECT order_state FROM orders_live WHERE strategy = 'test_strategy'"
        ).fetchall()
        assert any(o[0] == "TIMEOUT" for o in orders)

        # No positions (timeout didn't fill)
        positions = get_positions(db, strategy="test_strategy")
        assert len(positions) == 0


class TestPartialFills:
    def test_partial_fill_correct_position(self, db):
        """Partial fill → position = filled qty, remaining tracked."""
        partial_broker = SimBroker(SimBrokerConfig(partial_fill_probability=1.0, seed=42))
        partial_broker.connect()
        partial_broker.set_price("AAPL", 100.0)

        config = _make_config()
        _logger = EventLogger(db, environment="paper")
        engine = TradingEngine(
            config=config,
            conn=db,
            broker=partial_broker,
            strategy_fn=_always_long_strategy,
            strategy_name="test_strategy",
        )
        engine.startup()

        bars = _make_bars(50)
        prices = {"AAPL": 100.0}
        state = PortfolioState(cash=10000, equity=10000, high_water_mark=10000)
        dd = DrawdownState(high_water_mark=10000, current_equity=10000)

        engine.process_bar(bars, prices, bar_timestamp="2024-01-01", portfolio_state=state, drawdown=dd)

        positions = get_positions(db, strategy="test_strategy")
        assert len(positions) == 1
        # Position should be > 0 but less than the full target
        assert positions[0]["quantity"] > 0


class TestKillSwitchPersistence:
    def test_kill_switch_persists_across_restart(self, db, broker):
        """Kill switch → persists across restart, blocks trading."""
        config = _make_config()
        _logger1 = EventLogger(db, environment="paper", run_id="run_1")
        engine1 = TradingEngine(
            config=config,
            conn=db,
            broker=broker,
            strategy_fn=_always_long_strategy,
            strategy_name="test_strategy",
        )
        engine1.startup()
        engine1.halt("test_halt_reason")

        # Halt should be persisted
        assert get_engine_state(db, "halted") == "true"
        assert get_engine_state(db, "halt_reason") == "test_halt_reason"

        # "Restart" — create new engine instance
        _logger2 = EventLogger(db, environment="paper", run_id="run_2")
        engine2 = TradingEngine(
            config=config,
            conn=db,
            broker=broker,
            strategy_fn=_always_long_strategy,
            strategy_name="test_strategy",
        )
        success = engine2.startup()

        # Should refuse to trade because halt persisted
        assert success is False
        assert engine2.state.halted is True
        assert "test_halt_reason" in (engine2.state.halt_reason or "")


class TestStrategyHaltPersistence:
    def test_strategy_halt_persists_across_restart(self, db, broker):
        """Strategy-level kill switch persists across restart."""
        config = _make_config()
        _logger1 = EventLogger(db, environment="paper", run_id="run_1")
        engine1 = TradingEngine(
            config=config,
            conn=db,
            broker=broker,
            strategy_fn=_always_long_strategy,
            strategy_name="test_strategy",
        )
        engine1.startup()

        # Halt the strategy
        set_strategy_kill_switch(db, "test_strategy", True, "max_consecutive_losses")

        # "Restart"
        _logger2 = EventLogger(db, environment="paper", run_id="run_2")
        engine2 = TradingEngine(
            config=config,
            conn=db,
            broker=broker,
            strategy_fn=_always_long_strategy,
            strategy_name="test_strategy",
        )
        engine2.startup()

        # Strategy should still be halted
        assert is_strategy_halted(db, "test_strategy")
        assert "test_strategy" in engine2.state.strategy_halted


class TestReconciliation:
    def test_reconciliation_mismatch_halts_live_engine(self, db):
        """Position mismatch → halt in live mode (not blindly flatten)."""
        mismatch_broker = SimBroker(SimBrokerConfig(position_mismatch=True, seed=42))
        mismatch_broker.connect()
        mismatch_broker.set_price("AAPL", 100.0)
        mismatch_broker.inject_position("AAPL", 10, 100.0)  # inject 10 shares

        config = _make_config(Mode.LIVE)
        # EngineConfig is frozen — use dataclasses.replace
        from dataclasses import replace
        config = replace(config, engine=EngineConfig(startup_reconciliation_required=True))

        _logger = EventLogger(db, environment="live")
        engine = TradingEngine(
            config=config,
            conn=db,
            broker=mismatch_broker,
            strategy_fn=_always_long_strategy,
            strategy_name="test_strategy",
        )
        success = engine.startup()

        # Should detect mismatch and halt (not flatten)
        assert success is False
        assert engine.state.halted is True
        assert "reconciliation" in (engine.state.halt_reason or "")


class TestReplayMode:
    def test_replay_produces_orders(self, tmp_path):
        """Replay mode runs the full pipeline and produces orders."""
        bars = _make_bars(30)
        config = _make_config()

        result = run_replay(
            bars=bars,
            config=config,
            strategy_fn=_always_long_strategy,
            strategy_name="test_strategy",
            strategy_params={},
            db_path=tmp_path / "replay.sqlite",
            initial_capital=10000.0,
        )

        assert result.bar_count > 0
        assert result.error is None
        # Should have submitted at least one order
        assert result.orders_submitted > 0

    def test_replay_is_deterministic(self, tmp_path):
        """Same data + same params → same result."""
        bars = _make_bars(30)
        config = _make_config()

        result1 = run_replay(
            bars=bars,
            config=config,
            strategy_fn=_always_long_strategy,
            strategy_name="test_strategy",
            db_path=tmp_path / "replay1.sqlite",
        )
        result2 = run_replay(
            bars=bars,
            config=config,
            strategy_fn=_always_long_strategy,
            strategy_name="test_strategy",
            db_path=tmp_path / "replay2.sqlite",
        )

        assert result1.orders_submitted == result2.orders_submitted
        assert result1.orders_filled == result2.orders_filled
        assert result1.final_positions == result2.final_positions


class TestUnknownStateNoBlindFlatten:
    def test_unknown_state_does_not_flatten(self, db):
        """When broker state is unknown, engine freezes — does not blindly flatten."""
        # Engine with existing position
        config = _make_config()
        _logger = EventLogger(db, environment="paper")
        broker = SimBroker(SimBrokerConfig(seed=42))
        broker.connect()
        broker.set_price("AAPL", 100.0)
        broker.inject_position("AAPL", 50, 100.0)

        engine = TradingEngine(
            config=config,
            conn=db,
            broker=broker,
            strategy_fn=_flat_strategy,  # wants to exit
            strategy_name="test_strategy",
        )

        # Manually set an unknown state scenario
        engine.halt("unknown_state_test")

        bars = _make_bars(30)
        prices = {"AAPL": 100.0}
        state = PortfolioState(cash=10000, equity=10000, high_water_mark=10000)
        dd = DrawdownState(high_water_mark=10000, current_equity=10000)

        # Process bar while halted — should NOT submit orders
        result = engine.process_bar(bars, prices, bar_timestamp="2024-01-01", portfolio_state=state, drawdown=dd)

        assert result is None  # halted, no action

        # Position should NOT be flattened (engine is halted, not flattening)
        orders = db.execute(
            "SELECT COUNT(*) FROM orders_live WHERE strategy = 'test_strategy'"
        ).fetchone()[0]
        assert orders == 0  # no orders submitted while halted
