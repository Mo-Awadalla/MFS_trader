"""Trading engine — the runtime loop.

One engine, three modes: research | paper | live
Mode is set by config, not by code path. Same signals, same risk, same OMS.

Bar cycle (deterministic, idempotent):
    1. Read bars
    2. Generate signals
    3. Compute target positions (portfolio)
    4. Run risk checks
    5. Submit orders (OMS, with deterministic client_order_id)
    6. Log cycle complete
    7. Sleep until next bar

Startup:
    1. Read kill-switch state from DB
    2. If halted → refuse to trade, log, notify
    3. Reconcile with broker (orders, positions)
    4. Verify data freshness
    5. Resume normal cycle

Shutdown:
    SIGTERM → finish current bar, persist, exit
    SIGKILL → startup reconciliation on next boot
"""

from __future__ import annotations

import signal
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import numpy as np
import pandas as pd
import structlog

from config.schema import Config
from execution.base import BrokerAdapter, OrderSide, OrderType
from execution.oms import OMS, OrderIntent
from portfolio.sizing import PortfolioState, compute_position_delta, compute_target_positions
from risk.engine import DrawdownState, RiskEngine, RiskEvaluation
from storage.event_logger import EventLogger, utc_now_iso
from storage.repository import (
    get_engine_state,
    get_positions,
    is_strategy_halted,
    set_engine_state,
    set_strategy_kill_switch,
)

log = structlog.get_logger(__name__)


class EngineMode(StrEnum):
    RESEARCH = "research"
    PAPER = "paper"
    LIVE = "live"


@dataclass
class EngineState:
    """Current engine runtime state."""

    mode: EngineMode
    running: bool = False
    halted: bool = False
    halt_reason: str | None = None
    current_bar: pd.Timestamp | None = None
    last_heartbeat: str | None = None
    cycle_count: int = 0
    strategy_halted: set[str] = field(default_factory=set)


