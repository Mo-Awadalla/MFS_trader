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

    # Summary statistics
    prob_loss: float = 0.0  # P(terminal wealth < initial)
    prob_ruin: float = 0.0  # P(max drawdown < ruin_threshold)
    pct_5_cagr: float = 0.0  # 5th percentile CAGR
    pct_95_max_dd: float = 0.0  # 95th percentile max drawdown
    pct_5_sharpe: float = 0.0
    pct_95_sharpe: float = 0.0
    mean_sharpe: float = 0.0
    median_sharpe: float = 0.0
    prob_positive_sharpe: float = 0.0

    def summarize(self, *, initial_capital: float, ruin_threshold: float = -0.50) -> dict[str, float]:
        """Compute summary statistics from the simulated paths."""
        if len(self.terminal_wealth) == 0:
            return {}

        self.prob_loss = float(np.mean(self.terminal_wealth < initial_capital))
        self.prob_ruin = float(np.mean(self.max_drawdowns < ruin_threshold))
        self.pct_5_cagr = float(np.percentile(self.cagrs, 5))
        self.pct_95_max_dd = float(np.percentile(self.max_drawdowns, 95))
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
            "pct_95_max_dd": self.pct_95_max_dd,
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
    rng = np.random.default_rng(seed)
    n = len(returns)
    rets = returns.values
    num_blocks = n // block_size + 1

    paths = np.empty((num_paths, n))
    for p in range(num_paths):
        # Sample block start indices
        block_starts = rng.integers(0, max(n - block_size, 1), size=num_blocks)
        # Concatenate blocks
        sampled = np.concatenate([rets[s : s + block_size] for s in block_starts])[:n]
        paths[p] = sampled

    return paths


def compute_path_metrics(
    returns: np.ndarray,
    initial_capital: float = 10000.0,
    ann_factor: int = 252,
) -> dict[str, float]:
    """Compute terminal wealth, Sharpe, Sortino, max DD, CAGR for one path."""
    equity = initial_capital * np.cumprod(1 + returns)
    terminal_wealth = float(equity[-1])

    # Sharpe
    ann_return = float(np.mean(returns) * ann_factor)
    ann_vol = float(np.std(returns) * np.sqrt(ann_factor))
    sharpe = ann_return / ann_vol if ann_vol > 0 else 0.0

    # Sortino
    downside = returns[returns < 0]
    sortino = ann_return / (float(np.std(downside) * np.sqrt(ann_factor))) if len(downside) > 0 and np.std(downside) > 0 else 0.0

    # Max drawdown
    cummax = np.maximum.accumulate(equity)
    drawdown = (equity - cummax) / cummax
    max_dd = float(np.min(drawdown))

    # CAGR
    years = len(returns) / ann_factor
    cagr = float((terminal_wealth / initial_capital) ** (1 / years) - 1) if years > 0 else 0.0

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
) -> MCResult:
    """Run block-bootstrap Monte Carlo simulation on a return series.

    Args:
        returns: Strategy daily returns (out-of-sample preferred).
        num_paths: Number of bootstrap paths (default 10k).
        block_size: Block size in bars (default 20).
        initial_capital: Starting capital for path simulation.
        ruin_threshold: Drawdown threshold for "ruin" (default -50%).
        seed: Random seed.

    Returns:
        MCResult with distributions and summary statistics.
    """
    if returns.empty or len(returns) < block_size:
        log.warning("mc_insufficient_data", bars=len(returns), block_size=block_size)
        return MCResult(num_paths=0, block_size=block_size, seed=seed)

    log.info("mc_starting", paths=num_paths, block_size=block_size, bars=len(returns))

    # Generate block-bootstrap paths
    paths = block_bootstrap_returns(returns, num_paths, block_size, seed)

    # Compute metrics for each path (vectorized where possible)
    ann_factor = 252
    equity = initial_capital * np.cumprod(1 + paths, axis=1)
    terminal_wealth = equity[:, -1]

    # Sharpe per path (vectorized)
    path_means = np.mean(paths, axis=1)
    path_stds = np.std(paths, axis=1)
    sharpes = np.where(path_stds > 0, path_means * ann_factor / (path_stds * np.sqrt(ann_factor)), 0.0)

    # Sortino per path
    downside_only = np.where(paths < 0, paths, 0.0)
    downside_stds = np.std(downside_only, axis=1)
    sortinos = np.where(
        (downside_stds > 0) & (path_stds > 0),
        path_means * ann_factor / (downside_stds * np.sqrt(ann_factor)),
        0.0,
    )

    # Max drawdown per path (vectorized)
    cummax = np.maximum.accumulate(equity, axis=1)
    drawdowns = (equity - cummax) / cummax
    max_drawdowns = np.min(drawdowns, axis=1)

    # CAGR per path
    years = paths.shape[1] / ann_factor
    cagrs = (terminal_wealth / initial_capital) ** (1 / years) - 1 if years > 0 else np.zeros(num_paths)

    result = MCResult(
        num_paths=num_paths,
        block_size=block_size,
        seed=seed,
        terminal_wealth=terminal_wealth,
        sharpes=sharpes,
        sortinos=sortinos,
        max_drawdowns=max_drawdowns,
        cagrs=cagrs,
    )
    result.summarize(initial_capital=initial_capital, ruin_threshold=ruin_threshold)

    log.info(
        "mc_complete",
        prob_loss=result.prob_loss,
        prob_ruin=result.prob_ruin,
        pct_5_cagr=result.pct_5_cagr,
        pct_95_max_dd=result.pct_95_max_dd,
        mean_sharpe=result.mean_sharpe,
    )

    return result


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
