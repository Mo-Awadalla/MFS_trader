"""Execution-assumption declarations and research-vs-runtime ledger parity.

A structural replay PASS (bars, cycles, orders, fills, operational report) is
not financial parity. This module makes the execution assumptions of the ETF
TSM research backtest and of the runtime replay explicit and machine-readable,
then compares the two paths' per-bar ledgers:

* ``ExecutionAssumptions`` is one versioned declaration per path.
* ``simulate_ledger`` is an independent share-level reference model driven only
  by a declaration. It must reproduce the actual research ledger under the
  research declaration and the actual runtime ledger under the runtime
  declaration; otherwise the declaration does not describe that path.
* ``evaluate_execution_parity`` checks both, compares research and runtime
  ledgers field by field, and attributes the final-equity gap to each declared
  difference by toggling one mechanism at a time in the reference model.

Only ``established`` means financial parity. ``attributed`` means every
difference is explained by a declared, deliberate mechanism; the paths still
produce different money.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config.schema import Config, CostModelConfig
from risk.engine import RiskDecision, RiskEvaluation

ASSUMPTIONS_VERSION = "etf_tsm_execution_assumptions.v1"
PARITY_REPORT_VERSION = "etf_tsm_execution_parity.v1"
STRUCTURAL_SCOPE = "structural_replay"

FINANCIAL_PARITY_NOT_ESTABLISHED = "not_established"
FINANCIAL_PARITY_ESTABLISHED = "established"
FINANCIAL_PARITY_ATTRIBUTED = "attributed"
FINANCIAL_PARITY_FAILED = "failed"

FILL_SIGNAL_BAR_CLOSE = "close_of_signal_bar"
FILL_NEXT_BAR_CLOSE = "close_of_bar_after_signal_bar"
SIZING_MARK_TO_MARKET = "mark_to_market_equity"
SIZING_FIXED_INITIAL_CAPITAL = "fixed_initial_capital"
REBALANCE_EVERY_BAR = "every_bar_to_target_weight"
REBALANCE_THRESHOLDED = "thresholded_position_delta"
COST_RESEARCH_WEIGHT_DELTA = "research_weight_delta"
COST_FILL_PRICE_SLIPPAGE = "fill_price_slippage"

# The runtime fixed-fraction sizer assumes a 5% stop when no stop is supplied
# (portfolio.sizing._size_fixed_fraction, risk.engine._check_per_position_risk).
_RUNTIME_DEFAULT_STOP_FRACTION = 0.05
# Runtime OMS/sizing treat |qty| < 1e-9 as flat.
_FLAT_QTY = 1e-9
# Research sell-side constant added by research.cross_sectional_pipeline.trade_costs.
_RESEARCH_SELL_EXTRA_PCT = 0.0001

# Per-field agreement tolerances (see docs/release/execution-parity-boundary.md).
WEIGHT_ATOL = 1e-12
QTY_ATOL = 1e-9
QTY_RTOL = 1e-9
MONEY_RTOL = 1e-9
MONEY_ATOL_PER_CAPITAL = 1e-8

LEDGER_FIELDS = ("target_weight", "order_qty", "position", "cash", "fees", "equity")
_SYMBOL_FIELDS = ("target_weight", "order_qty", "position")

# All other non-approved risk decisions make analytical attribution unavailable,
# even if today's risk implementation reports them without changing quantities.
MODELED_RISK_CHECKS = frozenset({"per_position_risk", "max_open_positions", "gross_exposure"})

# Declared mechanisms, in the order the attribution chain toggles them from the
# research declaration to the runtime declaration. Each lists the declaration
# fields it owns.
MECHANISMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("fill_timing", ("fill_timing", "fill_lag_bars")),
    ("sizing_basis", ("sizing_basis", "sizing_exposure_multiplier", "cash_handling")),
    ("rebalance_policy", ("rebalance_policy", "min_notional_delta", "min_pct_position_delta", "min_qty_delta")),
    ("costs", ("costs",)),
    ("risk_constraints", ("risk",)),
)
# Any other differing field (decision_timing, fill_price, quantity_rounding,
# corporate_actions) is "unmodeled": the reference model cannot vary it, so a
# difference there fails parity instead of being attributed.


class ParityDeclarationError(ValueError):
    """Fail-closed error: parity asserted without a matching assumptions declaration."""


@dataclass(frozen=True)
class CostAssumptions:
    model: str
    buy_cost_pct: float
    sell_cost_pct: float
    commission_pct_applied: float
    borrow_cost_annual_pct: float
    charged_on: str
    charge_timing: str


@dataclass(frozen=True)
class RiskConstraintAssumptions:
    applied: bool
    per_position_notional_cap: float | None
    max_gross_exposure: float | None
    max_open_positions: int | None
    evaluated_against: str
    loss_limits: str


@dataclass(frozen=True)
class ExecutionAssumptions:
    """Versioned execution assumptions for one path (research or runtime)."""

    version: str
    path: str
    decision_timing: str
    fill_timing: str
    fill_lag_bars: int
    fill_price: str
    sizing_basis: str
    sizing_exposure_multiplier: float
    cash_handling: str
    rebalance_policy: str
    min_notional_delta: float
    min_pct_position_delta: float
    min_qty_delta: float
    quantity_rounding: str
    corporate_actions: str
    costs: CostAssumptions
    risk: RiskConstraintAssumptions
    spread_model: str = "none; no separate bid-ask spread"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionAssumptions:
        values = dict(data)
        values["costs"] = CostAssumptions(**values["costs"])
        values["risk"] = RiskConstraintAssumptions(**values["risk"])
        return cls(**values)


@dataclass(frozen=True)
class ExecutionAssumptionsDeclaration:
    """Predeclared research + runtime assumptions pair for a parity assertion."""

    version: str
    research: ExecutionAssumptions
    runtime: ExecutionAssumptions

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "research": self.research.to_dict(),
            "runtime": self.runtime.to_dict(),
            "diff": diff_assumptions(self.research, self.runtime),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionAssumptionsDeclaration:
        try:
            return cls(
                version=str(data["version"]),
                research=ExecutionAssumptions.from_dict(data["research"]),
                runtime=ExecutionAssumptions.from_dict(data["runtime"]),
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ParityDeclarationError(f"malformed execution assumptions declaration: {exc}") from exc


def load_declaration(path: str | Path) -> ExecutionAssumptionsDeclaration:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ParityDeclarationError(f"cannot read execution assumptions declaration {path}: {exc}") from exc
    return ExecutionAssumptionsDeclaration.from_dict(data)


def write_declaration(declaration: ExecutionAssumptionsDeclaration, path: str | Path) -> None:
    atomic_write_text(
        path, json.dumps(declaration.to_dict(), indent=2, sort_keys=True) + "\n",
        create_only=True,
    )


def atomic_write_text(path: str | Path, content: str, *, create_only: bool = False) -> None:
    """Publish complete artifacts; immutable declarations are create-if-absent."""
    target = Path(path)
    fd, temporary = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if create_only:
            os.link(temporary, target)
        else:
            os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def research_cost_rates(cost: CostModelConfig) -> tuple[float, float]:
    """Buy/sell cost fractions exactly as research ``trade_costs`` charges them."""

    variable = cost.slippage_fixed_pct if cost.slippage_variable_coeff else 0.0
    buy = cost.slippage_fixed_pct + cost.commission_pct + variable
    sell = (
        cost.slippage_fixed_pct
        + cost.commission_pct
        + cost.sec_fee_per_dollar_sold
        + _RESEARCH_SELL_EXTRA_PCT
        + variable
    )
    return buy, sell


def research_assumptions(cost: CostModelConfig) -> ExecutionAssumptions:
    """Assumptions of ``research.cross_sectional_pipeline.backtest_cross_sectional``."""

    buy, sell = research_cost_rates(cost)
    return ExecutionAssumptions(
        version=ASSUMPTIONS_VERSION,
        path="research",
        decision_timing="monthly rebalance session; signal uses bars strictly before the session",
        fill_timing=FILL_SIGNAL_BAR_CLOSE,
        fill_lag_bars=0,
        fill_price="close",
        sizing_basis=SIZING_MARK_TO_MARKET,
        sizing_exposure_multiplier=1.0,
        cash_handling="implicit cash = equity * (1 - sum(weights)); no interest; no financing",
        rebalance_policy=REBALANCE_EVERY_BAR,
        min_notional_delta=0.0,
        min_pct_position_delta=0.0,
        min_qty_delta=0.0,
        quantity_rounding="fractional (continuous weights)",
        corporate_actions="input panel close used as given by both paths",
        costs=CostAssumptions(
            model=COST_RESEARCH_WEIGHT_DELTA,
            buy_cost_pct=buy,
            sell_cost_pct=sell,
            commission_pct_applied=cost.commission_pct,
            borrow_cost_annual_pct=cost.borrow_cost_annual_pct,
            charged_on="target-weight changes times sizing equity; drift rebalancing free",
            charge_timing="deducted in the next bar return",
        ),
        risk=RiskConstraintAssumptions(
            applied=False,
            per_position_notional_cap=None,
            max_gross_exposure=None,
            max_open_positions=None,
            evaluated_against="not_applicable",
            loss_limits="not_modeled",
        ),
    )


def runtime_assumptions(replay_config: Config, *, slippage_pct: float) -> ExecutionAssumptions:
    """Assumptions of ``engine.etf_tsm_replay`` for an already-overridden replay config.

    Raises ``ParityDeclarationError`` for runtime configurations the reference
    model does not describe, rather than declaring something untrue.
    """

    portfolio = replay_config.portfolio
    limits = replay_config.risk_limits
    if portfolio.sizing_method != "fixed_fraction":
        raise ParityDeclarationError(f"unsupported runtime sizing_method for parity: {portfolio.sizing_method}")
    if portfolio.execution_mode != "continuous_rebalance":
        raise ParityDeclarationError(f"unsupported runtime execution_mode for parity: {portfolio.execution_mode}")
    if portfolio.dollar_neutral:
        raise ParityDeclarationError("dollar_neutral runtime sizing is not described by the parity model")
    return ExecutionAssumptions(
        version=ASSUMPTIONS_VERSION,
        path="runtime",
        decision_timing="monthly rebalance session; signal uses bars strictly before the session",
        fill_timing=FILL_NEXT_BAR_CLOSE,
        fill_lag_bars=1,
        fill_price="close",
        sizing_basis=SIZING_FIXED_INITIAL_CAPITAL,
        sizing_exposure_multiplier=portfolio.per_position_risk_pct / _RUNTIME_DEFAULT_STOP_FRACTION,
        cash_handling=(
            "cash reconstructed as initial capital - signed fill notional; no interest; no financing; "
            "may go negative; SimBroker account cash/equity itself is not updated"
        ),
        rebalance_policy=REBALANCE_THRESHOLDED,
        min_notional_delta=float(portfolio.min_notional_delta),
        min_pct_position_delta=float(portfolio.min_pct_position_delta),
        min_qty_delta=float(portfolio.min_qty_delta),
        quantity_rounding="fractional (continuous weights)",
        corporate_actions="input panel close used as given by both paths",
        costs=CostAssumptions(
            model=COST_FILL_PRICE_SLIPPAGE,
            buy_cost_pct=float(slippage_pct),
            sell_cost_pct=float(slippage_pct),
            commission_pct_applied=0.0,
            borrow_cost_annual_pct=0.0,
            charged_on="every filled order's notional, including drift rebalances",
            charge_timing="embedded in SimBroker fill price (close * (1 +/- slippage)); commission_pct ignored",
        ),
        risk=RiskConstraintAssumptions(
            applied=True,
            per_position_notional_cap=limits.per_position_pct / _RUNTIME_DEFAULT_STOP_FRACTION,
            max_gross_exposure=float(limits.max_gross_exposure_pct),
            max_open_positions=int(limits.max_open_positions),
            evaluated_against=SIZING_FIXED_INITIAL_CAPITAL,
            loss_limits="evaluated with a constant DrawdownState (zero PnL); cannot trigger in replay",
        ),
    )


def diff_assumptions(research: ExecutionAssumptions, runtime: ExecutionAssumptions) -> list[dict[str, Any]]:
    """Field-level differences between two declarations, tagged with their mechanism."""

    owner = {name: mechanism for mechanism, names in MECHANISMS for name in names}
    diffs: list[dict[str, Any]] = []
    left, right = research.to_dict(), runtime.to_dict()
    for item in fields(ExecutionAssumptions):
        name = item.name
        if name in ("version", "path") or left[name] == right[name]:
            continue
        diffs.append(
            {
                "field": name,
                "research": left[name],
                "runtime": right[name],
                "mechanism": owner.get(name, "unmodeled"),
            }
        )
    return diffs


@dataclass
class ExecutionLedger:
    """Per-bar ledger. Symbol fields are bars x symbols; money fields are per bar."""

    target_weight: pd.DataFrame
    order_qty: pd.DataFrame
    position: pd.DataFrame
    cash: pd.Series
    fees: pd.Series
    equity: pd.Series
    risk_modified_bars: int = 0

    @property
    def final_equity(self) -> float:
        return float(self.equity.iloc[-1])

    def to_long_frame(self) -> pd.DataFrame:
        """Long-format export: one row per (bar, symbol) with bar-level money columns."""

        stacked = pd.concat(
            {name: getattr(self, name).stack() for name in _SYMBOL_FIELDS},
            axis=1,
        )
        stacked.index.names = ["timestamp", "symbol"]
        frame = stacked.reset_index()
        bar = pd.DataFrame({"cash": self.cash, "fees": self.fees, "equity": self.equity})
        bar.index.name = "timestamp"
        return frame.merge(bar.reset_index(), on="timestamp", how="left")


def simulate_ledger(
    close: pd.DataFrame,
    decision_weights: pd.DataFrame,
    assumptions: ExecutionAssumptions,
    *,
    initial_capital: float,
) -> ExecutionLedger:
    """Share-level reference ledger driven only by ``assumptions``."""

    if np.isinf(close.to_numpy()).any() or (close.to_numpy() <= 0).any():
        raise ValueError("parity reference model requires positive observed closes")
    symbols = list(close.columns)
    signal = decision_weights.reindex(index=close.index, columns=symbols).fillna(0.0).astype(float)
    fill_weights = signal.shift(assumptions.fill_lag_bars).fillna(0.0).to_numpy()
    # Pre-inception bars are legal only while that symbol is unheld/unrequested.
    prices = close.to_numpy(dtype=float)
    n_bars, n_symbols = prices.shape

    costs = assumptions.costs
    risk = assumptions.risk
    research_costs = costs.model == COST_RESEARCH_WEIGHT_DELTA
    slippage = costs.model == COST_FILL_PRICE_SLIPPAGE
    thresholded = assumptions.rebalance_policy == REBALANCE_THRESHOLDED
    fixed_sizing = assumptions.sizing_basis == SIZING_FIXED_INITIAL_CAPITAL

    qty = np.zeros(n_symbols)
    cash = float(initial_capital)
    pending_cost = 0.0
    previous_weights = np.zeros(n_symbols)
    orders = np.zeros((n_bars, n_symbols))
    positions = np.zeros((n_bars, n_symbols))
    cash_out = np.zeros(n_bars)
    fees_out = np.zeros(n_bars)
    equity_out = np.zeros(n_bars)
    risk_modified = 0

    for t in range(n_bars):
        price = prices[t]
        missing = np.isnan(price)
        if np.any(missing & ((qty != 0.0) | (fill_weights[t] != 0.0))):
            raise ValueError("parity reference model cannot value a held/requested symbol without a close")
        price = np.where(missing, 1.0, price)
        cash -= pending_cost
        fees = pending_cost
        pending_cost = 0.0
        equity_pre = cash + float(qty @ price)
        sizing_equity = float(initial_capital) if fixed_sizing else equity_pre
        weights = fill_weights[t]

        target = np.where(
            np.abs(weights) < _FLAT_QTY,
            0.0,
            sizing_equity * assumptions.sizing_exposure_multiplier * weights / price,
        )
        active = np.ones(n_symbols, dtype=bool)
        if risk.applied:
            before = target.copy()
            target, active = _apply_runtime_risk(target, price, qty, sizing_equity, risk)
            if not np.array_equal(before, target) or not active.all():
                risk_modified += 1

        for j in range(n_symbols):
            if not active[j]:
                continue
            delta = target[j] - qty[j]
            if thresholded:
                if abs(delta) < assumptions.min_qty_delta:
                    continue
                if abs(delta) * price[j] < assumptions.min_notional_delta:
                    continue
                if abs(qty[j]) > _FLAT_QTY and abs(delta) / abs(qty[j]) < assumptions.min_pct_position_delta:
                    continue
                if abs(delta) < _FLAT_QTY:
                    continue
            elif delta == 0.0:
                continue
            fill = price[j]
            if slippage:
                fill = price[j] * (1.0 + costs.buy_cost_pct) if delta > 0 else price[j] * (1.0 - costs.sell_cost_pct)
            cash -= delta * fill
            fees += abs(delta) * abs(fill - price[j])
            new_qty = qty[j] + delta
            qty[j] = 0.0 if abs(new_qty) < _FLAT_QTY else new_qty
            orders[t, j] = delta

        if research_costs:
            change = weights - previous_weights
            pending_cost = sizing_equity * (
                costs.buy_cost_pct * float(np.clip(change, 0.0, None).sum())
                + costs.sell_cost_pct * float(np.clip(-change, 0.0, None).sum())
            )
        if costs.borrow_cost_annual_pct:
            pending_cost += sizing_equity * float(np.clip(-weights, 0.0, None).sum()) * (
                costs.borrow_cost_annual_pct / 252.0
            )
        previous_weights = weights

        positions[t] = qty
        cash_out[t] = cash
        fees_out[t] = fees
        equity_out[t] = cash + float(qty @ price)

    index = close.index
    return ExecutionLedger(
        target_weight=pd.DataFrame(fill_weights, index=index, columns=symbols),
        order_qty=pd.DataFrame(orders, index=index, columns=symbols),
        position=pd.DataFrame(positions, index=index, columns=symbols),
        cash=pd.Series(cash_out, index=index),
        fees=pd.Series(fees_out, index=index),
        equity=pd.Series(equity_out, index=index),
        risk_modified_bars=risk_modified,
    )


def _apply_runtime_risk(
    target: np.ndarray,
    price: np.ndarray,
    qty: np.ndarray,
    equity: float,
    risk: RiskConstraintAssumptions,
) -> tuple[np.ndarray, np.ndarray]:
    """Declared runtime risk constraints, in RiskEngine.evaluate order."""

    target = target.copy()
    active = np.ones(len(target), dtype=bool)
    nonflat = np.abs(target) >= _FLAT_QTY
    if risk.per_position_notional_cap is not None:
        cap = risk.per_position_notional_cap * equity
        notional = np.abs(target) * price
        over = nonflat & (notional > cap)
        target[over] *= cap / notional[over]
    if risk.max_open_positions is not None:
        open_now = np.abs(qty) >= _FLAT_QTY
        new = np.flatnonzero(nonflat & ~open_now)
        allowed = risk.max_open_positions - int(open_now.sum())
        if int(open_now.sum()) + len(new) > risk.max_open_positions:
            rejected = new if allowed <= 0 else new[allowed:]
            active[rejected] = False
    if risk.max_gross_exposure is not None:
        kept = nonflat & active
        gross = float((np.abs(target[kept]) * price[kept]).sum())
        limit = risk.max_gross_exposure * equity
        if gross > limit:
            target[kept] *= limit / gross if gross > 0 else 0.0
    return target, active


def research_ledger(result: Any, close: pd.DataFrame, *, initial_capital: float) -> ExecutionLedger:
    """Ledger implied by an actual ``CrossSectionalBacktestResult``.

    Research is weight-based: positions are the shares implied by its return
    identity (equity * weight / close at the fill close), cash is the residual.
    Equity and fees are taken directly from the research return components.
    """

    symbols = list(close.columns)
    weights = result.decision_weights.reindex(index=close.index, columns=symbols).fillna(0.0).astype(float)
    equity = result.equity_curve.reindex(close.index).astype(float)
    equity_prev = equity.shift(1).fillna(float(initial_capital))
    fees = (result.cost_returns + result.borrow_returns).reindex(close.index).fillna(0.0) * equity_prev
    position = (weights.mul(equity, axis=0) / close).where(weights != 0.0, 0.0)
    order_qty = position.diff()
    order_qty.iloc[0] = position.iloc[0]
    cash = equity - (position * close).sum(axis=1)
    return ExecutionLedger(
        target_weight=weights,
        order_qty=order_qty,
        position=position,
        cash=cash,
        fees=fees,
        equity=equity,
    )


def runtime_ledger(
    db_path: str | Path,
    close: pd.DataFrame,
    target_weights: pd.DataFrame,
    *,
    observed_positions: pd.DataFrame,
    initial_capital: float,
) -> ExecutionLedger:
    """SQLite fill quantities/cash, observed OMS positions, and close-marked equity."""

    symbols = list(close.columns)
    bar_by_key = {str(ts): i for i, ts in enumerate(close.index)}
    orders = np.zeros(close.shape)
    fills = np.zeros(close.shape)
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            """SELECT bar_timestamp, symbol, side, filled_qty, avg_fill_price
               FROM orders_live
               WHERE order_state = 'FILLED' AND filled_qty > 0
               ORDER BY created_at, client_order_id"""
        ).fetchall()
    prices = close.to_numpy(dtype=float)
    fees = np.zeros(len(close))
    for bar_ts, symbol, side, filled_qty, fill_price in rows:
        i = bar_by_key[str(bar_ts)]
        j = symbols.index(str(symbol))
        signed = float(filled_qty) if side == "buy" else -float(filled_qty)
        orders[i, j] += signed
        fills[i, j] += signed * float(fill_price)
        fees[i] += float(filled_qty) * abs(float(fill_price) - prices[i, j])
    index = close.index
    order_qty = pd.DataFrame(orders, index=index, columns=symbols)
    position = observed_positions.reindex(index=index, columns=symbols).fillna(0.0).astype(float)
    cash = float(initial_capital) - pd.Series(fills.sum(axis=1), index=index).cumsum()
    equity = cash + (position * close).sum(axis=1)
    return ExecutionLedger(
        target_weight=target_weights.reindex(index=index, columns=symbols).fillna(0.0).astype(float),
        order_qty=order_qty,
        position=position,
        cash=cash,
        fees=pd.Series(fees, index=index),
        equity=equity,
    )


def field_tolerance(field_name: str, initial_capital: float) -> tuple[float, float]:
    """(atol, rtol) per ledger field."""

    if field_name == "target_weight":
        return WEIGHT_ATOL, 0.0
    if field_name in ("order_qty", "position"):
        return QTY_ATOL, QTY_RTOL
    return MONEY_ATOL_PER_CAPITAL * float(initial_capital), MONEY_RTOL


def compare_ledgers(
    left: ExecutionLedger,
    right: ExecutionLedger,
    *,
    initial_capital: float,
) -> dict[str, dict[str, Any]]:
    """Per-field agreement between two ledgers on the same bars and symbols."""

    report: dict[str, dict[str, Any]] = {}
    for name in LEDGER_FIELDS:
        a = getattr(left, name)
        b = getattr(right, name)
        a_values = np.asarray(a.to_numpy(dtype=float))
        b_values = np.asarray(b.reindex_like(a).to_numpy(dtype=float))
        atol, rtol = field_tolerance(name, initial_capital)
        diff = np.abs(a_values - b_values)
        limit = atol + rtol * np.maximum(np.abs(a_values), np.abs(b_values))
        bad = ~np.isfinite(a_values) | ~np.isfinite(b_values) | (diff > limit)
        bad_rows = bad.any(axis=1) if bad.ndim == 2 else bad
        first = str(a.index[int(np.argmax(bad_rows))]) if bad_rows.any() else None
        report[name] = {
            "max_abs_diff": float(diff.max()) if np.isfinite(diff).all() and diff.size else None,
            "atol": atol,
            "rtol": rtol,
            "within_tolerance": not bool(bad.any()),
            "divergent_bars": int(bad_rows.sum()),
            "first_divergence": first,
        }
    return report


def _all_within(report: dict[str, dict[str, Any]]) -> bool:
    return all(item["within_tolerance"] for item in report.values())


def _toggle(base: ExecutionAssumptions, source: ExecutionAssumptions, mechanism: str) -> ExecutionAssumptions:
    names = dict(MECHANISMS)[mechanism]
    return replace(base, **{name: getattr(source, name) for name in names})


def unmodeled_risk_checks(evaluation: RiskEvaluation | None) -> tuple[str, ...]:
    """Observe actual risk results; unknown/reduced checks cannot silently pass."""
    if evaluation is None:
        return ("risk_evaluation_unavailable",)
    return tuple(sorted({
        check.check_name for check in evaluation.decisions
        if check.decision != RiskDecision.APPROVED and check.check_name not in MODELED_RISK_CHECKS
    }))


def evaluate_execution_parity(
    *,
    close: pd.DataFrame,
    decision_weights: pd.DataFrame,
    research_actual: ExecutionLedger,
    runtime_actual: ExecutionLedger,
    research: ExecutionAssumptions,
    runtime: ExecutionAssumptions,
    initial_capital: float,
    runtime_unmodeled_risk_checks: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Check both paths against their declarations and attribute every difference."""

    diffs = diff_assumptions(research, runtime)
    unmodeled = [d["field"] for d in diffs if d["mechanism"] == "unmodeled"]
    risk_coverage_verified = not runtime.risk.applied or runtime_unmodeled_risk_checks == ()

    def run(assumptions: ExecutionAssumptions) -> ExecutionLedger:
        return simulate_ledger(close, decision_weights, assumptions, initial_capital=initial_capital)

    research_model = run(research)
    runtime_model = run(runtime)
    research_check = compare_ledgers(research_actual, research_model, initial_capital=initial_capital)
    runtime_check = compare_ledgers(runtime_actual, runtime_model, initial_capital=initial_capital)
    declarations_hold = _all_within(research_check) and _all_within(runtime_check)

    differing = {d["mechanism"] for d in diffs}
    chain: list[dict[str, Any]] = []
    isolated: dict[str, float] = {}
    current = research
    current_equity = research_model.final_equity
    for mechanism, _names in MECHANISMS:
        if mechanism not in differing:
            continue
        stepped = _toggle(current, runtime, mechanism)
        stepped_ledger = run(stepped)
        chain.append(
            {
                "mechanism": mechanism,
                "final_equity_before": current_equity,
                "final_equity_after": stepped_ledger.final_equity,
                "equity_delta": stepped_ledger.final_equity - current_equity,
                "risk_modified_bars": stepped_ledger.risk_modified_bars,
            }
        )
        current, current_equity = stepped, stepped_ledger.final_equity
        isolated[mechanism] = run(_toggle(research, runtime, mechanism)).final_equity - research_model.final_equity

    actual_gap = runtime_actual.final_equity - research_actual.final_equity
    attributed_gap = sum(step["equity_delta"] for step in chain)
    residual = actual_gap - attributed_gap
    money_atol, money_rtol = field_tolerance("equity", initial_capital)
    residual_limit = money_atol + money_rtol * max(abs(research_actual.final_equity), abs(runtime_actual.final_equity))
    residual_ok = abs(residual) <= residual_limit

    direct = compare_ledgers(research_actual, runtime_actual, initial_capital=initial_capital)
    lagged_decisions = research_actual.target_weight.shift(runtime.fill_lag_bars - research.fill_lag_bars).fillna(0.0)
    decision_diff = float(np.abs(lagged_decisions.to_numpy() - runtime_actual.target_weight.to_numpy()).max())
    decisions_identical = decision_diff <= WEIGHT_ATOL

    fields_report: dict[str, dict[str, Any]] = {}
    for name in LEDGER_FIELDS:
        entry = dict(direct[name])
        if entry["within_tolerance"]:
            entry["status"] = "equal"
        elif declarations_hold and not unmodeled and residual_ok and risk_coverage_verified:
            entry["status"] = "attributed"
        else:
            entry["status"] = "unexplained"
        fields_report[name] = entry

    if not declarations_hold or unmodeled or not residual_ok or not decisions_identical or not risk_coverage_verified:
        status = FINANCIAL_PARITY_FAILED
    elif not diffs and all(item["status"] == "equal" for item in fields_report.values()):
        status = FINANCIAL_PARITY_ESTABLISHED
    else:
        status = FINANCIAL_PARITY_ATTRIBUTED

    return {
        "version": PARITY_REPORT_VERSION,
        "assumptions_version": research.version,
        "financial_parity": status,
        "declared_differences": diffs,
        "unmodeled_differences": unmodeled,
        "risk_model_coverage": {
            "verified": risk_coverage_verified,
            "modeled_checks": sorted(MODELED_RISK_CHECKS),
            "unmodeled_triggered_checks": (
                list(runtime_unmodeled_risk_checks) if runtime_unmodeled_risk_checks is not None else None
            ),
        },
        "decision_parity": {
            "research_vs_runtime_target_weights_max_abs_diff_after_declared_lag": decision_diff,
            "identical": decisions_identical,
        },
        "research_matches_research_declaration": _all_within(research_check),
        "runtime_matches_runtime_declaration": _all_within(runtime_check),
        "research_declaration_check": research_check,
        "runtime_declaration_check": runtime_check,
        "research_vs_runtime_fields": fields_report,
        "final_equity": {
            "research_actual": research_actual.final_equity,
            "runtime_actual": runtime_actual.final_equity,
            "research_model": research_model.final_equity,
            "runtime_model": runtime_model.final_equity,
            "gap_runtime_minus_research": actual_gap,
        },
        "attribution": {
            "method": "sequential one-mechanism toggles in the declared reference model, research -> runtime",
            "order": [step["mechanism"] for step in chain],
            "chain": chain,
            "isolated_equity_delta_from_research": isolated,
            "interaction_equity_delta": attributed_gap - sum(isolated.values()),
            "attributed_gap": attributed_gap,
            "residual": residual,
            "residual_limit": residual_limit,
            "residual_within_tolerance": residual_ok,
        },
    }
