"""Tests for monitoring — alerts, throttling, watchdog."""

from __future__ import annotations

import time
from datetime import UTC

from monitoring.alerts import AlertManager
from monitoring.watchdog import HeartbeatWatchdog, WatchdogConfig
from storage.event_logger import EventLogger
from storage.schema import init_db


class TestAlertManager:
    def test_first_alert_sends(self):
        am = AlertManager(cooldown_minutes=10)
        assert am.send_alert("DATA_STALE", "AAPL data stale", "WARN", "AAPL")

    def test_duplicate_within_cooldown_suppressed(self):
        am = AlertManager(cooldown_minutes=10)
        am.send_alert("DATA_STALE", "stale", "WARN", "AAPL")
        # Second alert within cooldown — should be suppressed
        assert not am.send_alert("DATA_STALE", "stale again", "WARN", "AAPL")

    def test_different_symbol_not_suppressed(self):
        am = AlertManager(cooldown_minutes=10)
        am.send_alert("DATA_STALE", "stale", "WARN", "AAPL")
        # Different symbol — should send
        assert am.send_alert("DATA_STALE", "stale", "WARN", "MSFT")

    def test_after_cooldown_sends(self):
        am = AlertManager(cooldown_minutes=0)  # 0 minute cooldown = immediate
        am.send_alert("DATA_STALE", "stale", "WARN", "AAPL")
        time.sleep(0.01)
        # After cooldown — should send
        assert am.send_alert("DATA_STALE", "stale", "WARN", "AAPL")

    def test_resolve_clears_alert(self):
        am = AlertManager(cooldown_minutes=10)
        am.send_alert("DATA_STALE", "stale", "WARN", "AAPL")
        resolved = am.resolve("DATA_STALE", "AAPL", "WARN")
        assert resolved
        assert len(am.get_active_alerts()) == 0

    def test_active_alerts_tracked(self):
        am = AlertManager(cooldown_minutes=10)
        am.send_alert("DATA_STALE", "stale", "WARN", "AAPL")
        am.send_alert("POSITION_MISMATCH", "mismatch", "CRITICAL", "MSFT")
        assert len(am.get_active_alerts()) == 2


class TestWatchdog:
    def test_no_db_returns_not_alive(self):
        wd = HeartbeatWatchdog(WatchdogConfig(db_path="/nonexistent/path.sqlite"))
        result = wd.check_heartbeat()
        assert not result["alive"]
        assert "database_not_found" in result.get("error", "")

    def test_no_heartbeat_returns_not_alive(self, tmp_path):
        db = init_db(tmp_path / "test.sqlite")
        db.close()

        wd = HeartbeatWatchdog(WatchdogConfig(db_path=str(tmp_path / "test.sqlite")))
        result = wd.check_heartbeat()
        assert not result["alive"]
        assert "no_heartbeat" in result.get("error", "") or "no_events" in result.get("error", "")

    def test_fresh_heartbeat_returns_alive(self, tmp_path):
        db = init_db(tmp_path / "test.sqlite")
        logger = EventLogger(db, environment="paper")
        logger.log("ENGINE_HEARTBEAT", message="alive")
        db.close()

        wd = HeartbeatWatchdog(
            WatchdogConfig(db_path=str(tmp_path / "test.sqlite"), heartbeat_timeout_seconds=120)
        )
        result = wd.check_heartbeat()
        assert result["alive"]
        assert result["age_seconds"] < 120

    def test_stale_heartbeat_returns_not_alive(self, tmp_path):
        db = init_db(tmp_path / "test.sqlite")
        # Log heartbeat with an old timestamp by manipulating directly
        from datetime import datetime, timedelta

        old_time = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        db.execute(
            "INSERT INTO events (timestamp, event_type, severity, environment, message) "
            "VALUES (?, 'ENGINE_HEARTBEAT', 'INFO', 'paper', 'old')",
            (old_time,),
        )
        db.commit()
        db.close()

        wd = HeartbeatWatchdog(
            WatchdogConfig(db_path=str(tmp_path / "test.sqlite"), heartbeat_timeout_seconds=120)
        )
        result = wd.check_heartbeat()
        assert not result["alive"]
        assert result["age_seconds"] > 120

    def test_run_once_with_alert_manager(self, tmp_path):
        db = init_db(tmp_path / "test.sqlite")
        db.close()

        am = AlertManager(cooldown_minutes=0)
        wd = HeartbeatWatchdog(
            WatchdogConfig(
                db_path=str(tmp_path / "test.sqlite"),
                alert_manager=am,
            )
        )
        result = wd.run_once()
        # No DB → should trigger alert
        assert not result["alive"]
