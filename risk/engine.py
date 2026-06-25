"""Risk engine — circuit breakers, exposure limits, correlation, kill switches.

Strategy-agnostic. Does NOT know about MA, BB, pairs, or CSMR.
Input: target positions from portfolio/.
Output: APPROVED / REDUCED / REJECTED with reasons.

Three exception severity classes:
  - SOFT:      one strategy fails → disable that strategy only
  - HARD:      risk engine failure / position mismatch → halt all trading
  - CATASTROPHIC: unknown state / broker unreachable → freeze, alert, manual

No blind flattening. Flatten only if state KNOWN and risk requires it.
Unknown state → freeze + alert + manual review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from config.schema import RiskLimits
from portfolio.sizing import PortfolioState, TargetPosition


class RiskDecision(StrEnum):
    APPROVED = "APPROVED"
    REDUCED = "REDUCED"
    REJECTED = "REJECTED"


class ExceptionSeverity(StrEnum):
    SOFT = "SOFT"
    HARD = "HARD"
    CATASTROPHIC = "CATASTROPHIC"


@dataclass
class RiskCheckResult:
    """Result of a single risk check."""

    check_name: str
    decision: RiskDecision
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskEvaluation:
    """Full risk evaluation for a set of target positions."""

    decisions: list[RiskCheckResult] = field(default_factory=list)
    final_decision: RiskDecision = RiskDecision.APPROVED
    adjusted_targets: list[TargetPosition] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    reduction_reasons: list[str] = field(default_factory=list)

    @property
    def is_approved(self) -> bool:
        return self.final_decision == RiskDecision.APPROVED

    @property
    def is_rejected(self) -> bool:
        return self.final_decision == RiskDecision.REJECTED


@dataclass
class DrawdownState:
    """Current drawdown tracking state."""

    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    monthly_pnl: float = 0.0
    high_water_mark: float = 0.0
    current_equity: float = 0.0
    consecutive_losses: int = 0

    @property
    def daily_loss_pct(self) -> float:
        return self.daily_pnl / self.high_water_mark if self.high_water_mark > 0 else 0.0

    @property
    def weekly_loss_pct(self) -> float:
        return self.weekly_pnl / self.high_water_mark if self.high_water_mark > 0 else 0.0

    @property
    def monthly_loss_pct(self) -> float:
        return self.monthly_pnl / self.high_water_mark if self.high_water_mark > 0 else 0.0

    @property
    def drawdown_from_hwm(self) -> float:
        if self.high_water_mark <= 0:
            return 0.0
        return (self.current_equity - self.high_water_mark) / self.high_water_mark


class RiskEngine:
    """Portfolio-level risk engine. Strategy-agnostic.

    Checks (in order):
      1. Kill switch state — if active, reject everything
      2. Per-position risk — each position ≤ per_position_pct
      3. Max gross exposure — total notional ≤ max_gross_exposure_pct
      4. Max net exposure — |net| ≤ max_net_exposure_pct
      5. Max open positions — count ≤ max_open_positions
      6. Sector exposure — per-sector gross/net limits
      7. Correlation cluster — correlated positions ≤ cluster limit
      8. Daily loss — block new at 2%, flatten at 3%
      9. Weekly loss — block at 6%
      10. Monthly drawdown — hard halt at 15%
    """

    def __init__(self, limits: RiskLimits):
        self.limits = limits
        self._kill_switch_active = False
        self._kill_switch_reason: str | None = None
        self._halted_strategies: set[str] = set()

    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch_active

    @property
    def kill_switch_reason(self) -> str | None:
        return self._kill_switch_reason

    def activate_kill_switch(self, reason: str) -> None:
        """Activate the global kill switch — blocks all trading."""
        self._kill_switch_active = True
        self._kill_switch_reason = reason

    def deactivate_kill_switch(self) -> None:
        """Manually clear the kill switch."""
        self._kill_switch_active = False
        self._kill_switch_reason = None

    def halt_strategy(self, strategy: str, reason: str) -> None:
        """Halt a single strategy (soft exception)."""
        self._halted_strategies.add(strategy)

    def resume_strategy(self, strategy: str) -> None:
        """Resume a halted strategy."""
        self._halted_strategies.discard(strategy)

    def is_strategy_halted(self, strategy: str) -> bool:
        return strategy in self._halted_strategies

    def evaluate(
        self,
        targets: list[TargetPosition],
        state: PortfolioState,
        drawdown: DrawdownState,
        *,
        strategy_name: str = "",
        current_positions: dict[str, dict[str, Any]] | None = None,
        sector_map: dict[str, str] | None = None,
        correlation_matrix: dict[str, dict[str, float]] | None = None,
    ) -> RiskEvaluation:
        """Evaluate target positions against all risk limits.

        Args:
            targets: Target positions from portfolio.
            state: Current portfolio state.
            drawdown: Current drawdown tracking state.
            strategy_name: Strategy requesting the targets (for per-strategy halts).
            current_positions: Current open positions {symbol: {qty, avg_price, side}}.
            sector_map: {symbol: sector_name} for sector exposure checks.
            correlation_matrix: {sym1: {sym2: corr}} for correlation cluster checks.

        Returns:
            RiskEvaluation with final decision and adjusted targets.
        """
        evaluation = RiskEvaluation()
        current_positions = current_positions or {}
        sector_map = sector_map or {}

        # 1. Kill switch — blocks everything
        if self._kill_switch_active:
            evaluation.decisions.append(
                RiskCheckResult("kill_switch", RiskDecision.REJECTED, self._kill_switch_reason or "kill switch active")
            )
            evaluation.final_decision = RiskDecision.REJECTED
            evaluation.rejection_reasons.append(f"kill_switch: {self._kill_switch_reason}")
            evaluation.adjusted_targets = []
            return evaluation

        # 2. Per-strategy halt
        if strategy_name and self.is_strategy_halted(strategy_name):
            evaluation.decisions.append(
                RiskCheckResult("strategy_halt", RiskDecision.REJECTED, f"strategy {strategy_name} halted")
            )
            evaluation.final_decision = RiskDecision.REJECTED
            evaluation.rejection_reasons.append(f"strategy_halt: {strategy_name}")
            evaluation.adjusted_targets = []
            return evaluation

        # 3. Daily loss check — block new entries at block_new_at_daily_loss_pct
        if drawdown.daily_loss_pct <= -self.limits.block_new_at_daily_loss_pct:
            evaluation.decisions.append(
                RiskCheckResult(
                    "daily_loss_block",
                    RiskDecision.REJECTED,
                    f"daily loss {drawdown.daily_loss_pct:.2%} ≤ -{self.limits.block_new_at_daily_loss_pct:.2%}",
                )
            )
            # Allow exits only (flat targets), block new entries
            targets = [t for t in targets if t.is_flat]
            if not targets:
                evaluation.final_decision = RiskDecision.REJECTED
                evaluation.rejection_reasons.append("daily_loss: only exits allowed, no flat targets")

        # 4. Hard daily loss — flatten at max_daily_loss_pct
        if drawdown.daily_loss_pct <= -self.limits.max_daily_loss_pct:
            evaluation.decisions.append(
                RiskCheckResult(
                    "daily_loss_halt",
                    RiskDecision.REJECTED,
                    f"daily loss {drawdown.daily_loss_pct:.2%} ≤ -{self.limits.max_daily_loss_pct:.2%} → flatten",
                )
            )
            targets = [self._flatten_target(t) for t in targets]
            evaluation.final_decision = RiskDecision.REDUCED
            evaluation.reduction_reasons.append("daily_loss_halt: flatten all")

        # 5. Weekly loss
        if drawdown.weekly_loss_pct <= -self.limits.max_weekly_loss_pct:
            evaluation.decisions.append(
                RiskCheckResult(
                    "weekly_loss",
                    RiskDecision.REJECTED,
                    f"weekly loss {drawdown.weekly_loss_pct:.2%} ≤ -{self.limits.max_weekly_loss_pct:.2%}",
                )
            )
            targets = [t for t in targets if t.is_flat]
            if not targets:
                evaluation.final_decision = RiskDecision.REJECTED
                evaluation.rejection_reasons.append("weekly_loss: block new entries")

        # 6. Monthly drawdown — hard halt
        if drawdown.monthly_loss_pct <= -self.limits.max_monthly_loss_pct:
            evaluation.decisions.append(
                RiskCheckResult(
                    "monthly_halt",
                    RiskDecision.REJECTED,
                    f"monthly loss {drawdown.monthly_loss_pct:.2%} ≤ -{self.limits.max_monthly_loss_pct:.2%} → HARD HALT",
                )
            )
            targets = [self._flatten_target(t) for t in targets]
            evaluation.final_decision = RiskDecision.REJECTED
            evaluation.rejection_reasons.append("monthly_halt: requires manual review")

        # 7. Per-position risk
        targets = self._check_per_position_risk(targets, state, evaluation)

        # 8. Max open positions
        targets = self._check_max_open_positions(targets, current_positions, evaluation)

        # 9. Gross exposure
        targets = self._check_gross_exposure(targets, state, evaluation)

        # 10. Net exposure
        targets = self._check_net_exposure(targets, state, evaluation)

        # 11. Sector exposure
        if sector_map:
            targets = self._check_sector_exposure(targets, state, sector_map, evaluation)

        # 12. Correlation cluster
        if correlation_matrix:
            targets = self._check_correlation_cluster(targets, state, correlation_matrix, evaluation)

        evaluation.adjusted_targets = targets

        # Determine final decision
        if any(d.decision == RiskDecision.REJECTED for d in evaluation.decisions):
            if evaluation.final_decision != RiskDecision.REJECTED:
                evaluation.final_decision = RiskDecision.REJECTED
        elif any(d.decision == RiskDecision.REDUCED for d in evaluation.decisions):
            evaluation.final_decision = RiskDecision.REDUCED
        else:
            evaluation.final_decision = RiskDecision.APPROVED

        return evaluation

    def _flatten_target(self, t: TargetPosition) -> TargetPosition:
        """Convert a target to flat (exit)."""
        return TargetPosition(
            symbol=t.symbol,
            asset_class=t.asset_class,
            side="flat",
            target_qty=0.0,
            target_notional=0.0,
            current_price=t.current_price,
            stop_price=t.stop_price,
            sizing_method=t.sizing_method,
            metadata={**t.metadata, "flattened_by_risk": True},
        )

    def _check_per_position_risk(
        self,
        targets: list[TargetPosition],
        state: PortfolioState,
        evaluation: RiskEvaluation,
    ) -> list[TargetPosition]:
        """Ensure each position's risk ≤ per_position_pct of equity."""
        max_risk = self.limits.per_position_pct * state.equity
        adjusted: list[TargetPosition] = []

        for t in targets:
            if t.is_flat:
                adjusted.append(t)
                continue

            # Estimate risk: notional * 5% default, or use stop if available
            if t.risk_per_unit and t.risk_per_unit > 0:
                position_risk = abs(t.target_qty) * t.risk_per_unit
            else:
                position_risk = t.target_notional * 0.05  # default 5% stop

            if position_risk > max_risk:
                # Reduce position to fit risk limit
                scale = max_risk / position_risk
                t.target_qty *= scale
                t.target_notional = abs(t.target_qty) * t.current_price
                evaluation.decisions.append(
                    RiskCheckResult(
                        "per_position_risk",
                        RiskDecision.REDUCED,
                        f"{t.symbol}: risk {position_risk:.2f} > {max_risk:.2f}, reduced by {scale:.2%}",
                    )
                )
                evaluation.reduction_reasons.append(f"per_position_risk: {t.symbol}")
            else:
                evaluation.decisions.append(
                    RiskCheckResult("per_position_risk", RiskDecision.APPROVED, f"{t.symbol}: risk {position_risk:.2f} ≤ {max_risk:.2f}")
                )
            adjusted.append(t)

        return adjusted

    def _check_max_open_positions(
        self,
        targets: list[TargetPosition],
        current_positions: dict[str, dict[str, Any]],
        evaluation: RiskEvaluation,
    ) -> list[TargetPosition]:
        """Ensure total open positions ≤ max_open_positions."""
        # Count new positions (not flat, and not already in current_positions)
        new_positions = [t for t in targets if not t.is_flat and t.symbol not in current_positions]
        current_count = len(current_positions)

        if current_count + len(new_positions) > self.limits.max_open_positions:
            # Reject the newest positions that exceed the limit
            allowed_new = self.limits.max_open_positions - current_count
            if allowed_new <= 0:
                evaluation.decisions.append(
                    RiskCheckResult(
                        "max_open_positions",
                        RiskDecision.REJECTED,
                        f"{current_count} open + {len(new_positions)} new > {self.limits.max_open_positions}",
                    )
                )
                evaluation.rejection_reasons.append("max_open_positions: limit reached")
                # Keep only existing position adjustments and flat targets
                targets = [t for t in targets if t.is_flat or t.symbol in current_positions]
            else:
                # Keep only the first `allowed_new` new positions
                kept_new = new_positions[:allowed_new]
                rejected_new = new_positions[allowed_new:]
                for r in rejected_new:
                    evaluation.decisions.append(
                        RiskCheckResult("max_open_positions", RiskDecision.REJECTED, f"{r.symbol}: exceeds limit")
                    )
                targets = [t for t in targets if t.is_flat or t.symbol in current_positions or t in kept_new]
                evaluation.rejection_reasons.append(f"max_open_positions: rejected {len(rejected_new)} new")

        return targets

    def _check_gross_exposure(
        self,
        targets: list[TargetPosition],
        state: PortfolioState,
        evaluation: RiskEvaluation,
    ) -> list[TargetPosition]:
        """Ensure total gross notional ≤ max_gross_exposure_pct of equity."""
        total_gross = sum(t.target_notional for t in targets if not t.is_flat)
        max_gross = self.limits.max_gross_exposure_pct * state.equity

        if total_gross > max_gross:
            scale = max_gross / total_gross if total_gross > 0 else 0.0
            evaluation.decisions.append(
                RiskCheckResult(
                    "gross_exposure",
                    RiskDecision.REDUCED,
                    f"gross {total_gross:.2f} > {max_gross:.2f}, scaling by {scale:.2%}",
                )
            )
            evaluation.reduction_reasons.append("gross_exposure")
            for t in targets:
                if not t.is_flat:
                    t.target_qty *= scale
                    t.target_notional = abs(t.target_qty) * t.current_price

        return targets

    def _check_net_exposure(
        self,
        targets: list[TargetPosition],
        state: PortfolioState,
        evaluation: RiskEvaluation,
    ) -> list[TargetPosition]:
        """Ensure |net exposure| ≤ max_net_exposure_pct of equity."""
        net = sum(t.target_qty * t.current_price for t in targets if not t.is_flat)
        max_net = self.limits.max_net_exposure_pct * state.equity

        if abs(net) > max_net:
            evaluation.decisions.append(
                RiskCheckResult(
                    "net_exposure",
                    RiskDecision.REDUCED,
                    f"net {net:.2f} > ±{max_net:.2f}",
                )
            )
            evaluation.reduction_reasons.append("net_exposure")

        return targets

    def _check_sector_exposure(
        self,
        targets: list[TargetPosition],
        state: PortfolioState,
        sector_map: dict[str, str],
        evaluation: RiskEvaluation,
    ) -> list[TargetPosition]:
        """Check per-sector gross and net exposure limits."""
        sector_gross: dict[str, float] = {}
        sector_net: dict[str, float] = {}

        for t in targets:
            if t.is_flat:
                continue
            sector = sector_map.get(t.symbol, "unknown")
            sector_gross[sector] = sector_gross.get(sector, 0) + t.target_notional
            sector_net[sector] = sector_net.get(sector, 0) + t.target_qty * t.current_price

        max_sector_gross = self.limits.max_sector_gross_pct * state.equity
        max_sector_net = self.limits.max_sector_net_pct * state.equity

        for sector, gross in sector_gross.items():
            if gross > max_sector_gross:
                evaluation.decisions.append(
                    RiskCheckResult(
                        "sector_gross",
                        RiskDecision.REDUCED,
                        f"sector {sector}: gross {gross:.2f} > {max_sector_gross:.2f}",
                    )
                )
                evaluation.reduction_reasons.append(f"sector_gross: {sector}")

        for sector, net in sector_net.items():
            if abs(net) > max_sector_net:
                evaluation.decisions.append(
                    RiskCheckResult(
                        "sector_net",
                        RiskDecision.REDUCED,
                        f"sector {sector}: net {net:.2f} > ±{max_sector_net:.2f}",
                    )
                )
                evaluation.reduction_reasons.append(f"sector_net: {sector}")

        return targets

    def _check_correlation_cluster(
        self,
        targets: list[TargetPosition],
        state: PortfolioState,
        correlation_matrix: dict[str, dict[str, float]],
        evaluation: RiskEvaluation,
    ) -> list[TargetPosition]:
        """Check that correlated position clusters don't exceed limits."""
        threshold = self.limits.correlation_threshold
        max_cluster_gross = self.limits.max_correlated_cluster_gross_pct * state.equity

        # Build clusters: group symbols with correlation > threshold
        active_symbols = [t.symbol for t in targets if not t.is_flat]
        clusters = self._find_correlation_clusters(active_symbols, correlation_matrix, threshold)

        for cluster_id, symbols in clusters.items():
            if len(symbols) < 2:
                continue
            cluster_gross = sum(
                t.target_notional for t in targets if t.symbol in symbols and not t.is_flat
            )
            if cluster_gross > max_cluster_gross:
                evaluation.decisions.append(
                    RiskCheckResult(
                        "correlation_cluster",
                        RiskDecision.REDUCED,
                        f"cluster {cluster_id} ({symbols}): gross {cluster_gross:.2f} > {max_cluster_gross:.2f}",
                    )
                )
                evaluation.reduction_reasons.append(f"correlation_cluster: {cluster_id}")

        return targets

    def _find_correlation_clusters(
        self,
        symbols: list[str],
        corr_matrix: dict[str, dict[str, float]],
        threshold: float,
    ) -> dict[int, list[str]]:
        """Group symbols into clusters based on correlation threshold."""
        # Union-Find
        parent = {s: s for s in symbols}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        for i, s1 in enumerate(symbols):
            for s2 in symbols[i + 1:]:
                corr = corr_matrix.get(s1, {}).get(s2, 0.0)
                if abs(corr) > threshold:
                    union(s1, s2)

        clusters: dict[int, list[str]] = {}
        for s in symbols:
            root = find(s)
            clusters.setdefault(hash(root), []).append(s)

        return clusters


