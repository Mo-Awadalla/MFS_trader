"""Declared trial-search evidence for the Deflated Sharpe Ratio.

DSR deflates the *selected* trial's Sharpe by the search that produced it, so a
caller must supply every declared trial, on one shared observation window, and
identify which column is the frozen selected candidate. This module assembles
that evidence and explains, rather than papers over, anything missing.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DeclaredSearch:
    """Every declared trial as one column of a shared ``(bars, trials)`` matrix."""

    returns_matrix: np.ndarray | None
    selected_trial_index: int | None
    selection_error: str | None
    search_scope: str
    trial_parameters: tuple[dict[str, Any], ...] = ()
    selected_parameters: dict[str, Any] | None = None
    observation_index_sha256: str | None = None


def declared_search(
    trial_params: Sequence[Mapping[str, Any]],
    trial_returns: Sequence[pd.Series],
    selected_params: Mapping[str, Any],
    *,
    search_scope: str,
) -> DeclaredSearch:
    """Build DSR search evidence from declared trials in their declared order.

    ``trial_params[i]`` must describe ``trial_returns[i]``. The selected
    candidate is located by exact parameter equality; it is never replaced
    by the best-performing trial. All trials must share one observation index.
    """
    if len(trial_params) != len(trial_returns):
        return DeclaredSearch(None, None, "each declared trial needs exactly one return series", search_scope)
    if not trial_params:
        return DeclaredSearch(None, None, "the declared search contains no trials", search_scope)

    index = trial_returns[0].index
    if not index.is_unique or not index.is_monotonic_increasing:
        return DeclaredSearch(None, None, "trial observation index must be unique and ordered", search_scope)
    if any(not series.index.equals(index) for series in trial_returns[1:]):
        return DeclaredSearch(
            None,
            None,
            "declared trials do not share one observation window",
            search_scope,
        )
    matrix = np.column_stack([series.to_numpy(dtype=float) for series in trial_returns])

    matches = [i for i, params in enumerate(trial_params) if _same_params(params, selected_params)]
    if len(matches) != 1:
        return DeclaredSearch(
            matrix,
            None,
            f"the frozen selected parameters match {len(matches)} declared trials; expected exactly one",
            search_scope,
        )
    return DeclaredSearch(
        matrix, matches[0], None, search_scope,
        trial_parameters=tuple(dict(params) for params in trial_params),
        selected_parameters=dict(selected_params),
        observation_index_sha256=hashlib.sha256(
            pd.util.hash_pandas_object(index, index=False).to_numpy().tobytes()
        ).hexdigest(),
    )


def _same_params(trial: Mapping[str, Any], selected: Mapping[str, Any]) -> bool:
    if set(trial) != set(selected):
        return False
    return all(_same_value(trial[name], selected[name]) for name in selected)


def _same_value(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float, np.integer, np.floating)) and isinstance(
        right, (int, float, np.integer, np.floating)
    ):
        return float(left) == float(right)
    return bool(left == right)
