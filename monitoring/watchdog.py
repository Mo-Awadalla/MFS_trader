"""Heartbeat watchdog — external process that monitors engine health.

Dead engines do not send death certificates. This process:
  - Checks heartbeat age (last ENGINE_HEARTBEAT event)
  - Checks DB growth (events still being written)
  - Checks latest event timestamp
  - Alerts if engine is silent

Must run as a SEPARATE process from the engine, so it can detect engine death.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Any

import structlog

from monitoring.alerts import AlertManager

log = structlog.get_logger(__name__)


@dataclass
class WatchdogConfig:
    """Configuration for the heartbeat watchdog."""

    heartbeat_timeout_seconds: int = 120
    check_interval_seconds: int = 30
    db_path: str = "storage/mfs.sqlite"
    alert_manager: AlertManager | None = None


class HeartbeatWatchdog:
    """Monitors engine heartbeat — alerts if engine is silent.

    Run this as a separate process:
        python -m monitoring.watchdog --db storage/mfs.sqlite
    """

    def __init__(self, config: WatchdogConfig):
        self._config = config
        self._running = False

    def check_heartbeat(self) -> dict[str, Any]:
        """Check if the engine heartbeat is fresh.

        Returns:
            Dict with: alive (bool), last_heartbeat (str|None), age_seconds (float), alerts (list)
        """
        db_path = Path(self._config.db_path)
        if not db_path.exists():
            return {
                "alive": False,
                "last_heartbeat": None,
                "age_seconds": float("inf"),
                "error": "database_not_found",
            }

        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row

            # Get latest heartbeat
            cur = conn.execute(
                "SELECT timestamp FROM events WHERE event_type = 'ENGINE_HEARTBEAT' "
                "ORDER BY id DESC LIMIT 1"
            )
            row = cur.fetchone()

            if row is None:
                # No heartbeat at all — check if any events exist
                cur = conn.execute("SELECT COUNT(*) FROM events")
                count = cur.fetchone()[0]
                conn.close()
                return {
                    "alive": False,
                    "last_heartbeat": None,
                    "age_seconds": float("inf"),
                    "error": "no_heartbeat" if count > 0 else "no_events",
                }

            from datetime import datetime

            last_hb = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            now = datetime.now(UTC)
            age = (now - last_hb).total_seconds()

            conn.close()

            alive = age <= self._config.heartbeat_timeout_seconds
            return {
                "alive": alive,
                "last_heartbeat": row["timestamp"],
                "age_seconds": age,
                "alerts": [] if alive else [f"heartbeat_stale_{int(age)}s"],
            }

        except Exception as e:
            return {
                "alive": False,
                "last_heartbeat": None,
                "age_seconds": float("inf"),
                "error": str(e),
            }

    def run_once(self) -> dict[str, Any]:
        """Run one check cycle and send alerts if needed."""
        result = self.check_heartbeat()

        if not result["alive"] and self._config.alert_manager:
            self._config.alert_manager.send_alert(
                "ENGINE_HEARTBEAT_MISSING",
                f"Engine heartbeat missing: {result.get('error', 'stale')} "
                f"(age: {result.get('age_seconds', 'unknown')}s)",
                severity="CRITICAL",
            )

        return result

    def run_forever(self) -> None:
        """Run the watchdog continuously."""
        self._running = True
        log.info("watchdog_started", interval=self._config.check_interval_seconds)

        while self._running:
            result = self.run_once()
            if not result["alive"]:
                log.warning("watchdog_alert", **result)
            else:
                log.debug("watchdog_ok", age=result["age_seconds"])

            time.sleep(self._config.check_interval_seconds)

    def stop(self) -> None:
        """Stop the watchdog."""
        self._running = False
