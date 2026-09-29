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
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from config.schema import Config
from engine.paper_calendar import XNYS_PAPER_CALENDAR, default_data_grace
from engine.paper_evidence import (
    PaperLedger,
    derive_observations,
    digest,
    execution_version,
    finite,
    instant,
)
from engine.paper_session import (
    PAPER_OPS_PASS_SESSION_KIND,
    PAPER_OPS_SMOKE_SESSION_KIND,
    build_and_write_paper_ops_pass_report_set,
    paper_caps_from_config,
    validate_tiny_paper_caps,
    write_paper_ops_smoke_report,
)
from engine.runtime import TradingEngine
from experiments.artifacts import (
    ArtifactError,
    ArtifactManager,
)
from experiments.models import (
    Experiment,
    ExperimentNotFoundError,
    PromotionStatus,
)
from experiments.operator_confirmations import verify_experiment_hash
from experiments.registry import ExperimentRegistry
from portfolio.state import PortfolioState as PortfolioStateAuthority
from storage.schema import init_db

log = structlog.get_logger(__name__)


ALLOWED_PAPER_STATUSES = frozenset({
    PromotionStatus.PAPER_OPS,
})


class PaperRunHalt(Exception):
    """Raised when the paper run loop must stop (kill switch, suspension)."""


def verify_local_paper_prerequisites(db_path: str | Path) -> None:
    """Refuse persisted uncertainty without connecting to a broker."""
    path = Path(db_path)
    checkpoint = path.with_suffix(".paper_run_checkpoint.json")
    if checkpoint.exists():
        try:
            envelope = json.loads(checkpoint.read_text(encoding="utf-8"))
            payload = envelope["payload"]
            if digest(payload) != envelope["sha256"] or payload["halted"] is not False:
                raise ValueError("checkpoint integrity or persisted halt")
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"paper checkpoint prerequisite failed: {exc}") from exc
    if not path.exists():
        return
    try:
        with contextlib.closing(sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)) as conn:
            halted = conn.execute("SELECT value FROM engine_state WHERE key='halted'").fetchone()
            uncertain = conn.execute(
                "SELECT client_order_id FROM orders_live WHERE order_state IN "
                "('UNKNOWN','SUBMITTING','ACKNOWLEDGED','PARTIALLY_FILLED','CANCEL_REQUESTED') "
                "OR reconciliation_status IN ('MISMATCHED','UNRESOLVED') LIMIT 1"
            ).fetchone()
            if (halted and halted[0] == "true") or uncertain:
                raise ValueError("persisted halt or unresolved paper order state")
    except sqlite3.Error as exc:
        raise ValueError(f"paper state cannot be verified: {exc}") from exc


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
    data_grace_seconds: float | None = None


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
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = config
        self._broker = broker
        self._strategy_fn = strategy_fn
        self._strategy_name = strategy_name
        self._strategy_params = strategy_params or {}
        self._run_config = run_config
        self._bars_provider = bars_provider
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleeper = sleeper
        self._ledger: PaperLedger | None = None
        self._calendar = XNYS_PAPER_CALENDAR
        self._grace = (
            default_data_grace(run_config.bar_frequency)
            if run_config.data_grace_seconds is None
            else timedelta(seconds=finite(run_config.data_grace_seconds))
        )
        if self._grace.total_seconds() < 0:
            raise ValueError("data grace must be non-negative")
        self._namespace = ""
        self._finalized = False

        self._state = PaperRunState()
        self._shutdown_requested = False
        self._registry: ExperimentRegistry | None = None
        self._conn: sqlite3.Connection | None = None
        self._engine: TradingEngine | None = None
        self._db_path: Path | None = None
        self._experiment_verified = False
        self._session_started_at = self._clock().timestamp()
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
            experiment = verify_experiment_hash(
                registry,
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
        if self._ledger is not None and self._namespace:
            self._ledger.record_kill_switch_block(ks.reason, self._clock())
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
        sessions = {c["market_session"] for c in self._state.bar_cycles if c["result"] == "completed"}
        return target is None or len(sessions) >= target

    def _calendar_target_reached(self) -> bool:
        target = self._run_config.window_calendar_days
        return target is None or self._clock().timestamp() - self._session_started_at >= target * 86_400

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
        conn = self._conn if self._conn is not None else init_db(db_path)
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
            paper_order_namespace=self._namespace,
        )
        self._engine = engine
        self._setup_signal_handlers()
        return engine

    def run(self, bars: pd.DataFrame, db_path: str | Path) -> PaperRunState:
        """Reconcile before execution; all attempts and cycles survive process death."""
        self._db_path = Path(db_path)
        self._checkpoint_path = self._db_path.with_suffix(".paper_run_checkpoint.json")
        try:
            experiment = self._verify_experiment()
            self._check_experiment_status(experiment)
            if ArtifactManager(self._run_config.experiment_root).paper_session_path(
                experiment.uuid, self._session_id
            ).exists():
                self._finalized = True
                raise PaperRunHalt("paper session is immutable and already finalized")
            self._conn = init_db(db_path)
            identity = self._identity()
            self._ledger = PaperLedger(self._conn, identity, self._clock())
            self._ledger.start_attempt(self._clock())
            previous_halts = [a for a in self._ledger.rows("paper_attempts") if a["outcome"] in {"halted", "failed"}]
            if previous_halts:
                raise PaperRunHalt(previous_halts[-1]["reason"] or "persisted paper halt")
            self._session_started_at = instant(self._ledger.identity["window_started_at"]).timestamp()
            self._restore_checkpoint()
            self._sync_cycles()
            self._check_kill_switch()
            if self._state.halted:
                raise PaperRunHalt(self._state.halt_reason or "persisted paper halt")
            self._connect_broker()
            if not self._broker.is_connected:
                raise PaperRunHalt("broker disconnected at startup")
            self._ledger.bind_account(self._broker.get_account().account_id)
            self._namespace = self._ledger.identity["binding_digest"]
            engine = self._init_engine(db_path)
            if not engine.startup():
                raise PaperRunHalt("engine startup failed")
            # Paper recovery never allows the config flag to bypass reconciliation.
            engine.reconcile_broker()
            self._check_portfolio_state()
            self._ledger.capture_orders(self._clock())
            self._ledger.reconcile_orders(self._broker, self._clock())
            self._write_checkpoint()
            first = True
            while not self._should_stop():
                self._check_kill_switch()
                if not self._broker.is_connected:
                    raise PaperRunHalt("broker disconnected mid-run")
                if not first and self._bars_provider is not None:
                    bars = self._bars_provider()
                first = False
                if self._shutdown_requested:
                    break
                now = self._clock()
                self._record_overdue(now)
                if self._state.halted:
                    break
                bar_ts = str(bars.index[-1]) if not bars.empty else None
                cycle = self._calendar.cycle_for_bar(self._run_config.bar_frequency, pd.Timestamp(bar_ts)) if bar_ts else None
                known = {c["cycle_key"] for c in self._state.bar_cycles}
                start = datetime.fromtimestamp(self._session_started_at, UTC)
                eligible = (
                    cycle is not None and cycle.cycle_key not in known
                    and start <= cycle.expected_at <= now <= cycle.deadline(self._grace)
                )
                if not eligible:
                    if self._bars_provider is None:
                        break
                    self._sleep_between_cycles()
                    continue
                decision_id = f"paper:{self._namespace}:{bar_ts}"
                row = {
                    "cycle_key": cycle.cycle_key, "market_session": cycle.market_session,
                    "expected_at": cycle.expected_at.isoformat(), "deadline_at": cycle.deadline(self._grace).isoformat(),
                    "started_at": now.isoformat(), "completed_at": None,
                    "input_data_watermark": bar_ts, "result": "started", "reason": None,
                    "decision_record_id": decision_id,
                    "broker_sync_record_id": f"{self._ledger.attempt_id}:{cycle.cycle_key}",
                }
                self._ledger.record_cycle(row, now)
                engine.reconcile_broker()
                self._check_portfolio_state()
                prices = self._fetch_prices(bars)
                if len(prices) != len(self._run_config.symbols):
                    row.update(result="missed_unexplained", reason="no valid broker prices available")
                    self._ledger.record_cycle(row, self._clock())
                    raise PaperRunHalt("missed bar cycle: no valid broker prices available")
                self._ledger.record_reference_prices(cycle.cycle_key, prices, now)
                engine.process_bar(bars=bars, prices=prices, bar_timestamp=bar_ts)
                self._check_kill_switch()
                if engine.state.halted or engine.oms.is_frozen or not self._broker.is_connected:
                    raise PaperRunHalt("execution halted or broker disconnected during cycle")
                engine.reconcile_broker()
                self._check_portfolio_state()
                self._ledger.capture_orders(self._clock())
                self._ledger.bind_account(self._broker.get_account().account_id)
                self._ledger.reconcile_orders(self._broker, self._clock())
                done = self._clock()
                if done > cycle.deadline(self._grace):
                    row.update(result="missed_overdue", reason="cycle completion overdue")
                    self._ledger.record_cycle(row, done)
                    raise PaperRunHalt("cycle completion overdue")
                row.update(result="completed", completed_at=done.isoformat())
                self._ledger.record_cycle(row, done)
                self._sync_cycles()
                self._write_checkpoint()
                if not self._should_stop():
                    self._sleep_between_cycles()
        except Exception as exc:
            self._state.halted = True
            self._state.halt_reason = str(exc)
            self._state.record_error(str(exc))
            log.error("paper_run_halted", error=str(exc))
        finally:
            try:
                if self._ledger is not None:
                    try:
                        self._ledger.capture_orders(self._clock())
                    except Exception as exc:
                        self._state.halted = True
                        self._state.halt_reason = str(exc)
                        self._state.record_error(str(exc))
                    complete = not self._state.halted and self._should_stop() and not self._shutdown_requested
                    outcome = "halted" if self._state.halted else ("completed" if complete else "stopped")
                    self._ledger.close_attempt(self._clock(), outcome, self._state.halt_reason)
                    self._sync_cycles()
                    self._write_checkpoint()
                    self._write_session_evidence(final=complete or not self._has_window_targets())
                    if complete:
                        self._remove_checkpoint()
            finally:
                self._cleanup()
        return self._state

    def _identity(self) -> dict[str, Any]:
        name = getattr(self._broker, "name", "")
        environment = "sim_broker" if name == "sim_broker" else "alpaca_paper"
        if self._config.mode.value != "paper":
            raise PaperRunHalt("paper loop requires paper mode")
        if name != "sim_broker":
            broker = next((b for b in self._config.brokers if b.name == "alpaca"), None)
            if name != "alpaca" or broker is None or not broker.is_paper or broker.base_url.rstrip("/") != "https://paper-api.alpaca.markets":
                raise PaperRunHalt("paper loop refuses unverified broker environment")
            if getattr(self._broker, "_base_url", None) != "https://paper-api.alpaca.markets":
                raise PaperRunHalt("adapter endpoint does not prove broker-paper environment")
            validate_tiny_paper_caps(paper_caps_from_config(self._config))
            deployment = self._config.live_deployment
            if not deployment.paper_submit_enabled or deployment.dry_run_mode:
                raise PaperRunHalt("paper submission is not explicitly enabled")
            if not self._config.engine.startup_reconciliation_required or not self._config.engine.kill_switch_persistent:
                raise PaperRunHalt("paper reconciliation/persistent kill prerequisites missing")
        effective = {
            "config": asdict(self._config), "strategy": self._strategy_name, "parameters": self._strategy_params,
            "symbols": self._run_config.symbols, "frequency": self._run_config.bar_frequency,
            "window_calendar_days": self._run_config.window_calendar_days,
            "window_market_sessions": self._run_config.window_market_sessions,
            "max_cycles": self._run_config.max_cycles,
        }
        return {
            "experiment_uuid": self._run_config.experiment_uuid, "experiment_hash": self._run_config.experiment_hash,
            "session_id": self._session_id, "session_kind": self._run_config.session_kind,
            "config_hash": digest(effective), "code_version": execution_version(),
            "broker_environment": environment, "calendar_id": self._calendar.calendar_id,
            "calendar_version": self._calendar.version, "bar_frequency": self._run_config.bar_frequency,
            "data_grace_seconds": self._grace.total_seconds(),
            "expected_slippage_bps": self._config.cost_model.slippage_fixed_pct * 10000,
        }

    def _sync_cycles(self) -> None:
        if self._ledger is None:
            return
        self._state.bar_cycles = self._ledger.rows("paper_cycles")
        self._state.cycle_count = len(self._state.bar_cycles)
        self._state.total_orders_submitted = len(self._ledger.rows("paper_session_orders"))

    def _record_overdue(self, now: datetime) -> None:
        if self._ledger is None:
            return
        start = datetime.fromtimestamp(self._session_started_at, UTC)
        known = {row["cycle_key"] for row in self._ledger.rows("paper_cycles")}
        for cycle in self._calendar.expected_cycles(self._run_config.bar_frequency, start, now):
            if cycle.cycle_key not in known and now > cycle.deadline(self._grace):
                self._ledger.record_cycle({
                    "cycle_key": cycle.cycle_key, "market_session": cycle.market_session,
                    "expected_at": cycle.expected_at.isoformat(), "deadline_at": cycle.deadline(self._grace).isoformat(),
                    "result": "missed_overdue", "reason": "fresh data did not arrive within cadence and grace",
                    "overdue_detected_at": now.isoformat(),
                }, now)
                self._state.halted = True
                self._state.halt_reason = "fresh data overdue"
        self._sync_cycles()

    def _fetch_prices(self, bars: pd.DataFrame) -> dict[str, float]:
        prices: dict[str, float] = {}
        if bars.empty:
            return prices
        for symbol in self._run_config.symbols:
            try:
                price = self._broker.get_price(symbol)
                if price is not None and finite(price) > 0:
                    prices[symbol] = float(price)
            except Exception:
                pass
        return prices

    def _write_session_evidence(self, *, final: bool = True) -> None:
        if not self._run_config.write_evidence or not self._experiment_verified:
            return
        if self._finalized or self._ledger is None:
            return
        evidence = self._ledger.snapshot(self._clock())
        expected_bps = self._config.cost_model.slippage_fixed_pct * 10000
        try:
            observed = derive_observations(evidence, expected_bps)
        except (ValueError, KeyError, TypeError) as exc:
            observed = {"window": {}, "bar_cycle_report": {}, "slippage_samples": []}
            self._state.record_error(f"incomplete paper evidence: {exc}")
        payload = {
            "experiment_uuid": self._run_config.experiment_uuid,
            "experiment_hash": self._run_config.experiment_hash,
            "session_id": self._session_id,
            "session_kind": self._run_config.session_kind,
            "session_type": "paper_run",
            "operator": self._run_config.operator,
            "broker": getattr(self._broker, "name", "unknown"),
            "identity": evidence["identity"],
            "observations": evidence,
            "expected_slippage_bps": expected_bps,
            "calendar": self._calendar.declaration(),
            "bar_frequency": self._run_config.bar_frequency,
            "symbols": list(self._run_config.symbols),
            "cycle_count": self._state.cycle_count,
            "bar_cycles": list(self._state.bar_cycles),
            "bar_cycle_report": observed["bar_cycle_report"],
            "window": observed["window"],
            "portfolio_state": self._current_portfolio_state(),
            "slippage_samples": observed["slippage_samples"],
            "operator_notes": {
                "claimed_trades": self._run_config.window_trades,
                "claimed_interruptions": self._run_config.window_unplanned_interruptions,
                "insufficient_activity_override_approved": self._run_config.insufficient_activity_override_approved,
                "slippage_samples": list(self._run_config.slippage_samples),
                "kill_switch_drill": self._run_config.kill_switch_drill,
            },
            "halted": self._state.halted,
            "halt_reason": self._state.halt_reason,
            "total_orders_submitted": self._state.total_orders_submitted,
            "order_lifecycle": self._read_order_lifecycle_snapshot(),
            "errors": list(self._state.errors),
            "passed": (
                final and not self._state.halted and not self._state.errors
                and evidence["attempts"][-1]["outcome"] == "completed"
            ),
            "blockers": list(self._state.errors) + ([self._state.halt_reason] if self._state.halt_reason else []),
        }
        try:
            if not final:
                path = ArtifactManager(self._run_config.experiment_root).write_paper_session_report_json(
                    self._run_config.experiment_uuid, self._session_id,
                    f"attempt-{self._ledger.attempt_id}.json", payload,
                )
                self._state.evidence_path = str(path)
                return
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
        except (ArtifactError, ValueError) as e:
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

    def _restore_checkpoint(self) -> None:
        path = self._checkpoint_path
        if path is None or not path.exists():
            return
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            payload = envelope["payload"]
            if digest(payload) != envelope["sha256"] or payload["identity"] != self._identity():
                raise ValueError("checkpoint identity or checksum mismatch")
            self._state.halted = payload["halted"]
            self._state.halt_reason = payload["halt_reason"]
            self._state.errors = payload["errors"]
            if type(self._state.halted) is not bool or not isinstance(self._state.errors, list):
                raise ValueError("checkpoint state is malformed")
        except (ValueError, KeyError, TypeError) as exc:
            raise PaperRunHalt(f"corrupt or mismatched paper checkpoint: {exc}") from exc

    def _write_checkpoint(self) -> None:
        path = self._checkpoint_path
        if path is None or self._ledger is None:
            return
        payload = {
            "identity": self._identity(), "halted": self._state.halted,
            "halt_reason": self._state.halt_reason, "errors": self._state.errors,
        }
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump({"payload": payload, "sha256": digest(payload)}, handle, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
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
        if self._ledger is None:
            return []
        return self._ledger.snapshot(self._clock())["orders"]

    def _sleep_between_cycles(self) -> None:
        if not self._should_stop():
            self._sleeper(max(0.0, self._run_config.sleep_between_bars_seconds))

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
