"""Offline paper qualification: real SQLite, declared calendar, attributable rows."""
from __future__ import annotations

import copy
import json
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from engine.paper_calendar import XNYS_PAPER_CALENDAR, CalendarCoverageError
from engine.paper_evidence import PaperLedger, derive_observations, digest
from engine.paper_session import (
    PaperSessionGateError,
    build_and_write_paper_ops_pass_report_set,
    evaluate_paper_ops_pass_session,
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


def qualified_session(registry, exp, db_path, session_id="pass-session", environment="alpaca_paper", order_count=100):
    """Seed a recorded fake-broker campaign, not precomputed activity totals."""
    conn = init_db(db_path)
    identity = {
        "experiment_uuid": exp.uuid, "experiment_hash": exp.experiment_hash,
        "session_id": session_id, "session_kind": "paper_ops_pass",
        "config_hash": digest({"fixture_config": 1}), "code_version": digest("fixture-execution"),
        "broker_environment": environment, "calendar_id": XNYS_PAPER_CALENDAR.calendar_id,
        "calendar_version": XNYS_PAPER_CALENDAR.version, "bar_frequency": "1d",
        "data_grace_seconds": 64800.0, "expected_slippage_bps": 5.0,
    }
    ledger = PaperLedger(conn, identity, START)
    ledger.start_attempt(START)
    ledger.bind_account("fake-paper-account-never-exported")
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
            "account_id": "fake-paper-account-never-exported", "environment": "paper",
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
        "session_kind": "paper_ops_pass", "session_type": "paper_run", "portfolio_state": "KNOWN", "passed": True,
        "identity": evidence["identity"], "observations": evidence, "expected_slippage_bps": 5.0,
        "bar_cycles": evidence["cycles"], "window": observed["window"],
        "bar_cycle_report": observed["bar_cycle_report"], "slippage_samples": observed["slippage_samples"],
    }
    conn.close()
    return session


def write_qualified_evidence(registry, exp, session_id="pass-session"):
    db_path = registry.root / f"{session_id}.sqlite"
    session = qualified_session(registry, exp, db_path, session_id)
    ArtifactManager(registry.root).write_paper_session_json(exp.uuid, session_id, session)
    build_and_write_paper_ops_pass_report_set(registry=registry, experiment_uuid=exp.uuid,
                                            session_id=session_id, db_path=db_path)
    return session_id


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
