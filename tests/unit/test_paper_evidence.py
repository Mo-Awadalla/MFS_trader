"""Offline paper qualification: real SQLite, declared calendar, attributable rows."""
from __future__ import annotations

import copy
import json
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from engine.paper_calendar import XNYS_PAPER_CALENDAR, CalendarCoverageError
from engine.paper_evidence import PaperLedger, derive_observations, digest
from engine.paper_guard import PaperRunnerOwnership
from engine.paper_session import (
    PaperSessionGateError,
    build_and_write_paper_ops_pass_report_set,
    evaluate_paper_ops_pass_session,
    write_paper_ops_smoke_report,
)
from experiments.artifacts import ArtifactManager
from experiments.backfill import build_bb_aapl_1d_default_snapshot
from experiments.models import ExperimentDraft, PromotionStatus
from experiments.registry import ExperimentRegistry
from storage.repository import upsert_order
from storage.schema import init_db
from tests.qualification import enter_paper_ops

START = datetime(2024, 4, 1, 13, 30, tzinfo=UTC)
END = datetime(2024, 5, 1, 20, 0, tzinfo=UTC)


def paper_experiment(registry):
    exp = registry.create(ExperimentDraft(label="paper-evidence", snapshot=build_bb_aapl_1d_default_snapshot()))
    for status in (PromotionStatus.VALIDATION_RUNNING, PromotionStatus.VALIDATION_PASSED):
        exp = registry.transition_promotion_status(exp.uuid, status)
    return enter_paper_ops(registry, exp.uuid)


def qualified_session(registry, exp, db_path, session_id="pass-session", environment="alpaca_paper",
                      order_count=100, session_kind="paper_ops_pass",
                      account_id="fake-paper-account-never-exported"):
    """Synthetic temporary events only: never real broker-paper qualification."""
    conn = init_db(db_path)
    identity = {
        "experiment_uuid": exp.uuid, "experiment_hash": exp.experiment_hash,
        "session_id": session_id, "session_kind": session_kind,
        "config_hash": digest({"fixture_config": 1}), "code_version": digest("fixture-execution"),
        "broker_environment": environment, "calendar_id": XNYS_PAPER_CALENDAR.calendar_id,
        "calendar_version": XNYS_PAPER_CALENDAR.version, "bar_frequency": "1d",
        "data_grace_seconds": 64800.0, "expected_slippage_bps": 5.0,
    }
    ledger = PaperLedger(conn, identity, START)
    ownership = PaperRunnerOwnership(db_path)
    ownership.acquire()
    ledger.start_attempt(START, ownership)
    ledger.bind_account(account_id)
    cycles = XNYS_PAPER_CALENDAR.expected_cycles("1d", START, END)
    for cycle in cycles:
        watermark = f"{cycle.market_session} 00:00:00+00:00"
        ledger.record_cycle({
            "cycle_key": cycle.cycle_key, "market_session": cycle.market_session,
            "expected_at": cycle.expected_at.isoformat(), "deadline_at": cycle.deadline(timedelta(hours=18)).isoformat(),
            "started_at": cycle.expected_at.isoformat(), "completed_at": cycle.expected_at.isoformat(),
            "input_data_watermark": watermark, "result": "completed",
            "decision_record_id": f"paper:{ledger.identity['binding_digest']}:{watermark}",
            "broker_sync_record_id": f"sync-{cycle.cycle_key}",
        }, cycle.expected_at)
    cycle = cycles[0]
    correlation = ledger.rows("paper_cycles")[0]["decision_record_id"]
    ledger.record_reference_prices(cycle.cycle_key, {"AAPL": 100.0}, cycle.expected_at)
    for i in range(order_count):
        upsert_order(conn, {
            "client_order_id": f"{session_id}-order-{i}", "broker_order_id": f"broker-{i}",
            "broker": "alpaca" if environment == "alpaca_paper" else "sim_broker",
            "account_id": account_id, "environment": "paper",
            "strategy": "test", "symbol": "AAPL", "asset_class": "equity", "side": "buy",
            "order_type": "market", "time_in_force": "day", "requested_qty": 1.0,
            "filled_qty": 1.0, "remaining_qty": 0.0, "avg_fill_price": 100.04,
            "order_state": "FILLED", "reconciliation_status": "MATCHED",
            "bar_timestamp": f"{cycle.market_session}T00:00:00+00:00", "correlation_id": correlation,
            "version": "fixture-execution",
        })
    ledger.capture_orders(cycle.expected_at)
    ledger.record_kill_switch_block("offline observed guard outcome", cycle.expected_at)
    ledger.close_attempt(END, "completed", None)
    evidence = ledger.snapshot(END)
    observed = derive_observations(evidence, 5.0)
    session = {
        "experiment_uuid": exp.uuid, "experiment_hash": exp.experiment_hash, "session_id": session_id,
        "session_kind": session_kind, "session_type": "paper_run", "portfolio_state": "KNOWN",
        "passed": True, "blockers": [],
        "identity": evidence["identity"], "observations": evidence, "expected_slippage_bps": 5.0,
        "bar_cycles": evidence["cycles"], "window": observed["window"],
        "bar_cycle_report": observed["bar_cycle_report"], "slippage_samples": observed["slippage_samples"],
    }
    conn.close()
    ownership.release()
    return session


