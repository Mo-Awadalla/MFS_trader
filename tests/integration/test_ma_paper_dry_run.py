from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from engine.paper_dry_run import run_ma_paper_dry_run
from engine.shakedown import make_replay_config, make_synthetic_bars
from execution.base import BrokerAccount
from storage.parquet_io import parquet_path, write_bars


class FakeReadOnlyBroker:
    name = "alpaca"

    def __init__(self, price=200.0):
        self.submit_calls = 0
        self.price = price

    def get_account(self):
        return BrokerAccount(account_id="paper-test", cash=10000.0, equity=10000.0)

    def get_positions(self):
        return []

    def get_open_orders(self):
        return []

    def get_price(self, symbol):
        assert symbol == "AAPL"
        return self.price

    def submit_order(self, request):  # pragma: no cover - failure path
        self.submit_calls += 1
        raise AssertionError("dry-run must never call broker.submit_order")


def test_dry_run_mode_never_calls_broker_submit(tmp_path):
    bars = make_synthetic_bars(n=240, seed=21)
    config = _config_with_storage(tmp_path)
    path = parquet_path(tmp_path / "parquet", "AAPL", "1d", source="alpaca")
    write_bars(bars, path)
    broker = FakeReadOnlyBroker()

    result = run_ma_paper_dry_run(
        config=config,
        broker=broker,
        symbol="AAPL",
        frequency="1d",
        source="alpaca",
        out_dir=tmp_path / "dry_run",
        fast_window=5,
        slow_window=20,
        trend_filter_active=False,
    )

    assert broker.submit_calls == 0
    assert result.passed
    assert result.decision.mode == "paper_dry_run"
    assert result.decision.broker_positions_before == result.decision.broker_positions_after
    assert result.decision.broker_open_orders_before == result.decision.broker_open_orders_after
    assert Path(result.db_path).exists()
    assert Path(result.report_path).exists()
    assert Path(result.json_path).exists()

    conn = sqlite3.connect(result.db_path)
    event_types = [row[0] for row in conn.execute("SELECT event_type FROM events ORDER BY id")]
    conn.close()
    assert "ORDER_DRY_RUN" in event_types
    assert any(event_type.startswith("RISK_CHECK_") for event_type in event_types)
    assert "ENGINE_HEARTBEAT" in event_types
    assert "ALERT_TEST" in event_types


def test_dry_run_rejects_broker_price_far_from_last_close(tmp_path):
    bars = make_synthetic_bars(n=240, seed=21)
    config = _config_with_storage(tmp_path)
    path = parquet_path(tmp_path / "parquet", "AAPL", "1d", source="alpaca")
    write_bars(bars, path)
    broker = FakeReadOnlyBroker(price=0.01)

    with pytest.raises(ValueError, match="inconsistent with last stored close"):
        run_ma_paper_dry_run(
            config=config,
            broker=broker,
            symbol="AAPL",
            frequency="1d",
            source="alpaca",
            out_dir=tmp_path / "dry_run_bad_price",
            fast_window=5,
            slow_window=20,
            trend_filter_active=False,
        )


def _config_with_storage(tmp_path):
    config = make_replay_config()
    data = replace(config.data[0], storage_dir=str(tmp_path / "parquet"))
    return replace(config, data=[data])
