"""Tests for portfolio_state derivation — KNOWN | PARTIAL | UNKNOWN."""

from __future__ import annotations

import pytest

from execution.order_state_machine import OrderState, ReconciliationStatus
from portfolio.state import (
    ExposureConfidence,
    OrderRiskView,
    PortfolioState,
    PortfolioStateInput,
    derive_portfolio_state,
    exposure_confidence_from_state,
)


def _order(
    client_order_id: str = "o1",
    symbol: str = "AAPL",
    side: str = "buy",
    remaining_qty: float = 10.0,
    last_price: float = 100.0,
    order_state: OrderState = OrderState.FILLED,
    reconciliation_status: ReconciliationStatus = ReconciliationStatus.MATCHED,
) -> OrderRiskView:
    return OrderRiskView(
        client_order_id=client_order_id,
        symbol=symbol,
        side=side,
        remaining_qty=remaining_qty,
        last_price=last_price,
        order_state=order_state,
        reconciliation_status=reconciliation_status,
    )


def _input(
    *,
    orders: tuple[OrderRiskView, ...] = (),
    current_net_exposure: float = 0.0,
    max_net_exposure_pct: float = 0.30,
    equity: float = 10_000.0,
    broker_positions_available: bool = True,
) -> PortfolioStateInput:
    return PortfolioStateInput(
        broker_positions_available=broker_positions_available,
        current_net_exposure=current_net_exposure,
        max_net_exposure_pct=max_net_exposure_pct,
        equity=equity,
        orders=orders,
    )


class TestPortfolioStateDerivation:
    def test_known_when_all_orders_terminal_and_reconciled(self) -> None:
        orders = (
            _order(client_order_id="filled", order_state=OrderState.FILLED),
            _order(client_order_id="cancelled", order_state=OrderState.CANCELLED),
        )
        result = derive_portfolio_state(_input(orders=orders))
        assert result.state == PortfolioState.KNOWN
        assert result.confidence == ExposureConfidence.HIGH
        assert result.reconciling_orders == ()
        assert result.unresolved_orders == ()

    def test_unknown_when_broker_positions_unavailable(self) -> None:
        result = derive_portfolio_state(
            _input(broker_positions_available=False, orders=())
        )
        assert result.state == PortfolioState.UNKNOWN
        assert result.confidence == ExposureConfidence.LOW
        assert "broker positions unavailable" in result.reason

    def test_unknown_when_any_order_in_unknown_state(self) -> None:
        orders = (_order(client_order_id="lost", order_state=OrderState.UNKNOWN),)
        result = derive_portfolio_state(_input(orders=orders))
        assert result.state == PortfolioState.UNKNOWN
        assert result.unresolved_orders == ("lost",)
        assert "UNRESOLVED" in result.reason or "UNKNOWN" in result.reason

    def test_unknown_when_any_reconciliation_unresolved(self) -> None:
        orders = (
            _order(
                client_order_id="bad",
                order_state=OrderState.PARTIALLY_FILLED,
                reconciliation_status=ReconciliationStatus.UNRESOLVED,
            ),
        )
        result = derive_portfolio_state(_input(orders=orders))
        assert result.state == PortfolioState.UNKNOWN
        assert result.unresolved_orders == ("bad",)

    def test_partial_when_reconciling_and_worst_case_within_limit(self) -> None:
        # current net = 0; one pending buy 10 @ 100 = +1000 notional.
        # equity = 10_000; max_net = 30% = 3000. Worst-case = +1000 => 10%.
        orders = (
            _order(
                client_order_id="open",
                order_state=OrderState.ACKNOWLEDGED,
                reconciliation_status=ReconciliationStatus.NOT_CHECKED,
            ),
        )
        result = derive_portfolio_state(_input(orders=orders))
        assert result.state == PortfolioState.PARTIAL
        assert result.confidence == ExposureConfidence.MEDIUM
        assert result.reconciling_orders == ("open",)
        assert result.worst_case_net_exposure == pytest.approx(1000.0)
        assert result.worst_case_net_pct == pytest.approx(0.10)
        assert result.within_net_limit is True

    def test_unknown_when_reconciling_pushes_worst_case_beyond_limit(self) -> None:
        # equity = 10_000; max_net = 30% = 3000. Pending sell 50 @ 100 = -5000
        # => |worst| = 5000 = 50% > 30%.
        orders = (
            _order(
                client_order_id="big",
                side="sell",
                remaining_qty=50.0,
                order_state=OrderState.ACKNOWLEDGED,
                reconciliation_status=ReconciliationStatus.NOT_CHECKED,
            ),
        )
        result = derive_portfolio_state(_input(orders=orders))
        assert result.state == PortfolioState.UNKNOWN
        assert "unbounded future exposure" in result.reason
        assert result.reconciling_orders == ("big",)

    def test_partial_when_offsetting_orders_keep_worst_case_within_limit(self) -> None:
        # current_net = 0; pending buy 5 @ 100 = +500 and sell 4 @ 100 = -400.
        # Worst-case net = +100 = 1%, well under limit.
        orders = (
            _order(
                client_order_id="buy",
                side="buy",
                remaining_qty=5.0,
                order_state=OrderState.ACKNOWLEDGED,
                reconciliation_status=ReconciliationStatus.NOT_CHECKED,
            ),
            _order(
                client_order_id="sell",
                side="sell",
                remaining_qty=4.0,
                order_state=OrderState.ACKNOWLEDGED,
                reconciliation_status=ReconciliationStatus.NOT_CHECKED,
            ),
        )
        result = derive_portfolio_state(_input(orders=orders))
        assert result.state == PortfolioState.PARTIAL
        assert result.worst_case_net_exposure == pytest.approx(100.0)

    def test_known_when_reconciling_order_has_repaired_reconciliation(self) -> None:
        # A repaired reconciliation is treated as resolved — not reconciling.
        orders = (
            _order(
                client_order_id="fixed",
                order_state=OrderState.PARTIALLY_FILLED,
                reconciliation_status=ReconciliationStatus.REPAIRED,
            ),
        )
        result = derive_portfolio_state(_input(orders=orders))
        assert result.state == PortfolioState.KNOWN

    def test_exposure_confidence_mapping(self) -> None:
        assert exposure_confidence_from_state(PortfolioState.KNOWN) == ExposureConfidence.HIGH
        assert exposure_confidence_from_state(PortfolioState.PARTIAL) == ExposureConfidence.MEDIUM
        assert exposure_confidence_from_state(PortfolioState.UNKNOWN) == ExposureConfidence.LOW

    def test_result_serializes(self) -> None:
        orders = (
            _order(
                client_order_id="o",
                order_state=OrderState.ACKNOWLEDGED,
                reconciliation_status=ReconciliationStatus.NOT_CHECKED,
            ),
        )
        result = derive_portfolio_state(_input(orders=orders))
        payload = result.to_dict()
        assert payload["state"] == "PARTIAL"
        assert payload["confidence"] == "MEDIUM"
        assert payload["reconciling_orders"] == ["o"]
        assert payload["within_net_limit"] is True

    def test_invalid_inputs_raise(self) -> None:
        with pytest.raises(ValueError, match="equity"):
            PortfolioStateInput(
                broker_positions_available=True,
                current_net_exposure=0.0,
                max_net_exposure_pct=0.3,
                equity=0.0,
            )
        with pytest.raises(ValueError, match="max_net_exposure_pct"):
            PortfolioStateInput(
                broker_positions_available=True,
                current_net_exposure=0.0,
                max_net_exposure_pct=0.0,
                equity=10_000.0,
            )
