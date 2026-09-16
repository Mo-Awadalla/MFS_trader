"""Validation gauntlet — orchestrates WFA + MC + DSR + parameter stability.

This is the filter that kills most strategies. A strategy only passes if it
survives ALL four checks:

  1. Walk-forward: OOS Sharpe > 0.8, Sortino > 1.0, < 50% negative folds
  2. Monte Carlo: P(ruin) < 5%, 5th pct CAGR > 0, adverse 5th pct max DD under limit
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
                "pct_5_max_dd": self.mc_result.pct_5_max_dd if self.mc_result else 0,
                "mean_sharpe": self.mc_result.mean_sharpe if self.mc_result else 0,
            } if self.mc_result else None,
            "dsr": {
                "passed": self.dsr_result.passed if self.dsr_result else False,
                "available": self.dsr_result.available if self.dsr_result else False,
                "unavailable_reason": self.dsr_result.unavailable_reason if self.dsr_result else None,
                "formula": "Bailey-Lopez-de-Prado Eq. (2)",
                "formula_version": self.dsr_result.formula_version if self.dsr_result else "",
                "sharpe_unit": "per_observation",
                "pvalue": self.dsr_result.dsr_pvalue if self.dsr_result else 1.0,
                "confidence": self.dsr_result.dsr_confidence if self.dsr_result else 0.0,
                "observed_sharpe": self.dsr_result.observed_sharpe if self.dsr_result else None,
                "expected_max_sharpe": self.dsr_result.expected_max_sharpe if self.dsr_result else None,
                "track_record_length": self.dsr_result.track_record_length if self.dsr_result else 0,
                "selected_return_skewness": self.dsr_result.selected_return_skewness if self.dsr_result else None,
                "selected_return_kurtosis": self.dsr_result.selected_return_kurtosis if self.dsr_result else None,
                "trial_sharpe_variance": self.dsr_result.trial_sharpe_variance if self.dsr_result else None,
                "m_raw": self.dsr_result.num_trials_raw if self.dsr_result else 0,
                "m_eff": self.dsr_result.num_trials_eff if self.dsr_result else 0,
                "method": self.dsr_result.method if self.dsr_result else "",
                "search_scope": self.dsr_result.search_scope if self.dsr_result else "",
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
    dsr_selected_trial_index: int | None = None,
    dsr_selected_returns: pd.Series | np.ndarray | None = None,
    dsr_search_scope: str | None = None,
    dsr_selection_error: str | None = None,
    dsr_sharpe_annualization_factor: float | None = None,
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
        best_sharpe: Optional reported Sharpe for the selected trial; it is
            checked only when dsr_sharpe_annualization_factor is supplied.
        returns_matrix: Full returns matrix for DSR (n_bars x all searched trials).
        dsr_selected_trial_index: Column for the frozen selected trial in returns_matrix.
        dsr_selected_returns: Optional selected trial series; it must equal that column.
        dsr_search_scope: Human-readable disclosure of every trial in returns_matrix.
        dsr_selection_error: Reason the frozen candidate could not be mapped
            to exactly one matrix column; makes DSR explicitly unavailable.
        dsr_sharpe_annualization_factor: Required to compare legacy best_sharpe.
        oos_returns: OOS returns series for Monte Carlo. Auto-extracted from WFA if None.
        initial_capital: Starting capital for MC.
        ruin_threshold: Drawdown threshold for ruin (default -50%).
        max_dd_limit: Max acceptable adverse signed 5th-percentile drawdown.
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
        if mc_result.pct_5_max_dd < max_dd_limit:
            failures.append(
                f"MC: adverse 5th pct max DD = {mc_result.pct_5_max_dd:.3f} < {max_dd_limit}"
            )
    else:
        failures.append("MC: no OOS returns available for simulation")

    # ── 3. Deflated Sharpe Ratio ──────────────────────────────────────────
    # Eq. (2) is an in-search selection statistic. Its selected Sharpe,
    # selected-return moments, T, and cross-trial Sharpe variance must all be
    # measured from one full trial matrix. Do not mix a full-sample sweep
    # winner with the WFA OOS length used by Monte Carlo, or silently replace
    # the frozen selected candidate with another matrix column.
    num_trials_raw = len(sweep_results) if not sweep_results.empty else 0
    search_scope = dsr_search_scope or ""
    try:
        matrix = None if returns_matrix is None else np.asarray(returns_matrix, dtype=float)
    except (TypeError, ValueError):
        matrix = None
    input_error = _dsr_input_error(matrix, num_trials_raw, dsr_selected_trial_index, search_scope)
    if dsr_selection_error:
        dsr_result = _unavailable_dsr(num_trials_raw, search_scope, dsr_selection_error)
    elif input_error:
        dsr_result = _unavailable_dsr(num_trials_raw, search_scope, input_error)
    else:
        selected_returns = matrix[:, dsr_selected_trial_index]
        if dsr_selected_returns is not None and not np.array_equal(
            np.asarray(dsr_selected_returns, dtype=float), selected_returns
        ):
            dsr_result = compute_dsr(
                num_trials_raw=num_trials_raw,
                search_scope=search_scope,
            )
            dsr_result.unavailable_reason = (
                "dsr_selected_returns does not match dsr_selected_trial_index in returns_matrix"
            )
            dsr_result.failure_reasons = [f"DSR unavailable: {dsr_result.unavailable_reason}"]
        elif best_sharpe is not None and (
            dsr_sharpe_annualization_factor is None
            or dsr_sharpe_annualization_factor <= 0.0
            or not np.isclose(
                best_sharpe,
                (selected_returns.mean() / selected_returns.std(ddof=1))
                * np.sqrt(dsr_sharpe_annualization_factor),
                rtol=1e-8,
                atol=1e-10,
            )
        ):
            dsr_result = compute_dsr(
                num_trials_raw=num_trials_raw,
                search_scope=search_scope,
            )
            dsr_result.unavailable_reason = (
                "best_sharpe does not identify the selected DSR trial in the documented annualization unit"
            )
            dsr_result.failure_reasons = [f"DSR unavailable: {dsr_result.unavailable_reason}"]
        else:
            trial_volatility = matrix.std(axis=0, ddof=1)
            trial_sharpes = np.divide(
                matrix.mean(axis=0),
                trial_volatility,
                out=np.full(matrix.shape[1], np.nan),
                where=trial_volatility > 0.0,
            )
            dsr_result = compute_dsr(
                selected_returns=selected_returns,
                returns_matrix=matrix,
                trial_sharpe_variance=float(np.var(trial_sharpes, ddof=1)),
                num_trials_raw=num_trials_raw,
                search_scope=search_scope,
            )
    result.dsr_result = dsr_result
    if not dsr_result.passed:
        failures.extend([f"DSR: {reason}" for reason in dsr_result.failure_reasons])

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


def _unavailable_dsr(num_trials_raw: int, search_scope: str, reason: str) -> DSRResult:
    """Return an explicitly unavailable DSR result without inventing evidence."""
    result = compute_dsr(num_trials_raw=num_trials_raw, search_scope=search_scope)
    result.unavailable_reason = reason
    result.failure_reasons = [f"DSR unavailable: {reason}"]
    return result


def _dsr_input_error(
    matrix: np.ndarray | None,
    num_trials_raw: int,
    selected_trial_index: int | None,
    search_scope: str,
) -> str | None:
    """Validate identity evidence before indexing a trial matrix."""
    if not search_scope:
        return "DSR search_scope is required"
    if matrix is None:
        return "DSR requires a finite full returns_matrix"
    if matrix.ndim != 2 or matrix.shape[0] < 4 or not np.isfinite(matrix).all():
        return "DSR requires a finite (bars, trials) returns_matrix with at least four bars"
    if matrix.shape[1] != num_trials_raw:
        return "returns_matrix columns must cover exactly the documented raw trial count"
    if selected_trial_index is None:
        return "DSR requires an explicit selected trial index"
    if isinstance(selected_trial_index, bool) or not isinstance(selected_trial_index, (int, np.integer)):
        return "dsr_selected_trial_index must be a non-boolean integer"
    if not 0 <= selected_trial_index < num_trials_raw:
        return "dsr_selected_trial_index is outside the documented trial matrix"
    return None
