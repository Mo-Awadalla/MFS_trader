"""Portfolio construction — convert strategy exposures to target positions.

Strategy-agnostic. Input: desired exposure (e.g. +1.0 long, -1.0 short, 0.0 flat).
Output: target positions in units (shares/contracts), accounting for capital,
per-position risk limits, and current prices.

Dependency flow:
    strategy produces desired exposure
    portfolio converts exposure → target positions
    risk accepts/rejects/modifies targets
    execution converts approved target delta → orders
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from config.schema import PortfolioConfig


class SizingMethod(StrEnum):
    FIXED_FRACTION = "fixed_fraction"
    VOL_TARGET = "vol_target"
    KELLY = "kelly"  # reserved for future — not implemented yet


class ExecutionMode(StrEnum):
    SIGNAL_TRANSITION = "signal_transition"
    CONTINUOUS_REBALANCE = "continuous_rebalance"


@dataclass
class TargetPosition:
    """A target position for one symbol."""

    symbol: str
    asset_class: str
    side: str  # "long" | "short" | "flat"
    target_qty: float
    target_notional: float
    current_price: float
    stop_price: float | None = None
    risk_per_unit: float | None = None
    sizing_method: str = "fixed_fraction"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_flat(self) -> bool:
        return abs(self.target_qty) < 1e-9


@dataclass
class PortfolioState:
    """Current portfolio state — capital, equity, open positions."""

    cash: float
    equity: float
    high_water_mark: float
    positions: dict[str, dict[str, Any]] = field(default_factory=dict)
    # positions[symbol] = {"qty": float, "avg_price": float, "side": str}

    @property
    def gross_exposure(self) -> float:
        return sum(abs(p["qty"] * p.get("avg_price", 0)) for p in self.positions.values())

    @property
    def net_exposure(self) -> float:
        return sum(p["qty"] * p.get("avg_price", 0) for p in self.positions.values())


def compute_target_positions(
    exposures: dict[str, float],
    prices: dict[str, float],
    state: PortfolioState,
    config: PortfolioConfig,
    *,
    asset_classes: dict[str, str] | None = None,
    stop_prices: dict[str, float] | None = None,
    volatilities: dict[str, float] | None = None,
) -> list[TargetPosition]:
    """Convert strategy exposures into target positions.

    Args:
        exposures: {symbol: exposure} where exposure is +1 (long), -1 (short), 0 (flat).
                   Can be fractional (e.g. 0.5 = half-size long).
        prices: {symbol: current_price}
        state: Current portfolio state (capital, equity, positions).
        config: Portfolio configuration (sizing method, risk pct, etc.).
        asset_classes: {symbol: "equity"|"crypto"} for cost model dispatch.
        stop_prices: {symbol: stop_price} for risk-based sizing.
        volatilities: {symbol: annualized_vol} for vol-target sizing.

    Returns:
        List of TargetPosition objects, one per symbol in exposures.
    """
    asset_classes = asset_classes or {}
    stop_prices = stop_prices or {}
    volatilities = volatilities or {}
    targets: list[TargetPosition] = []

    for symbol, exposure in exposures.items():
        price = prices.get(symbol, 0.0)
        if price <= 0:
            targets.append(
                TargetPosition(
                    symbol=symbol,
                    asset_class=asset_classes.get(symbol, "equity"),
                    side="flat",
                    target_qty=0.0,
                    target_notional=0.0,
                    current_price=price,
                    sizing_method=config.sizing_method,
                )
            )
            continue

        if abs(exposure) < 1e-9:
            targets.append(
                TargetPosition(
                    symbol=symbol,
                    asset_class=asset_classes.get(symbol, "equity"),
                    side="flat",
                    target_qty=0.0,
                    target_notional=0.0,
                    current_price=price,
                    sizing_method=config.sizing_method,
                )
            )
            continue

        # Determine side
        side = "long" if exposure > 0 else "short"

        # Compute position size based on sizing method
        if config.sizing_method == SizingMethod.FIXED_FRACTION.value:
            qty = _size_fixed_fraction(
                exposure=exposure,
                price=price,
                equity=state.equity,
                risk_pct=config.per_position_risk_pct,
                stop_price=stop_prices.get(symbol),
            )
        elif config.sizing_method == SizingMethod.VOL_TARGET.value:
            qty = _size_vol_target(
                exposure=exposure,
                price=price,
                equity=state.equity,
                risk_pct=config.per_position_risk_pct,
                volatility=volatilities.get(symbol, 0.20),
            )
        else:
            qty = _size_fixed_fraction(
                exposure=exposure,
                price=price,
                equity=state.equity,
                risk_pct=config.per_position_risk_pct,
                stop_price=stop_prices.get(symbol),
            )

        notional = abs(qty) * price
        targets.append(
            TargetPosition(
                symbol=symbol,
                asset_class=asset_classes.get(symbol, "equity"),
                side=side,
                target_qty=qty,
                target_notional=notional,
                current_price=price,
                stop_price=stop_prices.get(symbol),
                risk_per_unit=abs(price - stop_prices[symbol]) if symbol in stop_prices else None,
                sizing_method=config.sizing_method,
            )
        )

    # Apply dollar-neutral constraint if enabled
    if config.dollar_neutral:
        targets = _apply_dollar_neutral(targets, config)

    return targets


def _size_fixed_fraction(
    exposure: float,
    price: float,
    equity: float,
    risk_pct: float,
    stop_price: float | None,
) -> float:
    """Size position so that max loss = risk_pct * equity.

    If stop_price is provided: qty = (risk_pct * equity) / |price - stop|
    If no stop: qty = (risk_pct * equity) / price (treat full price as risk)
    """
    max_risk = risk_pct * equity
    if stop_price is not None and abs(price - stop_price) > 1e-9:
        risk_per_unit = abs(price - stop_price)
        qty = max_risk / risk_per_unit
    else:
        # No stop — use a default 5% stop assumption
        risk_per_unit = price * 0.05
        qty = max_risk / risk_per_unit

    # Apply exposure fraction
    qty = qty * abs(exposure)

    # Sign for direction
    return qty if exposure > 0 else -qty


def _size_vol_target(
    exposure: float,
    price: float,
    equity: float,
    risk_pct: float,
    volatility: float,
) -> float:
    """Size position targeting a constant volatility contribution.

    qty = (risk_pct * equity) / (price * volatility * sqrt(252/252))
    Simplified: target vol contribution = risk_pct per position.
    """
    if volatility <= 0:
        return 0.0
    daily_vol = volatility / (252**0.5)
    target_dollar_vol = risk_pct * equity
    qty = target_dollar_vol / (price * daily_vol)
    return qty * abs(exposure) if exposure > 0 else -qty * abs(exposure)


def _apply_dollar_neutral(targets: list[TargetPosition], config: PortfolioConfig) -> list[TargetPosition]:
    """Adjust positions so gross long = gross short (dollar-neutral)."""
    long_notional = sum(t.target_notional for t in targets if t.side == "long")
    short_notional = sum(t.target_notional for t in targets if t.side == "short")

    if long_notional <= 0 or short_notional <= 0:
        return targets  # can't neutralize without both sides

    # Scale the larger side down to match the smaller
    if long_notional > short_notional:
        scale = short_notional / long_notional
        for t in targets:
            if t.side == "long":
                t.target_qty *= scale
                t.target_notional *= scale
    elif short_notional > long_notional:
        scale = long_notional / short_notional
        for t in targets:
            if t.side == "short":
                t.target_qty *= scale
                t.target_notional *= scale

    return targets


def compute_position_delta(
    target: TargetPosition,
    current_qty: float,
    *,
    execution_mode: str = ExecutionMode.SIGNAL_TRANSITION.value,
    min_notional_delta: float = 0.0,
    min_qty_delta: float = 1e-9,
    min_pct_position_delta: float = 0.0,
) -> dict[str, float]:
    """Compute the delta between target and current position.

    Returns:
        {"action": "buy"|"sell"|"hold", "delta_qty": float, "delta_notional": float}
    """
    if execution_mode == ExecutionMode.SIGNAL_TRANSITION.value:
        current_side = _position_side(current_qty)
        target_side = _position_side(target.target_qty)
        if current_side == target_side:
            return {"action": "hold", "delta_qty": 0.0, "delta_notional": 0.0}

    delta_qty = target.target_qty - current_qty

    if abs(delta_qty) < min_qty_delta:
        return {"action": "hold", "delta_qty": 0.0, "delta_notional": 0.0}

    action = "buy" if delta_qty > 0 else "sell"
    delta_notional = abs(delta_qty) * target.current_price

    if delta_notional < min_notional_delta:
        return {"action": "hold", "delta_qty": 0.0, "delta_notional": 0.0}

    if abs(current_qty) > 1e-9:
        pct_delta = abs(delta_qty) / abs(current_qty)
        if pct_delta < min_pct_position_delta:
            return {"action": "hold", "delta_qty": 0.0, "delta_notional": 0.0}

    return {
        "action": action,
        "delta_qty": delta_qty,
        "delta_notional": delta_notional,
    }


def _position_side(qty: float) -> str:
    if qty > 1e-9:
        return "long"
    if qty < -1e-9:
        return "short"
    return "flat"
