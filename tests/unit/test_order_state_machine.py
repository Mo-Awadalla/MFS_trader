"""Tests for the order state machine."""

from __future__ import annotations

import pytest

from execution.order_state_machine import (
    IllegalTransitionError,
    OrderState,
    ReconciliationStatus,
    is_filled_state,
    is_terminal,
    is_transition_allowed,
    reconcile_timeout,
    validate_transition,
)


class TestAllowedTransitions:
    def test_intended_to_submitting(self):
        assert is_transition_allowed(OrderState.INTENDED, OrderState.SUBMITTING)

    def test_intended_to_blocked_by_risk(self):
        assert is_transition_allowed(OrderState.INTENDED, OrderState.BLOCKED_BY_RISK)

    def test_submitting_to_acknowledged(self):
        assert is_transition_allowed(OrderState.SUBMITTING, OrderState.ACKNOWLEDGED)

    def test_submitting_to_timeout(self):
        assert is_transition_allowed(OrderState.SUBMITTING, OrderState.TIMEOUT)

    def test_acknowledged_to_partially_filled(self):
        assert is_transition_allowed(OrderState.ACKNOWLEDGED, OrderState.PARTIALLY_FILLED)

    def test_acknowledged_to_cancel_requested(self):
        assert is_transition_allowed(OrderState.ACKNOWLEDGED, OrderState.CANCEL_REQUESTED)

    def test_partially_filled_to_cancelled(self):
        assert is_transition_allowed(OrderState.PARTIALLY_FILLED, OrderState.CANCEL_REQUESTED)
        assert is_transition_allowed(OrderState.CANCEL_REQUESTED, OrderState.CANCELLED)

    def test_partially_filled_to_expired(self):
        assert is_transition_allowed(OrderState.PARTIALLY_FILLED, OrderState.EXPIRED)

    def test_timeout_to_acknowledged(self):
        """TIMEOUT can resolve to ACKNOWLEDGED via reconciliation."""
        assert is_transition_allowed(OrderState.TIMEOUT, OrderState.ACKNOWLEDGED)

    def test_timeout_to_filled(self):
        assert is_transition_allowed(OrderState.TIMEOUT, OrderState.FILLED)

    def test_timeout_to_unknown(self):
        assert is_transition_allowed(OrderState.TIMEOUT, OrderState.UNKNOWN)


class TestForbiddenTransitions:
    def test_filled_to_submitting_forbidden(self):
        assert not is_transition_allowed(OrderState.FILLED, OrderState.SUBMITTING)

    def test_cancelled_to_submitting_forbidden(self):
        assert not is_transition_allowed(OrderState.CANCELLED, OrderState.SUBMITTING)

    def test_timeout_to_submitting_forbidden(self):
        """No blind retry from TIMEOUT."""
        assert not is_transition_allowed(OrderState.TIMEOUT, OrderState.SUBMITTING)

    def test_rejected_to_acknowledged_forbidden(self):
        assert not is_transition_allowed(OrderState.REJECTED, OrderState.ACKNOWLEDGED)

    def test_blocked_by_risk_is_terminal(self):
        """BLOCKED_BY_RISK cannot transition to SUBMITTING."""
        assert not is_transition_allowed(OrderState.BLOCKED_BY_RISK, OrderState.SUBMITTING)

    def test_validate_transition_raises(self):
        with pytest.raises(IllegalTransitionError):
            validate_transition(OrderState.FILLED, OrderState.SUBMITTING)


class TestTerminalStates:
    def test_filled_is_terminal(self):
        assert is_terminal(OrderState.FILLED)

    def test_cancelled_is_terminal(self):
        assert is_terminal(OrderState.CANCELLED)

    def test_rejected_is_terminal(self):
        assert is_terminal(OrderState.REJECTED)

    def test_expired_is_terminal(self):
        assert is_terminal(OrderState.EXPIRED)

    def test_blocked_by_risk_is_terminal(self):
        assert is_terminal(OrderState.BLOCKED_BY_RISK)

    def test_acknowledged_not_terminal(self):
        assert not is_terminal(OrderState.ACKNOWLEDGED)

    def test_submitting_not_terminal(self):
        assert not is_terminal(OrderState.SUBMITTING)


class TestFilledState:
    def test_filled_is_filled(self):
        assert is_filled_state(OrderState.FILLED)

    def test_partially_filled_is_filled(self):
        assert is_filled_state(OrderState.PARTIALLY_FILLED)

    def test_acknowledged_not_filled(self):
        assert not is_filled_state(OrderState.ACKNOWLEDGED)


class TestReconcileTimeout:
    def test_broker_unreachable_returns_unknown(self):
        state = reconcile_timeout(None, 0, 100)
        assert state == OrderState.UNKNOWN

    def test_fully_filled_returns_filled(self):
        state = reconcile_timeout("FILLED", 100, 100)
        assert state == OrderState.FILLED

    def test_partially_filled_returns_partial(self):
        state = reconcile_timeout("PARTIALLY_FILLED", 50, 100)
        assert state == OrderState.PARTIALLY_FILLED

    def test_acknowledged_returns_acknowledged(self):
        state = reconcile_timeout("ACKNOWLEDGED", 0, 100)
        assert state == OrderState.ACKNOWLEDGED

    def test_open_returns_acknowledged(self):
        state = reconcile_timeout("OPEN", 0, 100)
        assert state == OrderState.ACKNOWLEDGED

    @pytest.mark.parametrize(
        ("broker_status", "expected"),
        [
            ("CANCELLED", OrderState.CANCELLED),
            ("CANCELED", OrderState.CANCELLED),
            ("REJECTED", OrderState.REJECTED),
            ("EXPIRED", OrderState.EXPIRED),
            ("cancelled", OrderState.CANCELLED),
            (" rejected ", OrderState.REJECTED),
        ],
    )
    def test_terminal_broker_status_returns_terminal_state(self, broker_status, expected):
        state = reconcile_timeout(broker_status, 0, 100)
        assert state == expected


class TestReconciliationStatus:
    def test_reconciliation_is_separate_field(self):
        """ReconciliationStatus is a separate enum, not an OrderState."""
        assert ReconciliationStatus.NOT_CHECKED not in OrderState
        assert ReconciliationStatus.MATCHED not in OrderState
        assert ReconciliationStatus.MISMATCHED not in OrderState
        assert ReconciliationStatus.REPAIRED not in OrderState
        assert ReconciliationStatus.UNRESOLVED not in OrderState
