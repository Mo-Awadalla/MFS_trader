"""Local paper-run ownership and durable, pre-OMS tiny-cap admission."""
from __future__ import annotations

import os
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from engine.paper_evidence import digest, finite
from engine.paper_session import PaperCaps, validate_tiny_paper_caps
from execution.oms import OrderIntent


class PaperRunnerOwnership:
    """Nonblocking process ownership; the OS releases locks on process death.

    Never unlink a lock file: replacing its inode would permit two owners.
    The database lock also serializes different sessions sharing engine state.
    The optional artifact lock serializes one session across database paths.
    """

    def __init__(self, db_path: str | Path, session_path: Path | None = None):
        self.db_path = Path(db_path).resolve()
        self._paths = [self.db_path.with_suffix(self.db_path.suffix + ".paper.lock")]
        if session_path is not None:
            self._paths.append(session_path.resolve().with_suffix(".runner.lock"))
        self._handles: list[Any] = []
        self._pid: int | None = None
        self.token: str | None = None
        self._attempt_claimed = False

    def acquire(self) -> None:
        if os.name != "posix":
            raise ValueError("paper runner ownership requires POSIX local file locks")
        import fcntl

        if self._handles:
            raise ValueError("paper runner ownership already acquired")
        try:
            for path in sorted(self._paths):
                path.parent.mkdir(parents=True, exist_ok=True)
                handle = path.open("a+b")
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BaseException:
                    handle.close()
                    raise
                self._handles.append(handle)
            self._pid = os.getpid()
            self.token = uuid.uuid4().hex
            self._attempt_claimed = False
        except BlockingIOError as exc:
            self.release()
            raise ValueError("paper runner already owns this database or session") from exc
        except BaseException:
            self.release()
            raise

    def assert_owned(self) -> None:
        if self._pid != os.getpid() or len(self._handles) != len(self._paths):
            raise ValueError("paper runner ownership is not held")

    def claim_attempt(self) -> str:
        self.assert_owned()
        if self._attempt_claimed:
            raise ValueError("paper runner ownership already has an attempt")
        self._attempt_claimed = True
        return self.token

    def release(self) -> None:
        for handle in reversed(self._handles):
            handle.close()
        self._handles.clear()
        self._pid = None
        self.token = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()


