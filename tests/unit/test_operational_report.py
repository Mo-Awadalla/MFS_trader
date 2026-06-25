from __future__ import annotations

from monitoring.reports import build_operational_report, format_operational_report
from storage.event_logger import EventLogger
from storage.schema import init_db


def test_operational_report_passes_clean_completed_cycle(tmp_path):
    conn = init_db(tmp_path / "clean.sqlite")
    logger = EventLogger(conn, environment="paper")
    logger.log("ENGINE_HEARTBEAT", cycle_id="cycle-1", message="Processing bar 2024-01-01")
    logger.log("RISK_CHECK_PASSED", cycle_id="cycle-1", message="Risk decision: APPROVED")
    logger.log("ENGINE_HEARTBEAT", cycle_id="cycle-1", message="Bar 2024-01-01 complete — cycle 1")

    report = build_operational_report(conn)

    assert report.passed
    assert report.bars_started == 1
    assert report.bars_completed == 1
    assert report.blockers == []
    assert "Status: PASS" in format_operational_report(report)
    conn.close()


def test_operational_report_blocks_on_errors_and_open_orders(tmp_path):
    conn = init_db(tmp_path / "blocked.sqlite")
    logger = EventLogger(conn, environment="paper")
    logger.log("ENGINE_HEARTBEAT", cycle_id="cycle-1", message="Processing bar 2024-01-01")
    logger.log("BROKER_TIMEOUT", severity="ERROR", cycle_id="cycle-1", message="broker timeout")
    conn.execute(
        """
        INSERT INTO orders_live (
            client_order_id, broker, environment, strategy, symbol, asset_class,
            side, order_type, requested_qty, filled_qty, remaining_qty,
            order_state, reconciliation_status, created_at, updated_at
        ) VALUES (
            'order-1', 'sim_broker', 'paper', 'test', 'AAPL', 'equity',
            'buy', 'market', 1, 0, 1, 'ACKNOWLEDGED', 'NOT_CHECKED',
            '2024-01-01T00:00:00Z', '2024-01-01T00:00:00Z'
        )
        """
    )
    conn.commit()

    report = build_operational_report(conn)

    assert not report.passed
    assert any("Error events" in blocker for blocker in report.blockers)
    assert any("Open/unresolved orders" in blocker for blocker in report.blockers)
    assert any("Broker timeouts" in blocker for blocker in report.blockers)
    conn.close()
