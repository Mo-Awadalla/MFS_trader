"""Deterministic paper-loop recovery using fake brokers and real temporary SQLite."""
from __future__ import annotations

import json
import multiprocessing
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
import responses

from config.loader import load_config
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
from engine.paper_guard import PaperRunnerOwnership
from engine.paper_run import PaperRunConfig, PaperRunLoop
from engine.paper_strategy import BROKER_PAPER_EXECUTION_MODE
from execution.alpaca.adapter import AlpacaAdapter
from execution.base import OrderSide, OrderType
from execution.oms import OMS, OrderIntent
from execution.sim_broker.broker import SimBroker
from experiments.artifacts import ArtifactManager
from experiments.kill_switch import KillSwitchSeverity
from experiments.models import ExperimentDraft, PromotionStatus
from experiments.registry import ExperimentRegistry
from storage.event_logger import EventLogger
from storage.schema import init_db
from strategies.ma.signal import MAParams
from tests.qualification import enter_paper_ops
from tests.unit.test_paper_evidence import paper_experiment
from tests.unit.test_paper_strategy import snapshot_for_config


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
    ownership = PaperRunnerOwnership(db)
    ownership.acquire()
    ledger.start_attempt(clock(), ownership)
    ledger.bind_account("sim_account")
    conn.close()  # Simulated process death: no close_attempt/finally.
    ownership.release()
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
    ownership = PaperRunnerOwnership(db)
    ownership.acquire()
    ledger.start_attempt(clock(), ownership)
    ledger.close_attempt(clock(), "halted", "unresolved broker state")
    conn.close()
    ownership.release()
    broker = FakeBroker()
    result = make_loop(setup, broker=broker, run_config=config).run(bars(), db)
    assert result.halted and "unresolved broker state" in result.halt_reason
    assert broker.connections == 0


def test_account_identity_mismatch_on_restart_blocks_execution(setup):
    _, _, clock, _, db = setup
    conn = init_db(db)
    ledger = PaperLedger(conn, make_loop(setup)._identity(), clock())
    ownership = PaperRunnerOwnership(db)
    ownership.acquire()
    ledger.start_attempt(clock(), ownership)
    ledger.bind_account("different-account")
    conn.close()
    ownership.release()
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
    ownership = PaperRunnerOwnership(db)
    ownership.acquire()
    ledger.start_attempt(clock(), ownership)
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
    ownership.release()
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


@pytest.mark.parametrize("separate_database", [False, True])
def test_overlapping_runner_cannot_touch_active_attempt_or_finalize(setup, separate_database):
    _, _, _, _, db = setup
    contender = FakeBroker()
    class OverlappingBroker(FakeBroker):
        def connect(self):
            other_db = db.with_name("other.sqlite") if separate_database else db
            refused = make_loop(setup, broker=contender).run(bars(), other_db)
            assert refused.halted and "already owns" in refused.halt_reason
            assert refused.evidence_path is None
            assert contender.connections == 0
            conn = init_db(db)
            attempts = conn.execute("SELECT outcome,ended_at FROM paper_attempts").fetchall()
            assert [(r["outcome"], r["ended_at"]) for r in attempts] == [(None, None)]
            conn.close()
            super().connect()
    result = make_loop(setup, broker=OverlappingBroker()).run(bars(), db)
    assert not result.halted
    conn = init_db(db)
    assert [r[0] for r in conn.execute("SELECT outcome FROM paper_attempts")] == ["completed"]
    assert conn.execute("SELECT result FROM paper_cycles").fetchone()[0] == "completed"
    conn.close()


def _hold_unclosed_attempt(db, identity, now, pipe):
    ownership = PaperRunnerOwnership(db)
    ownership.acquire()
    conn = init_db(db)
    ledger = PaperLedger(conn, identity, now)
    ledger.start_attempt(now, ownership)
    pipe.send(ledger.attempt_id)
    pipe.recv()  # Parent kills this process; no Python cleanup runs.


