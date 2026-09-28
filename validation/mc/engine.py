"""Monte Carlo simulation — block-bootstrap + parameter perturbation.

Generates 10k paths to measure:
  - terminal wealth distribution
  - Sharpe/Sortino distribution
  - max drawdown distribution
  - probability of loss
  - probability of ruin

Two randomization modes:
  (A) block-bootstrap: resample blocks of daily returns (preserves autocorrelation)
  (B) parameter perturbation: perturb strategy params within stable region and re-run

Mode (D) = both: block-bootstrap path randomness + parameter perturbation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger(__name__)

DEFAULT_BLOCK_SIZE = 20  # 20-day blocks for daily bars
DEFAULT_NUM_PATHS = 10000
DEFAULT_SEED = 42
DEFAULT_PERIODS_PER_YEAR = 252.0
# v2: starting capital is part of the running peak, the drawdown tail is the
# adverse signed 5th percentile, the final block start is sampled, and invalid
# inputs produce an explicit unavailable result instead of favorable zeros.
MC_FORMULA_VERSION = "mc_block_bootstrap_v2"


@dataclass
class MCResult:
    """Results of a Monte Carlo simulation."""

    num_paths: int
    block_size: int
    seed: int
    terminal_wealth: np.ndarray = field(default_factory=lambda: np.array([]))
    sharpes: np.ndarray = field(default_factory=lambda: np.array([]))
    sortinos: np.ndarray = field(default_factory=lambda: np.array([]))
    max_drawdowns: np.ndarray = field(default_factory=lambda: np.array([]))
    cagrs: np.ndarray = field(default_factory=lambda: np.array([]))
    observation_count: int = 0  # Returns per path; the annualization length
    periods_per_year: float = DEFAULT_PERIODS_PER_YEAR
    formula_version: str = MC_FORMULA_VERSION
    available: bool = True
    unavailable_reason: str | None = None

    # Summary statistics
    prob_loss: float = 0.0  # P(terminal wealth < initial)
    prob_ruin: float = 0.0  # P(max drawdown < ruin_threshold)
    pct_5_cagr: float = 0.0  # 5th percentile CAGR
    pct_5_max_dd: float = 0.0  # Adverse signed 5th-percentile maximum drawdown
    pct_5_sharpe: float = 0.0
    pct_95_sharpe: float = 0.0
    mean_sharpe: float = 0.0
    median_sharpe: float = 0.0
    prob_positive_sharpe: float = 0.0

    def summarize(self, *, initial_capital: float, ruin_threshold: float = -0.50) -> dict[str, float]:
        """Compute summary statistics from the simulated paths."""
        if not self.available:
            return {}
        if not np.isfinite(initial_capital) or initial_capital <= 0:
            raise ValueError("initial_capital must be finite and positive")
        if not np.isfinite(ruin_threshold) or not -1.0 < ruin_threshold < 0.0:
            raise ValueError("ruin_threshold must be a drawdown fraction in (-1, 0)")
        distributions = (
            self.terminal_wealth, self.sharpes, self.sortinos, self.max_drawdowns, self.cagrs
        )
        if self.num_paths <= 0 or any(
            values.ndim != 1 or len(values) != self.num_paths or not np.isfinite(values).all()
            for values in distributions
        ):
            self.available = False
            self.unavailable_reason = "path distributions must contain one finite metric per path"
            return {}

        self.prob_loss = float(np.mean(self.terminal_wealth < initial_capital))
        self.prob_ruin = float(np.mean(self.max_drawdowns < ruin_threshold))
        self.pct_5_cagr = float(np.percentile(self.cagrs, 5))
        self.pct_5_max_dd = float(np.percentile(self.max_drawdowns, 5))
        self.pct_5_sharpe = float(np.percentile(self.sharpes, 5))
        self.pct_95_sharpe = float(np.percentile(self.sharpes, 95))
        self.mean_sharpe = float(np.mean(self.sharpes))
        self.median_sharpe = float(np.median(self.sharpes))
        self.prob_positive_sharpe = float(np.mean(self.sharpes > 0))

        return {
            "num_paths": self.num_paths,
            "block_size": self.block_size,
            "prob_loss": self.prob_loss,
            "prob_ruin": self.prob_ruin,
            "prob_positive_sharpe": self.prob_positive_sharpe,
            "mean_sharpe": self.mean_sharpe,
            "median_sharpe": self.median_sharpe,
            "pct_5_sharpe": self.pct_5_sharpe,
            "pct_95_sharpe": self.pct_95_sharpe,
            "pct_5_cagr": self.pct_5_cagr,
            "pct_5_max_dd": self.pct_5_max_dd,
        }


def block_bootstrap_returns(
    returns: pd.Series,
    num_paths: int,
    block_size: int = DEFAULT_BLOCK_SIZE,
    seed: int = DEFAULT_SEED,
) -> np.ndarray:
    """Generate block-bootstrapped return paths.

    Args:
        returns: Original daily return series.
        num_paths: Number of bootstrap paths to generate.
        block_size: Block size in bars (20 for daily = ~1 month).
        seed: Random seed for reproducibility.

    Returns:
        Array of shape (num_paths, len(returns)) with bootstrapped returns.
    """
    if isinstance(block_size, bool) or not isinstance(block_size, (int, np.integer)) or block_size <= 0:
        raise ValueError("block_size must be a positive integer")
    if isinstance(num_paths, bool) or not isinstance(num_paths, (int, np.integer)) or num_paths <= 0:
        raise ValueError("num_paths must be a positive integer")

    rng = np.random.default_rng(seed)
    n = len(returns)
    if n < block_size:
        raise ValueError("block_size cannot exceed the number of returns")

    rets = np.asarray(returns, dtype=float)
    error = _input_error(rets, 1.0, DEFAULT_PERIODS_PER_YEAR)
    if error:
        raise ValueError(error)
    num_blocks = int(np.ceil(n / block_size))

    paths = np.empty((num_paths, n))
    for p in range(num_paths):
        # Sample block start indices
        block_starts = rng.integers(0, n - block_size + 1, size=num_blocks)
        # Concatenate blocks
        sampled = np.concatenate([rets[s : s + block_size] for s in block_starts])[:n]
        paths[p] = sampled

    return paths


def compute_path_metrics(
    returns: np.ndarray,
    initial_capital: float = 10000.0,
    ann_factor: float = DEFAULT_PERIODS_PER_YEAR,
) -> dict[str, float]:
    """Compute terminal wealth, Sharpe, Sortino, max DD, CAGR for one path.

    Uses the same definitions as the vectorized ``run_monte_carlo`` path.
    """
    returns = np.asarray(returns, dtype=float)
    error = _input_error(returns, initial_capital, ann_factor)
    if error:
        raise ValueError(error)
    equity = initial_capital * np.concatenate(([1.0], np.cumprod(1 + returns)))
    terminal_wealth = float(equity[-1])

    # Sharpe
    ann_return = float(np.mean(returns) * ann_factor)
    ann_vol = float(np.std(returns) * np.sqrt(ann_factor))
    sharpe = ann_return / ann_vol if ann_vol > 0 else 0.0

    # Sortino: downside deviation over every observation (non-negative -> 0).
    downside_std = float(np.std(np.where(returns < 0, returns, 0.0)))
    sortino = ann_return / (downside_std * np.sqrt(ann_factor)) if downside_std > 0 and ann_vol > 0 else 0.0

    # Max drawdown
    cummax = np.maximum.accumulate(equity)
    drawdown = (equity - cummax) / cummax
    max_dd = float(np.min(drawdown))

    # CAGR over the actual number of return observations.
    years = len(returns) / ann_factor
    cagr = float(np.power(terminal_wealth / initial_capital, 1 / years) - 1)
    if not np.isfinite([terminal_wealth, sharpe, sortino, max_dd, cagr]).all():
        raise ValueError("path metrics exceed finite numeric range")

    return {
        "terminal_wealth": terminal_wealth,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_dd,
        "cagr": cagr,
    }


def run_monte_carlo(
    returns: pd.Series,
    *,
    num_paths: int = DEFAULT_NUM_PATHS,
    block_size: int = DEFAULT_BLOCK_SIZE,
    initial_capital: float = 10000.0,
    ruin_threshold: float = -0.50,
    seed: int = DEFAULT_SEED,
    periods_per_year: float = DEFAULT_PERIODS_PER_YEAR,
) -> MCResult:
    """Run block-bootstrap Monte Carlo simulation on a return series.

    Args:
        returns: Strategy per-period returns (out-of-sample preferred).
        num_paths: Number of bootstrap paths (default 10k).
        block_size: Block size in bars (default 20).
        initial_capital: Starting capital for path simulation.
        ruin_threshold: Drawdown threshold for "ruin" (default -50%).
        seed: Random seed.
        periods_per_year: Return observations per year (252 for daily bars).

    Returns:
        MCResult with distributions and summary statistics. Configuration
        errors raise ``ValueError``; unusable return data yields
        ``available=False`` with a reason, never favorable default metrics.
    """
    if isinstance(num_paths, bool) or not isinstance(num_paths, (int, np.integer)) or num_paths <= 0:
        raise ValueError("num_paths must be a positive integer")
    if isinstance(block_size, bool) or not isinstance(block_size, (int, np.integer)) or block_size <= 0:
        raise ValueError("block_size must be a positive integer")
    if not np.isfinite(initial_capital) or initial_capital <= 0:
        raise ValueError("initial_capital must be finite and positive")
    if not np.isfinite(ruin_threshold) or not -1.0 < ruin_threshold < 0.0:
        raise ValueError("ruin_threshold must be a drawdown fraction in (-1, 0)")
    if not np.isfinite(periods_per_year) or periods_per_year <= 0:
        raise ValueError("periods_per_year must be finite and positive")

    try:
        values = np.asarray(returns, dtype=float)
        reason = _input_error(values, initial_capital, periods_per_year)
    except (TypeError, ValueError):
        values = np.array([], dtype=float)
        reason = "Monte Carlo requires numeric simple returns"
    if reason is None and len(values) < block_size:
        reason = f"{len(values)} returns cannot fill one {block_size}-bar bootstrap block"
    if reason is not None:
        count = len(values) if values.ndim == 1 else 0
        log.warning("mc_unavailable", bars=count, block_size=block_size, reason=reason)
        return MCResult(
            num_paths=0,
            block_size=block_size,
            seed=seed,
            observation_count=count,
            periods_per_year=float(periods_per_year),
            available=False,
            unavailable_reason=reason,
        )

    log.info("mc_starting", paths=num_paths, block_size=block_size, bars=len(returns))

    # Generate block-bootstrap paths
    paths = block_bootstrap_returns(returns, num_paths, block_size, seed)

    # Compute metrics for each path (vectorized where possible)
    ann_factor = float(periods_per_year)
    equity = initial_capital * np.concatenate(
        (np.ones((num_paths, 1)), np.cumprod(1 + paths, axis=1)), axis=1
    )
    terminal_wealth = equity[:, -1]

    # Sharpe per path (vectorized)
    path_means = np.mean(paths, axis=1)
    path_stds = np.std(paths, axis=1)
    sharpes = np.zeros_like(path_means)
    np.divide(
        path_means * ann_factor,
        path_stds * np.sqrt(ann_factor),
        out=sharpes,
        where=path_stds > 0,
    )

    # Sortino per path
    downside_only = np.where(paths < 0, paths, 0.0)
    downside_stds = np.std(downside_only, axis=1)
    sortinos = np.zeros_like(path_means)
    valid_sortino = (downside_stds > 0) & (path_stds > 0)
    np.divide(
        path_means * ann_factor,
        downside_stds * np.sqrt(ann_factor),
        out=sortinos,
        where=valid_sortino,
    )

    # Max drawdown per path (vectorized)
    cummax = np.maximum.accumulate(equity, axis=1)
    drawdowns = (equity - cummax) / cummax
    max_drawdowns = np.min(drawdowns, axis=1)

    # CAGR per path over the actual number of return observations.
    years = paths.shape[1] / ann_factor
    cagrs = (terminal_wealth / initial_capital) ** (1 / years) - 1

    result = MCResult(
        num_paths=num_paths,
        block_size=block_size,
        seed=seed,
        terminal_wealth=terminal_wealth,
        sharpes=sharpes,
        sortinos=sortinos,
        max_drawdowns=max_drawdowns,
        cagrs=cagrs,
        observation_count=paths.shape[1],
        periods_per_year=ann_factor,
    )
    result.summarize(initial_capital=initial_capital, ruin_threshold=ruin_threshold)

    log.info(
        "mc_complete",
        prob_loss=result.prob_loss,
        prob_ruin=result.prob_ruin,
        pct_5_cagr=result.pct_5_cagr,
        pct_5_max_dd=result.pct_5_max_dd,
        mean_sharpe=result.mean_sharpe,
    )

    return result


def _input_error(returns: np.ndarray, initial_capital: float, periods_per_year: float) -> str | None:
    """Explain why a return series cannot produce honest path metrics."""
    if returns.ndim != 1 or len(returns) == 0:
        return "Monte Carlo requires a non-empty one-dimensional return series"
    if not np.isfinite(returns).all():
        return "Monte Carlo returns must all be finite (NaN/inf present)"
    if (returns < -1.0).any():
        return "Monte Carlo returns below -100% are not valid simple returns"
    if not np.isfinite(initial_capital) or initial_capital <= 0:
        return "initial_capital must be finite and positive"
    if not np.isfinite(periods_per_year) or periods_per_year <= 0:
        return "periods_per_year must be finite and positive"
    return None


def run_parameter_perturbation(
    df: pd.DataFrame,
    backtest_fn: Callable[[pd.DataFrame, dict[str, Any]], pd.Series],
    base_params: dict[str, Any],
    perturbation_ranges: dict[str, tuple[float, float]],
    *,
    num_paths: int = 1000,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Perturb strategy parameters and re-run backtests.

    Args:
        df: Full dataset.
        backtest_fn: Function(df, params) -> returns Series.
        base_params: Base parameter values.
        perturbation_ranges: {param_name: (min_pct, max_pct)} perturbation range.
        num_paths: Number of perturbed runs.
        seed: Random seed.

    Returns:
        Dict with distribution of Sharpe ratios across perturbed params.
    """
    rng = np.random.default_rng(seed)
    sharpes: list[float] = []
    all_returns: list[pd.Series] = []

    for _ in range(num_paths):
        perturbed = dict(base_params)
        for param, (lo, hi) in perturbation_ranges.items():
            if param in perturbed and isinstance(perturbed[param], (int, float)):
                pct = rng.uniform(lo, hi)
                perturbed[param] = type(perturbed[param])(perturbed[param] * (1 + pct))

        try:
            rets = backtest_fn(df, perturbed)
            if not rets.empty and rets.std() > 0:
                sharpe = float(rets.mean() * 252 / (rets.std() * np.sqrt(252)))
                sharpes.append(sharpe)
                all_returns.append(rets)
        except Exception:
            continue

    if not sharpes:
        return {"num_paths": 0, "mean_sharpe": 0, "pct_5_sharpe": 0}

    sharpes_arr = np.array(sharpes)
    return {
        "num_paths": len(sharpes),
        "mean_sharpe": float(np.mean(sharpes_arr)),
        "median_sharpe": float(np.median(sharpes_arr)),
        "pct_5_sharpe": float(np.percentile(sharpes_arr, 5)),
        "pct_95_sharpe": float(np.percentile(sharpes_arr, 95)),
        "prob_positive": float(np.mean(sharpes_arr > 0)),
        "sharpes": sharpes_arr,
    }