class PaperSubmissionGuard:
    """Reserve actual order notional durably before OMS can cause effects.

    Reservations are never refunded on cancellation/rejection. Uncertain or
    missing outcomes block further submission, including after restart.
    Research/replay engines do not install this paper-only guard.
    """

    def __init__(self, ledger: Any, broker: Any, caps: PaperCaps, clock: Any):
        validate_tiny_paper_caps(caps)
        for value in caps.to_dict().values():
            if finite(value) <= 0:
                raise ValueError("paper caps must be finite and positive")
        self.ledger = ledger
        self.broker = broker
        self.caps = caps
        self.clock = clock

    def _check_observed_orders(self) -> float:
        total = 0.0
        for reservation in self.ledger.rows("paper_order_reservations"):
            oid = reservation["client_order_id"]
            if not oid:
                raise ValueError("unclosed paper order reservation requires reconciliation")
            order = self.ledger.conn.execute(
                "SELECT * FROM orders_live WHERE client_order_id=?", (oid,),
            ).fetchone()
            if order is None or order["order_state"] not in {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}:
                raise ValueError("unresolved paper order reservation requires reconciliation")
            if (
                order["symbol"] != reservation["symbol"] or order["side"] != reservation["side"]
                or finite(order["requested_qty"]) != finite(reservation["quantity"])
                or order["environment"] != "paper"
                or order["reconciliation_status"] in {"MISMATCHED", "UNRESOLVED"}
            ):
                raise ValueError("paper reservation order identity or reconciliation mismatch")
            filled = finite(order["filled_qty"])
            if filled < 0 or filled > finite(reservation["quantity"]):
                raise ValueError("inconsistent paper reservation fill quantity")
            actual = 0.0
            if filled:
                price = finite(order["avg_fill_price"])
                if price <= 0:
                    raise ValueError("paper fill price unavailable")
                actual = finite(filled * price)
            previous = reservation["observed_notional"]
            if previous is not None and actual < finite(previous):
                raise ValueError("paper observed order notional decreased")
            charged = max(finite(reservation["reserved_notional"]), actual)
            with self.ledger.conn:
                self.ledger.conn.execute(
                    "UPDATE paper_order_reservations SET observed_notional=?,observed_at=? WHERE reservation_id=?",
                    (actual, self.clock().isoformat(), reservation["reservation_id"]),
                )
            if charged > self.caps.max_notional_per_order:
                raise ValueError("paper max_notional_per_order exceeded by observed fill")
            total = finite(total + charged)
        if total > self.caps.max_paper_session_notional:
            raise ValueError("paper max_paper_session_notional exceeded by observed fills")
        return total

    def _open_exposure(self, intent: OrderIntent | None = None, reference_price: float | None = None) -> float:
        # No new authority while open orders make eventual exposure uncertain.
        getter = getattr(self.broker, "get_open_orders", None)
        if getter is None:
            if self.broker.name != "sim_broker":
                raise ValueError("paper open orders unavailable")
            open_orders = self.ledger.conn.execute(
                "SELECT 1 FROM orders_live WHERE order_state NOT IN "
                "('FILLED','CANCELLED','REJECTED','EXPIRED','BLOCKED_BY_RISK') LIMIT 1",
            ).fetchall()
        else:
            open_orders = getter()
        if open_orders is None or open_orders:
            raise ValueError("paper open orders unavailable or unresolved")
        positions = self.broker.get_positions()
        if positions is None:
            raise ValueError("paper positions unavailable")
        exposure = 0.0
        seen = set()
        for position in positions:
            if not position.symbol or position.symbol in seen:
                raise ValueError("ambiguous paper position observation")
            seen.add(position.symbol)
            quantity = finite(position.quantity)
            if position.side not in {"long", "short", "flat"}:
                raise ValueError("paper position side unavailable")
            if position.side == "short":
                quantity = -abs(quantity)
            if intent is not None and position.symbol == intent.symbol:
                price = reference_price
                quantity += intent.quantity if intent.side.value == "buy" else -intent.quantity
            else:
                price = finite(self.broker.get_price(position.symbol))
            if price is None or price <= 0:
                raise ValueError("paper position price unavailable")
            exposure = finite(exposure + abs(quantity) * price)
        if intent is not None and intent.symbol not in seen:
            exposure = finite(exposure + intent.quantity * reference_price)
        return exposure

    def reserve(self, intent: OrderIntent) -> str:
        self.ledger.assert_active_attempt()
        quantity = finite(intent.quantity)
        price = finite(self.broker.get_price(intent.symbol))
        if quantity <= 0 or price <= 0:
            raise ValueError("paper order quantity/price must be positive")
        notional = finite(quantity * price)
        if notional > self.caps.max_notional_per_order:
            raise ValueError("paper max_notional_per_order exceeded before submission")
        used = self._check_observed_orders()
        if used + notional > self.caps.max_paper_session_notional:
            raise ValueError("paper max_paper_session_notional exceeded before submission")
        exposure = self._open_exposure(intent, price)
        if exposure > self.caps.max_open_paper_exposure:
            raise ValueError("paper max_open_paper_exposure exceeded before submission")
        reservation_id = digest([self.ledger.session_id, asdict(intent)])
        with self.ledger.conn:
            self.ledger.conn.execute(
                "INSERT INTO paper_order_reservations "
                "(reservation_id,session_id,attempt_id,symbol,side,quantity,reference_price,reserved_notional,reserved_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (reservation_id, self.ledger.session_id, self.ledger.attempt_id, intent.symbol,
                 intent.side.value, quantity, price, notional, self.clock().isoformat()),
            )
        return reservation_id

    def observe(self, reservation_id: str, client_order_id: str | None) -> None:
        self.ledger.assert_active_attempt()
        with self.ledger.conn:
            self.ledger.conn.execute(
                "UPDATE paper_order_reservations SET client_order_id=? WHERE reservation_id=? AND attempt_id=?",
                (client_order_id, reservation_id, self.ledger.attempt_id),
            )
        self._check_observed_orders()
        if self._open_exposure() > self.caps.max_open_paper_exposure:
            raise ValueError("paper max_open_paper_exposure exceeded by observed positions")

    def verify_recovery(self) -> None:
        self.ledger.assert_active_attempt()
        self._check_observed_orders()
        if self._open_exposure() > self.caps.max_open_paper_exposure:
            raise ValueError("paper max_open_paper_exposure exceeded at recovery")
