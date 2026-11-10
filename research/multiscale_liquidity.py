"""Pure measurements used by the multiscale liquidity hypothesis batch."""

from __future__ import annotations

import numpy as np


def norm_ratios(values: np.ndarray) -> dict[str, float]:
    """Return mean-normalized Lp/L2 ratios for a nonnegative local field."""
    values = np.asarray(values, dtype=float)
    rms = float(np.sqrt(np.mean(values**2)))
    if rms <= 0:
        return {"l4_l2": 0.0, "l8_l2": 0.0, "l16_l2": 0.0, "linf_l2": 0.0}
    return {
        "l4_l2": float(np.mean(values**4) ** 0.25 / rms),
        "l8_l2": float(np.mean(values**8) ** 0.125 / rms),
        "l16_l2": float(np.mean(values**16) ** 0.0625 / rms),
        "linf_l2": float(np.max(values) / rms),
    }


def normalized_profile(positions: np.ndarray, amounts: np.ndarray) -> np.ndarray:
    """Interpolate a depth profile after width and amplitude normalization."""
    order = np.argsort(positions)
    x = np.asarray(positions, dtype=float)[order]
    y = np.asarray(amounts, dtype=float)[order]
    total = max(float(y.sum()), 1e-12)
    y = y / total
    width = max(float(np.sqrt(np.sum(y * x**2))), 1e-12)
    x = x / width
    grid = np.linspace(-3.0, 3.0, 41)
    return np.interp(grid, x, y, left=0.0, right=0.0)


def power_law_fit(values: np.ndarray, step_seconds: float = 10.0) -> dict[str, float]:
    """Fit a trailing series to A(T-t)^(-alpha) over fixed prospective times."""
    values = np.asarray(values, dtype=float)
    valid = np.isfinite(values) & (values > 0)
    if valid.sum() < 10:
        return {"power_alpha": 0.0, "power_r2": 0.0, "critical_seconds": 300.0, "critical_score": 0.0}
    age = np.arange(len(values) - 1, -1, -1, dtype=float) * step_seconds
    y = np.log(values[valid])
    best = (-np.inf, 0.0, 300.0)
    for critical in (10.0, 20.0, 30.0, 60.0, 120.0, 300.0):
        x = -np.log(critical + age[valid])
        slope, intercept = np.polyfit(x, y, 1)
        fitted = intercept + slope * x
        denominator = float(np.sum((y - y.mean()) ** 2))
        r2 = 1.0 - float(np.sum((y - fitted) ** 2)) / max(denominator, 1e-12)
        if slope > 0 and r2 > best[0]:
            best = (r2, float(slope), critical)
    if not np.isfinite(best[0]):
        return {"power_alpha": 0.0, "power_r2": 0.0, "critical_seconds": 300.0, "critical_score": 0.0}
    r2, alpha, critical = best
    return {
        "power_alpha": alpha,
        "power_r2": float(r2),
        "critical_seconds": critical,
        "critical_score": float(alpha * max(r2, 0.0) / critical),
    }


def haar_energy_ratio(values: np.ndarray) -> float:
    """Return fine-scale versus coarse-scale energy from a Haar decomposition."""
    current = np.asarray(values, dtype=float)
    current = current - np.mean(current)
    energies = []
    while len(current) >= 2:
        if len(current) % 2:
            current = current[1:]
        detail = (current[0::2] - current[1::2]) / np.sqrt(2.0)
        energies.append(float(np.sum(detail**2)))
        current = (current[0::2] + current[1::2]) / np.sqrt(2.0)
    if len(energies) < 4:
        return 0.0
    return float(sum(energies[:3]) / max(sum(energies[3:]), 1e-12))


def multifractal_width(values: np.ndarray) -> float:
    """Estimate a compact generalized-scaling-width proxy at q=1 and q=4."""
    values = np.asarray(values, dtype=float)
    scales = np.asarray([1, 2, 4, 8], dtype=float)
    zeta = []
    for q in (1.0, 4.0):
        moments = []
        for scale in scales.astype(int):
            size = len(values) // scale
            aggregated = values[-size * scale :].reshape(size, scale).sum(axis=1)
            moments.append(max(float(np.mean(np.abs(aggregated) ** q)), 1e-18))
        zeta.append(float(np.polyfit(np.log(scales), np.log(moments), 1)[0] / q))
    return abs(zeta[0] - zeta[1])
