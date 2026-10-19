"""Validated broker snapshots and durable account-level risk baselines."""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from execution.base import BrokerAccount, BrokerPosition
from risk.engine import DrawdownState


@dataclass(frozen=True)
class PortfolioSnapshot:
    """One coherent account observation consumed by sizing and risk.

    ``observed_at`` is the local completion time of adapter reads. It records
    when the application observed the values; it is not represented as a
    provider-side update timestamp.
    """

    broker: str
    account_id: str
    observed_at: datetime
    cash: float
    equity: float
    currency: str
    positions: tuple[BrokerPosition, ...]
    pending_orders: tuple[dict[str, Any], ...]
    pending_orders_complete: bool = False
    pending_orders_observed_at: datetime | None = None
    pending_orders_source: str | None = None
    external_cash_flow: float | None = None
    allow_new_baseline: bool = False

    def validate(self, *, now: datetime | None = None, max_age: timedelta = timedelta(seconds=60)) -> None:
        now = now or datetime.now(UTC)
        observed = self.observed_at
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError("snapshot observation time must be timezone-aware")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("snapshot validation time must be timezone-aware")
        age = now.astimezone(UTC) - observed.astimezone(UTC)
        if age < timedelta(0) or age > max_age:
            raise ValueError(f"account snapshot is stale or future-dated ({age.total_seconds():.3f}s)")
        if not self.pending_orders_complete:
            raise ValueError("account snapshot has no complete broker open-order evidence")
        if self.pending_orders_observed_at is None or not self.pending_orders_source:
            raise ValueError("account snapshot is missing open-order observation metadata")
        if self.pending_orders_observed_at.tzinfo is None or self.pending_orders_observed_at.utcoffset() is None:
            raise ValueError("open-order observation timestamp must be timezone-aware")
        pending_age = now.astimezone(UTC) - self.pending_orders_observed_at.astimezone(UTC)
        if pending_age < timedelta(0) or pending_age > timedelta(seconds=5):
            raise ValueError("broker open-order evidence is stale or future-dated")
        if not self.account_id.strip() or self.account_id == "unknown":
            raise ValueError("account snapshot has no verified account identity")
        if not self.currency.strip():
            raise ValueError("account snapshot has no currency")
        if not _finite_positive(self.equity) or not _finite(self.cash):
            raise ValueError("account snapshot cash/equity is missing, nonfinite, or nonpositive")
        if self.external_cash_flow is not None and not _finite(self.external_cash_flow):
            raise ValueError("external cash flow must be finite")
        symbols: set[str] = set()
        for position in self.positions:
            if position.symbol in symbols:
                raise ValueError(f"duplicate broker position for {position.symbol}")
            symbols.add(position.symbol)
            if not _finite(position.quantity) or not _finite(position.avg_entry_price):
                raise ValueError(f"position {position.symbol} contains nonfinite quantity or entry price")
            if position.quantity and (position.market_value is None or not _finite(position.market_value)):
                raise ValueError(f"position {position.symbol} is missing finite marked value")
            if position.unrealized_pnl is not None and not _finite(position.unrealized_pnl):
                raise ValueError(f"position {position.symbol} has nonfinite unrealized P&L")
        for order in self.pending_orders:
            if (
                not str(order.get("client_order_id") or "")
                or not str(order.get("symbol") or "")
                or str(order.get("side", "")).lower() not in {"buy", "sell"}
            ):
                raise ValueError("pending order is missing a valid id, symbol, or side")
            quantity = float(order.get("remaining_qty", 0.0) or 0.0)
            price = float(order.get("last_price", order.get("limit_price", order.get("avg_fill_price", 0.0))) or 0.0)
            if not _finite(quantity) or not _finite(price) or (quantity and price <= 0):
                raise ValueError(f"pending order {order.get('client_order_id', '<unknown>')} has incomplete exposure")

        position_value = sum(float(position.market_value or 0.0) for position in self.positions)
        reconstructed_equity = self.cash + position_value
        tolerance = max(1.0, abs(self.equity) * 0.02)
        if abs(reconstructed_equity - self.equity) > tolerance:
            raise ValueError(
                f"cash plus marked positions ({reconstructed_equity:.2f}) is inconsistent with equity ({self.equity:.2f})"
            )

    @classmethod
    def from_broker(
        cls,
        broker: str,
        account: BrokerAccount,
        positions: list[BrokerPosition],
        pending_orders: list[dict[str, Any]],
        *,
        pending_orders_complete: bool = False,
        pending_orders_observed_at: datetime | None = None,
        pending_orders_source: str | None = None,
        observed_at: datetime | None = None,
        external_cash_flow: float | None = None,
        allow_new_baseline: bool = False,
    ) -> PortfolioSnapshot:
        return cls(
            broker=broker,
            account_id=account.account_id,
            observed_at=observed_at or datetime.now(UTC),
            cash=account.cash,
            equity=account.equity,
            currency=account.currency,
            positions=tuple(positions),
            pending_orders=tuple(pending_orders),
            pending_orders_complete=pending_orders_complete,
            pending_orders_observed_at=pending_orders_observed_at,
            pending_orders_source=pending_orders_source,
            external_cash_flow=external_cash_flow,
            allow_new_baseline=allow_new_baseline,
        )