def write_qualified_evidence(registry, exp, session_id="pass-session", *, missing_prerequisite=None):
    """Write synthetic test qualification, including both retained prerequisites."""
    db_path = registry.root / f"{session_id}.sqlite"
    session = qualified_session(registry, exp, db_path, session_id)
    ArtifactManager(registry.root).write_paper_session_json(exp.uuid, session_id, session)
    build_and_write_paper_ops_pass_report_set(registry=registry, experiment_uuid=exp.uuid,
                                            session_id=session_id, db_path=db_path)
    write_prerequisite_evidence(registry, exp, missing=missing_prerequisite)
    return session_id


def write_prerequisite_evidence(registry, exp, *, missing=None, smoke_environment="alpaca_paper",
                                smoke_account="fake-paper-account-never-exported"):
    """Existing artifact formats backed by synthetic events, never broker access."""
    artifacts = ArtifactManager(registry.root)
    if missing != "simulated_drills":
        artifacts.write_paper_session_json(exp.uuid, "sim-drills", {
            "experiment_uuid": exp.uuid, "experiment_hash": exp.experiment_hash,
            "session_id": "sim-drills", "session_kind": "paper_ops_smoke",
            "session_type": "simulated_drills", "broker": "sim_broker",
            "passed": True, "blockers": [],
            "lifecycle_gates": {"status_is_paper_ops": True, "hash_verified": True, "kill_switch_clear": True},
            "caps": {"max_notional_per_order": 25.0, "max_paper_session_notional": 100.0,
                     "max_open_paper_exposure": 100.0},
            "details": {"drills": {
                "reject": {"passed": True, "status": "REJECTED"},
                "timeout": {"passed": True, "status": "TIMEOUT"},
                "reconciliation": {"passed": True, "mismatch_detected": True,
                                   "positions": [{"symbol": "AAPL", "quantity": 2.0}]},
            }},
        })
    if missing != "alpaca_paper_smoke":
        smoke = qualified_session(
            registry, exp, registry.root / "broker-smoke.sqlite", "broker-smoke",
            environment=smoke_environment, account_id=smoke_account,
            order_count=0, session_kind="paper_ops_smoke",
        )
        smoke["session_type"] = "alpaca_paper_smoke"
        artifacts.write_paper_session_json(exp.uuid, "broker-smoke", smoke)
        write_paper_ops_smoke_report(
            registry=registry, experiment_uuid=exp.uuid, session_id="broker-smoke",
        )


