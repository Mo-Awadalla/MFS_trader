"""Continuous paper trading loop with Experiment lifecycle awareness.

Wraps the ``TradingEngine`` with Experiment-scoped kill switch checks,
portfolio state gating, and lifecycle-awareness. The loop:

1. Verifies the Experiment exists, hash matches, and status allows trading.
2. Before each cycle, checks the experiment-scoped kill switch.
3. Delegates to ``TradingEngine.startup()`` and ``TradingEngine.process_bar()``.
4. Handles SIGTERM/SIGINT for graceful shutdown.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import sqlite3
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from config.schema import Config
from engine.paper_session import (
    PAPER_OPS_PASS_SESSION_KIND,
    PAPER_OPS_SMOKE_SESSION_KIND,
    build_and_write_paper_ops_pass_report_set,
    write_paper_ops_smoke_report,
)
from engine.runtime import TradingEngine
from experiments.artifacts import (
    ArtifactError,
    ArtifactManager,
)
from experiments.authority import ExperimentAuthority
from experiments.models import (
    Experiment,
    ExperimentNotFoundError,
    PromotionStatus,
)
from experiments.registry import ExperimentRegistry
from portfolio.state import PortfolioState as PortfolioStateAuthority
from storage.schema import init_db

log = structlog.get_logger(__name__)


ALLOWED_PAPER_STATUSES = frozenset({
    PromotionStatus.PAPER_OPS,
})


class PaperRunHalt(Exception):
    """Raised when the paper run loop must stop (kill switch, suspension)."""


@dataclass(frozen=True)
class PaperRunConfig:
    experiment_uuid: str
    experiment_hash: str
    experiment_root: str | Path
    operator: str | None = None
    symbols: tuple[str, ...] = ("AAPL",)
    session_id: str | None = None
    session_kind: str = "paper_ops_smoke"
    bar_frequency: str = "1d"
    window_calendar_days: int | None = None
    window_market_sessions: int | None = None
    window_trades: int | None = None
    window_unplanned_interruptions: int = 0
    insufficient_activity_override_approved: bool = False
    slippage_samples: tuple[dict[str, Any], ...] = ()
    kill_switch_drill: dict[str, Any] = field(default_factory=dict)
    sleep_between_bars_seconds: float = 60.0
    max_cycles: int | None = None
    write_evidence: bool = True


@dataclass
class PaperRunState:
    cycle_count: int = 0
    halted: bool = False
    halt_reason: str | None = None
    total_orders_submitted: int = 0
    session_id: str | None = None
    evidence_path: str | None = None
    errors: list[str] = field(default_factory=list)
    bar_cycles: list[dict[str, Any]] = field(default_factory=list)

    def record_error(self, msg: str) -> None:
        self.errors.append(msg)

    def record_bar_cycle(self, cycle: dict[str, Any]) -> None:
        self.bar_cycles.append(cycle)


class PaperRunLoop:
    """Continuous paper trading loop with Experiment lifecycle awareness.

    Args:
        config: System configuration.
        broker: Broker adapter (real or simulated).
        strategy_fn: Callable(bars_df, params) -> {symbol: exposure} dict.
        strategy_name: Name of the strategy being run.
        strategy_params: Parameters dict passed to strategy_fn.
        run_config: Paper run configuration (experiment identity, loop params).
    """

    def __init__(
        self,
        config: Config,
        broker: Any,
        strategy_fn: Callable[[pd.DataFrame, dict[str, Any]], dict[str, float]],
        strategy_name: str,
        run_config: PaperRunConfig,
        strategy_params: dict[str, Any] | None = None,
        bars_provider: Callable[[], pd.DataFrame] | None = None,
    ) -> None:
        self._config = config
        self._broker = broker
        self._strategy_fn = strategy_fn
        self._strategy_name = strategy_name
        self._strategy_params = strategy_params or {}
        self._run_config = run_config
        self._bars_provider = bars_provider

        self._state = PaperRunState()
        self._shutdown_requested = False
        self._registry: ExperimentRegistry | None = None
        self._conn: sqlite3.Connection | None = None
        self._engine: TradingEngine | None = None
        self._db_path: Path | None = None
        self._experiment_verified = False
        self._session_started_at = time.time()
        self._checkpoint_path: Path | None = None
        self._session_id = run_config.session_id or f"paper-run-{uuid.uuid4().hex[:12]}"
        self._state.session_id = self._session_id

        self._setup_signal_handlers()

    def _setup_signal_handlers(self) -> None:
        try:
            signal.signal(signal.SIGTERM, self._handle_sigterm)
            signal.signal(signal.SIGINT, self._handle_sigterm)
        except (ValueError, OSError):
            pass

    def _handle_sigterm(self, signum: Any, frame: Any) -> None:
        log.info("paper_run_shutdown_signal", signal=signum)
        self._shutdown_requested = True

    @property
    def state(self) -> PaperRunState:
        return self._state

    @property
    def engine(self) -> TradingEngine | None:
        return self._engine

    def _open_registry(self) -> ExperimentRegistry:
        reg = ExperimentRegistry(self._run_config.experiment_root)
        self._registry = reg
        return reg

    def _verify_experiment(self) -> Experiment:
        registry = self._open_registry()
        try:
            experiment = ExperimentAuthority(registry).verify(
                self._run_config.experiment_uuid,
                self._run_config.experiment_hash,
            )
        except ExperimentNotFoundError:
            registry.close()
            raise
        self._experiment_verified = True
        return experiment

    def _check_experiment_status(self, experiment: Experiment) -> None:
        if experiment.promotion_status not in ALLOWED_PAPER_STATUSES:
            status = experiment.promotion_status.value
            msg = (
                f"Experiment {experiment.uuid[:8]} has status {status}; "
                "paper run requires paper_ops"
            )
            self._state.halted = True
            self._state.halt_reason = msg
            raise PaperRunHalt(msg)

    def _check_kill_switch(self) -> None:
        if self._registry is None:
            return
        ks = self._registry.get_kill_switch(self._run_config.experiment_uuid)
        if ks is None or not ks.is_active:
            return
        self._state.halted = True
        self._state.halt_reason = (
            f"Experiment {self._run_config.experiment_uuid[:8]} has active "
            f"kill switch: {ks.reason} (severity={ks.severity.value})"
        )
        log.warning("paper_run_kill_switch_active", reason=ks.reason, severity=ks.severity.value)
        raise PaperRunHalt(self._state.halt_reason)

    def _check_portfolio_state(self) -> None:
        if self._engine is None:
            return
        authority = self._engine.state.portfolio_state_authority
        if authority != PortfolioStateAuthority.KNOWN:
            log.error(
                "paper_run_portfolio_not_known",
                portfolio_state=authority.value if authority is not None else None,
                message="Portfolio state is not KNOWN — refusing paper run.",
            )
            self._state.halted = True
            state_value = authority.value if authority is not None else "unset"
            self._state.halt_reason = f"portfolio_state {state_value}"
            raise PaperRunHalt(self._state.halt_reason)

    def _should_stop(self) -> bool:
        if self._shutdown_requested or self._state.halted:
            return True
        if self._has_window_targets():
            return self._market_session_target_reached() and self._calendar_target_reached()
        return (
            self._run_config.max_cycles is not None
            and self._state.cycle_count >= self._run_config.max_cycles
        )

    def _has_window_targets(self) -> bool:
        return bool(
            self._run_config.window_market_sessions
            or self._run_config.window_calendar_days
        )

    def _market_session_target_reached(self) -> bool:
        target = self._run_config.window_market_sessions
        if target is None:
            target = self._run_config.max_cycles
        return target is None or self._state.cycle_count >= target

    def _calendar_target_reached(self) -> bool:
        target = self._run_config.window_calendar_days
        return target is None or time.time() - self._session_started_at >= target * 86_400

    def _connect_broker(self) -> None:
        if not self._broker.is_connected:
            self._broker.connect()

    def _disconnect_broker(self) -> None:
        try:
            if self._broker.is_connected:
                self._broker.disconnect()
        except Exception as e:
            log.warning("paper_run_disconnect_error", error=str(e))

    def _init_engine(self, db_path: str | Path) -> TradingEngine:
        conn = init_db(db_path)
        self._conn = conn
        engine = TradingEngine(
            config=self._config,
            conn=conn,
            broker=self._broker,
            strategy_fn=self._strategy_fn,
            strategy_name=self._strategy_name,
            strategy_params=self._strategy_params,
            experiment_uuid=self._run_config.experiment_uuid,
            registry=self._registry,
        )
        self._engine = engine
        return engine

    def run(self, bars: pd.DataFrame, db_path: str | Path) -> PaperRunState:
        """Run the continuous paper trading loop.

        Args:
            bars: OHLCV data to trade on.
            db_path: Path to the engine SQLite database.

        Returns:
            Final PaperRunState after the loop terminates.
        """
        log.info(
            "paper_run_starting",
            experiment_uuid=self._run_config.experiment_uuid[:8],
            cycles=self._run_config.max_cycles or "unlimited",
        )
        self._db_path = Path(db_path)
        self._checkpoint_path = self._db_path.with_suffix(".paper_run_checkpoint.json")
        self._restore_checkpoint()

        try:
            experiment = self._verify_experiment()
            self._check_experiment_status(experiment)

            self._connect_broker()
            engine = self._init_engine(db_path)
            started = engine.startup()
            if not started:
                self._state.halted = True
                self._state.halt_reason = "engine startup failed"
                log.error("paper_run_startup_failed")
                return self._state
            self._check_portfolio_state()

            last_processed_bar_timestamp = (
                str(self._state.bar_cycles[-1].get("input_data_watermark"))
                if self._state.bar_cycles
                else None
            )
            while not self._should_stop():
                self._check_kill_switch()

                if self._market_session_target_reached() and not self._calendar_target_reached():
                    self._sleep_between_cycles()
                    continue

                if self._bars_provider is not None and last_processed_bar_timestamp is not None:
                    bars = self._bars_provider()

                bar_ts = str(bars.index[-1]) if not bars.empty else None
                if (
                    self._bars_provider is not None
                    and bar_ts is not None
                    and bar_ts == last_processed_bar_timestamp
                ):
                    self._sleep_between_cycles()
                    continue
                broker_sync_record_id = f"{self._session_id}-reconciliation-{self._state.cycle_count + 1:06d}"
                engine.reconcile_broker()
                try:
                    self._check_portfolio_state()
                except PaperRunHalt:
                    self._state.cycle_count += 1
                    self._record_cycle(
                        result="blocked",
                        bar_timestamp=bar_ts,
                        reason=self._state.halt_reason,
                        broker_sync_record_id=broker_sync_record_id,
                    )
                    raise
                prices = self._fetch_prices(bars)

                if not prices:
                    self._state.cycle_count += 1
                    self._record_cycle(
                        result="missed_unexplained",
                        bar_timestamp=bar_ts,
                        reason="no valid broker prices available",
                        broker_sync_record_id=broker_sync_record_id,
                    )
                    self._state.halted = True
                    self._state.halt_reason = "missed bar cycle: no valid broker prices available"
                    log.warning("paper_run_no_prices", message=self._state.halt_reason)
                    break

                evaluation = engine.process_bar(
                    bars=bars,
                    prices=prices,
                    bar_timestamp=bar_ts,
                )

                self._state.cycle_count += 1
                last_processed_bar_timestamp = bar_ts
                self._record_cycle(
                    result="completed",
                    bar_timestamp=bar_ts,
                    decision_record_id=getattr(evaluation, "correlation_id", None),
                    broker_sync_record_id=broker_sync_record_id,
                )
                if evaluation is not None:
                    self._state.total_orders_submitted += len(evaluation.adjusted_targets or [])

                log.info(
                    "paper_run_cycle_complete",
                    cycle=self._state.cycle_count,
                    orders_submitted=self._state.total_orders_submitted,
                )
                self._write_checkpoint()

                if self._should_stop():
                    break

                self._sleep_between_cycles()

        except PaperRunHalt:
            self._state.halted = True
            if not self._state.halt_reason:
                self._state.halt_reason = "paper run halted"
            log.warning("paper_run_halted", reason=self._state.halt_reason)
        except ExperimentNotFoundError as e:
            self._state.halted = True
            self._state.halt_reason = str(e)
            self._state.record_error(str(e))
            log.error("paper_run_experiment_not_found", error=str(e))
        except Exception as e:
            self._state.halted = True
            if self._state.halt_reason is None:
                self._state.halt_reason = str(e)
            self._state.record_error(str(e))
            log.error("paper_run_error", error=str(e))
        finally:
            if not self._has_window_targets() or (
                self._market_session_target_reached() and self._calendar_target_reached()
            ):
                self._write_session_evidence()
                self._remove_checkpoint()
            self._cleanup()

        return self._state

    def _fetch_prices(self, bars: pd.DataFrame) -> dict[str, float]:
        prices: dict[str, float] = {}
        if bars.empty:
            return prices
        for symbol in self._run_config.symbols:
            try:
                price = self._broker.get_price(symbol)
                if price is not None and price > 0:
                    prices[symbol] = float(price)
            except Exception:
                pass
        return prices

    def _write_session_evidence(self) -> None:
        if not self._run_config.write_evidence or not self._experiment_verified:
            return
        payload = {
            "experiment_uuid": self._run_config.experiment_uuid,
            "experiment_hash": self._run_config.experiment_hash,
            "session_id": self._session_id,
            "session_kind": self._run_config.session_kind,
            "session_type": "paper_run",
            "operator": self._run_config.operator,
            "broker": getattr(self._broker, "name", "unknown"),
            "bar_frequency": self._run_config.bar_frequency,
            "symbols": list(self._run_config.symbols),
            "cycle_count": self._state.cycle_count,
            "bar_cycles": list(self._state.bar_cycles),
            "bar_cycle_report": self._build_bar_cycle_report(),
            "window": self._build_window_summary(),
            "portfolio_state": self._current_portfolio_state(),
            "slippage_samples": list(self._run_config.slippage_samples),
            "kill_switch_drill": dict(self._run_config.kill_switch_drill),
            "halted": self._state.halted,
            "halt_reason": self._state.halt_reason,
            "total_orders_submitted": self._state.total_orders_submitted,
            "order_lifecycle": self._read_order_lifecycle_snapshot(),
            "errors": list(self._state.errors),
            "passed": not self._state.halted and not self._state.errors,
            "blockers": list(self._state.errors) + ([self._state.halt_reason] if self._state.halt_reason else []),
        }
        try:
            path = ArtifactManager(self._run_config.experiment_root).write_paper_session_json(
                self._run_config.experiment_uuid,
                self._session_id,
                payload,
            )
            self._state.evidence_path = str(path)
            if self._run_config.session_kind == PAPER_OPS_PASS_SESSION_KIND:
                self._write_pass_reports()
            elif self._run_config.session_kind == PAPER_OPS_SMOKE_SESSION_KIND:
                self._write_smoke_report()
        except ArtifactError as e:
            self._state.halted = True
            self._state.halt_reason = str(e)
            self._state.record_error(str(e))
            log.error("paper_run_evidence_write_failed", error=str(e))

    def _write_smoke_report(self) -> None:
        if self._registry is None:
            self._state.halted = True
            self._state.halt_reason = "paper_ops_smoke report generation missing registry"
            self._state.record_error(self._state.halt_reason)
            return
        try:
            write_paper_ops_smoke_report(
                registry=self._registry,
                experiment_uuid=self._run_config.experiment_uuid,
                session_id=self._session_id,
            )
        except Exception as e:
            self._state.halted = True
            self._state.halt_reason = str(e)
            self._state.record_error(str(e))
            log.error("paper_run_smoke_report_write_failed", error=str(e))

    def _write_pass_reports(self) -> None:
        if self._registry is None or self._db_path is None:
            self._state.halted = True
            self._state.halt_reason = "paper_ops_pass report generation missing registry/db"
            self._state.record_error(self._state.halt_reason)
            return
        try:
            build_and_write_paper_ops_pass_report_set(
                registry=self._registry,
                experiment_uuid=self._run_config.experiment_uuid,
                session_id=self._session_id,
                db_path=self._db_path,
            )
        except Exception as e:
            self._state.halted = True
            self._state.halt_reason = str(e)
            self._state.record_error(str(e))
            log.error("paper_run_pass_report_write_failed", error=str(e))

    def _record_cycle(
        self,
        *,
        result: str,
        bar_timestamp: str | None,
        reason: str | None = None,
        decision_record_id: str | None = None,
        broker_sync_record_id: str | None = None,
    ) -> None:
        cycle_no = self._state.cycle_count
        self._state.record_bar_cycle(
            {
                "cycle_id": f"{self._session_id}-{cycle_no:06d}",
                "expected_at": bar_timestamp,
                "started_at": bar_timestamp,
                "completed_at": bar_timestamp if result in {"completed", "late_completed"} else None,
                "market_session": None,
                "bar_timeframe": self._run_config.bar_frequency,
                "input_data_watermark": bar_timestamp,
                "decision_record_id": decision_record_id,
                "broker_sync_record_id": broker_sync_record_id,
                "result": result,
                "reason": reason,
            }
        )

    def _build_bar_cycle_report(self) -> dict[str, Any]:
        cycles = self._state.bar_cycles
        expected = len(cycles)
        completed = sum(1 for c in cycles if c.get("result") in {"completed", "late_completed"})
        unexplained = sum(1 for c in cycles if c.get("result") == "missed_unexplained")
        completion = (completed / expected) if expected else 0.0
        return {
            "passed": expected > 0 and unexplained == 0,
            "expected_bar_cycles": expected,
            "completed_bar_cycles": completed,
            "bar_cycle_completion": completion,
            "unexplained_missed_cycles": unexplained,
        }

    def _build_window_summary(self) -> dict[str, Any]:
        elapsed_days = int((time.time() - self._session_started_at) // 86_400)
        return {
            "calendar_days": elapsed_days,
            "market_sessions": self._state.cycle_count,
            "trades": (
                self._run_config.window_trades
                if self._run_config.window_trades is not None
                else self._state.total_orders_submitted
            ),
            "unplanned_interruptions": self._run_config.window_unplanned_interruptions,
            "insufficient_activity_override_approved": (
                self._run_config.insufficient_activity_override_approved
            ),
        }

    def _restore_checkpoint(self) -> None:
        path = self._checkpoint_path
        if path is None or not path.exists():
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("session_id") != self._session_id:
            raise PaperRunHalt("paper-run checkpoint session identity mismatch")
        self._session_started_at = float(payload["session_started_at"])
        self._state.cycle_count = int(payload.get("cycle_count", 0))
        self._state.total_orders_submitted = int(payload.get("total_orders_submitted", 0))
        self._state.bar_cycles = list(payload.get("bar_cycles", []))

    def _write_checkpoint(self) -> None:
        path = self._checkpoint_path
        if path is None:
            return
        payload = {
            "session_id": self._session_id,
            "session_started_at": self._session_started_at,
            "cycle_count": self._state.cycle_count,
            "total_orders_submitted": self._state.total_orders_submitted,
            "bar_cycles": self._state.bar_cycles,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)

    def _remove_checkpoint(self) -> None:
        if self._checkpoint_path is not None:
            self._checkpoint_path.unlink(missing_ok=True)

    def _current_portfolio_state(self) -> str | None:
        if self._engine is None:
            return None
        authority = self._engine.state.portfolio_state_authority
        return authority.value if authority is not None else None

    def _read_order_lifecycle_snapshot(self) -> list[dict[str, Any]]:
        if self._conn is None:
            return []
        rows = self._conn.execute(
            """
            SELECT client_order_id, broker_order_id, broker, strategy, symbol,
                   side, requested_qty, filled_qty, remaining_qty,
                   avg_fill_price, order_state, reconciliation_status,
                   bar_timestamp, correlation_id, created_at, updated_at
            FROM orders_live
            ORDER BY created_at, client_order_id
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def _sleep_between_cycles(self) -> None:
        sleep_secs = self._run_config.sleep_between_bars_seconds
        if sleep_secs <= 0:
            return
        interval = 0.25
        elapsed = 0.0
        while elapsed < sleep_secs and not self._should_stop():
            time.sleep(interval)
            elapsed += interval

    def _cleanup(self) -> None:
        if self._engine is not None:
            with contextlib.suppress(Exception):
                self._engine.shutdown()
        self._disconnect_broker()
        if self._conn is not None:
            with contextlib.suppress(Exception):
                self._conn.close()
        if self._registry is not None:
            with contextlib.suppress(Exception):
                self._registry.close()
