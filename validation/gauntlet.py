"""Validation gauntlet — orchestrates WFA + MC + DSR + parameter stability.

This is the filter that kills most strategies. A strategy only passes if it
survives ALL four checks:

  1. Walk-forward: OOS Sharpe > 0.8, Sortino > 1.0, < 50% negative folds
  2. Monte Carlo: P(ruin) < 5%, 5th pct CAGR > 0, 95th pct max DD under limit
  3. DSR: p < 0.05 using M_eff_corr, doesn't collapse under M_raw
  4. Stability: no isolated peak, plateau within 20-30% of best

If any check fails, the strategy is archived with a postmortem.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import structlog

from validation.dsr.engine import DSRResult, compute_dsr
from validation.mc.engine import MCResult, run_monte_carlo
from validation.stability.engine import StabilityResult, analyze_stability
from validation.wfa.engine import WFAResult, run_wfa

log = structlog.get_logger(__name__)


@dataclass
class GauntletResult:
    """Final result of the validation gauntlet."""

    strategy_name: str
    wfa_result: WFAResult | None = None
    mc_result: MCResult | None = None
    dsr_result: DSRResult | None = None
    stability_result: StabilityResult | None = None
    passed: bool = False
    failure_reasons: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "passed": self.passed,
            "failure_reasons": self.failure_reasons,
            "wfa": {
                "passed": self.wfa_result.passed if self.wfa_result else False,
                "oos_sharpe": self.wfa_result.aggregate_metrics.get("oos_sharpe", 0) if self.wfa_result else 0,
                "num_folds": self.wfa_result.num_folds if self.wfa_result else 0,
                "frac_negative": self.wfa_result.frac_negative_folds if self.wfa_result else 0,
            } if self.wfa_result else None,
            "monte_carlo": {
                "prob_loss": self.mc_result.prob_loss if self.mc_result else 0,
                "prob_ruin": self.mc_result.prob_ruin if self.mc_result else 0,
                "pct_5_cagr": self.mc_result.pct_5_cagr if self.mc_result else 0,
                "pct_95_max_dd": self.mc_result.pct_95_max_dd if self.mc_result else 0,
                "mean_sharpe": self.mc_result.mean_sharpe if self.mc_result else 0,
            } if self.mc_result else None,
            "dsr": {
                "passed": self.dsr_result.passed if self.dsr_result else False,
                "pvalue": self.dsr_result.dsr_pvalue if self.dsr_result else 1.0,
                "m_raw": self.dsr_result.num_trials_raw if self.dsr_result else 0,
                "m_eff": self.dsr_result.num_trials_eff if self.dsr_result else 0,
                "method": self.dsr_result.method if self.dsr_result else "",
            } if self.dsr_result else None,
            "stability": {
                "passed": self.stability_result.passed if self.stability_result else False,
                "has_isolated_peak": self.stability_result.has_isolated_peak if self.stability_result else True,
                "plateau_within_pct": self.stability_result.plateau_within_pct if self.stability_result else 0,
            } if self.stability_result else None,
        }


def run_gauntlet(
    strategy_name: str,
    df: pd.DataFrame,
    train_fn: Callable[..., dict[str, Any]],
    test_fn: Callable[..., dict[str, Any]],
    sweep_results: pd.DataFrame,
    param_columns: list[str],
    *,
    best_sharpe: float | None = None,
    returns_matrix: np.ndarray | pd.DataFrame | None = None,
    oos_returns: pd.Series | None = None,
    initial_capital: float = 10000.0,
    ruin_threshold: float = -0.50,
    max_dd_limit: float = -0.30,
    mc_num_paths: int = 10000,
    mc_block_size: int = 20,
    wfa_config: Any = None,
    seed: int = 42,
    **wfa_kwargs: Any,
) -> GauntletResult:
    """Run the full validation gauntlet on a strategy.

    Args:
        strategy_name: Name of the strategy being tested.
        df: Full OHLCV dataset.
        train_fn: WFA training function.
        test_fn: WFA testing function.
        sweep_results: DataFrame of parameter sweep results (for DSR + stability).
        param_columns: Parameter column names in sweep_results.
        best_sharpe: Best observed Sharpe (for DSR). Auto-detected if None.
        returns_matrix: Returns matrix for M_eff estimation (n_bars x n_trials).
        oos_returns: OOS returns series for Monte Carlo. Auto-extracted from WFA if None.
        initial_capital: Starting capital for MC.
        ruin_threshold: Drawdown threshold for ruin (default -50%).
        max_dd_limit: Max acceptable 95th percentile drawdown.
        mc_num_paths: Number of MC paths.
        mc_block_size: MC block size.
        wfa_config: WFA config (defaults to PRIMARY).
        seed: Random seed.
        **wfa_kwargs: Extra args for WFA train_fn.

    Returns:
        GauntletResult with all four checks and overall pass/fail.
    """
    result = GauntletResult(strategy_name=strategy_name)
    failures: list[str] = []

    # ── 1. Walk-Forward Analysis ──────────────────────────────────────────
    log.info("gauntlet_wfa_start", strategy=strategy_name)
    wfa_result = run_wfa(df, train_fn, test_fn, wfa_config, **wfa_kwargs)
    result.wfa_result = wfa_result

    if not wfa_result.passed:
        failures.extend([f"WFA: {r}" for r in wfa_result.failure_reasons])

    # Extract OOS returns for MC
    if oos_returns is None:
        oos_returns = wfa_result.oos_returns
    if oos_returns is None or (hasattr(oos_returns, "empty") and oos_returns.empty):
        # Fallback: use the last fold's returns if available
        if wfa_result.folds:
            for fold in reversed(wfa_result.folds):
                if "returns" in fold.test_metrics and isinstance(fold.test_metrics["returns"], pd.Series):
                    oos_returns = fold.test_metrics["returns"]
                    break

    # ── 2. Monte Carlo Simulation ─────────────────────────────────────────
    if oos_returns is not None and not oos_returns.empty:
        log.info("gauntlet_mc_start", strategy=strategy_name, bars=len(oos_returns))
        mc_result = run_monte_carlo(
            oos_returns,
            num_paths=mc_num_paths,
            block_size=mc_block_size,
            initial_capital=initial_capital,
            ruin_threshold=ruin_threshold,
            seed=seed,
        )
        result.mc_result = mc_result

        # MC pass criteria
        if mc_result.prob_ruin >= 0.05:
            failures.append(f"MC: P(ruin) = {mc_result.prob_ruin:.3f} >= 0.05")
        if mc_result.pct_5_cagr <= 0:
            failures.append(f"MC: 5th pct CAGR = {mc_result.pct_5_cagr:.3f} <= 0")
        if mc_result.pct_95_max_dd < max_dd_limit:
            failures.append(
                f"MC: 95th pct max DD = {mc_result.pct_95_max_dd:.3f} < {max_dd_limit}"
            )
    else:
        failures.append("MC: no OOS returns available for simulation")

    # ── 3. Deflated Sharpe Ratio ──────────────────────────────────────────
    if best_sharpe is None and not sweep_results.empty:
        best_sharpe = float(sweep_results["sharpe"].max())

    if best_sharpe is not None and best_sharpe > 0:
        log.info("gauntlet_dsr_start", strategy=strategy_name, sharpe=best_sharpe)
        num_trials_raw = len(sweep_results) if not sweep_results.empty else 1
        T = len(oos_returns) if oos_returns is not None else 0

        dsr_result = compute_dsr(
            observed_sharpe=best_sharpe,
            returns_matrix=returns_matrix,
            num_trials_raw=num_trials_raw,
            track_record_length=T or 252,
        )
        result.dsr_result = dsr_result

        if not dsr_result.passed:
            failures.extend([f"DSR: {r}" for r in dsr_result.failure_reasons])
    else:
        failures.append("DSR: no positive Sharpe to deflate")

    # ── 4. Parameter Stability ────────────────────────────────────────────
    if not sweep_results.empty and param_columns:
        log.info("gauntlet_stability_start", strategy=strategy_name)
        stability_result = analyze_stability(sweep_results, param_columns)
        result.stability_result = stability_result

        if not stability_result.passed:
            failures.extend([f"Stability: {r}" for r in stability_result.failure_reasons])
    else:
        failures.append("Stability: no sweep results to analyze")

    # ── Final verdict ─────────────────────────────────────────────────────
    result.failure_reasons = failures
    result.passed = len(failures) == 0
    result.summary = result.to_dict()

    if result.passed:
        log.info("gauntlet_passed", strategy=strategy_name)
    else:
        log.warning("gauntlet_failed", strategy=strategy_name, failures=failures)

    return result
