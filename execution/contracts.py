"""Explicit local execution contracts used before OMS submission."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal


@dataclass(frozen=True)
class ExecutionContract:
    name: str
    quantity_step: Decimal
    minimum_quantity: Decimal
    minimum_notional: Decimal
    currency: str
    fractional_orders_require_day: bool

    def constrain_quantity(
        self,
        quantity: float,
        price: float,
        *,
        available_cash: float | None = None,
    ) -> float:
        """Round toward zero and apply quantity, notional, and cash bounds."""
        requested = Decimal(str(abs(quantity)))
        unit_price = Decimal(str(price))
        if not requested.is_finite() or not unit_price.is_finite() or unit_price <= 0:
            raise ValueError("order quantity and price must be finite, with positive price")
        steps = (requested / self.quantity_step).to_integral_value(rounding=ROUND_DOWN)
        constrained = steps * self.quantity_step
        if available_cash is not None:
            cash = Decimal(str(available_cash))
            if not cash.is_finite() or cash < 0:
                raise ValueError("available cash must be finite and nonnegative")
            cash_steps = (cash / unit_price / self.quantity_step).to_integral_value(rounding=ROUND_DOWN)
            constrained = min(constrained, cash_steps * self.quantity_step)
        if constrained < self.minimum_quantity or constrained * unit_price < self.minimum_notional:
            return 0.0
        return float(constrained)


# Selected runtime profile: Alpaca US equities, USD, DAY orders. Fractional
# orders are restricted to DAY by Alpaca's published order matrix. Six decimal
# quantity steps and a $1 minimum notional are intentionally conservative local
# guards; quantities are always truncated, never rounded up.
ALPACA_EQUITY_DAY = ExecutionContract(
    name="alpaca_equity_day_fractional_6dp",
    quantity_step=Decimal("0.000001"),
    minimum_quantity=Decimal("0.000001"),
    minimum_notional=Decimal("1.00"),
    currency="USD",
    fractional_orders_require_day=True,
)


def execution_contract_for(broker_name: str, asset_class: str) -> ExecutionContract:
    if broker_name in {"alpaca", "sim_broker"} and asset_class == "equity":
        return ALPACA_EQUITY_DAY
    raise ValueError(f"no explicit execution contract for broker={broker_name!r}, asset_class={asset_class!r}")
