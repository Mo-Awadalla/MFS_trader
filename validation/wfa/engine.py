"""Walk-forward analysis (WFA).

Three tiers:
  - primary:    18m train / 6m test / 3m step  — standard evaluation
  - robustness: 12m train / 3m test / 1m step  — many folds, parameter stability
  - expanding:  train from inception, 6m test, 3m step — finalize params

A "fold" is one (train, test) pair. The strategy is trained on the train window,
and out-of-sample performance is measured on the test window.

This module is agnostic to the strategy — it takes a callable that, given a
train DataFrame and test DataFrame, returns a BacktestResult on the test set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger(__name__)


class WFATier(StrEnum):
    PRIMARY = "primary"
    ROBUSTNESS = "robustness"
    EXPANDING = "expanding"


@dataclass(frozen=True)
class WFAConfig:
    tier: WFATier
    train_window: str  # e.g. "18m", "12m", or "expanding"
    test_window: str  # e.g. "6m", "3m"
    step: str  # e.g. "3m", "1m"


PRESETS = {
    WFATier.PRIMARY: WFAConfig(WFATier.PRIMARY, "18m", "6m", "3m"),
    WFATier.ROBUSTNESS: WFAConfig(WFATier.ROBUSTNESS, "12m", "3m", "1m"),
    WFATier.EXPANDING: WFAConfig(WFATier.EXPANDING, "expanding", "6m", "3m"),
}


class TrainFn(Protocol):
    """A strategy training function: takes train data + params, returns fitted params."""

    def __call__(self, train_df: pd.DataFrame, **kwargs: Any) -> dict[str, Any]: ...


class TestFn(Protocol):
    """A strategy test function: takes test data + fitted params, returns BacktestResult."""

    def __call__(self, test_df: pd.DataFrame, fitted_params: dict[str, Any]) -> dict[str, float]: ...


@dataclass
class WFAFold:
    fold_index: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    fitted_params: dict[str, Any] = field(default_factory=dict)
    test_metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class WFAResult:
    tier: WFATier
    config: WFAConfig
    folds: list[WFAFold] = field(default_factory=list)
    aggregate_metrics: dict[str, float] = field(default_factory=dict)
    oos_returns: pd.Series | None = None
    passed: bool = False
    failure_reasons: list[str] = field(default_factory=list)

    @property
    def num_folds(self) -> int:
        return len(self.folds)

    @property
    def num_negative_folds(self) -> int:
        return sum(1 for f in self.folds if f.test_metrics.get("total_return", 0) < 0)

    @property
    def frac_negative_folds(self) -> float:
        return self.num_negative_folds / self.num_folds if self.num_folds > 0 else 0.0


def parse_window(window: str, anchor: pd.Timestamp) -> pd.Timedelta | None:
    """Parse a window string like '18m', '6m', '3m' into a Timedelta.

    Returns None for 'expanding' (handled specially).
    """
    if window == "expanding":
        return None
    unit = window[-1].lower()
    value = int(window[:-1])
    if unit == "m":
        # Months — approximate as 30.44 days
        return pd.Timedelta(days=value * 30.44)
    elif unit == "d":
        return pd.Timedelta(days=value)
    elif unit == "w":
        return pd.Timedelta(weeks=value)
    elif unit == "y":
        return pd.Timedelta(days=value * 365.25)
    else:
        raise ValueError(f"Unknown window unit: {unit} in {window}")


def generate_folds(
    df: pd.DataFrame,
    config: WFAConfig,
) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """Generate (train_start, train_end, test_start, test_end) tuples for WFA.

    Args:
        df: Full dataset with DatetimeIndex.
        config: WFA configuration.

    Returns:
        List of (train_start, train_end, test_start, test_end) tuples.
    """
    if df.empty:
        return []

    data_start = df.index[0]
    data_end = df.index[-1]

    train_delta = parse_window(config.train_window, data_start)
    test_delta = parse_window(config.test_window, data_start)
    step_delta = parse_window(config.step, data_start)

    if train_delta is None or test_delta is None or step_delta is None:
        raise ValueError("expanding window not supported in generate_folds — use generate_expanding_folds")

    folds: list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]] = []
    test_start = data_start + train_delta

    while test_start + test_delta <= data_end:
        train_start = data_start if config.train_window == "expanding" else test_start - train_delta

        train_end = test_start
        test_end = test_start + test_delta
        folds.append((train_start, train_end, test_start, test_end))
        test_start = test_start + step_delta

    return folds


def generate_expanding_folds(
    df: pd.DataFrame,
    test_window: str = "6m",
    step: str = "3m",
) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """Generate folds for expanding-window WFA.

    Train always starts at data inception; the train window grows each fold.
    """
    if df.empty:
        return []

    data_start = df.index[0]
    data_end = df.index[-1]

    test_delta = parse_window(test_window, data_start)
    step_delta = parse_window(step, data_start)

    if test_delta is None or step_delta is None:
        raise ValueError("test_window and step must be fixed durations for expanding folds")

    folds: list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]] = []
    test_start = data_start + test_delta  # first test window needs at least one test_delta of train

    # Expanding: need at least some training data before first test
    # Use a minimum train of ~6 months
    min_train = parse_window("6m", data_start)
    if min_train is None:
        min_train = pd.Timedelta(days=180)
    first_test_start = data_start + min_train

    test_start = first_test_start
    while test_start + test_delta <= data_end:
        train_start = data_start
        train_end = test_start
        test_end = test_start + test_delta
        folds.append((train_start, train_end, test_start, test_end))
        test_start = test_start + step_delta

    return folds


def run_wfa(
    df: pd.DataFrame,
    train_fn: TrainFn,
    test_fn: TestFn,
    config: WFAConfig | None = None,
    *,
    pass_criteria: dict[str, float] | None = None,
    **train_kwargs: Any,
) -> WFAResult:
    """Run walk-forward analysis on a dataset.

    Args:
        df: Full OHLCV dataset.
        train_fn: Function(train_df, **kwargs) -> fitted_params dict.
        test_fn: Function(test_df, fitted_params) -> metrics dict.
        config: WFA config. Defaults to PRIMARY.
        pass_criteria: Thresholds for passing. Defaults:
            - oos_sharpe > 0.8
            - oos_sortino > 1.0
            - frac_negative_folds < 0.5
            - no single fold contributes > 60% of total profit
        **train_kwargs: Extra args passed to train_fn.

    Returns:
        WFAResult with per-fold metrics and aggregate pass/fail.
    """
    config = config or PRESETS[WFATier.PRIMARY]
    if pass_criteria is None:
        pass_criteria = {
            "oos_sharpe_min": 0.8,
            "oos_sortino_min": 1.0,
            "frac_negative_max": 0.5,
            "max_single_fold_profit_share": 0.60,
        }

    result = WFAResult(tier=config.tier, config=config)

    if config.tier == WFATier.EXPANDING:
        fold_tuples = generate_expanding_folds(df, config.test_window, config.step)
    else:
        fold_tuples = generate_folds(df, config)

    if not fold_tuples:
        result.failure_reasons.append("no_valid_folds_generated")
        return result

    all_oos_returns: list[pd.Series] = []

    for i, (train_start, train_end, test_start, test_end) in enumerate(fold_tuples):
        train_df = df.loc[train_start:train_end]
        test_df = df.loc[test_start:test_end]

        if train_df.empty or test_df.empty:
            log.warning("wfa_empty_fold", fold=i, train_bars=len(train_df), test_bars=len(test_df))
            continue

        try:
            fitted_params = train_fn(train_df, **train_kwargs)
            test_metrics = test_fn(test_df, fitted_params)
        except Exception as e:
            log.error("wfa_fold_failed", fold=i, error=str(e))
            result.folds.append(
                WFAFold(
                    fold_index=i,
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    test_metrics={"error": 1.0},
                )
            )
            result.failure_reasons.append(f"fold_{i}_error: {e}")
            continue

        fold = WFAFold(
            fold_index=i,
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            fitted_params=fitted_params,
            test_metrics=test_metrics,
        )
        result.folds.append(fold)

        if "returns" in test_metrics and isinstance(test_metrics["returns"], pd.Series):
            all_oos_returns.append(test_metrics["returns"])

        log.info(
            "wfa_fold_complete",
            fold=i,
            test_start=str(test_start),
            test_end=str(test_end),
            sharpe=test_metrics.get("sharpe", 0),
        )

    # Aggregate OOS metrics
    result.aggregate_metrics = _aggregate_metrics(result.folds, all_oos_returns)
    result.oos_returns = pd.concat(all_oos_returns) if all_oos_returns else pd.Series(dtype=float)

    # Evaluate pass/fail
    _evaluate_pass_fail(result, pass_criteria)

    return result


def _aggregate_metrics(folds: list[WFAFold], all_returns: list[pd.Series]) -> dict[str, float]:
    """Aggregate OOS metrics across all folds."""
    if not folds:
        return {}

    sharpes = [f.test_metrics.get("sharpe", 0) for f in folds if "error" not in f.test_metrics]
    sortinos = [f.test_metrics.get("sortino", 0) for f in folds if "error" not in f.test_metrics]
    returns = [f.test_metrics.get("total_return", 0) for f in folds if "error" not in f.test_metrics]
    max_dds = [f.test_metrics.get("max_drawdown", 0) for f in folds if "error" not in f.test_metrics]

    agg = {
        "oos_sharpe_mean": float(pd.Series(sharpes).mean()) if sharpes else 0,
        "oos_sharpe_median": float(pd.Series(sharpes).median()) if sharpes else 0,
        "oos_sharpe_std": float(pd.Series(sharpes).std()) if len(sharpes) > 1 else 0,
        "oos_sortino_mean": float(pd.Series(sortinos).mean()) if sortinos else 0,
        "oos_total_return_mean": float(pd.Series(returns).mean()) if returns else 0,
        "oos_max_dd_mean": float(pd.Series(max_dds).mean()) if max_dds else 0,
        "oos_max_dd_worst": float(min(max_dds)) if max_dds else 0,
        "num_folds": len(folds),
        "num_valid_folds": sum(1 for f in folds if "error" not in f.test_metrics),
    }

    # Concatenated OOS Sharpe (treating all OOS returns as one series)
    if all_returns:
        combined = pd.concat(all_returns)
        if len(combined) > 1 and combined.std() > 0:
            ann_factor = 252
            agg["oos_sharpe"] = float(combined.mean() * ann_factor / (combined.std() * np.sqrt(ann_factor)))
        else:
            agg["oos_sharpe"] = 0.0
    else:
        agg["oos_sharpe"] = 0.0

    # Profit concentration — does one fold dominate?
    positive_returns = [r for r in returns if r > 0]
    total_profit = sum(positive_returns)
    if total_profit > 0 and positive_returns:
        max_fold_profit = max(positive_returns)
        agg["max_single_fold_profit_share"] = float(max_fold_profit / total_profit)
    else:
        agg["max_single_fold_profit_share"] = 0.0

    return agg


def _evaluate_pass_fail(result: WFAResult, criteria: dict[str, float]) -> None:
    """Evaluate WFA pass/fail against criteria."""
    metrics = result.aggregate_metrics
    failures: list[str] = []

    if metrics.get("oos_sharpe", 0) < criteria.get("oos_sharpe_min", 0.8):
        failures.append(
            f"oos_sharpe {metrics.get('oos_sharpe', 0):.2f} < {criteria['oos_sharpe_min']}"
        )

    if metrics.get("oos_sortino_mean", 0) < criteria.get("oos_sortino_min", 1.0):
        failures.append(
            f"oos_sortino {metrics.get('oos_sortino_mean', 0):.2f} < {criteria['oos_sortino_min']}"
        )

    if result.frac_negative_folds > criteria.get("frac_negative_max", 0.5):
        failures.append(
            f"frac_negative_folds {result.frac_negative_folds:.2f} > {criteria['frac_negative_max']}"
        )

    max_share = metrics.get("max_single_fold_profit_share", 0)
    if max_share > criteria.get("max_single_fold_profit_share", 0.60):
        failures.append(
            f"single fold contributes {max_share:.0%} of profit > {criteria['max_single_fold_profit_share']:.0%}"
        )

    result.failure_reasons.extend(failures)
    result.passed = len(failures) == 0


# Import numpy at the end to avoid circular imports in type hints