@dataclass(frozen=True)
class AccountRiskState:
    daily_pnl: float
    weekly_pnl: float
    monthly_pnl: float
    daily_baseline: float
    weekly_baseline: float
    monthly_baseline: float
    daily_external_cash_flow: float
    weekly_external_cash_flow: float
    monthly_external_cash_flow: float
    high_water_mark: float
    realized_pnl: float
    unrealized_pnl: float

    def drawdown(self, equity: float) -> DrawdownState:
        return DrawdownState(
            daily_pnl=self.daily_pnl,
            weekly_pnl=self.weekly_pnl,
            monthly_pnl=self.monthly_pnl,
            high_water_mark=self.high_water_mark,
            current_equity=equity,
            daily_baseline=self.daily_baseline,
            weekly_baseline=self.weekly_baseline,
            monthly_baseline=self.monthly_baseline,
        )


class AccountRiskRepository:
    """Persist validated snapshots and cash-flow-adjusted UTC period anchors."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS account_risk_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                broker TEXT NOT NULL,
                account_id TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                cash REAL NOT NULL,
                equity REAL NOT NULL,
                currency TEXT NOT NULL,
                external_cash_flow REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                unrealized_pnl REAL NOT NULL,
                positions_json TEXT NOT NULL,
                pending_orders_json TEXT NOT NULL
            )"""
        )
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS account_risk_periods (
                broker TEXT NOT NULL,
                account_id TEXT NOT NULL,
                period_kind TEXT NOT NULL,
                period_key TEXT NOT NULL,
                baseline_equity REAL NOT NULL,
                external_cash_flow REAL NOT NULL,
                high_water_mark REAL NOT NULL,
                PRIMARY KEY(broker, account_id, period_kind, period_key)
            )"""
        )
        self._conn.commit()

    def record(self, snapshot: PortfolioSnapshot) -> AccountRiskState:
        snapshot.validate()
        observed = snapshot.observed_at.astimezone(UTC)
        stamp = observed.isoformat()
        latest_snapshot = self._conn.execute(
            "SELECT observed_at FROM account_risk_snapshots WHERE broker=? AND account_id=? "
            "ORDER BY id DESC LIMIT 1",
            (snapshot.broker, snapshot.account_id),
        ).fetchone()
        has_period_history = self._conn.execute(
            "SELECT 1 FROM account_risk_periods WHERE broker=? AND account_id=? LIMIT 1",
            (snapshot.broker, snapshot.account_id),
        ).fetchone() is not None
        if latest_snapshot is None and not snapshot.allow_new_baseline:
            raise ValueError(
                "period risk history is unavailable for this existing account; "
                "baseline initialization is permitted only for an explicitly new isolated simulation"
            )
        if latest_snapshot is not None and not has_period_history:
            raise ValueError("period risk baseline history is missing for an account with prior snapshots")
        if latest_snapshot is not None and snapshot.external_cash_flow is None:
            raise ValueError("external cash-flow evidence is required after the first account snapshot")
        cash_flow = float(snapshot.external_cash_flow or 0.0)
        unrealized = sum(float(position.unrealized_pnl or 0.0) for position in snapshot.positions)
        serialized_positions = [
            {
                "symbol": position.symbol,
                "quantity": position.quantity,
                "avg_entry_price": position.avg_entry_price,
                "side": position.side,
                "unrealized_pnl": position.unrealized_pnl,
                "market_value": position.market_value,
            }
            for position in snapshot.positions
        ]
        realized = 0.0
        periods = {
            "daily": observed.strftime("%Y-%m-%d"),
            "weekly": f"{observed.isocalendar().year}-W{observed.isocalendar().week:02d}",
            "monthly": observed.strftime("%Y-%m"),
        }
        keys = {"daily": "D", "weekly": "W", "monthly": "M"}

        with self._conn:
            self._conn.execute(
                "INSERT INTO account_risk_snapshots "
                "(broker,account_id,observed_at,cash,equity,currency,external_cash_flow,realized_pnl,unrealized_pnl,positions_json,pending_orders_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    snapshot.broker, snapshot.account_id, stamp, snapshot.cash, snapshot.equity,
                    snapshot.currency, cash_flow, realized, unrealized,
                    json.dumps(serialized_positions, sort_keys=True),
                    json.dumps(snapshot.pending_orders, sort_keys=True),
                ),
            )
            values: dict[str, tuple[float, float, float]] = {}
            high_water_mark = snapshot.equity
            for name, period_key in periods.items():
                row = self._conn.execute(
                    "SELECT baseline_equity,external_cash_flow,high_water_mark FROM account_risk_periods "
                    "WHERE broker=? AND account_id=? AND period_kind=? AND period_key=?",
                    (snapshot.broker, snapshot.account_id, keys[name], period_key),
                ).fetchone()
                if row is None:
                    if latest_snapshot is not None and not snapshot.allow_new_baseline:
                        raise ValueError(
                            f"{name} risk baseline history is missing or unavailable for this account period"
                        )
                    baseline = snapshot.equity - cash_flow
                    flow_total = cash_flow
                    high = snapshot.equity
                    if latest_snapshot is not None:
                        latest_at = datetime.fromisoformat(str(latest_snapshot[0])).astimezone(UTC)
                        latest_key = {
                            "daily": latest_at.strftime("%Y-%m-%d"),
                            "weekly": f"{latest_at.isocalendar().year}-W{latest_at.isocalendar().week:02d}",
                            "monthly": latest_at.strftime("%Y-%m"),
                        }[name]
                        if latest_key == period_key:
                            raise ValueError(f"{name} risk baseline history is missing for the current period")
                    self._conn.execute(
                        "INSERT INTO account_risk_periods VALUES (?,?,?,?,?,?,?)",
                        (snapshot.broker, snapshot.account_id, keys[name], period_key, baseline, flow_total, high),
                    )
                else:
                    baseline = float(row[0])
                    flow_total = float(row[1]) + cash_flow
                    high = max(float(row[2]), snapshot.equity - cash_flow)
                    self._conn.execute(
                        "UPDATE account_risk_periods SET external_cash_flow=?,high_water_mark=? "
                        "WHERE broker=? AND account_id=? AND period_kind=? AND period_key=?",
                        (flow_total, high, snapshot.broker, snapshot.account_id, keys[name], period_key),
                    )
                values[name] = (snapshot.equity - baseline - flow_total, baseline, flow_total)
                high_water_mark = max(high_water_mark, high)

        total_period_pnl = values["monthly"][0]
        realized = total_period_pnl - unrealized
        with self._conn:
            self._conn.execute(
                "UPDATE account_risk_snapshots SET realized_pnl=? WHERE id=last_insert_rowid()",
                (realized,),
            )
        return AccountRiskState(
            daily_pnl=values["daily"][0],
            weekly_pnl=values["weekly"][0],
            monthly_pnl=values["monthly"][0],
            daily_baseline=values["daily"][1],
            weekly_baseline=values["weekly"][1],
            monthly_baseline=values["monthly"][1],
            daily_external_cash_flow=values["daily"][2],
            weekly_external_cash_flow=values["weekly"][2],
            monthly_external_cash_flow=values["monthly"][2],
            high_water_mark=high_water_mark,
            realized_pnl=realized,
            unrealized_pnl=unrealized,
        )


def _finite(value: float) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _finite_positive(value: float) -> bool:
    return _finite(value) and float(value) > 0.0


def broker_external_cash_flow(broker: Any) -> float | None:
    """Return cash-flow evidence only when the adapter explicitly provides it."""
    reader = getattr(broker, "get_external_cash_flow", None)
    if not callable(reader):
        return None
    value = reader()
    if value is None or not _finite(value):
        raise ValueError("broker returned missing or invalid external cash-flow evidence")
    return float(value)


def broker_allows_new_risk_baseline(broker: Any) -> bool:
    """Only adapters that explicitly identify an isolated new simulation may seed history."""
    marker = getattr(broker, "is_new_isolated_simulation", False)
    return marker is True