class TradingEngine:
    """The runtime trading engine — one loop, three modes.

    Args:
        config: System configuration.
        conn: SQLite connection for state persistence.
        broker: Broker adapter (real or simulated).
        strategy_fn: Callable(bars_df, params) → {symbol: exposure} dict.
        strategy_name: Name of the strategy being run.
        strategy_params: Parameters dict passed to strategy_fn.
    """

    def __init__(
        self,
        config: Config,
        conn: sqlite3.Connection,
        broker: BrokerAdapter,
        strategy_fn: Callable[[pd.DataFrame, dict[str, Any]], dict[str, float]],
        strategy_name: str,
        strategy_params: dict[str, Any] | None = None,
    ):
        self._config = config
        self._conn = conn
        self._broker = broker
        self._strategy_fn = strategy_fn
        self._strategy_name = strategy_name
        self._strategy_params = strategy_params or {}

        self._logger = EventLogger(conn, environment=config.mode.value)
        self._oms = OMS(broker, conn, self._logger, environment=config.mode.value)
        self._risk = RiskEngine(config.risk_limits)
        self._state = EngineState(mode=EngineMode(config.mode.value))

        self._shutdown_requested = False
        self._setup_signal_handlers()

    def _setup_signal_handlers(self) -> None:
        """Setup SIGTERM handler for graceful shutdown."""
        try:
            signal.signal(signal.SIGTERM, self._handle_sigterm)
            signal.signal(signal.SIGINT, self._handle_sigterm)
        except (ValueError, OSError):
            pass  # not in main thread (tests)

    def _handle_sigterm(self, signum, frame) -> None:
        log.info("shutdown_signal", signal=signum)
        self._shutdown_requested = True

    @property
    def state(self) -> EngineState:
        return self._state

    @property
    def oms(self) -> OMS:
        return self._oms

    @property
    def risk_engine(self) -> RiskEngine:
        return self._risk

    def startup(self) -> bool:
        """Engine startup sequence — reconciliation before trading.

        Returns True if startup succeeded, False if halted.
        """
        self._logger.log("ENGINE_STARTUP", severity="INFO", message=f"Engine starting in {self._state.mode.value} mode")

        # 1. Check kill-switch state from DB
        halted = get_engine_state(self._conn, "halted")
        if halted == "true":
            self._state.halted = True
            self._state.halt_reason = get_engine_state(self._conn, "halt_reason") or "unknown"
            self._logger.log(
                "ENGINE_HALTED",
                severity="WARN",
                message=f"Engine was halted: {self._state.halt_reason} — refusing to trade",
            )
            return False

        # 2. Check strategy halt
        if is_strategy_halted(self._conn, self._strategy_name):
            self._state.strategy_halted.add(self._strategy_name)
            self._risk.halt_strategy(self._strategy_name, "persisted_halt")
            self._logger.log(
                "ENGINE_HALTED",
                severity="WARN",
                message=f"Strategy {self._strategy_name} was halted — resuming in monitoring only",
            )

        # 3. Reconcile with broker
        if self._config.engine.startup_reconciliation_required:
            self._reconcile_broker()
            # Reconciliation may have halted the engine
            if self._state.halted:
                return False

        # 4. Connect broker
        if not self._broker.is_connected:
            try:
                self._broker.connect()
            except Exception as e:
                self._logger.log(
                    "BROKER_DISCONNECTED",
                    severity="CRITICAL",
                    exception=str(e),
                    message="Failed to connect to broker",
                )
                return False

        self._state.running = True
        self._logger.log("ENGINE_RESUMED", severity="INFO", message="Engine started successfully")
        return True

    def _reconcile_broker(self) -> None:
        """Reconcile internal state with broker state."""
        self._logger.log("RECONCILIATION_RUN", severity="INFO", message="Starting broker reconciliation")

        try:
            broker_positions = self._broker.get_positions()
            internal_positions = get_positions(self._conn, strategy=self._strategy_name)

            # Build broker position map
            broker_map = {p.symbol: p.quantity for p in broker_positions}
            internal_map = {p["symbol"]: p["quantity"] for p in internal_positions}

            mismatches: list[str] = []
            for sym in set(broker_map) | set(internal_map):
                broker_qty = broker_map.get(sym, 0.0)
                internal_qty = internal_map.get(sym, 0.0)
                if abs(broker_qty - internal_qty) > 1e-6:
                    mismatches.append(f"{sym}: broker={broker_qty}, internal={internal_qty}")

            if mismatches:
                self._logger.log(
                    "RECONCILIATION_MISMATCH",
                    severity="CRITICAL",
                    message=f"Position mismatches: {'; '.join(mismatches)}",
                    details={"mismatches": mismatches},
                )
                # Don't blindly flatten — freeze and alert
                if self._state.mode == EngineMode.LIVE:
                    self._state.halted = True
                    self._state.halt_reason = "reconciliation_mismatch"
                    set_engine_state(self._conn, "halted", "true")
                    set_engine_state(self._conn, "halt_reason", "reconciliation_mismatch")
            else:
                self._logger.log(
                    "RECONCILIATION_RUN",
                    severity="INFO",
                    message="Reconciliation passed — all positions match",
                )

        except Exception as e:
            self._logger.log(
                "RECONCILIATION_MISMATCH",
                severity="CRITICAL",
                exception=str(e),
                message="Reconciliation failed — broker unreachable",
            )
            if self._state.mode == EngineMode.LIVE:
                self._state.halted = True
                self._state.halt_reason = "reconciliation_failed"

    def process_bar(
        self,
        bars: pd.DataFrame,
        prices: dict[str, float],
        *,
        bar_timestamp: str | None = None,
        portfolio_state: PortfolioState | None = None,
        drawdown: DrawdownState | None = None,
    ) -> RiskEvaluation | None:
        """Process one bar — the deterministic cycle.

        This is idempotent: processing the same bar twice produces the same
        result (no duplicate orders) thanks to deterministic client_order_ids.

        Args:
            bars: OHLCV data up to and including this bar.
            prices: Current prices {symbol: price}.
            bar_timestamp: ISO timestamp of this bar (for order ID determinism).
            portfolio_state: Current portfolio state (capital, equity, positions).
            drawdown: Current drawdown state for risk checks.

        Returns:
            RiskEvaluation if orders were attempted, None if halted/frozen.
        """
        if self._state.halted:
            self._logger.log(
                "ENGINE_HALTED",
                severity="WARN",
                message=f"Bar skipped — engine halted: {self._state.halt_reason}",
            )
            return None

        bar_ts = bar_timestamp or utc_now_iso()
        self._state.current_bar = pd.Timestamp(bar_ts)
        self._state.cycle_count += 1

        cycle_id = f"cycle_{self._state.cycle_count}_{bar_ts}"
        self._logger.log(
            "ENGINE_HEARTBEAT",
            severity="INFO",
            cycle_id=cycle_id,
            bar_timestamp=bar_ts,
            message=f"Processing bar {bar_ts}",
        )

        # 1. Generate signals (strategy produces desired exposure)
        try:
            exposures = self._strategy_fn(bars, self._strategy_params)
        except Exception as e:
            self._logger.log(
                "EXCEPTION_SOFT",
                severity="ERROR",
                strategy=self._strategy_name,
                exception=str(e),
                message="Strategy signal generation failed — disabling strategy",
            )
            self._risk.halt_strategy(self._strategy_name, "signal_generation_error")
            set_strategy_kill_switch(self._conn, self._strategy_name, True, "signal_generation_error")
            return None

        if not exposures:
            self._logger.log(
                "SIGNAL_GENERATED",
                strategy=self._strategy_name,
                bar_timestamp=bar_ts,
                message="No signals generated",
            )
            self._log_cycle_complete(cycle_id, bar_ts)
            return None

        # Filter out NaN exposures (strategy hasn't warmed up yet)
        exposures = {k: v for k, v in exposures.items() if not (isinstance(v, float) and np.isnan(v))}
        if not exposures:
            self._logger.log(
                "SIGNAL_GENERATED",
                strategy=self._strategy_name,
                bar_timestamp=bar_ts,
                message="Only NaN warmup exposures generated — no orders submitted",
            )
            self._log_cycle_complete(cycle_id, bar_ts)
            return None

        # 2. Compute target positions (portfolio converts exposure → targets)
        state = portfolio_state or PortfolioState(
            cash=10000, equity=10000, high_water_mark=10000
        )
        targets = compute_target_positions(
            exposures,
            prices,
            state,
            self._config.portfolio,
        )

        # 3. Run risk checks (risk accepts/rejects/modifies)
        dd = drawdown or DrawdownState(
            high_water_mark=state.high_water_mark, current_equity=state.equity
        )
        current_positions = {p["symbol"]: p for p in get_positions(self._conn, strategy=self._strategy_name)}
        evaluation = self._risk.evaluate(
            targets,
            state,
            dd,
            strategy_name=self._strategy_name,
            current_positions=current_positions,
        )

        if evaluation.is_approved:
            risk_event_type = "RISK_CHECK_PASSED"
        elif evaluation.is_rejected:
            risk_event_type = "RISK_CHECK_BLOCKED"
        else:
            risk_event_type = "RISK_CHECK_REDUCED"

        self._logger.log(
            risk_event_type,
            severity="INFO" if evaluation.is_approved else "WARN",
            strategy=self._strategy_name,
            bar_timestamp=bar_ts,
            message=f"Risk decision: {evaluation.final_decision.value}",
            details={"reasons": evaluation.rejection_reasons + evaluation.reduction_reasons},
        )

        # 4. Submit orders for approved targets
        for target in evaluation.adjusted_targets:
            # Compute delta from current position
            current_qty = current_positions.get(target.symbol, {}).get("quantity", 0.0)
            delta = compute_position_delta(target, current_qty)

            if delta["action"] == "hold":
                continue

            # Determine order side
            side = OrderSide.BUY if delta["delta_qty"] > 0 else OrderSide.SELL
            qty = abs(delta["delta_qty"])
            if qty < 1e-9:
                continue  # skip zero-size orders

            intent = OrderIntent(
                strategy=self._strategy_name,
                symbol=target.symbol,
                asset_class=target.asset_class,
                side=side,
                order_type=OrderType.MARKET,
                quantity=float(qty),
                bar_timestamp=bar_ts,
                correlation_id=cycle_id,
                version=self._config.strategy_version,
            )

            self._oms.create_and_submit(intent)

        self._log_cycle_complete(cycle_id, bar_ts)

        return evaluation

    def _log_cycle_complete(self, cycle_id: str, bar_ts: str) -> None:
        """Record completion of a bar cycle, including no-op/warmup bars."""
        self._logger.log(
            "ENGINE_HEARTBEAT",
            severity="INFO",
            cycle_id=cycle_id,
            bar_timestamp=bar_ts,
            message=f"Bar {bar_ts} complete — cycle {self._state.cycle_count}",
        )

    def shutdown(self) -> None:
        """Graceful shutdown — persist state and exit."""
        self._logger.log(
            "ENGINE_SHUTDOWN",
            severity="INFO",
            message=f"Engine shutting down after {self._state.cycle_count} cycles",
        )
        self._state.running = False
        set_engine_state(self._conn, "running", "false")

    def halt(self, reason: str) -> None:
        """Halt the engine — persists to DB, survives restart."""
        self._state.halted = True
        self._state.halt_reason = reason
        self._risk.activate_kill_switch(reason)
        set_engine_state(self._conn, "halted", "true")
        set_engine_state(self._conn, "halt_reason", reason)
        self._logger.log(
            "ENGINE_HALTED",
            severity="CRITICAL",
            message=f"Engine halted: {reason}",
        )

    def resume(self) -> None:
        """Manually resume after halt."""
        self._state.halted = False
        self._state.halt_reason = None
        self._risk.deactivate_kill_switch()
        set_engine_state(self._conn, "halted", "false")
        set_engine_state(self._conn, "halt_reason", "")
        self._logger.log("ENGINE_RESUMED", severity="INFO", message="Engine resumed")
