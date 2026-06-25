"""Deflated Sharpe Ratio (DSR).

Answers: "Given the number of trials/strategies/parameters tested,
what's the probability the best Sharpe is just luck?"

Three methods to estimate M (number of independent trials):
  (A) M_raw:        count all parameter combos in the sweep (conservative upper bound)
  (B) M_eff_corr:   use correlation/eigenvalue structure of strategy returns
  (C) M_cluster:    cluster parameter space, count distinct regions (interpretability)

Primary: B. Conservative upper bound: A. Interpretability check: C.

Reference: Bailey & López de Prado, "The Deflated Sharpe Ratio" (2014).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import structlog
from scipy import stats

log = structlog.get_logger(__name__)


@dataclass
class DSRResult:
    """Results of a Deflated Sharpe Ratio calculation."""

    observed_sharpe: float
    num_trials_raw: int  # M_raw — total parameter combos
    num_trials_eff: float  # M_eff — effective independent trials
    num_trials_cluster: int  # M_cluster — distinct parameter regions
    track_record_length: int  # T (in bars)
    dsr_pvalue: float  # p-value: probability this Sharpe is luck
    dsr_statistic: float  # the deflated Sharpe ratio statistic
    method: str  # which M estimation method was primary
    passed: bool = False
    pvalue_m_raw: float = 0.0  # p-value using M_raw (conservative)
    pvalue_m_eff: float = 0.0  # p-value using M_eff_corr (primary)
    pvalue_m_cluster: float = 0.0  # p-value using M_cluster
    failure_reasons: list[str] = field(default_factory=list)


def estimate_m_eff_corr(returns_matrix: np.ndarray | pd.DataFrame) -> float:
    """Estimate effective number of independent trials from correlation structure.

    Uses the eigenvalue method: M_eff = (sum(eigenvalues))^2 / sum(eigenvalues^2)

    This is the "participation ratio" — effectively the number of independent
    dimensions in the strategy returns matrix.

    Args:
        returns_matrix: Array of shape (n_bars, n_trials) where each column is
                        the return series of one parameter combination.

    Returns:
        M_eff — effective number of independent trials (float).
    """
    if isinstance(returns_matrix, pd.DataFrame):
        returns_matrix = returns_matrix.values

    if returns_matrix.size == 0 or returns_matrix.shape[1] < 2:
        return float(returns_matrix.shape[1])

    # Compute correlation matrix of strategy returns across parameter combos
    # Each column is a strategy variant's returns
    corr = np.corrcoef(returns_matrix.T)  # shape (n_trials, n_trials)

    # Handle NaN correlations (constant returns)
    corr = np.nan_to_num(corr, nan=0.0)

    # Eigenvalue method: participation ratio
    eigenvalues = np.linalg.eigvalsh(corr)
    eigenvalues = np.maximum(eigenvalues, 1e-10)  # avoid division by zero

    m_eff = float(np.sum(eigenvalues) ** 2 / np.sum(eigenvalues**2))

    return max(m_eff, 1.0)


def estimate_m_cluster(
    param_results: pd.DataFrame,
    param_columns: list[str],
    n_clusters: int | None = None,
) -> int:
    """Estimate M by clustering the parameter space.

    Groups parameter combinations into distinct regions and counts clusters
    that contain at least one "good" result (above median Sharpe).

    Args:
        param_results: DataFrame with parameter columns and a 'sharpe' column.
        param_columns: Columns to use for clustering.
        n_clusters: Number of clusters (auto-determined if None).

    Returns:
        M_cluster — number of distinct parameter regions.
    """
    if param_results.empty or not param_columns:
        return 1

    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    features = param_results[param_columns].values
    scaler = StandardScaler()
    features_scaled = scaler.fit_transform(features)

    if n_clusters is None:
        # Heuristic: sqrt(n_samples) clusters, capped at 20
        n_clusters = min(int(np.sqrt(len(param_results))), 20)
        n_clusters = max(n_clusters, 2)

    if len(param_results) < n_clusters:
        n_clusters = len(param_results)

    km = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
    labels = km.fit_predict(features_scaled)

    # Count clusters that have at least one above-median result
    median_sharpe = param_results["sharpe"].median()
    good_clusters = set()
    for i, label in enumerate(labels):
        if param_results["sharpe"].iloc[i] >= median_sharpe:
            good_clusters.add(int(label))

    return max(len(good_clusters), 1)


def compute_dsr(
    observed_sharpe: float,
    returns_matrix: np.ndarray | pd.DataFrame | None,
    num_trials_raw: int,
    track_record_length: int,
    *,
    num_trials_cluster: int | None = None,
    ann_factor: int = 252,
    method: str = "M_eff_corr",
) -> DSRResult:
    """Compute the Deflated Sharpe Ratio.

    Args:
        observed_sharpe: The best observed (annualized) Sharpe ratio.
        returns_matrix: Array (n_bars, n_trials) for M_eff estimation.
        num_trials_raw: M_raw — total number of parameter combinations tested.
        track_record_length: T — number of bars in the track record.
        num_trials_cluster: M_cluster — distinct parameter regions.
        ann_factor: Annualization factor (252 for daily).
        method: Primary method for p-value ("M_eff_corr", "M_raw", or "M_cluster").

    Returns:
        DSRResult with p-values for all three methods.
    """
    # Estimate M_eff from correlation structure
    if returns_matrix is not None:
        m_eff = estimate_m_eff_corr(returns_matrix)
    else:
        m_eff = float(num_trials_raw)

    m_cluster = num_trials_cluster or int(m_eff)

    log.info(
        "dsr_estimates",
        m_raw=num_trials_raw,
        m_eff=m_eff,
        m_cluster=m_cluster,
        observed_sharpe=observed_sharpe,
        T=track_record_length,
    )

    # Compute p-values for all three methods
    pval_raw = _dsr_pvalue(observed_sharpe, num_trials_raw, track_record_length, ann_factor)
    pval_eff = _dsr_pvalue(observed_sharpe, m_eff, track_record_length, ann_factor)
    pval_cluster = _dsr_pvalue(observed_sharpe, m_cluster, track_record_length, ann_factor)

    # Select primary p-value
    if method == "M_raw":
        primary_pval = pval_raw
    elif method == "M_cluster":
        primary_pval = pval_cluster
    else:  # M_eff_corr (default)
        primary_pval = pval_eff

    # DSR statistic (z-score of the deflated Sharpe)
    dsr_stat = _dsr_statistic(observed_sharpe, m_eff, track_record_length, ann_factor)

    # Pass if p < 0.05 using primary method, and doesn't collapse under M_raw
    passed = primary_pval < 0.05 and pval_raw < 0.10  # M_raw is a sanity check

    failures: list[str] = []
    if primary_pval >= 0.05:
        failures.append(f"DSR p-value ({method}) = {primary_pval:.4f} >= 0.05")
    if pval_raw >= 0.10:
        failures.append(f"DSR collapses under M_raw: p = {pval_raw:.4f} >= 0.10")

    return DSRResult(
        observed_sharpe=observed_sharpe,
        num_trials_raw=num_trials_raw,
        num_trials_eff=m_eff,
        num_trials_cluster=m_cluster,
        track_record_length=track_record_length,
        dsr_pvalue=primary_pval,
        dsr_statistic=dsr_stat,
        method=method,
        passed=passed,
        pvalue_m_raw=pval_raw,
        pvalue_m_eff=pval_eff,
        pvalue_m_cluster=pval_cluster,
        failure_reasons=failures,
    )


def _dsr_pvalue(sharpe: float, m: float, T: int, ann_factor: int = 252) -> float:
    """Compute the DSR p-value for a given M and T.

    Under the null hypothesis, the expected maximum Sharpe across M independent
    trials is approximately:

        E[max Sharpe] = sqrt(2 * ln(M)) / sqrt(ann_factor)

    The p-value is the probability of observing a Sharpe >= observed under the null.
    """
    if T <= 1 or m <= 0:
        return 1.0

    # Expected max Sharpe under null (Bailey & López de Prado)
    # The non-NaN variance of Sharpe estimator is (1 - skewness*sharpe + ...) / (T-1)
    # Simplified: variance of Sharpe ~ 1/(T-1) * (1 + sharpe^2/2) for normal returns
    # But for the DSR, we use the expected max under multiple testing

    # Standard error of Sharpe: SE = 1/sqrt(T) (annualized)
    # With annualization: SE_annual = sqrt(ann_factor / T)
    se_sharpe = np.sqrt(ann_factor / T)

    # Expected max Sharpe under M trials (extreme value distribution)
    if m > 1:
        expected_max = np.sqrt(2 * np.log(m)) * se_sharpe
        # Variance of max also scales
        se_max = np.pi / np.sqrt(6) * se_sharpe / np.sqrt(2 * np.log(m)) if m > 1 else se_sharpe
    else:
        expected_max = 0.0
        se_max = se_sharpe

    # Deflated Sharpe: how many std devs above the expected max?
    z = (sharpe - expected_max) / se_max if se_max > 0 else 0.0

    # One-sided p-value
    pvalue = 1.0 - stats.norm.cdf(z)
    return float(pvalue)


def _dsr_statistic(sharpe: float, m: float, T: int, ann_factor: int = 252) -> float:
    """Compute the DSR z-statistic (not the p-value)."""
    se_sharpe = np.sqrt(ann_factor / T)
    if m > 1:
        expected_max = np.sqrt(2 * np.log(m)) * se_sharpe
        se_max = np.pi / np.sqrt(6) * se_sharpe / np.sqrt(2 * np.log(m))
    else:
        expected_max = 0.0
        se_max = se_sharpe

    if se_max > 0:
        return float((sharpe - expected_max) / se_max)
    return 0.0
