"""Order state machine — 12 states + separate reconciliation_status.

States:
    INTENDED → BLOCKED_BY_RISK → SUBMITTING → ACKNOWLEDGED →
    PARTIALLY_FILLED → FILLED → CANCEL_REQUESTED → CANCELLED →
    REJECTED → EXPIRED → TIMEOUT → UNKNOWN

Separate field (NOT a lifecycle state):
    reconciliation_status: NOT_CHECKED | MATCHED | MISMATCHED | REPAIRED | UNRESOLVED

Rules:
    - TIMEOUT must reconcile by client_order_id before manual review
    - No retry from TIMEOUT → SUBMITTING (prevents duplicates)
    - PARTIALLY_FILLED → CANCELLED/EXPIRED preserves filled quantity
    - BLOCKED_BY_RISK is separate from REJECTED (broker rejection)
"""

from __future__ import annotations

from enum import StrEnum


class OrderState(StrEnum):
    INTENDED = "INTENDED"
    BLOCKED_BY_RISK = "BLOCKED_BY_RISK"
    SUBMITTING = "SUBMITTING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


class ReconciliationStatus(StrEnum):
    NOT_CHECKED = "NOT_CHECKED"
    MATCHED = "MATCHED"
    MISMATCHED = "MISMATCHED"
    REPAIRED = "REPAIRED"
    UNRESOLVED = "UNRESOLVED"


# Allowed transitions: (from_state → set of allowed to_states)
ALLOWED_TRANSITIONS: dict[OrderState, set[OrderState]] = {
    OrderState.INTENDED: {
        OrderState.BLOCKED_BY_RISK,
        OrderState.SUBMITTING,
        OrderState.REJECTED,  # if validation fails pre-submit
    },
    OrderState.BLOCKED_BY_RISK: set(),  # terminal — risk blocked
    OrderState.SUBMITTING: {
        OrderState.ACKNOWLEDGED,
        OrderState.REJECTED,
        OrderState.TIMEOUT,
        OrderState.FILLED,  # instant fill (market orders)
        OrderState.PARTIALLY_FILLED,  # instant partial fill
    },
    OrderState.ACKNOWLEDGED: {
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCEL_REQUESTED,
        OrderState.REJECTED,  # broker can reject after ack
        OrderState.EXPIRED,
        OrderState.TIMEOUT,  # lost connection after ack
    },
    OrderState.PARTIALLY_FILLED: {
        OrderState.FILLED,
        OrderState.CANCEL_REQUESTED,
        OrderState.EXPIRED,
        OrderState.PARTIALLY_FILLED,  # more partial fills
    },
    OrderState.FILLED: set(),  # terminal
    OrderState.CANCEL_REQUESTED: {
        OrderState.CANCELLED,
        OrderState.FILLED,  # race: filled before cancel processed
        OrderState.PARTIALLY_FILLED,  # partial fill + cancel remainder
    },
    OrderState.CANCELLED: set(),  # terminal
    OrderState.REJECTED: set(),  # terminal
    OrderState.EXPIRED: set(),  # terminal
    OrderState.TIMEOUT: {
        # TIMEOUT must reconcile, NOT retry blindly
        OrderState.ACKNOWLEDGED,  # found alive on broker
        OrderState.CANCELLED,  # broker confirms cancel/no live order
        OrderState.REJECTED,  # broker confirms rejection
        OrderState.EXPIRED,  # broker confirms order expired
        OrderState.FILLED,  # actually filled
        OrderState.PARTIALLY_FILLED,
        OrderState.UNKNOWN,  # cannot determine → manual review
    },
    OrderState.UNKNOWN: {
        OrderState.ACKNOWLEDGED,  # resolved via reconciliation
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.REJECTED,
    },
}

TERMINAL_STATES = {
    OrderState.BLOCKED_BY_RISK,
    OrderState.FILLED,
    OrderState.CANCELLED,
    OrderState.REJECTED,
    OrderState.EXPIRED,
}


class IllegalTransitionError(Exception):
    """Raised when an order state transition is not allowed."""

    def __init__(self, from_state: OrderState, to_state: OrderState):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Illegal order state transition: {from_state.value} → {to_state.value}"
        )


def is_transition_allowed(from_state: OrderState, to_state: OrderState) -> bool:
    """Check if a state transition is allowed."""
    if from_state == to_state:
        return True  # idempotent — same state is always allowed
    allowed = ALLOWED_TRANSITIONS.get(from_state, set())
    return to_state in allowed


def validate_transition(from_state: OrderState, to_state: OrderState) -> None:
    """Validate a transition, raising IllegalTransitionError if not allowed."""
    if not is_transition_allowed(from_state, to_state):
        raise IllegalTransitionError(from_state, to_state)


def is_terminal(state: OrderState) -> bool:
    """Check if an order state is terminal (no further transitions)."""
    return state in TERMINAL_STATES


def is_filled_state(state: OrderState) -> bool:
    """Check if the state indicates the order has been (at least partially) filled."""
    return state in (OrderState.FILLED, OrderState.PARTIALLY_FILLED)


def reconcile_timeout(
    broker_status: str | None,
    broker_filled_qty: float,
    requested_qty: float,
) -> OrderState:
    """Determine the correct state after a TIMEOUT reconciliation.

    Args:
        broker_status: Status reported by broker (None if unreachable).
        broker_filled_qty: Quantity filled according to broker.
        requested_qty: Original requested quantity.

    Returns:
        The resolved OrderState after reconciliation.
    """
    if broker_status is None:
        # Broker unreachable → UNKNOWN, manual review
        return OrderState.UNKNOWN

    normalized_status = broker_status.strip().upper()
    terminal_statuses = {
        "CANCELLED": OrderState.CANCELLED,
        "CANCELED": OrderState.CANCELLED,
        "REJECTED": OrderState.REJECTED,
        "EXPIRED": OrderState.EXPIRED,
    }
    acknowledged_statuses = {"ACKNOWLEDGED", "OPEN", "NEW", "ACCEPTED"}

    if broker_filled_qty >= requested_qty:
        return OrderState.FILLED
    elif broker_filled_qty > 0:
        return OrderState.PARTIALLY_FILLED
    elif normalized_status in terminal_statuses:
        return terminal_statuses[normalized_status]
    elif normalized_status in acknowledged_statuses:
        return OrderState.ACKNOWLEDGED
    else:
        return OrderState.UNKNOWN
