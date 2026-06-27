"""Portfolio state derivation — KNOWN | PARTIAL | UNKNOWN.

Per CONTEXT.md:

- **KNOWN**  — current broker positions and pending exposure are fully
  reconciled; safe to flatten and cancel safe orders.
- **PARTIAL** — broker-reported net positions are fully known, but one or
  more non-terminal orders are still reconciling and their final execution
  cannot increase net exposure beyond configured limits; flatten confirmed
  positions only after canceling or confirming outstanding orders; block new
  orders; suspend Experiment; continue reconciliation.
- **UNKNOWN** — broker truth cannot be established; future net exposure is
  ambiguous; freeze; no flatten; no new orders; manual intervention required.

The decision engine uses only ``PortfolioState``. ``ExposureConfidence`` is
derived read-time telemetry for dashboards — never stored independently.

A historically known fill does not authorize liquidation if pending orders
could still change net exposure. Flatten only when the current reconciled
broker position is confirmed with no ambiguous future exposure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from execution.order_state_machine import (
    OrderState,
    ReconciliationStatus,
    is_terminal,
)


class PortfolioState(StrEnum):
    """Authority for rollback / flatten / block decisions."""

    KNOWN = "KNOWN"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class ExposureConfidence(StrEnum):
    """Dashboard telemetry derived from ``portfolio_state`` at read time.

    Never stored independently — derived from ``PortfolioState`` by
    ``exposure_confidence_from_state``.
    """

    HIGH = "HIGH"  # KNOWN
    MEDIUM = "MEDIUM"  # PARTIAL
    LOW = "LOW"  # UNKNOWN


@dataclass(frozen=True)
class OrderRiskView:
    """Per-order risk view used by the portfolio-state derivation."""

    client_order_id: str
    symbol: str
    side: str  # "buy" | "sell"
    remaining_qty: float
    last_price: float
    order_state: OrderState
    reconciliation_status: ReconciliationStatus

    @property
    def is_reconciling(self) -> bool:
        """True when the order is non-terminal AND reconciliation is open."""
        return (
            not is_terminal(self.order_state)
            and self.reconciliation_status
            in {ReconciliationStatus.NOT_CHECKED, ReconciliationStatus.MISMATCHED}
        )

    @property
    def is_unresolved(self) -> bool:
        """True when the order's broker truth itself cannot be established."""
        return (
            self.order_state == OrderState.UNKNOWN
            or self.reconciliation_status == ReconciliationStatus.UNRESOLVED
        )

    def worst_case_exposure(self) -> float:
        """Signed worst-case dollar exposure contribution if this order
        finishes fully in the direction it was submitted.

        Buys contribute +notional; sells contribute -notional. The derivation
        is conservative — it assumes the remaining quantity fills in full.
        """
        notional = self.remaining_qty * self.last_price
        return notional if self.side.lower().startswith("b") else -notional


@dataclass(frozen=True)
class PortfolioStateInput:
    """Inputs to ``derive_portfolio_state``."""

    broker_positions_available: bool
    current_net_exposure: float
    max_net_exposure_pct: float  # configured bound on |net| relative to equity
    equity: float
    orders: tuple[OrderRiskView, ...] = field(default_factory=tuple)
    notes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.equity <= 0.0:
            raise ValueError("equity must be > 0")
        if self.max_net_exposure_pct <= 0.0:
            raise ValueError("max_net_exposure_pct must be > 0")


@dataclass(frozen=True)
class PortfolioStateResult:
    """Output of ``derive_portfolio_state``."""

    state: PortfolioState
    confidence: ExposureConfidence
    reconciling_orders: tuple[str, ...]
    unresolved_orders: tuple[str, ...]
    worst_case_net_exposure: float
    worst_case_net_pct: float
    within_net_limit: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "confidence": self.confidence.value,
            "reconciling_orders": list(self.reconciling_orders),
            "unresolved_orders": list(self.unresolved_orders),
            "worst_case_net_exposure": self.worst_case_net_exposure,
            "worst_case_net_pct": self.worst_case_net_pct,
            "within_net_limit": self.within_net_limit,
            "reason": self.reason,
        }