def classify_exception(error_type: str, context: dict[str, Any] | None = None) -> ExceptionSeverity:
    """Classify an exception into SOFT / HARD / CATASTROPHIC.

    Soft:      one strategy fails, indicator calc fails, bad symbol data
    Hard:      risk engine failure, position mismatch, stale market data, DB write failure
    Catastrophic: internal position unknown, broker unreachable during exposure, repeated ambiguity
    """
    context = context or {}

    soft_errors = {
        "indicator_calc_error",
        "strategy_runtime_error",
        "bad_symbol_data",
        "single_strategy_failed",
    }
    hard_errors = {
        "risk_engine_failure",
        "position_mismatch",
        "broker_order_ambiguity",
        "db_write_failure",
        "stale_market_data",
        "broker_reject_spike",
    }
    catastrophic_errors = {
        "internal_position_unknown",
        "broker_unreachable_during_exposure",
        "repeated_order_ambiguity",
        "exposure_calculation_failed",
    }

    if error_type in soft_errors:
        return ExceptionSeverity.SOFT
    elif error_type in hard_errors:
        return ExceptionSeverity.HARD
    elif error_type in catastrophic_errors:
        return ExceptionSeverity.CATASTROPHIC

    # Default to HARD for unknown errors
    return ExceptionSeverity.HARD


def determine_emergency_action(
    severity: ExceptionSeverity,
    state_known: bool,
    risk_breach: bool,
) -> str:
    """Determine the correct emergency action.

    Known-risk emergency + risk breach → flatten allowed
    Unknown-state emergency → freeze, alert, manual review
    """
    if severity == ExceptionSeverity.SOFT:
        return "disable_strategy"

    if severity == ExceptionSeverity.CATASTROPHIC:
        return "freeze_alert_manual"

    # HARD
    if not state_known:
        return "freeze_alert_manual"

    if risk_breach:
        return "flatten_if_safe"

    return "halt_new_orders"
