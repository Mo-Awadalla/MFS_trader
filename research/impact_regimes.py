"""Causally aligned rolling measurements for state-dependent market impact."""

from __future__ import annotations

import numpy as np
import pandas as pd


def log_impact_fit(log_participation: np.ndarray, log_impact: np.ndarray) -> tuple[float, float]:
    """Return linear exponent and quadratic curvature for a log impact curve."""
    x = np.asarray(log_participation, dtype=float)
    y = np.asarray(log_impact, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    if valid.sum() < 10 or float(np.std(x[valid])) < 1e-12:
        return 0.0, 0.0
    linear = float(np.polyfit(x[valid], y[valid], 1)[0])
    quadratic = float(np.polyfit(x[valid], y[valid], 2)[0])
    return linear, quadratic


def impact_features(
    midpoint: pd.Series,
    signed_volume: pd.Series,
    gross_volume: pd.Series,
    prior_stress: pd.Series,
    window: int = 30,
    horizon: int = 6,
) -> pd.DataFrame:
    """Build rolling impact exponent, convexity, susceptibility, and permanence."""
    returns = np.log(midpoint).diff() * 10_000.0
    scale = gross_volume.rolling(window, min_periods=10).median().clip(lower=1e-6)
    participation = signed_volume.abs() / scale
    log_q = np.log(participation.clip(lower=1e-6))
    log_i = np.log(returns.abs().add(0.01))
    exponent = np.full(len(midpoint), np.nan)
    convexity = np.full(len(midpoint), np.nan)
    for index in range(len(midpoint)):
        start = max(0, index - window + 1)
        exponent[index], convexity[index] = log_impact_fit(
            log_q.iloc[start : index + 1].to_numpy(),
            log_i.iloc[start : index + 1].to_numpy(),
        )
    aligned_impact = returns * np.sign(signed_volume)
    future_return = np.log(midpoint.shift(-horizon) / midpoint) * 10_000.0
    episode_permanence = (future_return * np.sign(signed_volume) / aligned_impact.abs().clip(lower=0.05)).clip(-2.0, 2.0)
    known_permanence = episode_permanence.shift(horizon).rolling(window, min_periods=10).median()
    result = pd.DataFrame(index=midpoint.index)
    result["participation"] = participation
    result["prior_stress"] = prior_stress
    result["impact_susceptibility"] = returns.abs() / np.sqrt(participation.clip(lower=1e-6))
    result["rolling_impact_exponent"] = exponent
    result["rolling_impact_convexity"] = convexity
    result["impact_exponent_change_60s"] = result["rolling_impact_exponent"].diff(horizon)
    result["known_permanence_5m"] = known_permanence
    result["stress_flow_interaction"] = prior_stress * signed_volume.abs()
    result["episode_permanence"] = episode_permanence
    result["immediate_aligned_impact"] = aligned_impact
    return result.replace([np.inf, -np.inf], np.nan)