def derive_portfolio_state(inputs: PortfolioStateInput) -> PortfolioStateResult:
    """Authoritative decision-engine input.

    Rules (in order):

    1. If broker truth is unavailable, return ``UNKNOWN``.
    2. If any order has ``order_state == UNKNOWN`` or ``reconciliation_status
       == UNRESOLVED``, return ``UNKNOWN`` — broker truth cannot be
       established for the whole book while any leg is unresolved.
    3. If there are no reconciling orders, return ``KNOWN``.
    4. Otherwise compute the worst-case net exposure assuming every
       reconciling order fills fully in its submitted direction. If the
       absolute worst-case stays within ``max_net_exposure_pct * equity``,
       return ``PARTIAL``; else return ``UNKNOWN`` — unbounded pending
       exposure means we cannot safely flatten or cancel.
    """
    if not inputs.broker_positions_available:
        return _result(
            state=PortfolioState.UNKNOWN,
            inputs=inputs,
            worst_case=inputs.current_net_exposure,
            reason="broker positions unavailable",
        )

    unresolved = tuple(
        order.client_order_id for order in inputs.orders if order.is_unresolved
    )
    if unresolved:
        return _result(
            state=PortfolioState.UNKNOWN,
            inputs=inputs,
            worst_case=inputs.current_net_exposure,
            unresolved=unresolved,
            reason=(
                f"{len(unresolved)} order(s) have unresolved broker truth "
                "(UNKNOWN state or UNRESOLVED reconciliation)"
            ),
        )

    reconciling = tuple(
        order.client_order_id for order in inputs.orders if order.is_reconciling
    )
    if not reconciling:
        return _result(
            state=PortfolioState.KNOWN,
            inputs=inputs,
            worst_case=inputs.current_net_exposure,
            reason="all orders terminal or reconciled (MATCHED/REPAIRED)",
        )

    worst_case = inputs.current_net_exposure + sum(
        order.worst_case_exposure() for order in inputs.orders if order.is_reconciling
    )
    worst_pct = abs(worst_case) / inputs.equity
    within_limit = worst_pct <= inputs.max_net_exposure_pct
    if within_limit:
        return _result(
            state=PortfolioState.PARTIAL,
            inputs=inputs,
            worst_case=worst_case,
            reconciling=reconciling,
            reason=(
                f"{len(reconciling)} non-terminal order(s) still reconciling; "
                f"worst-case net {worst_pct:.4f} <= limit {inputs.max_net_exposure_pct:.4f}"
            ),
        )
    return _result(
        state=PortfolioState.UNKNOWN,
        inputs=inputs,
        worst_case=worst_case,
        reconciling=reconciling,
        reason=(
            f"{len(reconciling)} reconciling order(s); worst-case net {worst_pct:.4f} "
            f"> limit {inputs.max_net_exposure_pct:.4f} — unbounded future exposure"
        ),
    )


def exposure_confidence_from_state(state: PortfolioState) -> ExposureConfidence:
    """Derive dashboard telemetry from the authoritative field."""
    return {
        PortfolioState.KNOWN: ExposureConfidence.HIGH,
        PortfolioState.PARTIAL: ExposureConfidence.MEDIUM,
        PortfolioState.UNKNOWN: ExposureConfidence.LOW,
    }[state]


def _result(
    *,
    state: PortfolioState,
    inputs: PortfolioStateInput,
    worst_case: float,
    reconciling: tuple[str, ...] = (),
    unresolved: tuple[str, ...] = (),
    reason: str,
) -> PortfolioStateResult:
    worst_pct = abs(worst_case) / inputs.equity
    return PortfolioStateResult(
        state=state,
        confidence=exposure_confidence_from_state(state),
        reconciling_orders=reconciling,
        unresolved_orders=unresolved,
        worst_case_net_exposure=float(worst_case),
        worst_case_net_pct=float(worst_pct),
        within_net_limit=worst_pct <= inputs.max_net_exposure_pct,
        reason=reason,
    )
