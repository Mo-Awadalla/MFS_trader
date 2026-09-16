"""Bailey--López de Prado Deflated Sharpe Ratio (DSR).

This implements Eq. (2) from Bailey & López de Prado (2014), pp. 8--10:
https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf

Sharpe values and their variance must use *per-observation*, non-annualized
units. For daily data with 250 observations/year, convert annualized Sharpe
``2.5`` to ``2.5 / sqrt(250)`` and annualized variance ``0.5`` to ``0.5 / 250``.
Skewness is dimensionless; kurtosis is ordinary, non-excess kurtosis (Normal=3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import e

import numpy as np
import pandas as pd
import structlog
from scipy import stats

log = structlog.get_logger(__name__)
_EULER_MASCHERONI = 0.5772156649015329
_METHODS = {"M_raw", "M_eff_corr", "M_cluster"}


@dataclass
class DSRResult:
    """Eq. (2) result; unavailable results are deliberately non-passing."""

    observed_sharpe: float
    num_trials_raw: int
    num_trials_eff: float | None
    num_trials_cluster: int | None
    track_record_length: int
    # Complementary tail probability. The paper's DSR is ``dsr_confidence``.
    dsr_pvalue: float
    dsr_statistic: float
    method: str
    dsr_confidence: float = 0.0
    formula_version: str = "bailey_lopez_de_prado_eq2_v1"
    expected_max_sharpe: float | None = None
    selected_return_skewness: float | None = None
    selected_return_kurtosis: float | None = None
    trial_sharpe_variance: float | None = None
    search_scope: str = ""
    available: bool = True
    unavailable_reason: str | None = None
    passed: bool = False
    pvalue_m_raw: float | None = None
    pvalue_m_eff: float | None = None
    pvalue_m_cluster: float | None = None
    failure_reasons: list[str] = field(default_factory=list)


def estimate_m_eff_corr(returns_matrix: np.ndarray | pd.DataFrame) -> float:
    """Estimate effective independent trials from a finite ``(bars, trials)`` matrix."""
    matrix = _as_returns_matrix(returns_matrix)
    if matrix.shape[1] < 2:
        return float(matrix.shape[1])
    corr = np.nan_to_num(np.corrcoef(matrix.T), nan=0.0)
    eigenvalues = np.maximum(np.linalg.eigvalsh(corr), 1e-10)
    return max(float(np.sum(eigenvalues) ** 2 / np.sum(eigenvalues**2)), 1.0)


def estimate_m_cluster(
    param_results: pd.DataFrame,
    param_columns: list[str],
    n_clusters: int | None = None,
) -> int:
    """Estimate a parameter-space cluster count for a documented sweep."""
    if param_results.empty or not param_columns:
        return 1
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    features = StandardScaler().fit_transform(param_results[param_columns].values)
    clusters = n_clusters or max(min(int(np.sqrt(len(param_results))), 20), 2)
    clusters = min(clusters, len(param_results))
    labels = KMeans(n_clusters=clusters, n_init=10, random_state=42).fit_predict(features)
    median = param_results["sharpe"].median()
    return max(len({int(label) for i, label in enumerate(labels) if param_results["sharpe"].iloc[i] >= median}), 1)


def expected_max_sharpe(trial_sharpe_variance: float, num_trials: float) -> float:
    """Eq. (1)'s null expected maximum, in per-observation Sharpe units."""
    if not np.isfinite(trial_sharpe_variance) or trial_sharpe_variance < 0.0:
        raise ValueError("trial_sharpe_variance must be finite and non-negative")
    if not np.isfinite(num_trials) or num_trials < 2.0:
        raise ValueError("num_trials must be finite and at least 2 for Eq. (1)")
    first = stats.norm.ppf(1.0 - 1.0 / num_trials)
    second = stats.norm.ppf(1.0 - 1.0 / (num_trials * e))
    return float(np.sqrt(trial_sharpe_variance) * ((1.0 - _EULER_MASCHERONI) * first + _EULER_MASCHERONI * second))


