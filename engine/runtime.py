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
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import structlog

from config.schema import Config
from execution.base import (
    BrokerAdapter,
    OrderSide,
    OrderType,
)
from execution.contracts import execution_contract_for
from execution.evidence import merge_pending_orders
from execution.oms import OMS, OrderIntent
from execution.order_state_machine import OrderState, ReconciliationStatus
from execution.risk_guard import OutboundRiskGuard
from portfolio.accounting import (
    AccountRiskRepository,
    PortfolioSnapshot,
    broker_allows_new_risk_baseline,
    broker_external_cash_flow,
)
from portfolio.sizing import PortfolioState, compute_position_delta, compute_target_positions
from portfolio.state import (
    OrderRiskView,
    PortfolioStateInput,
    derive_portfolio_state,
)
from portfolio.state import (
    PortfolioState as PortfolioStateAuthority,
)
from risk.engine import DrawdownState, RiskCheckResult, RiskDecision, RiskEngine, RiskEvaluation
from risk.inputs import RiskMetadataSnapshot
from storage.event_logger import EventLogger, utc_now_iso
from storage.repository import (
    get_engine_state,
    get_open_orders,
    get_positions,
    is_strategy_halted,
    set_engine_state,
    set_strategy_kill_switch,
)

if TYPE_CHECKING:
    from engine.paper_guard import PaperSubmissionGuard

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
    portfolio_state_authority: PortfolioStateAuthority | None = None


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
        *,
        experiment_uuid: str | None = None,
        registry: Any | None = None,
        paper_order_namespace: str | None = None,
        paper_submission_guard: PaperSubmissionGuard | None = None,
        risk_metadata_provider: Callable[[Sequence[str]], RiskMetadataSnapshot] | None = None,
    ):
        self._config = config
        self._conn = conn
        self._broker = broker
        self._strategy_fn = strategy_fn
        self._strategy_name = strategy_name
        self._strategy_params = strategy_params or {}
        self._experiment_uuid = experiment_uuid
        self._registry = registry
        self._paper_order_namespace = paper_order_namespace
        self._paper_submission_guard = paper_submission_guard
        self._risk_metadata_provider = risk_metadata_provider

        self._logger = EventLogger(conn, environment=config.mode.value)
        self._account_risk = AccountRiskRepository(conn)
        self._risk = RiskEngine(config.risk_limits)
        self._latest_account_risk = None
        self._latest_risk_observed_at: datetime | None = None
        outbound_guard = OutboundRiskGuard(
            broker=broker,
            conn=conn,
            risk_engine=self._risk,
            strategy_name=strategy_name,
            risk_state_reader=self._risk_state_for_outbound,
            metadata_reader=self._risk_metadata,
            allow_short=config.live_deployment.allow_short,
        )
        self._oms = OMS(
            broker, conn, self._logger, environment=config.mode.value,
            outbound_risk_guard=outbound_guard,
        )
        self._state = EngineState(mode=EngineMode(config.mode.value))

        self._shutdown_requested = False
        self._setup_signal_handlers()

    def _risk_metadata(self, symbols: Sequence[str]) -> RiskMetadataSnapshot:
        reader = self._risk_metadata_provider
        if reader is None:
            candidate = getattr(self._broker, "get_risk_metadata", None)
            if not callable(candidate):
                raise ValueError("sector/correlation risk metadata provider is unavailable")
            reader = candidate
        metadata = reader(symbols)
        metadata.validate(symbols)
        return metadata

    def _risk_state_for_outbound(self):
        if self._latest_account_risk is None or self._latest_risk_observed_at is None:
            raise ValueError("durable account risk baselines have not been captured")
        return self._latest_account_risk, self._latest_risk_observed_at

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

        # 3. Connect before requesting authoritative broker truth.
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

        # 4. Reconcile with broker after connection. No caller-supplied or
        # synthetic account state may authorize the first order.
        if self._config.engine.startup_reconciliation_required:
            self._reconcile_broker()
            if self._state.halted:
                return False

        self._state.running = True
        self._logger.log("ENGINE_RESUMED", severity="INFO", message="Engine started successfully")
        return True

    def _reconcile_broker(self) -> None:
        """Reconcile internal state with broker state."""
        self._logger.log("RECONCILIATION_RUN", severity="INFO", message="Starting broker reconciliation")

        try:
            account = self._broker.get_account()
            broker_positions = self._broker.get_positions()
            self._broker.get_open_orders_snapshot().validate()
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
                self._derive_portfolio_state(broker_positions_available=False)
            else:
                self._logger.log(
                    "RECONCILIATION_RUN",
                    severity="INFO",
                    message="Reconciliation passed — all positions match",
                )
                self._derive_portfolio_state(
                    broker_positions_available=True, account=account, broker_positions=broker_positions
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
            self._derive_portfolio_state(broker_positions_available=False)

    def reconcile_broker(self) -> None:
        """Run broker reconciliation using the engine's canonical reconciliation path."""
        self._reconcile_broker()

    def _derive_portfolio_state(
        self,
        *,
        broker_positions_available: bool,
        account: Any | None = None,
        broker_positions: list[Any] | None = None,
        current_prices: dict[str, float] | None = None,
    ) -> None:
        """Derive ``PortfolioState`` (KNOWN | PARTIAL | UNKNOWN) from open
        orders and current positions. Called after every reconciliation. The
        authority drives subsequent ``process_bar`` gating — UNKNOWN freezes,
        PARTIAL blocks new orders.
        """
        open_orders = get_open_orders(self._conn)
        order_views = tuple(
            OrderRiskView(
                client_order_id=str(row["client_order_id"]),
                symbol=str(row["symbol"]),
                side=str(row["side"]),
                remaining_qty=float(row.get("remaining_qty") or 0.0),
                last_price=float(
                    row.get("avg_fill_price")
                    or row.get("limit_price")
                    or (current_prices or {}).get(str(row["symbol"]), 0.0)
                ),
                order_state=OrderState(str(row["order_state"])),
                reconciliation_status=ReconciliationStatus(
                    str(row.get("reconciliation_status") or "NOT_CHECKED")
                ),
            )
            for row in open_orders
        )
        if any(order.remaining_qty > 0 and (not np.isfinite(order.last_price) or order.last_price <= 0)
               for order in order_views):
            self._state.portfolio_state_authority = PortfolioStateAuthority.UNKNOWN
            return
        net_exposure = 0.0
        if not broker_positions_available or account is None or broker_positions is None:
            self._state.portfolio_state_authority = PortfolioStateAuthority.UNKNOWN
            return
        for pos in broker_positions:
            market_value = pos.market_value
            if market_value is None or not np.isfinite(float(market_value)):
                self._state.portfolio_state_authority = PortfolioStateAuthority.UNKNOWN
                return
            net_exposure += float(market_value)
        equity = float(account.equity)
        max_net = float(self._config.risk_limits.max_net_exposure_pct)
        if not np.isfinite(equity) or equity <= 0 or not np.isfinite(max_net) or max_net <= 0:
            self._state.portfolio_state_authority = PortfolioStateAuthority.UNKNOWN
            return

        result = derive_portfolio_state(
            PortfolioStateInput(
                broker_positions_available=broker_positions_available,
                current_net_exposure=float(net_exposure),
                max_net_exposure_pct=max_net,
                equity=equity,
                orders=order_views,
            )
        )
        self._state.portfolio_state_authority = result.state
        self._logger.log(
            "PORTFOLIO_STATE_DERIVED",
            severity="INFO" if result.state == PortfolioStateAuthority.KNOWN else "WARN",
            message=f"portfolio_state={result.state.value} ({result.reason})",
            details=result.to_dict(),
        )

    def _capture_portfolio_inputs(
        self,
        prices: dict[str, float],
        *,
        external_cash_flow: float | None = None,
    ) -> tuple[PortfolioState, DrawdownState, dict[str, dict[str, Any]], list[dict[str, Any]]]:
        """Read and persist one broker snapshot before any strategy/order work."""
        started_at = datetime.now(UTC)
        if external_cash_flow is None:
            external_cash_flow = broker_external_cash_flow(self._broker)
        account = self._broker.get_account()
        broker_positions = self._broker.get_positions()
        broker_orders = self._broker.get_open_orders_snapshot()
        broker_orders.validate()
        pending_orders = merge_pending_orders(broker_orders, get_open_orders(self._conn))
        for order in pending_orders:
            order["last_price"] = order.get("avg_fill_price") or order.get("limit_price") or 0.0
            if not order["last_price"]:
                quote = self._broker.get_quote(str(order.get("symbol", "")))
                if quote is None:
                    raise ValueError("fresh quote evidence is unavailable for a pending order")
                quote.validate(expected_symbol=str(order["symbol"]))
                order["last_price"] = quote.price
        observed_at = datetime.now(UTC)
        snapshot = PortfolioSnapshot.from_broker(
            self._broker.name,
            account,
            broker_positions,
            pending_orders,
            pending_orders_complete=broker_orders.complete,
            pending_orders_observed_at=broker_orders.observed_at,
            pending_orders_source=broker_orders.source,
            observed_at=observed_at,
            external_cash_flow=external_cash_flow,
            allow_new_baseline=broker_allows_new_risk_baseline(self._broker),
        )
        if (snapshot.observed_at - started_at).total_seconds() > 5.0:
            raise ValueError("broker account snapshot reads exceeded the five second collection window")
        snapshot.validate()
        account_risk = self._account_risk.record(snapshot)
        self._latest_account_risk = account_risk
        self._latest_risk_observed_at = observed_at
        positions = {
            position.symbol: {
                "quantity": position.quantity,
                "qty": position.quantity,
                "avg_entry_price": position.avg_entry_price,
                "avg_price": position.avg_entry_price,
                "mark_price": abs(float(position.market_value or 0.0) / position.quantity)
                if position.quantity else 0.0,
                "side": position.side,
            }
            for position in snapshot.positions
            if position.quantity
        }
        state = PortfolioState(
            cash=snapshot.cash,
            equity=snapshot.equity,
            high_water_mark=account_risk.high_water_mark,
            positions={
                symbol: {"qty": row["quantity"], "avg_price": row["mark_price"], "side": row["side"]}
                for symbol, row in positions.items()
            },
        )
        drawdown = account_risk.drawdown(snapshot.equity)
        self._derive_portfolio_state(
            broker_positions_available=True,
            account=account,
            broker_positions=broker_positions,
            current_prices=prices,
        )
        return state, drawdown, positions, pending_orders

    def process_bar(
        self,
        bars: pd.DataFrame,
        prices: dict[str, float],
        *,
        bar_timestamp: str | None = None,
        portfolio_state: PortfolioState | None = None,
        drawdown: DrawdownState | None = None,
        external_cash_flow: float | None = None,
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

        if self._state.portfolio_state_authority != PortfolioStateAuthority.UNKNOWN:
            try:
                fresh_state, fresh_drawdown, broker_positions, pending_orders = self._capture_portfolio_inputs(
                    prices, external_cash_flow=external_cash_flow
                )
                portfolio_state = fresh_state
                drawdown = fresh_drawdown
            except Exception as error:
                self._state.portfolio_state_authority = PortfolioStateAuthority.UNKNOWN
                self._logger.log(
                    "ACCOUNT_SNAPSHOT_INVALID",
                    severity="CRITICAL",
                    exception=str(error),
                    message="Bar skipped — fresh account and position truth could not be validated",
                )
                return None
        else:
            broker_positions = {}
            pending_orders = []

        authority = self._state.portfolio_state_authority
        if authority == PortfolioStateAuthority.UNKNOWN:
            self._logger.log(
                "PORTFOLIO_STATE_FREEZE",
                severity="CRITICAL",
                strategy=self._strategy_name,
                bar_timestamp=bar_timestamp,
                message=(
                    "Bar skipped — portfolio_state UNKNOWN: broker truth ambiguous, "
                    "manual intervention required (no flatten, no new orders)"
                ),
            )
            return None

        bar_ts = bar_timestamp or utc_now_iso()
        self._state.current_bar = pd.Timestamp(bar_ts)
        self._state.cycle_count += 1

        cycle_id = (
            f"paper:{self._paper_order_namespace}:{bar_ts}"
            if self._paper_order_namespace else f"cycle_{self._state.cycle_count}_{bar_ts}"
        )
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
            if self._experiment_uuid is not None and self._registry is not None:
                from experiments.kill_switch import KillSwitchSeverity

                self._registry.set_kill_switch(
                    self._experiment_uuid,
                    KillSwitchSeverity.SOFT,
                    f"signal_generation_error: {e}",
                    set_by="engine",
                )
            else:
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
        state = portfolio_state
        if state is None:
            self._state.portfolio_state_authority = PortfolioStateAuthority.UNKNOWN
            self._logger.log(
                "ACCOUNT_SNAPSHOT_INVALID",
                severity="CRITICAL",
                message="Bar skipped — no validated portfolio state available",
            )
            return None
        targets = compute_target_positions(
            exposures,
            prices,
            state,
            self._config.portfolio,
        )

        # 3. Run risk checks (risk accepts/rejects/modifies)
        dd = drawdown
        if dd is None:
            self._state.portfolio_state_authority = PortfolioStateAuthority.UNKNOWN
            self._logger.log(
                "ACCOUNT_SNAPSHOT_INVALID",
                severity="CRITICAL",
                message="Bar skipped — durable period loss state is unavailable",
            )
            return None
        current_positions = broker_positions
        required_symbols = set(current_positions)
        required_symbols.update(str(order.get("symbol", "")) for order in pending_orders)
        required_symbols.update(target.symbol for target in targets)
        required_symbols.discard("")
        try:
            risk_metadata = self._risk_metadata(sorted(required_symbols))
        except Exception as error:
            message = f"risk_metadata_unavailable: {error}"
            evaluation = RiskEvaluation(
                decisions=[RiskCheckResult("risk_metadata", RiskDecision.REJECTED, str(error))],
                final_decision=RiskDecision.REJECTED,
                rejection_reasons=[message],
            )
            self._logger.log(
                "RISK_CHECK_BLOCKED",
                severity="WARN",
                strategy=self._strategy_name,
                bar_timestamp=bar_ts,
                message="Bar blocked — complete sector and correlation evidence is unavailable",
                details={"reason": message},
            )
            self._log_cycle_complete(cycle_id, bar_ts)
            return evaluation
        evaluation = self._risk.evaluate(
            targets,
            state,
            dd,
            strategy_name=self._strategy_name,
            current_positions=current_positions,
            pending_orders=pending_orders,
            sector_map=risk_metadata.sectors,
            correlation_matrix=risk_metadata.correlations,
        )

        try:
            contract_targets = self._constrain_targets_to_contract(
                evaluation.adjusted_targets, state, current_positions, pending_orders
            )
        except ValueError as error:
            evaluation.final_decision = RiskDecision.REJECTED
            evaluation.adjusted_targets = []
            evaluation.rejection_reasons.append(f"execution_contract: {error}")
            contract_targets = []
        if evaluation.rejection_reasons and not contract_targets and "execution_contract" in evaluation.rejection_reasons[-1]:
            self._log_cycle_complete(cycle_id, bar_ts)
            return evaluation
        # Re-run limits against contract-sized quantities, repeating if any
        # risk reduction changes the exact broker quantity again.
        candidate_targets = contract_targets
        for _ in range(12):
            evaluation = self._risk.evaluate(
                candidate_targets,
                state,
                dd,
                strategy_name=self._strategy_name,
                current_positions=current_positions,
                pending_orders=pending_orders,
                sector_map=risk_metadata.sectors,
                correlation_matrix=risk_metadata.correlations,
            )
            constrained = self._constrain_targets_to_contract(
                evaluation.adjusted_targets, state, current_positions, pending_orders
            )
            contract_steps = [
                float(execution_contract_for(self._broker.name, left.asset_class).quantity_step)
                for left in evaluation.adjusted_targets
            ]
            if all(
                abs(left.target_qty - right.target_qty) < step
                for left, right, step in zip(evaluation.adjusted_targets, constrained, contract_steps, strict=True)
            ):
                # Contract sizing truncates deltas toward zero. Accept a final
                # sub-step remainder only when it is smaller than one broker
                # quantity increment; submitted quantities remain rounded down.
                evaluation.adjusted_targets = constrained
                break
            candidate_targets = constrained
        else:
            evaluation.final_decision = RiskDecision.REJECTED
            evaluation.adjusted_targets = []
            evaluation.rejection_reasons.append("execution_contract: risk and quantity rounding did not converge")

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

        # 4. Submit approved orders, plus only provably risk-reducing exits
        # when an order is reconciling or an entry gate rejected the signal.
        if authority == PortfolioStateAuthority.PARTIAL:
            self._logger.log(
                "PORTFOLIO_STATE_BLOCK_NEW_ORDERS",
                severity="WARN",
                strategy=self._strategy_name,
                bar_timestamp=bar_ts,
                message=(
                    "New entries blocked — portfolio_state PARTIAL; only exits "
                    "against confirmed positions without same-symbol pending orders may proceed."
                ),
            )

        for target in evaluation.adjusted_targets:
            # Compute delta from current position
            current_qty = current_positions.get(target.symbol, {}).get("quantity", 0.0)
            delta = compute_position_delta(
                target,
                current_qty,
                execution_mode=self._config.portfolio.execution_mode,
                min_notional_delta=self._config.portfolio.min_notional_delta,
                min_qty_delta=self._config.portfolio.min_qty_delta,
                min_pct_position_delta=self._config.portfolio.min_pct_position_delta,
            )

            if delta["action"] == "hold":
                continue

            same_symbol_pending = any(
                str(order.get("symbol", "")) == target.symbol
                and float(order.get("remaining_qty", 0.0) or 0.0) > 0.0
                for order in pending_orders
            )
            is_reducing_exit = (
                abs(float(current_qty)) > 1e-12
                and float(current_qty) * float(delta["delta_qty"]) < 0.0
                and abs(float(delta["delta_qty"])) <= abs(float(current_qty)) + 1e-12
                and not same_symbol_pending
            )
            if authority == PortfolioStateAuthority.PARTIAL and not is_reducing_exit:
                continue
            if evaluation.is_rejected and not is_reducing_exit:
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
                reference_price=float(target.current_price),
                bar_timestamp=bar_ts,
                correlation_id=cycle_id,
                version=self._config.strategy_version,
                client_order_namespace=self._paper_order_namespace or "",
            )

            if (
                self._state.mode == EngineMode.PAPER and self._broker.name != "sim_broker"
                and self._paper_submission_guard is None
            ):
                raise ValueError("broker-paper submission requires durable paper admission")
            reservation = (
                self._paper_submission_guard.reserve(intent)
                if self._paper_submission_guard is not None else None
            )
            order_id = self._oms.create_and_submit(intent)
            if self._paper_submission_guard is not None:
                self._paper_submission_guard.observe(reservation, order_id)

        self._log_cycle_complete(cycle_id, bar_ts)

        return evaluation

    def _constrain_targets_to_contract(
        self,
        targets: list[Any],
        state: PortfolioState,
        current_positions: dict[str, dict[str, Any]],
        pending_orders: list[dict[str, Any]],
    ) -> list[Any]:
        """Round every proposed delta down and leave sufficient cash reserved."""
        from portfolio.sizing import compute_position_delta

        cash_available = state.cash - sum(
            float(order.get("remaining_qty", 0.0) or 0.0) * float(order.get("last_price", 0.0) or 0.0)
            for order in pending_orders
            if str(order.get("side", "")).lower().startswith("b")
        )
        if not np.isfinite(cash_available):
            raise ValueError("cash available after pending buys is not finite")
        result: list[Any] = []
        for target in targets:
            current_qty = float(current_positions.get(target.symbol, {}).get("quantity", 0.0))
            delta = compute_position_delta(
                target,
                current_qty,
                execution_mode=self._config.portfolio.execution_mode,
                min_notional_delta=self._config.portfolio.min_notional_delta,
                min_qty_delta=self._config.portfolio.min_qty_delta,
                min_pct_position_delta=self._config.portfolio.min_pct_position_delta,
            )
            if delta["action"] == "hold":
                result.append(target)
                continue
            contract = execution_contract_for(self._broker.name, target.asset_class)
            buy = float(delta["delta_qty"]) > 0
            available = max(0.0, cash_available) if buy else None
            quantity = contract.constrain_quantity(
                float(delta["delta_qty"]), target.current_price, available_cash=available
            )
            if not buy and not self._config.live_deployment.allow_short:
                closeable_qty = max(0.0, current_qty)
                quantity = min(quantity, contract.constrain_quantity(closeable_qty, target.current_price))
            if buy:
                cash_available -= quantity * target.current_price
            signed_delta = quantity if buy else -quantity
            final_qty = current_qty + signed_delta
            side = "long" if final_qty > 0 else ("short" if final_qty < 0 else "flat")
            result.append(
                replace(
                    target,
                    side=side,
                    target_qty=final_qty,
                    target_notional=abs(final_qty) * target.current_price,
                )
            )
        return result

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
