"""Conversions that preserve broker and local pending-order evidence."""

from __future__ import annotations

from typing import Any

from execution.base import BrokerOpenOrdersSnapshot


def merge_pending_orders(
    broker_snapshot: BrokerOpenOrdersSnapshot,
    local_orders: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Union broker open orders with local uncertain intents, preferring broker quantities."""
    broker_snapshot.validate()
    merged: dict[str, dict[str, Any]] = {}
    for order in broker_snapshot.orders:
        merged[order.client_order_id] = {
            "client_order_id": order.client_order_id,
            "symbol": order.symbol,
            "side": order.side,
            "remaining_qty": order.remaining_qty,
            "limit_price": order.limit_price,
            "avg_fill_price": order.avg_fill_price,
            "last_price": order.limit_price or order.avg_fill_price or 0.0,
            "order_state": order.status,
            "source": broker_snapshot.source,
        }
    for order in local_orders:
        client_id = str(order.get("client_order_id") or "")
        if not client_id or client_id in merged:
            continue
        quantity = float(order.get("remaining_qty") or 0.0)
        if quantity <= 0:
            continue
        if not str(order.get("symbol") or "") or str(order.get("side", "")).lower() not in {"buy", "sell"}:
            raise ValueError(f"local pending order {client_id} is missing a valid symbol or side")
        merged[client_id] = {
            **order,
            "client_order_id": client_id,
            "remaining_qty": quantity,
            "source": "local_uncertain_order_state",
        }
    return list(merged.values())
