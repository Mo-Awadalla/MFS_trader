"""Integration tests for portfolio_state derivation wired into the runtime.

Covers the Batch 4 wiring: ``TradingEngine._reconcile_broker`` now derives
``PortfolioState`` (KNOWN | PARTIAL | UNKNOWN) from open orders and broker
truth, and ``process_bar`` freezes on UNKNOWN / blocks new orders on PARTIAL.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pandas as pd

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
from engine.runtime import TradingEngine
from execution.base import BrokerAccount, BrokerPosition
from execution.sim_broker.broker import SimBroker, SimBrokerConfig
from portfolio.state import PortfolioState as PortfolioStateAuthority
from risk.inputs import RiskMetadataSnapshot
from storage.repository import upsert_order
from storage.schema import init_db


class _FailingBroker(SimBroker):
    """Sim broker that fails ``get_positions`` to drive UNKNOWN portfolio_state."""

    def __init__(self) -> None:
        super().__init__(SimBrokerConfig())
        self._fail = False

    def fail_next(self) -> None:
        self._fail = True

    def get_positions(self) -> list[BrokerPosition]:
        if self._fail:
            raise RuntimeError("broker unreachable (test)")
        return super().get_positions()

    def get_account(self) -> BrokerAccount:  # type: ignore[override]
        return super().get_account()


def _make_config() -> Config:
    return Config(
        mode=Mode.PAPER,
        brokers=[BrokerConfig(name="sim_broker", asset_class=AssetClass.EQUITY, api_key_env="X", api_secret_env="Y", base_url="sim")],
        data=[DataConfig(symbols=["AAPL"], asset_class=AssetClass.EQUITY)],
        risk_limits=RiskLimits(per_position_pct=0.05, max_open_positions=10, max_net_exposure_pct=0.30),
        portfolio=PortfolioConfig(per_position_risk_pct=0.05),
        cost_model=CostModelConfig(),
        monitoring=MonitoringConfig(),
        engine=EngineConfig(),
        live_deployment=LiveDeploymentConfig(authorized=False),
    )


def _make_engine(config: Config, broker: SimBroker) -> TradingEngine:
    conn = init_db(":memory:")
    return TradingEngine(
        config=config,
        conn=conn,
        broker=broker,
        strategy_fn=lambda bars, params: {"AAPL": 1.0},
        strategy_name="test_strategy",
        strategy_params={},
    )


class TestRuntimePortfolioStateDerivation:
    def test_missing_risk_metadata_blocks_before_order_intent(self) -> None:
        broker = SimBroker(SimBrokerConfig())
        broker.connect()
        broker.set_price("AAPL", 100.0)
        engine = _make_engine(_make_config(), broker)
        engine._risk_metadata_provider = lambda _symbols: RiskMetadataSnapshot(
            sectors={}, correlations={}, observed_at=datetime.now(UTC), source="incomplete_test_fixture"
        )
        bars = pd.DataFrame(
            {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [1_000_000.0]},
            index=pd.DatetimeIndex(["2024-01-02"], name="timestamp"),
        )
        evaluation = engine.process_bar(
            bars=bars, prices={"AAPL": 100.5}, bar_timestamp="2024-01-02T00:00:00Z"
        )
        assert evaluation is not None and evaluation.is_rejected
        assert "risk_metadata_unavailable" in evaluation.rejection_reasons[0]
        assert engine._conn.execute("SELECT COUNT(*) FROM orders_live").fetchone()[0] == 0

    def test_small_account_does_not_bypass_sector_or_minimum_notional_limits(self) -> None:
        broker = SimBroker(SimBrokerConfig(starting_cash=100.0, slippage_pct=0.0))
        broker.connect()
        broker.set_price("AAPL", 10.0)
        config = _make_config()
        config = replace(config, portfolio=replace(config.portfolio, per_position_risk_pct=0.05))
        engine = _make_engine(config, broker)
        bars = pd.DataFrame(
            {"open": [10.0], "high": [10.1], "low": [9.9], "close": [10.0], "volume": [1_000_000.0]},
            index=pd.DatetimeIndex(["2024-01-02"], name="timestamp"),
        )
        evaluation = engine.process_bar(bars=bars, prices={"AAPL": 10.0}, bar_timestamp="2024-01-02T00:00:00Z")
        order = engine._conn.execute(
            "SELECT requested_qty FROM orders_live WHERE strategy='test_strategy'"
        ).fetchone()
        assert evaluation is not None and evaluation.adjusted_targets[0].target_notional == 10.0
        assert order is None  # Below the unchanged $25 minimum-notional rebalance threshold.
        assert broker.get_account().equity == 100.0

    def test_reconcile_broker_unreachable_sets_unknown(self) -> None:
        broker = _FailingBroker()
        engine = _make_engine(_make_config(), broker)
        broker.fail_next()
        engine._reconcile_broker()
        assert engine._state.portfolio_state_authority == PortfolioStateAuthority.UNKNOWN

    def test_reconcile_broker_clean_sets_known(self) -> None:
        broker = _FailingBroker()
        engine = _make_engine(_make_config(), broker)
        engine._reconcile_broker()
        assert engine._state.portfolio_state_authority == PortfolioStateAuthority.KNOWN

    def test_process_bar_freezes_on_unknown(self) -> None:
        broker = _FailingBroker()
        engine = _make_engine(_make_config(), broker)
        # Force UNKNOWN state directly
        engine._state.portfolio_state_authority = PortfolioStateAuthority.UNKNOWN
        bars = pd.DataFrame(
            {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [1_000_000.0]},
            index=pd.DatetimeIndex(["2024-01-02"], name="timestamp"),
        )
        evaluation = engine.process_bar(
            bars=bars,
            prices={"AAPL": 100.5},
            bar_timestamp="2024-01-02T00:00:00Z",
        )
        assert evaluation is None  # frozen — no orders attempted

    def test_process_bar_blocks_orders_on_partial(self) -> None:
        broker = _FailingBroker()
        engine = _make_engine(_make_config(), broker)
        upsert_order(engine._conn, {
            "client_order_id": "pending-test-order",
            "broker_order_id": "broker-pending-test-order",
            "broker": "sim_broker",
            "account_id": "sim_account",
            "environment": "paper",
            "strategy": "other_strategy",
            "symbol": "MSFT",
            "asset_class": "equity",
            "side": "buy",
            "order_type": "limit",
            "time_in_force": "day",
            "limit_price": 100.0,
            "stop_price": None,
            "requested_qty": 1.0,
            "filled_qty": 0.0,
            "remaining_qty": 1.0,
            "avg_fill_price": None,
            "notional": 100.0,
            "currency": "USD",
            "order_state": "ACKNOWLEDGED",
            "reconciliation_status": "NOT_CHECKED",
            "bar_timestamp": None,
            "correlation_id": None,
            "version": None,
        })
        bars = pd.DataFrame(
            {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [1_000_000.0]},
            index=pd.DatetimeIndex(["2024-01-02"], name="timestamp"),
        )
        engine.process_bar(
            bars=bars,
            prices={"AAPL": 100.5},
            bar_timestamp="2024-01-02T00:00:00Z",
        )
        # A known small pending order makes the portfolio PARTIAL. It blocks
        # entries until reconciliation and no unrelated order is submitted.
        orders = engine._conn.execute(
            "SELECT COUNT(*) AS n FROM orders_live WHERE strategy='test_strategy'"
        ).fetchone()
        assert orders["n"] == 0

    def test_partial_state_allows_only_confirmed_risk_reducing_exit(self) -> None:
        broker = _FailingBroker()
        broker.inject_position("AAPL", 1.0, 100.0)
        engine = _make_engine(_make_config(), broker)
        engine._strategy_fn = lambda bars, params: {"AAPL": 0.0}
        upsert_order(engine._conn, {
            "client_order_id": "pending-safe-exit-test",
            "broker_order_id": "broker-pending-safe-exit-test",
            "broker": "sim_broker",
            "account_id": "sim_account",
            "environment": "paper",
            "strategy": "other_strategy",
            "symbol": "MSFT",
            "asset_class": "equity",
            "side": "buy",
            "order_type": "limit",
            "time_in_force": "day",
            "limit_price": 100.0,
            "stop_price": None,
            "requested_qty": 1.0,
            "filled_qty": 0.0,
            "remaining_qty": 1.0,
            "avg_fill_price": None,
            "notional": 100.0,
            "currency": "USD",
            "order_state": "ACKNOWLEDGED",
            "reconciliation_status": "NOT_CHECKED",
            "bar_timestamp": None,
            "correlation_id": None,
            "version": None,
        })
        bars = pd.DataFrame(
            {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [1_000_000.0]},
            index=pd.DatetimeIndex(["2024-01-02"], name="timestamp"),
        )
        engine.process_bar(bars=bars, prices={"AAPL": 100.5}, bar_timestamp="2024-01-02T00:00:00Z")
        exits = engine._conn.execute(
            "SELECT symbol,side,requested_qty FROM orders_live WHERE strategy='test_strategy'"
        ).fetchall()
        assert [(row["symbol"], row["side"], row["requested_qty"]) for row in exits] == [
            ("AAPL", "sell", 1.0)
        ]
