"""Pairs v1 discovery and spread diagnostics.

Pairs v1 is US-equities-only and no-tuning. This module finds deterministic
Pair Relationships from an OHLCV panel; later strategy code consumes those
relationships to manage active pair lifecycle.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import combinations

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint

from strategies.cross_sectional import validate_panel_inputs


@dataclass(frozen=True)
class PairsParams:
    """Frozen Pairs v1 discovery and lifecycle parameters."""

    candidate_pool_size: int = 150
    formation_window_days: int = 252
    liquidity_lookback_days: int = 20
    min_history_days: int = 60
    min_eligible_universe: int = 100
    min_price: float = 5.0
    min_median_dollar_volume: float = 20_000_000.0
    coint_pvalue_threshold: float = 0.05
    entry_zscore: float = 2.0
    exit_zscore: float = 0.5
    stop_zscore: float = 4.0
    max_holding_days: int = 60
    max_active_pairs: int = 20
    one_active_position_per_symbol: bool = True
    equal_gross_budget_per_pair: bool = True


@dataclass(frozen=True)
class PairCandidate:
    """A deterministic ordered pair selected for statistical testing."""

    y_symbol: str
    x_symbol: str
    y_median_dollar_volume: float
    x_median_dollar_volume: float
    sector: str | None = None


@dataclass(frozen=True)
class SpreadDiagnostics:
    """Diagnostics for a fitted Pairs v1 spread over its formation window."""

    spread_mean: float
    spread_std: float
    latest_zscore: float
    max_abs_zscore: float
    observations: int


@dataclass(frozen=True)
class PairRelationship:
    """A fitted and cointegrated Pairs v1 relationship."""

    y_symbol: str
    x_symbol: str
    hedge_beta: float
    intercept: float
    cointegration_pvalue: float
    cointegration_statistic: float
    formation_start: str
    formation_end: str
    diagnostics: SpreadDiagnostics
    sector: str | None = None

    @property
    def symbols(self) -> tuple[str, str]:
        return self.y_symbol, self.x_symbol


def select_candidate_symbols(
    panel: pd.DataFrame,
    params: PairsParams | None = None,
) -> tuple[str, ...]:
    """Select the top liquid eligible symbols for Pairs v1 discovery."""
    params = params or PairsParams()
    validate_panel_inputs(panel, "Pairs")
    formation = panel.tail(params.formation_window_days)
    eligible = _eligible_symbols(formation, params)
    if int(eligible.sum()) < params.min_eligible_universe:
        return ()
    ranked = _median_dollar_volume(formation, params).loc[eligible].sort_values(
        ascending=False,
        kind="mergesort",
    )
    return tuple(str(symbol) for symbol in ranked.head(params.candidate_pool_size).index)


def generate_pair_candidates(
    panel: pd.DataFrame,
    params: PairsParams | None = None,
    *,
    sectors: Mapping[str, str] | None = None,
) -> list[PairCandidate]:
    """Generate deterministic all-vs-all or same-sector pair candidates."""
    params = params or PairsParams()
    symbols = select_candidate_symbols(panel, params)
    formation = panel.tail(params.formation_window_days)
    median_dv = _median_dollar_volume(formation, params)

    candidates: list[PairCandidate] = []
    for left, right in combinations(symbols, 2):
        sector = None
        if sectors is not None:
            left_sector = sectors.get(left)
            right_sector = sectors.get(right)
            if left_sector is None or right_sector is None or left_sector != right_sector:
                continue
            sector = left_sector
        y_symbol, x_symbol = _ordered_pair(left, right)
        candidates.append(
            PairCandidate(
                y_symbol=y_symbol,
                x_symbol=x_symbol,
                y_median_dollar_volume=float(median_dv.loc[y_symbol]),
                x_median_dollar_volume=float(median_dv.loc[x_symbol]),
                sector=sector,
            )
        )
    return candidates


def discover_pair_relationships(
    panel: pd.DataFrame,
    params: PairsParams | None = None,
    *,
    sectors: Mapping[str, str] | None = None,
    max_pairs: int | None = None,
) -> list[PairRelationship]:
    """Discover cointegrated Pair Relationships from the latest formation window."""
    params = params or PairsParams()
    validate_panel_inputs(panel, "Pairs")
    if len(panel) < params.formation_window_days:
        return []

    formation = panel.tail(params.formation_window_days)
    candidates = generate_pair_candidates(formation, params, sectors=sectors)
    relationships: list[PairRelationship] = []
    for candidate in candidates:
        relationship = fit_pair_relationship(formation, candidate, params)
        if relationship is None:
            continue
        relationships.append(relationship)

    relationships.sort(
        key=lambda pair: (
            pair.cointegration_pvalue,
            -abs(pair.diagnostics.latest_zscore),
            pair.y_symbol,
            pair.x_symbol,
        )
    )
    limit = max_pairs if max_pairs is not None else params.max_active_pairs
    return relationships[:limit]


def fit_pair_relationship(
    formation: pd.DataFrame,
    candidate: PairCandidate,
    params: PairsParams | None = None,
) -> PairRelationship | None:
    """Fit one Pair Relationship and return it only if it passes Engle-Granger."""
    params = params or PairsParams()
    close = formation.xs("close", axis=1, level=1)
    pair_close = close[[candidate.y_symbol, candidate.x_symbol]].dropna()
    if len(pair_close) < params.formation_window_days:
        return None
    log_y = np.log(pair_close[candidate.y_symbol].astype(float))
    log_x = np.log(pair_close[candidate.x_symbol].astype(float))
    if not np.isfinite(log_y).all() or not np.isfinite(log_x).all():
        return None

    beta, intercept = _ols_hedge_ratio(log_y, log_x)
    statistic, pvalue, _ = coint(log_y, log_x)
    if not np.isfinite(pvalue) or float(pvalue) > params.coint_pvalue_threshold:
        return None

    spread = compute_spread(log_y, log_x, beta=beta, intercept=intercept)
    diagnostics = spread_diagnostics(spread)
    if diagnostics.spread_std <= 0:
        return None

    return PairRelationship(
        y_symbol=candidate.y_symbol,
        x_symbol=candidate.x_symbol,
        hedge_beta=beta,
        intercept=intercept,
        cointegration_pvalue=float(pvalue),
        cointegration_statistic=float(statistic),
        formation_start=str(pair_close.index.min()),
        formation_end=str(pair_close.index.max()),
        diagnostics=diagnostics,
        sector=candidate.sector,
    )


def compute_spread(
    log_y: pd.Series,
    log_x: pd.Series,
    *,
    beta: float,
    intercept: float,
) -> pd.Series:
    return log_y - beta * log_x - intercept


def rolling_zscore(spread: pd.Series, window: int) -> pd.Series:
    mean = spread.rolling(window, min_periods=window).mean()
    std = spread.rolling(window, min_periods=window).std()
    stable_std = std.mask(std.abs() <= 1e-12)
    return ((spread - mean) / stable_std).fillna(0.0)


def spread_diagnostics(spread: pd.Series) -> SpreadDiagnostics:
    clean = spread.dropna()
    if clean.empty:
        return SpreadDiagnostics(
            spread_mean=0.0,
            spread_std=0.0,
            latest_zscore=0.0,
            max_abs_zscore=0.0,
            observations=0,
        )
    mean = float(clean.mean())
    std = float(clean.std())
    zscores = (clean - mean) / std if std > 0 else pd.Series(0.0, index=clean.index)
    return SpreadDiagnostics(
        spread_mean=mean,
        spread_std=std,
        latest_zscore=float(zscores.iloc[-1]),
        max_abs_zscore=float(zscores.abs().max()),
        observations=len(clean),
    )


def params_to_dict(params: PairsParams) -> dict[str, int | float | bool]:
    return {
        "candidate_pool_size": params.candidate_pool_size,
        "formation_window_days": params.formation_window_days,
        "liquidity_lookback_days": params.liquidity_lookback_days,
        "min_history_days": params.min_history_days,
        "min_eligible_universe": params.min_eligible_universe,
        "min_price": params.min_price,
        "min_median_dollar_volume": params.min_median_dollar_volume,
        "coint_pvalue_threshold": params.coint_pvalue_threshold,
        "entry_zscore": params.entry_zscore,
        "exit_zscore": params.exit_zscore,
        "stop_zscore": params.stop_zscore,
        "max_holding_days": params.max_holding_days,
        "max_active_pairs": params.max_active_pairs,
        "one_active_position_per_symbol": params.one_active_position_per_symbol,
        "equal_gross_budget_per_pair": params.equal_gross_budget_per_pair,
    }


def _eligible_symbols(formation: pd.DataFrame, params: PairsParams) -> pd.Series:
    close = formation.xs("close", axis=1, level=1)
    dollar_volume = _dollar_volume(formation)
    history_ok = close.notna().sum() >= params.min_history_days
    price_ok = close.iloc[-1] >= params.min_price
    liquidity_ok = (
        dollar_volume.tail(params.liquidity_lookback_days).median()
        >= params.min_median_dollar_volume
    )
    log_ok = (close > 0).all()
    return history_ok & price_ok & liquidity_ok & log_ok


def _median_dollar_volume(formation: pd.DataFrame, params: PairsParams) -> pd.Series:
    return _dollar_volume(formation).tail(params.liquidity_lookback_days).median()


def _dollar_volume(formation: pd.DataFrame) -> pd.DataFrame:
    close = formation.xs("close", axis=1, level=1)
    volume = formation.xs("volume", axis=1, level=1)
    return close * volume


def _ordered_pair(left: str, right: str) -> tuple[str, str]:
    ordered = sorted((left, right))
    return ordered[0], ordered[1]


def _ols_hedge_ratio(log_y: pd.Series, log_x: pd.Series) -> tuple[float, float]:
    x = log_x.to_numpy(dtype=float)
    y = log_y.to_numpy(dtype=float)
    design = np.column_stack([x, np.ones(len(x))])
    beta, intercept = np.linalg.lstsq(design, y, rcond=None)[0]
    return float(beta), float(intercept)