def compute_dsr(
    observed_sharpe: float | None = None,
    returns_matrix: np.ndarray | pd.DataFrame | None = None,
    num_trials_raw: int = 1,
    track_record_length: int | None = None,
    *,
    selected_returns: pd.Series | np.ndarray | None = None,
    trial_sharpe_variance: float | None = None,
    selected_return_skewness: float | None = None,
    selected_return_kurtosis: float | None = None,
    num_trials_cluster: int | None = None,
    search_scope: str | None = None,
    method: str = "M_eff_corr",
) -> DSRResult:
    """Compute Eq. (2), or return unavailable when required evidence is absent.

    Prefer ``selected_returns``: the per-observation Sharpe, skewness,
    ordinary kurtosis, and length are then calculated from one series. Scalar
    inputs are supported for reference examples only when all Eq. (2) inputs
    are explicit. ``trial_sharpe_variance`` is never inferred: it must describe
    the full documented search represented by ``num_trials_raw``.
    """
    if method not in _METHODS:
        return _unavailable(observed_sharpe, num_trials_raw, track_record_length, method, f"unknown DSR method {method!r}", search_scope)
    if not isinstance(search_scope, str) or not search_scope.strip():
        return _unavailable(observed_sharpe, num_trials_raw, track_record_length, method, "DSR search_scope is required; document which trials were searched", search_scope)
    if isinstance(num_trials_raw, bool) or not isinstance(num_trials_raw, (int, np.integer)) or num_trials_raw < 2:
        return _unavailable(observed_sharpe, num_trials_raw, track_record_length, method, "Eq. (1) requires at least two documented trials; a single trial cannot evidence DSR selection deflation", search_scope)
    if trial_sharpe_variance is None:
        return _unavailable(observed_sharpe, num_trials_raw, track_record_length, method, "trial_sharpe_variance across the documented trials is required", search_scope)

    selected = _selected_statistics(selected_returns, observed_sharpe, track_record_length, selected_return_skewness, selected_return_kurtosis)
    if isinstance(selected, str):
        return _unavailable(observed_sharpe, num_trials_raw, track_record_length, method, selected, search_scope)
    sharpe, T, skewness, kurtosis = selected
    if not np.isfinite(trial_sharpe_variance) or trial_sharpe_variance < 0.0:
        return _unavailable(sharpe, num_trials_raw, T, method, "trial_sharpe_variance must be finite and non-negative", search_scope)

    m_eff: float | None = None
    if returns_matrix is not None:
        try:
            matrix = _as_returns_matrix(returns_matrix)
        except ValueError as exc:
            return _unavailable(sharpe, num_trials_raw, T, method, str(exc), search_scope)
        if matrix.shape[1] != num_trials_raw:
            return _unavailable(sharpe, num_trials_raw, T, method, "returns_matrix columns must cover exactly num_trials_raw documented trials", search_scope)
        if matrix.shape[0] != T:
            return _unavailable(sharpe, num_trials_raw, T, method, "returns_matrix bars must match the selected track record length", search_scope)
        m_eff = estimate_m_eff_corr(matrix)

    if method == "M_eff_corr" and m_eff is None:
        return _unavailable(sharpe, num_trials_raw, T, method, "M_eff_corr requires a full returns_matrix for the documented trial scope", search_scope)
    if method == "M_eff_corr" and m_eff < 2.0:
        return _unavailable(sharpe, num_trials_raw, T, method, "M_eff_corr is below two; Eq. (1) has no no-selection benchmark", search_scope)
    if method == "M_cluster" and (
        isinstance(num_trials_cluster, bool)
        or not isinstance(num_trials_cluster, (int, np.integer))
        or num_trials_cluster < 2
        or num_trials_cluster > num_trials_raw
    ):
        return _unavailable(sharpe, num_trials_raw, T, method, "M_cluster requires an explicit cluster count of at least two", search_scope)

    try:
        confidence_raw, statistic_raw, threshold_raw = _eq2(
            sharpe, T, skewness, kurtosis, trial_sharpe_variance, float(num_trials_raw)
        )
    except ValueError as exc:
        return _unavailable(sharpe, num_trials_raw, T, method, str(exc), search_scope)
    confidence_eff = statistic_eff = threshold_eff = None
    # Eq. (1)'s extreme-value approximation has no N=1 form. A nearly
    # collinear matrix can legitimately estimate 1 <= M_eff < 2; it supports
    # neither an M_eff DSR nor an implicit PSR substitution. Raw DSR remains
    # well-defined and must not be made to fail because this optional estimate
    # is too small.
    if m_eff is not None and m_eff >= 2.0:
        try:
            confidence_eff, statistic_eff, threshold_eff = _eq2(
                sharpe, T, skewness, kurtosis, trial_sharpe_variance, m_eff
            )
        except ValueError as exc:
            return _unavailable(sharpe, num_trials_raw, T, method, str(exc), search_scope)
    confidence_cluster = statistic_cluster = threshold_cluster = None
    if num_trials_cluster is not None and 2 <= num_trials_cluster <= num_trials_raw:
        try:
            confidence_cluster, statistic_cluster, threshold_cluster = _eq2(
                sharpe, T, skewness, kurtosis, trial_sharpe_variance, float(num_trials_cluster)
            )
        except ValueError as exc:
            return _unavailable(sharpe, num_trials_raw, T, method, str(exc), search_scope)

    if method == "M_raw":
        confidence, statistic, threshold = confidence_raw, statistic_raw, threshold_raw
    elif method == "M_eff_corr":
        assert confidence_eff is not None and statistic_eff is not None and threshold_eff is not None
        confidence, statistic, threshold = confidence_eff, statistic_eff, threshold_eff
    else:
        assert confidence_cluster is not None and statistic_cluster is not None and threshold_cluster is not None
        confidence, statistic, threshold = confidence_cluster, statistic_cluster, threshold_cluster

    pvalue_raw = float(stats.norm.sf(statistic_raw))
    pvalue_eff = None if statistic_eff is None else float(stats.norm.sf(statistic_eff))
    pvalue_cluster = None if statistic_cluster is None else float(stats.norm.sf(statistic_cluster))
    pvalue = float(stats.norm.sf(statistic))
    # The existing 0.05 / 0.10 numeric gates are unchanged, just expressed as
    # the complement of the paper's confidence statistic.
    passed = pvalue < 0.05 and pvalue_raw < 0.10
    failures: list[str] = []
    if pvalue >= 0.05:
        failures.append(f"DSR confidence ({method}) = {confidence:.4f} <= 0.9500")
    if pvalue_raw >= 0.10:
        failures.append(f"DSR confidence under M_raw = {confidence_raw:.4f} <= 0.9000")

    log.info("dsr_eq2", method=method, search_scope=search_scope, m_raw=num_trials_raw, m_eff=m_eff, observed_sharpe=sharpe, T=T, trial_sharpe_variance=trial_sharpe_variance, confidence=confidence)
    return DSRResult(
        observed_sharpe=sharpe, num_trials_raw=num_trials_raw, num_trials_eff=m_eff,
        num_trials_cluster=num_trials_cluster, track_record_length=T, dsr_pvalue=pvalue,
        dsr_statistic=statistic, method=method, dsr_confidence=confidence,
        expected_max_sharpe=threshold, selected_return_skewness=skewness,
        selected_return_kurtosis=kurtosis, trial_sharpe_variance=float(trial_sharpe_variance),
        search_scope=search_scope, passed=passed, pvalue_m_raw=pvalue_raw,
        pvalue_m_eff=pvalue_eff, pvalue_m_cluster=pvalue_cluster, failure_reasons=failures,
    )