def test_process_death_releases_ownership_but_retains_unclosed_attempt(setup):
    _, _, clock, _, db = setup
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(
        target=_hold_unclosed_attempt, args=(db, make_loop(setup)._identity(), clock(), child),
    )
    process.start()
    child.close()
    try:
        assert parent.poll(15), "child never committed its attempt"
        attempt_id = parent.recv()
        broker = FakeBroker()
        refused = make_loop(setup, broker=broker).run(bars(), db)
        assert refused.halted and broker.connections == 0
        process.kill()
        process.join(15)
        assert not process.is_alive()
        clock.advance(30)
        recovered = make_loop(setup).run(bars(), db)
        assert not recovered.halted
        conn = init_db(db)
        prior = conn.execute("SELECT outcome,downtime_seconds FROM paper_attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
        assert tuple(prior) == ("interrupted", 30.0)
        assert [r[0] for r in conn.execute("SELECT outcome FROM paper_attempts ORDER BY rowid")] == ["interrupted", "completed"]
        conn.close()
    finally:
        if process.is_alive():
            process.kill()
            process.join(15)
        parent.close()


def capped_config(*, per_order=25.0, session=100.0, exposure=100.0):
    return replace(
        _make_config(),
        portfolio=PortfolioConfig(min_notional_delta=0),
        live_deployment=LiveDeploymentConfig(
            max_notional_per_order=per_order, max_paper_session_notional=session,
            max_open_paper_exposure=exposure,
        ),
    )


def test_actual_risk_sized_order_cannot_bypass_tiny_cap(setup):
    broker = FakeBroker()
    result = make_loop(
        setup, broker=broker, config=capped_config(), strategy=lambda bars, params: {"AAPL": 1.0},
    ).run(bars(), setup[-1])
    assert result.halted and "max_notional_per_order" in result.halt_reason
    assert broker.submissions == []
    conn = init_db(setup[-1])
    assert conn.execute("SELECT COUNT(*) FROM orders_live").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM paper_order_reservations").fetchone()[0] == 0
    assert conn.execute("SELECT outcome FROM paper_attempts").fetchone()[0] == "halted"
    conn.close()


@pytest.mark.parametrize("cap_name", ["session", "exposure"])
def test_durable_caps_block_second_order_before_oms(setup, cap_name):
    _, _, clock, rc, db = setup
    broker = FakeBroker()
    broker._config.slippage_pct = 0
    config = capped_config(**{cap_name: 30.0})
    config = replace(config, portfolio=replace(config.portfolio, execution_mode="continuous_rebalance"))
    def strategy(frame, params):
        return {"AAPL": 0.01 if frame.index[-1].day == 9 else 0.02}
    def provider():
        clock.advance(86400)
        return bars("2024-04-10")
    result = make_loop(
        setup, broker=broker, config=config, strategy=strategy, provider=provider,
        run_config=replace(rc, max_cycles=2),
    ).run(bars(), db)
    expected = "max_paper_session_notional" if cap_name == "session" else "max_open_paper_exposure"
    assert result.halted and expected in result.halt_reason
    assert len(broker.submissions) == 1
    conn = init_db(db)
    reservation = conn.execute("SELECT reserved_notional,observed_notional,client_order_id FROM paper_order_reservations").fetchall()
    assert len(reservation) == 1
    assert reservation[0]["reserved_notional"] == pytest.approx(20)
    assert reservation[0]["observed_notional"] == pytest.approx(20)
    assert reservation[0]["client_order_id"] == broker.submissions[0]
    conn.close()


def test_resumed_session_cannot_reset_cumulative_budget(setup):
    _, _, clock, rc, db = setup
    broker = FakeBroker()
    broker._config.slippage_pct = 0
    config = capped_config(session=30.0)
    run_config = replace(rc, max_cycles=None, window_market_sessions=2)
    def strategy(frame, params):
        return {"AAPL": 0.01 if frame.index[-1].day == 9 else 0.0}
    first = make_loop(setup, broker=broker, config=config, strategy=strategy, run_config=run_config)
    first._bars_provider = lambda: (first._handle_sigterm(None, None) or bars())
    stopped = first.run(bars(), db)
    assert not stopped.halted and len(broker.submissions) == 1
    clock.advance(86400)
    resumed = make_loop(
        setup, broker=broker, config=config, strategy=strategy, run_config=run_config,
    ).run(bars("2024-04-10"), db)
    assert resumed.halted and "max_paper_session_notional" in resumed.halt_reason
    assert len(broker.submissions) == 1
    conn = init_db(db)
    assert conn.execute("SELECT SUM(reserved_notional) FROM paper_order_reservations").fetchone()[0] == pytest.approx(20)
    assert [r[0] for r in conn.execute("SELECT outcome FROM paper_attempts ORDER BY rowid")] == ["stopped", "halted"]
    conn.close()


def test_actual_fill_not_reference_quote_consumes_session_budget(setup):
    broker = FakeBroker()
    broker._config.slippage_pct = 0.5
    result = make_loop(
        setup, broker=broker, config=capped_config(), strategy=lambda bars, params: {"AAPL": 0.01},
    ).run(bars(), setup[-1])
    assert result.halted and "observed fill" in result.halt_reason
    conn = init_db(setup[-1])
    row = conn.execute("SELECT reserved_notional,observed_notional FROM paper_order_reservations").fetchone()
    assert row["reserved_notional"] == pytest.approx(20)
    assert row["observed_notional"] == pytest.approx(30)
    assert len(broker.submissions) == 1
    conn.close()


def test_durable_reservation_precedes_broker_effect_and_blocks_uncertain_resume(setup):
    _, _, _, rc, db = setup
    class CrashingBroker(FakeBroker):
        def submit_order(self, request):
            conn = init_db(db)
            reservation = conn.execute("SELECT quantity,reference_price,client_order_id FROM paper_order_reservations").fetchone()
            conn.close()
            assert reservation["quantity"] == request.quantity
            assert reservation["reference_price"] == 150
            assert reservation["client_order_id"] is None
            raise RuntimeError("unknown submission outcome")
    broker = CrashingBroker()
    run_config = replace(rc, max_cycles=None, window_market_sessions=2)
    failed = make_loop(
        setup, broker=broker, config=capped_config(), run_config=run_config,
        strategy=lambda bars, params: {"AAPL": 0.01},
    ).run(bars(), db)
    assert failed.halted
    replacement = FakeBroker()
    resumed = make_loop(
        setup, broker=replacement, config=capped_config(), run_config=run_config,
        strategy=lambda bars, params: {"AAPL": 0.01},
    ).run(bars(), db)
    assert resumed.halted and replacement.connections == 0 and replacement.submissions == []


@pytest.fixture
def qualified_ma(tmp_path):
    config = load_config("builtin:paper_shakedown", load_env=False)
    config = replace(config, live_deployment=replace(
        config.live_deployment, max_notional_per_order=25,
        max_paper_session_notional=100, max_open_paper_exposure=100,
    ))
    parameters = asdict(MAParams())
    snapshot = snapshot_for_config(config, parameters=parameters, symbols=("AAPL",))
    snapshot = replace(snapshot, execution_mode=BROKER_PAPER_EXECUTION_MODE)
    registry = ExperimentRegistry(tmp_path / "qualified-experiments")
    exp = registry.create(ExperimentDraft(label="synthetic-runtime-admission", snapshot=snapshot))
    for status in (PromotionStatus.VALIDATION_RUNNING, PromotionStatus.VALIDATION_PASSED):
        exp = registry.transition_promotion_status(exp.uuid, status)
    exp = enter_paper_ops(registry, exp.uuid)
    run_config = PaperRunConfig(
        experiment_uuid=exp.uuid, experiment_hash=exp.experiment_hash, experiment_root=registry.root,
        session_id="qualified", max_cycles=1, data_grace_seconds=60,
    )
    yield config, parameters, run_config, Clock(), tmp_path / "qualified.sqlite"
    registry.close()


@pytest.mark.parametrize("mismatch", ["strategy", "parameters", "universe", "cost"])
def test_direct_loop_binds_qualified_hypothesis_before_factory(qualified_ma, mismatch):
    config, parameters, run_config, clock, db = qualified_ma
    name = config.strategy_name
    if mismatch == "strategy":
        name = "unrelated"
    elif mismatch == "parameters":
        parameters = {**parameters, "fast_ma_window": parameters["fast_ma_window"] + 1}
    elif mismatch == "universe":
        run_config = replace(run_config, symbols=("MSFT",))
    else:
        config = replace(config, cost_model=replace(config.cost_model, commission_pct=0.123))
    calls = []
    def factory():
        calls.append("credentials")
        raise AssertionError("mismatched hypothesis reached credentials")
    result = PaperRunLoop(
        config=config, broker=None, broker_factory=factory, strategy_fn=lambda frame, params: {},
        strategy_name=name, strategy_params=parameters, run_config=run_config, clock=clock,
    ).run(bars(), db)
    assert result.halted and calls == []
    conn = init_db(db)
    assert conn.execute("SELECT outcome FROM paper_attempts").fetchone()[0] == "halted"
    conn.close()


def test_deferred_simulation_cannot_be_labeled_as_broker_paper(qualified_ma):
    config, parameters, run_config, clock, db = qualified_ma
    broker = FakeBroker()
    result = PaperRunLoop(
        config=config, broker=None, broker_factory=lambda: broker,
        strategy_fn=lambda frame, params: {}, strategy_name=config.strategy_name,
        strategy_params=parameters, run_config=run_config, clock=clock,
    ).run(bars(), db)
    assert result.halted and "disagrees" in result.halt_reason
    assert broker.connections == 0
    conn = init_db(db)
    assert conn.execute("SELECT account_fingerprint FROM paper_sessions").fetchone()[0] == "unverified"
    conn.close()


@responses.activate
def test_real_adapter_position_http_failure_blocks_loop_with_durable_attempt(qualified_ma):
    config, parameters, run_config, clock, db = qualified_ma
    responses.get(
        "https://paper-api.alpaca.markets/v2/account",
        json={"id": "offline-account", "cash": "10000", "equity": "10000", "currency": "USD"},
    )
    responses.get("https://paper-api.alpaca.markets/v2/positions", status=500, json={"error": "offline"})
    result = PaperRunLoop(
        config=config,
        broker=AlpacaAdapter(api_key="offline-key", api_secret="offline-secret"),
        strategy_fn=lambda frame, params: {"AAPL": 1.0}, strategy_name=config.strategy_name,
        strategy_params=parameters, run_config=run_config, clock=clock,
    ).run(bars(), db)
    assert result.halted and result.cycle_count == 0
    assert any(call.request.url.endswith("/v2/positions") for call in responses.calls)
    assert all(call.request.method == "GET" for call in responses.calls)
    conn = init_db(db)
    assert conn.execute("SELECT outcome FROM paper_attempts").fetchone()[0] == "halted"
    assert conn.execute("SELECT COUNT(*) FROM orders_live").fetchone()[0] == 0
    conn.close()


def test_reducing_position_does_not_double_count_open_exposure(setup):
    _, _, clock, rc, db = setup
    broker = FakeBroker()
    broker._config.slippage_pct = 0
    def provider():
        clock.advance(86400)
        return bars("2024-04-10")
    result = make_loop(
        setup, broker=broker, config=capped_config(exposure=25), provider=provider,
        run_config=replace(rc, max_cycles=2),
        strategy=lambda frame, params: {"AAPL": 0.01 if frame.index[-1].day == 9 else 0},
    ).run(bars(), db)
    assert not result.halted and len(broker.submissions) == 2
    assert broker.get_positions() == []


def test_checkpoint_does_not_reuse_shared_temporary_name(setup):
    _, _, _, rc, db = setup
    shared_temp = db.with_suffix(".paper_run_checkpoint.json.tmp")
    shared_temp.write_bytes(b"previous process temporary evidence")
    loop = make_loop(setup, run_config=replace(rc, max_cycles=None, window_market_sessions=2))
    loop._bars_provider = lambda: (loop._handle_sigterm(None, None) or bars())
    result = loop.run(bars(), db)
    assert not result.halted
    checkpoint = json.loads(db.with_suffix(".paper_run_checkpoint.json").read_text())
    assert checkpoint["sha256"] == digest(checkpoint["payload"])
    assert shared_temp.read_bytes() == b"previous process temporary evidence"


def test_qualified_loop_uses_canonical_strategy_not_injected_callback(qualified_ma):
    config, parameters, run_config, clock, db = qualified_ma
    class PaperBroker(FakeBroker):
        _base_url = "https://paper-api.alpaca.markets"
        _data_url = "https://data.alpaca.markets"

        @property
        def name(self):
            return "alpaca"

        def get_open_orders(self):
            return []

    called = []
    def unrelated_strategy(frame, params):
        called.append("unqualified strategy")
        return {"AAPL": 1.0}
    broker = PaperBroker()
    result = PaperRunLoop(
        config=config, broker=broker, strategy_fn=unrelated_strategy,
        strategy_name=config.strategy_name, strategy_params=parameters,
        run_config=run_config, clock=clock,
    ).run(bars(), db)
    # One bar is MA warmup, not an arbitrary caller's buy instruction.
    assert not result.halted and result.cycle_count == 1
    assert called == [] and broker.submissions == []


def test_direct_broker_paper_runtime_cannot_submit_without_durable_guard(tmp_path):
    from engine.runtime import TradingEngine

    class PaperBroker(FakeBroker):
        @property
        def name(self):
            return "alpaca"

    broker = PaperBroker()
    conn = init_db(tmp_path / "direct.sqlite")
    engine = TradingEngine(
        config=capped_config(), conn=conn, broker=broker,
        strategy_fn=lambda frame, params: {"AAPL": 0.01}, strategy_name="test",
    )
    with pytest.raises(ValueError, match="requires durable paper admission"):
        engine.process_bar(bars(), {"AAPL": 150.0}, bar_timestamp=str(bars().index[-1]))
    assert broker.submissions == []
    assert conn.execute("SELECT COUNT(*) FROM orders_live").fetchone()[0] == 0
    conn.close()


def test_runner_ownership_extends_through_finalization_and_disconnect(setup):
    _, _, _, _, db = setup
    refused = []
    class FinalizingBroker(FakeBroker):
        def disconnect(self):
            refused.append(make_loop(setup).run(bars(), db))
            super().disconnect()
    result = make_loop(setup, broker=FinalizingBroker()).run(bars(), db)
    assert not result.halted
    assert len(refused) == 1 and "already owns" in refused[0].halt_reason
    assert refused[0].evidence_path is None
    conn = init_db(db)
    assert [r[0] for r in conn.execute("SELECT outcome FROM paper_attempts")] == ["completed"]
    conn.close()


def test_resume_budget_charges_actual_fill_not_only_reserved_quote(setup):
    _, _, clock, rc, db = setup
    broker = FakeBroker()
    broker._config.slippage_pct = 0.1
    config = capped_config(session=41)
    config = replace(config, portfolio=replace(config.portfolio, execution_mode="continuous_rebalance"))
    run_config = replace(rc, max_cycles=None, window_market_sessions=2)
    def strategy(frame, params):
        return {"AAPL": 0.01 if frame.index[-1].day == 9 else 0.02}
    first = make_loop(setup, broker=broker, config=config, strategy=strategy, run_config=run_config)
    first._bars_provider = lambda: (first._handle_sigterm(None, None) or bars())
    stopped = first.run(bars(), db)
    assert not stopped.halted and len(broker.submissions) == 1
    clock.advance(86400)
    result = make_loop(
        setup, broker=broker, config=config, strategy=strategy, run_config=run_config,
    ).run(bars("2024-04-10"), db)
    assert result.halted and "max_paper_session_notional" in result.halt_reason
    assert len(broker.submissions) == 1
    conn = init_db(db)
    row = conn.execute("SELECT reserved_notional,observed_notional FROM paper_order_reservations").fetchone()
    assert row["reserved_notional"] == pytest.approx(20)
    assert row["observed_notional"] == pytest.approx(22)
    conn.close()