@pytest.fixture
def campaign(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments")
    exp = paper_experiment(registry)
    db_path = tmp_path / "paper.sqlite"
    session = qualified_session(registry, exp, db_path)
    yield registry, exp, db_path, session
    registry.close()


def test_filled_orders_not_supplied_totals_or_sample_count(campaign):
    registry, exp, db, session = campaign
    assert session["window"]["trades"] == 100
    session["window"]["trades"] = 1000
    ArtifactManager(registry.root).write_paper_session_json(exp.uuid, "pass-session", session)
    with pytest.raises(PaperSessionGateError, match="observed activity"):
        build_and_write_paper_ops_pass_report_set(registry=registry, experiment_uuid=exp.uuid,
                                                session_id="pass-session", db_path=db)


def test_duplicate_fill_polling_and_partial_fills_do_not_inflate_trades(campaign):
    _, _, db, session = campaign
    conn = init_db(db)
    identity = session["identity"]
    ledger = PaperLedger(conn, identity, END)
    ledger.capture_orders(END)
    ledger.capture_orders(END)
    assert len(ledger.rows("paper_fills")) == 100
    conn.execute("UPDATE orders_live SET order_state='PARTIALLY_FILLED',filled_qty=0.5,remaining_qty=0.5 WHERE client_order_id='pass-session-order-0'")
    conn.execute(
        "UPDATE paper_fills SET fill_id=?,fill_qty=0.5,cumulative_filled_qty=0.5 WHERE client_order_id='pass-session-order-0'",
        (digest(["pass-session-order-0", 0.5]),),
    )
    conn.commit()
    partial = derive_observations(ledger.snapshot(END), 5)
    assert partial["window"]["trades"] == 99
    conn.execute("UPDATE orders_live SET order_state='FILLED',filled_qty=1,remaining_qty=0 WHERE client_order_id='pass-session-order-0'")
    conn.commit()
    ledger.capture_orders(END)
    ledger.capture_orders(END)
    # An additional partial increment is one fill observation, not another trade.
    complete = derive_observations(ledger.snapshot(END), 5)
    assert complete["window"]["trades"] == 100
    assert len(complete["slippage_samples"]) == 101
    conn.close()


@pytest.mark.parametrize("table,key,value", [
    ("fills", "session_id", "unrelated"), ("fills", "experiment_uuid", "wrong-experiment"),
    ("fills", "broker_environment", "sim_broker"), ("orders", "environment", "live"),
    ("orders", "broker", "sim_broker"), ("order_links", "session_id", "unrelated"),
    ("reference_prices", "experiment_uuid", "unrelated"),
])
def test_rejects_cross_identity_contamination(campaign, table, key, value):
    evidence = copy.deepcopy(campaign[3]["observations"])
    evidence[table][0][key] = value
    with pytest.raises(ValueError, match="unrelated"):
        derive_observations(evidence, 5)


def test_unrelated_database_orders_are_not_imported(campaign):
    _, _, db, session = campaign
    conn = init_db(db)
    conn.execute("UPDATE orders_live SET correlation_id='other-session' WHERE client_order_id='pass-session-order-0'")
    conn.commit()
    ledger = PaperLedger(conn, session["identity"], END)
    with pytest.raises(ValueError, match="decision attribution"):
        derive_observations(ledger.snapshot(END), 5)
    conn.close()


@pytest.mark.parametrize("mutation", ["duplicate_fill", "no_reference", "duplicate_cycle", "stale_watermark"])
def test_rejects_unattributable_or_repeated_activity(campaign, mutation):
    evidence = copy.deepcopy(campaign[3]["observations"])
    if mutation == "duplicate_fill":
        evidence["fills"].append(dict(evidence["fills"][0]))
    elif mutation == "no_reference":
        evidence["reference_prices"] = []
    elif mutation == "duplicate_cycle":
        evidence["cycles"].append(dict(evidence["cycles"][0]))
    else:
        evidence["cycles"][1]["input_data_watermark"] = evidence["cycles"][0]["input_data_watermark"]
    with pytest.raises(ValueError):
        derive_observations(evidence, 5)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_evidence_never_qualifies(campaign, bad):
    registry, exp, _, session = campaign
    session["observations"]["fills"][0]["fill_price"] = bad
    with pytest.raises(ValueError):
        derive_observations(session["observations"], 5)
    # Malformed imported artifacts fail the gate even if a report claims PASS.
    path = ArtifactManager(registry.root).paper_session_path(exp.uuid, "pass-session")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(session))
    result = evaluate_paper_ops_pass_session(registry=registry, experiment=exp, session_id="pass-session")
    assert result["passed"] is False


def test_missing_drill_proof_and_truthy_notes_do_not_pass(campaign):
    registry, exp, db, session = campaign
    session["observations"]["drill_events"] = []
    session["kill_switch_drill"] = {"kill_switch_drill_evidence_exists": True, "new_orders_blocked": True}
    conn = init_db(db)
    conn.execute("DELETE FROM paper_drill_events")
    conn.commit()
    conn.close()
    artifacts = ArtifactManager(registry.root)
    artifacts.write_paper_session_json(exp.uuid, "pass-session", session)
    build_and_write_paper_ops_pass_report_set(registry=registry, experiment_uuid=exp.uuid,
                                            session_id="pass-session", db_path=db)
    result = evaluate_paper_ops_pass_session(registry=registry, experiment=exp, session_id="pass-session")
    assert result["passed"] is False
    assert any("kill_switch_drill_report" in b for b in result["blockers"])