def _selected_statistics(selected_returns: pd.Series | np.ndarray | None, observed_sharpe: float | None, track_record_length: int | None, skewness: float | None, kurtosis: float | None) -> tuple[float, int, float, float] | str:
    if selected_returns is not None:
        values = np.asarray(selected_returns, dtype=float)
        if values.ndim != 1:
            return "selected_returns must be a one-dimensional return series"
        if len(values) < 4 or not np.isfinite(values).all():
            return "selected_returns must contain at least four finite per-observation returns"
        if track_record_length is not None and track_record_length != len(values):
            return "track_record_length must equal len(selected_returns)"
        volatility = float(np.std(values, ddof=1))
        if volatility <= 0.0:
            return "selected_returns must have positive sample volatility"
        sharpe = float(np.mean(values) / volatility)
        if observed_sharpe is not None and not np.isclose(observed_sharpe, sharpe, rtol=1e-12, atol=1e-12):
            return "observed_sharpe must match selected_returns in the same per-observation unit"
        return sharpe, len(values), float(stats.skew(values, bias=False)), float(stats.kurtosis(values, fisher=False, bias=False))
    if observed_sharpe is None or track_record_length is None or skewness is None or kurtosis is None:
        return "provide selected_returns, or observed_sharpe, track_record_length, selected_return_skewness, and selected_return_kurtosis"
    if (
        isinstance(track_record_length, bool)
        or not isinstance(track_record_length, (int, np.integer))
        or track_record_length <= 1
        or not all(np.isfinite(value) for value in (observed_sharpe, skewness, kurtosis))
    ):
        return "scalar Eq. (2) inputs must be finite and track_record_length must exceed one"
    if kurtosis < 1.0:
        return "selected_return_kurtosis must be ordinary (non-excess) kurtosis and at least one"
    return float(observed_sharpe), track_record_length, float(skewness), float(kurtosis)


def _eq2(sharpe: float, T: int, skewness: float, kurtosis: float, variance: float, num_trials: float) -> tuple[float, float, float]:
    threshold = expected_max_sharpe(variance, num_trials)
    denominator_squared = 1.0 - skewness * sharpe + ((kurtosis - 1.0) / 4.0) * sharpe**2
    if denominator_squared <= 0.0 or not np.isfinite(denominator_squared):
        raise ValueError("Eq. (2) standard-error denominator is not positive and finite")
    statistic = float((sharpe - threshold) * np.sqrt(T - 1.0) / np.sqrt(denominator_squared))
    return float(stats.norm.cdf(statistic)), statistic, threshold


def _unavailable(observed_sharpe: float | None, num_trials_raw: int, track_record_length: int | None, method: str, reason: str, search_scope: str | None) -> DSRResult:
    return DSRResult(
        observed_sharpe=0.0 if observed_sharpe is None else float(observed_sharpe),
        num_trials_raw=num_trials_raw, num_trials_eff=None, num_trials_cluster=None,
        track_record_length=track_record_length or 0, dsr_pvalue=1.0, dsr_statistic=0.0,
        method=method, search_scope=search_scope or "", available=False,
        unavailable_reason=reason, passed=False, failure_reasons=[f"DSR unavailable: {reason}"],
    )


def _as_returns_matrix(returns_matrix: np.ndarray | pd.DataFrame) -> np.ndarray:
    matrix = returns_matrix.to_numpy(dtype=float) if isinstance(returns_matrix, pd.DataFrame) else np.asarray(returns_matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] < 4 or matrix.shape[1] < 1:
        raise ValueError("returns_matrix must be a finite (bars, trials) matrix with at least four bars")
    if not np.isfinite(matrix).all():
        raise ValueError("returns_matrix must contain only finite values")
    return matrix
