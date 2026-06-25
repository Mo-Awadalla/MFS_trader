"""Alert manager — Telegram notifications with throttling.

Features:
  - Dedup alerts by event_type + symbol + severity
  - Cooldown window (suppress repeats for N minutes)
  - Escalation if unresolved after M minutes
  - Recovery alert when issue resolves
  - Dead engines don't send death certificates (external watchdog needed)
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import structlog

log = structlog.get_logger(__name__)


@dataclass
class AlertState:
    """Track one alert's state for throttling."""

    event_type: str
    symbol: str | None
    severity: str
    first_fired: float  # unix timestamp
    last_fired: float
    fire_count: int = 1
    escalated: bool = False
    resolved: bool = False


class AlertManager:
    """Throttled alert manager — prevents alert storms.

    Rules:
      - Same event_type + symbol + severity → suppress for cooldown_minutes
      - If still firing after escalation_minutes → escalate severity
      - When issue resolves → send recovery alert
    """

    def __init__(
        self,
        cooldown_minutes: int = 10,
        escalation_minutes: int = 30,
        *,
        telegram_bot_token: str | None = None,
        telegram_chat_id: str | None = None,
    ):
        self._cooldown = cooldown_minutes * 60
        self._escalation = escalation_minutes * 60
        self._telegram_token = telegram_bot_token
        self._telegram_chat_id = telegram_chat_id
        self._active: dict[str, AlertState] = {}

    def _alert_key(self, event_type: str, symbol: str | None, severity: str) -> str:
        return f"{event_type}:{symbol or 'GLOBAL'}:{severity}"

    def should_send(self, event_type: str, symbol: str | None, severity: str) -> bool:
        """Check if an alert should be sent (not throttled)."""
        key = self._alert_key(event_type, symbol, severity)
        now = time.time()

        if key not in self._active:
            # New alert — always send
            self._active[key] = AlertState(
                event_type=event_type,
                symbol=symbol,
                severity=severity,
                first_fired=now,
                last_fired=now,
            )
            return True

        state = self._active[key]
        elapsed = now - state.last_fired

        if elapsed < self._cooldown:
            # Within cooldown — suppress
            state.fire_count += 1
            return False

        # Cooldown passed — send and update
        state.last_fired = now
        state.fire_count += 1

        # Check escalation
        if not state.escalated and (now - state.first_fired) > self._escalation:
            state.escalated = True
            state.severity = "CRITICAL"
            return True

        return True

    def resolve(self, event_type: str, symbol: str | None, severity: str) -> bool:
        """Mark an alert as resolved — sends recovery notification."""
        key = self._alert_key(event_type, symbol, severity)
        if key in self._active and not self._active[key].resolved:
            self._active[key].resolved = True
            del self._active[key]
            return True
        return False

    def get_active_alerts(self) -> list[AlertState]:
        """Get all currently active (unresolved) alerts."""
        return list(self._active.values())

    def send_alert(self, event_type: str, message: str, severity: str = "WARN", symbol: str | None = None) -> bool:
        """Send an alert (with throttling). Returns True if sent."""
        if not self.should_send(event_type, symbol, severity):
            return False

        log.info(
            "alert_sent",
            event_type=event_type,
            symbol=symbol,
            severity=severity,
            message=message,
        )

        if self._telegram_token and self._telegram_chat_id:
            self._send_telegram(event_type, message, severity, symbol)

        return True

    def _send_telegram(self, event_type: str, message: str, severity: str, symbol: str | None) -> None:
        """Send alert via Telegram bot (best-effort, no crash on failure)."""
        try:
            import requests

            text = f"🚨 [{severity}] {event_type}"
            if symbol:
                text += f" ({symbol})"
            text += f"\n{message}"

            url = f"https://api.telegram.org/bot{self._telegram_token}/sendMessage"
            requests.post(
                url,
                json={"chat_id": self._telegram_chat_id, "text": text},
                timeout=10,
            )
        except Exception as e:
            log.error("telegram_send_failed", error=str(e))
