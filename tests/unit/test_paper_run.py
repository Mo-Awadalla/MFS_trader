"""Deterministic paper-loop recovery using fake brokers and real temporary SQLite."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
from engine.paper_evidence import PaperLedger, digest
from engine.paper_run import PaperRunConfig, PaperRunLoop
from execution.base import OrderSide, OrderType
from execution.oms import OMS, OrderIntent
from execution.sim_broker.broker import SimBroker
from experiments.artifacts import ArtifactManager
from experiments.kill_switch import KillSwitchSeverity
from experiments.registry import ExperimentRegistry
from storage.event_logger import EventLogger
from storage.schema import init_db
from tests.unit.test_paper_evidence import paper_experiment


class Clock:
    def __init__(self):
        self.now = datetime(2024, 4, 9, 20, tzinfo=UTC)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


def _make_config():
    return Config(
        mode=Mode.PAPER,
        brokers=[BrokerConfig(name="sim_broker", asset_class=AssetClass.EQUITY,
                              api_key_env="SIM_API_KEY", api_secret_env="SIM_API_SECRET", base_url="sim")],
        data=[DataConfig(symbols=["AAPL"], asset_class=AssetClass.EQUITY)],
        risk_limits=RiskLimits(), portfolio=PortfolioConfig(), cost_model=CostModelConfig(),
        monitoring=MonitoringConfig(), engine=EngineConfig(startup_reconciliation_required=True),
        live_deployment=LiveDeploymentConfig(), strategy_name="dual_ma_crossover",
        strategy_version="0.1.0", strategies_enabled=["ma"],
    )


def bars(day="2024-04-09"):
    return pd.DataFrame({"open": [150.0], "high": [151.0], "low": [149.0],
                         "close": [150.0], "volume": [1000000]}, index=[pd.Timestamp(day, tz="UTC")])


class FakeBroker(SimBroker):
    def __init__(self):
        super().__init__()
        self.set_price("AAPL", 150.0)
        self.submissions = []
        self.connections = 0

    def connect(self):
        self.connections += 1
        super().connect()

    def submit_order(self, request):
        self.submissions.append(request.client_order_id)
        return super().submit_order(request)


@pytest.fixture
def setup(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments")
    exp = paper_experiment(registry)
    clock = Clock()
    config = PaperRunConfig(experiment_uuid=exp.uuid, experiment_hash=exp.experiment_hash,
                            experiment_root=registry.root, session_id="run", max_cycles=1,
                            sleep_between_bars_seconds=0, data_grace_seconds=60)
    yield registry, exp, clock, config, tmp_path / "run.sqlite"
    registry.close()


def make_loop(setup, *, broker=None, run_config=None, strategy=None, provider=None, config=None, sleeper=None):
    _, _, clock, rc, _ = setup
    return PaperRunLoop(config=config or _make_config(), broker=broker or FakeBroker(),
                        strategy_fn=strategy or (lambda bars, params: {}), strategy_name="test",
                        run_config=run_config or rc, bars_provider=provider, clock=clock,
                        sleeper=sleeper or clock.advance)


def test_distinct_sessions_have_real_times_separate_from_watermarks(setup):
    registry, exp, clock, rc, db = setup
    def provider():
        clock.advance(86400)
        return bars("2024-04-10")
    result = make_loop(setup, run_config=replace(rc, max_cycles=2), provider=provider).run(bars(), db)
    assert not result.halted and result.cycle_count == 2
    payload = ArtifactManager(registry.root).read_paper_session_json(exp.uuid, "run")
    assert payload["window"]["market_sessions"] == 2
    assert payload["window"]["trades"] == 0
    assert payload["bar_cycle_report"]["bar_cycle_completion"] == 1
    assert payload["bar_cycles"][0]["expected_at"] == "2024-04-09T20:00:00+00:00"
    assert payload["bar_cycles"][0]["input_data_watermark"] == "2024-04-09 00:00:00+00:00"


def test_repeated_static_bars_do_not_manufacture_cycles(setup):
    registry, exp, _, rc, db = setup
    result = make_loop(setup, run_config=replace(rc, max_cycles=3)).run(bars(), db)
    assert result.cycle_count == 1
    payload = ArtifactManager(registry.root).read_paper_session_json(exp.uuid, "run")
    assert payload["window"]["market_sessions"] == 1
    assert payload["observations"]["attempts"][0]["outcome"] == "stopped"


def test_overdue_fresh_data_records_missed_cycle_without_sleeping_forever(setup):
    registry, exp, clock, rc, db = setup
    def provider():
        clock.advance(86461)
        return bars()
    result = make_loop(setup, run_config=replace(rc, max_cycles=2), provider=provider).run(bars(), db)
    assert result.halted and result.halt_reason == "fresh data overdue"
    payload = ArtifactManager(registry.root).read_paper_session_json(exp.uuid, "run")
    assert payload["bar_cycle_report"]["bar_cycle_completion"] == 0.5
    assert payload["bar_cycles"][1]["result"] == "missed_overdue"


def test_initial_stale_bar_is_not_completed(setup):
    _, _, clock, _, db = setup
    def provider():
        clock.advance(61)
        return bars("2024-04-08")
    result = make_loop(setup, provider=provider).run(bars("2024-04-08"), db)
    assert result.halted
    assert [c["result"] for c in result.bar_cycles] == ["missed_overdue"]


def test_holiday_and_weekend_do_not_count_as_sessions(setup):
    _, _, clock, rc, db = setup
    clock.now = datetime(2024, 7, 4, 20, tzinfo=UTC)
    result = make_loop(setup, run_config=replace(rc, max_cycles=2)).run(bars("2024-07-04"), db)
    assert result.cycle_count == 0
    assert not result.halted


@pytest.mark.parametrize("severity", [KillSwitchSeverity.SOFT, KillSwitchSeverity.HARD])
def test_active_kill_switch_blocks_before_broker_activity(setup, severity):
    registry, exp, _, _, db = setup
    registry.set_kill_switch(exp.uuid, severity, "manual hold", set_by="ops")
    broker = FakeBroker()
    result = make_loop(setup, broker=broker).run(bars(), db)
    assert result.halted and "manual hold" in result.halt_reason
    assert broker.connections == 0 and not broker.submissions
    conn = init_db(db)
    assert conn.execute("SELECT outcome FROM paper_attempts").fetchone()[0] == "halted"
    conn.close()


def test_bad_hash_blocks_before_broker_connection(setup):
    _, _, _, rc, db = setup
    broker = FakeBroker()
    result = make_loop(setup, broker=broker, run_config=replace(rc, experiment_hash="0"*64)).run(bars(), db)
    assert result.halted and "hash mismatch" in result.halt_reason
    assert broker.connections == 0


class TestPaperRunErrorHandling:
    def test_engine_startup_failure_halts(self, setup):
        class FailingBroker(FakeBroker):
            def get_positions(self):
                raise RuntimeError("broker unreachable (offline)")
        broker = FailingBroker()
        result = make_loop(setup, broker=broker).run(bars(), setup[-1])
        assert result.halted and result.cycle_count == 0
        assert not broker.submissions
        conn = init_db(setup[-1])
        assert conn.execute("SELECT outcome FROM paper_attempts").fetchone()[0] == "halted"
        conn.close()


def test_disabled_startup_reconciliation_cannot_bypass_paper_guard(setup):
    class FailingBroker(FakeBroker):
        def get_positions(self):
            raise RuntimeError("unavailable")
    cfg = replace(_make_config(), engine=EngineConfig(startup_reconciliation_required=False))
    result = make_loop(setup, broker=FailingBroker(), config=cfg).run(bars(), setup[-1])
    assert result.halted and result.cycle_count == 0


def test_broker_disconnect_mid_run_records_incomplete_window(setup):
    registry, exp, _, rc, db = setup
    broker = FakeBroker()
    def provider():
        broker.disconnect()
        return bars("2024-04-10")
    result = make_loop(setup, broker=broker, provider=provider,
                       run_config=replace(rc, max_cycles=None, window_market_sessions=2)).run(bars(), db)
    assert result.halted
    payload = json.loads(Path(result.evidence_path).read_text())
    assert payload["passed"] is False
    assert payload["observations"]["attempts"][0]["outcome"] == "halted"
    assert registry.get(exp.uuid).promotion_status.value == "paper_ops"


def test_abrupt_restart_detects_unclosed_attempt_and_preserves_downtime(setup):
    _, _, clock, _, db = setup
    first = make_loop(setup)
    conn = init_db(db)
    ledger = PaperLedger(conn, first._identity(), clock())
    ledger.start_attempt(clock())
    ledger.bind_account("sim_account")
    conn.close()  # Simulated process death: no close_attempt/finally.
    clock.advance(30)
    result = make_loop(setup).run(bars(), db)
    assert not result.halted
    conn = init_db(db)
    attempts = conn.execute("SELECT outcome,downtime_seconds FROM paper_attempts ORDER BY rowid").fetchall()
    assert attempts[0]["outcome"] == "interrupted"
    assert attempts[0]["downtime_seconds"] == 30
    assert attempts[1]["outcome"] == "completed"
    conn.close()
    payload = json.loads(Path(result.evidence_path).read_text())
    assert payload["window"]["unplanned_interruptions"] == 1


def test_attempt_is_committed_before_connect_even_when_connect_fails(setup):
    db = setup[-1]
    class InspectingBroker(FakeBroker):
        def connect(self):
            conn = init_db(db)
            row = conn.execute("SELECT outcome,ended_at FROM paper_attempts").fetchone()
            conn.close()
            assert row is not None and row["outcome"] is None and row["ended_at"] is None
            raise RuntimeError("connect failed")
    result = make_loop(setup, broker=InspectingBroker()).run(bars(), db)
    assert result.halted and "connect failed" in result.halt_reason


@pytest.mark.parametrize("damage", ["corrupt", "checksum", "experiment", "configuration", "session"])
def test_checkpoint_corruption_and_identity_mismatch_fail_before_broker(setup, damage):
    _, _, _, _, db = setup
    loop = make_loop(setup)
    identity = loop._identity()
    payload = {"identity": identity, "halted": False, "halt_reason": None, "errors": []}
    if damage == "experiment":
        identity["experiment_uuid"] = "unrelated"
    elif damage == "configuration":
        identity["config_hash"] = "0"*64
    elif damage == "session":
        identity["session_id"] = "other"
    envelope = {"payload": payload, "sha256": "wrong" if damage == "checksum" else digest(payload)}
    db.with_suffix(".paper_run_checkpoint.json").write_text("{" if damage == "corrupt" else json.dumps(envelope))
    broker = FakeBroker()
    result = make_loop(setup, broker=broker).run(bars(), db)
    assert result.halted and "checkpoint" in result.halt_reason
    assert broker.connections == 0 and not broker.submissions


def test_resume_preserves_halt_even_without_checkpoint(setup):
    _, _, clock, rc, db = setup
    config = replace(rc, max_cycles=None, window_market_sessions=2)
    first = make_loop(setup, run_config=config)
    conn = init_db(db)
    ledger = PaperLedger(conn, first._identity(), clock())
    ledger.start_attempt(clock())
    ledger.close_attempt(clock(), "halted", "unresolved broker state")
    conn.close()
    broker = FakeBroker()
    result = make_loop(setup, broker=broker, run_config=config).run(bars(), db)
    assert result.halted and "unresolved broker state" in result.halt_reason
    assert broker.connections == 0


def test_account_identity_mismatch_on_restart_blocks_execution(setup):
    _, _, clock, _, db = setup
    conn = init_db(db)
    ledger = PaperLedger(conn, make_loop(setup)._identity(), clock())
    ledger.start_attempt(clock())
    ledger.bind_account("different-account")
    conn.close()
    broker = FakeBroker()
    result = make_loop(setup, broker=broker).run(bars(), db)
    assert result.halted and "account identity mismatch" in result.halt_reason
    assert not broker.submissions


def test_checkpoint_resume_keeps_incomplete_attempt_artifact(setup):
    _, _, clock, rc, db = setup
    config = replace(rc, max_cycles=None, window_market_sessions=2)
    first = make_loop(setup, run_config=config)
    first._bars_provider = lambda: (first._handle_sigterm(None, None) or bars())
    stopped = first.run(bars(), db)
    assert stopped.cycle_count == 1 and stopped.evidence_path is not None
    incomplete_path = stopped.evidence_path
    assert db.with_suffix(".paper_run_checkpoint.json").exists()
    clock.advance(86400)
    resumed = make_loop(setup, run_config=config).run(bars("2024-04-10"), db)
    assert not resumed.halted and resumed.cycle_count == 2
    assert not db.with_suffix(".paper_run_checkpoint.json").exists()
    assert json.loads(Path(incomplete_path).read_text())["passed"] is False
    payload = json.loads(Path(resumed.evidence_path).read_text())
    assert payload["window"]["unplanned_interruptions"] == 1
    assert payload["observations"]["attempts"][0]["downtime_seconds"] == 86400


def test_deterministic_order_ids_dedupe_resubmission_after_restart(tmp_path):
    db = tmp_path / "orders.sqlite"
    broker = FakeBroker()
    broker.connect()
    intent = OrderIntent(strategy="test", symbol="AAPL", asset_class="equity", side=OrderSide.BUY,
                         order_type=OrderType.MARKET, quantity=1.0, bar_timestamp="2024-04-09T00:00:00+00:00",
                         client_order_namespace="experiment-session-config")
    conn = init_db(db)
    first = OMS(broker, conn, EventLogger(conn, environment="paper")).create_and_submit(intent)
    conn.close()
    conn = init_db(db)
    second = OMS(broker, conn, EventLogger(conn, environment="paper")).create_and_submit(intent)
    assert first == second
    assert broker.submissions == [first]
    assert conn.execute("SELECT COUNT(*) FROM orders_live").fetchone()[0] == 1
    conn.close()


def test_immutable_completed_session_cannot_trade_again(setup):
    _, _, _, _, db = setup
    result = make_loop(setup).run(bars(), db)
    assert not result.halted
    broker = FakeBroker()
    repeated = make_loop(setup, broker=broker).run(bars(), db)
    assert repeated.halted and "immutable" in repeated.halt_reason
    assert broker.connections == 0


def test_operator_overrides_are_notes_not_trades_or_drill_proof(setup):
    _, _, _, rc, db = setup
    claimed = replace(rc, window_trades=1000, insufficient_activity_override_approved=True,
                      kill_switch_drill={"new_orders_blocked": True, "kill_switch_drill_evidence_exists": True},
                      slippage_samples=({"actual_slippage_bps": 1, "expected_slippage_bps": 5},))
    result = make_loop(setup, run_config=claimed).run(bars(), db)
    payload = json.loads(Path(result.evidence_path).read_text())
    assert payload["window"]["trades"] == 0
    assert payload["slippage_samples"] == []
    assert payload["observations"]["drill_events"] == []


def test_process_death_after_submission_does_not_resubmit_on_restart(setup):
    _, _, clock, _, db = setup
    broker = FakeBroker()
    broker.connect()
    initial = make_loop(setup, broker=broker)
    conn = init_db(db)
    ledger = PaperLedger(conn, initial._identity(), clock())
    ledger.start_attempt(clock())
    ledger.bind_account("sim_account")
    watermark = str(bars().index[-1])
    decision_id = f"paper:{ledger.identity['binding_digest']}:{watermark}"
    ledger.record_cycle({
        "cycle_key": "2024-04-09", "market_session": "2024-04-09",
        "expected_at": clock().isoformat(), "deadline_at": (clock()+timedelta(seconds=60)).isoformat(),
        "started_at": clock().isoformat(), "input_data_watermark": watermark, "result": "started",
        "decision_record_id": decision_id, "broker_sync_record_id": "sync-before-crash",
    }, clock())
    ledger.record_reference_prices("2024-04-09", {"AAPL": 150.0}, clock())
    intent = OrderIntent(
        strategy="test", symbol="AAPL", asset_class="equity", side=OrderSide.BUY,
        order_type=OrderType.MARKET, quantity=1.0, bar_timestamp=watermark,
        correlation_id=decision_id, client_order_namespace=ledger.identity["binding_digest"],
    )
    oid = OMS(broker, conn, EventLogger(conn, environment="paper")).create_and_submit(intent)
    conn.close()  # No ledger capture, checkpoint or attempt-close has happened.
    clock.advance(10)
    resumed = make_loop(setup, broker=broker).run(bars(), db)
    assert not resumed.halted
    assert broker.submissions == [oid]
    conn = init_db(db)
    assert conn.execute("SELECT outcome FROM paper_attempts ORDER BY rowid LIMIT 1").fetchone()[0] == "interrupted"
    assert conn.execute("SELECT result FROM paper_cycles").fetchone()[0] == "blocked"
    assert conn.execute("SELECT COUNT(*) FROM paper_session_orders").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM paper_fills").fetchone()[0] == 1
    conn.close()
