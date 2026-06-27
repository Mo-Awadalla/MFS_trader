"""Integration tests for portfolio_state derivation wired into the runtime.

Covers the Batch 4 wiring: ``TradingEngine._reconcile_broker`` now derives
``PortfolioState`` (KNOWN | PARTIAL | UNKNOWN) from open orders and broker
truth, and ``process_bar`` freezes on UNKNOWN / blocks new orders on PARTIAL.
"""

from __future__ import annotations

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
        engine._state.portfolio_state_authority = PortfolioStateAuthority.PARTIAL
        bars = pd.DataFrame(
            {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [1_000_000.0]},
            index=pd.DatetimeIndex(["2024-01-02"], name="timestamp"),
        )
        engine.process_bar(
            bars=bars,
            prices={"AAPL": 100.5},
            bar_timestamp="2024-01-02T00:00:00Z",
        )
        # Risk evaluation still runs (the bar is processed) but no orders are
        # submitted — the OMS remains empty.
        orders = engine._conn.execute("SELECT COUNT(*) AS n FROM orders_live").fetchone()
        assert orders["n"] == 0
