from __future__ import annotations

from dataclasses import replace

import pytest

from config.schema import LiveDeploymentConfig, PortfolioConfig, RiskLimits
from engine.paper_trade import run_ma_paper_trade_once
from engine.shakedown import make_replay_config, make_synthetic_bars
from execution.base import BrokerAccount, BrokerOrderResponse, BrokerPosition
from storage.parquet_io import parquet_path, write_bars


class FakePaperBroker:
    name = "alpaca"

    def __init__(self, price: float):
        self.price = price
        self.submit_calls = 0
        self.orders: dict[str, BrokerOrderResponse] = {}
        self.position_qty = 0.0

    def get_account(self):
        return BrokerAccount(account_id="paper-test", cash=10000.0, equity=10000.0)

    def get_positions(self):
        if abs(self.position_qty) < 1e-9:
            return []
        return [
            BrokerPosition(
                symbol="AAPL",
                quantity=self.position_qty,
                avg_entry_price=self.price,
                side="long",
                market_value=self.position_qty * self.price,
            )
        ]

    def get_open_orders(self):
        return [order for order in self.orders.values() if order.status == "ACKNOWLEDGED"]

    def get_price(self, symbol):
        assert symbol == "AAPL"
        return self.price

    def submit_order(self, request):
        self.submit_calls += 1
        self.position_qty += request.quantity
        response = BrokerOrderResponse(
            client_order_id=request.client_order_id,
            broker_order_id=f"broker-{self.submit_calls}",
            status="FILLED",
            filled_qty=request.quantity,
            avg_fill_price=self.price,
            remaining_qty=0.0,
        )
        self.orders[request.client_order_id] = response
        return response

    def get_order_status(self, client_order_id):
        return self.orders.get(client_order_id)

    def cancel_order(self, client_order_id):
        return True

    @property
    def is_connected(self):
        return True

    def connect(self):
        return None

    def disconnect(self):
        return None


def test_paper_trade_requires_explicit_submit_gate(tmp_path):
    bars = make_synthetic_bars(n=240, seed=21)
    config = _config_with_storage(tmp_path, submit_enabled=False)
    path = parquet_path(tmp_path / "parquet", "AAPL", "1d", source="alpaca")
    write_bars(bars, path)
    broker = FakePaperBroker(price=float(bars["close"].iloc[-1]))

    with pytest.raises(ValueError, match="paper_submit_enabled must be true"):
        run_ma_paper_trade_once(
            config=config,
            broker=broker,
            symbol="AAPL",
            frequency="1d",
            source="alpaca",
            out_dir=tmp_path / "paper_trade",
            fast_window=5,
            slow_window=20,
            trend_filter_active=False,
        )


def test_paper_trade_submits_once_and_rerun_does_not_duplicate(tmp_path):
    bars = make_synthetic_bars(n=240, seed=21)
    config = _config_with_storage(tmp_path, submit_enabled=True)
    path = parquet_path(tmp_path / "parquet", "AAPL", "1d", source="alpaca")
    write_bars(bars, path)
    broker = FakePaperBroker(price=float(bars["close"].iloc[-1]))

    first = run_ma_paper_trade_once(
        config=config,
        broker=broker,
        symbol="AAPL",
        frequency="1d",
        source="alpaca",
        out_dir=tmp_path / "paper_trade",
        fast_window=5,
        slow_window=20,
        trend_filter_active=False,
    )

    assert first.passed
    assert first.submitted
    assert first.order_state == "FILLED"
    assert first.broker_status == "FILLED"
    assert broker.submit_calls == 1

    second = run_ma_paper_trade_once(
        config=config,
        broker=broker,
        symbol="AAPL",
        frequency="1d",
        source="alpaca",
        out_dir=tmp_path / "paper_trade",
        fast_window=5,
        slow_window=20,
        trend_filter_active=False,
    )

    assert second.passed
    assert not second.submitted
    assert broker.submit_calls == 1


def _config_with_storage(tmp_path, *, submit_enabled: bool):
    config = make_replay_config()
    data = replace(config.data[0], storage_dir=str(tmp_path / "parquet"))
    live = LiveDeploymentConfig(
        paper_submit_enabled=submit_enabled,
        max_paper_notional=100.0,
        max_notional_per_order=100.0,
        max_strategy_capital=500.0,
        strategy_capital_limit=500.0,
        allow_short=False,
        paper_order_type="limit",
        paper_limit_offset_pct=0.001,
        paper_session_count=1,
    )
    risk = replace(config.risk_limits, max_open_positions=1)
    portfolio = replace(
        config.portfolio,
        execution_mode="signal_transition",
        min_notional_delta=25.0,
    )
    assert isinstance(risk, RiskLimits)
    assert isinstance(portfolio, PortfolioConfig)
    return replace(config, data=[data], live_deployment=live, risk_limits=risk, portfolio=portfolio)