def test_simulation_cannot_qualify_as_broker_paper(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments")
    try:
        exp = paper_experiment(registry)
        db = tmp_path / "sim.sqlite"
        session = qualified_session(registry, exp, db, environment="sim_broker")
        ArtifactManager(registry.root).write_paper_session_json(exp.uuid, "pass-session", session)
        build_and_write_paper_ops_pass_report_set(registry=registry, experiment_uuid=exp.uuid,
                                                session_id="pass-session", db_path=db)
        result = evaluate_paper_ops_pass_session(registry=registry, experiment=exp, session_id="pass-session")
        assert not result["passed"]
        assert registry.get(exp.uuid).promotion_status == PromotionStatus.PAPER_OPS
    finally:
        registry.close()


def test_complete_observed_campaign_recommends_but_does_not_promote(campaign):
    registry, exp, db, session = campaign
    artifacts = ArtifactManager(registry.root)
    artifacts.write_paper_session_json(exp.uuid, "pass-session", session)
    build_and_write_paper_ops_pass_report_set(registry=registry, experiment_uuid=exp.uuid,
                                            session_id="pass-session", db_path=db)
    write_prerequisite_evidence(registry, exp)
    result = evaluate_paper_ops_pass_session(registry=registry, experiment=exp, session_id="pass-session")
    assert result["passed"] is True
    assert registry.get(exp.uuid).promotion_status == PromotionStatus.PAPER_OPS
    assert "fake-paper-account-never-exported" not in artifacts.paper_session_path(exp.uuid, "pass-session").read_text()


def test_calendar_holidays_weekends_early_close_and_dst():
    cal = XNYS_PAPER_CALENDAR
    assert not cal.is_session(date(2024, 7, 4))
    assert not cal.is_session(date(2024, 7, 6))
    assert not cal.is_session(date(2025, 1, 9))
    assert not cal.is_session(date(2026, 7, 3))
    early = cal.session(date(2024, 11, 29))
    assert early.close_utc.hour == 18
    hourly = cal.expected_cycles("1h", early.open_utc, early.close_utc)
    assert len(hourly) == 4
    assert hourly[-1].expected_at == early.close_utc
    before = cal.session(date(2024, 3, 8))
    after = cal.session(date(2024, 3, 11))
    assert before.open_utc.hour == 14 and after.open_utc.hour == 13
    sessions = cal.expected_cycles("1d", before.open_utc, after.close_utc)
    assert [c.market_session for c in sessions] == ["2024-03-08", "2024-03-11"]
    with pytest.raises(CalendarCoverageError):
        cal.is_session(date(2027, 1, 4))
    assert cal.cycle_for_bar("1d", pd.Timestamp("2024-07-04", tz="UTC")) is None


def test_absent_expected_session_reduces_completion(campaign):
    evidence = copy.deepcopy(campaign[3]["observations"])
    evidence["cycles"].pop()
    observed = derive_observations(evidence, 5)
    assert observed["bar_cycle_report"]["unexplained_missed_cycles"] == 1
    assert observed["bar_cycle_report"]["bar_cycle_completion"] < 0.995


def test_terminal_attempt_and_cycle_writes_are_fenced_after_takeover(campaign):
    _, _, db, session = campaign
    conn = init_db(db)
    first_owner = PaperRunnerOwnership(db)
    first_owner.acquire()
    first = PaperLedger(conn, session["identity"], END)
    first.start_attempt(END, first_owner)
    cycle = {
        "cycle_key": "2024-05-02", "market_session": "2024-05-02",
        "expected_at": END.isoformat(), "deadline_at": END.isoformat(),
        "started_at": END.isoformat(), "result": "started",
    }
    first.record_cycle(cycle, END)
    old_attempt = first.attempt_id
    first_owner.release()  # Represents ended OS ownership, not a heartbeat guess.
    second_owner = PaperRunnerOwnership(db)
    second_owner.acquire()
    try:
        second = PaperLedger(conn, session["identity"], END + timedelta(seconds=20))
        second.start_attempt(END + timedelta(seconds=20), second_owner)
        with pytest.raises(ValueError, match="ownership"):
            first.close_attempt(END, "completed", None)
        with pytest.raises(ValueError, match="ownership"):
            first.record_cycle({**cycle, "result": "completed"}, END)
        with pytest.raises(ValueError, match="terminal or owned"):
            second.record_cycle({**cycle, "result": "completed"}, END)
        assert conn.execute("SELECT outcome FROM paper_attempts WHERE attempt_id=?", (old_attempt,)).fetchone()[0] == "interrupted"
        row = conn.execute("SELECT attempt_id,result FROM paper_cycles WHERE cycle_key='2024-05-02'").fetchone()
        assert tuple(row) == (old_attempt, "blocked")
        second.close_attempt(END + timedelta(seconds=20), "stopped", None)
        with pytest.raises(ValueError, match="no longer active"):
            second.close_attempt(END, "completed", None)
        assert conn.execute("SELECT outcome FROM paper_attempts WHERE attempt_id=?", (second.attempt_id,)).fetchone()[0] == "stopped"
    finally:
        second_owner.release()
        conn.close()


def test_one_ownership_epoch_cannot_interrupt_its_own_active_attempt(campaign):
    _, _, db, session = campaign
    conn = init_db(db)
    with PaperRunnerOwnership(db) as ownership:
        first = PaperLedger(conn, session["identity"], END)
        first.start_attempt(END, ownership)
        second = PaperLedger(conn, session["identity"], END)
        with pytest.raises(ValueError, match="already has an attempt"):
            second.start_attempt(END, ownership)
        assert conn.execute("SELECT outcome FROM paper_attempts WHERE attempt_id=?", (first.attempt_id,)).fetchone()[0] is None
        first.close_attempt(END, "stopped", None)
    conn.close()
