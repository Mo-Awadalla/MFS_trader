"""Pairs v1 signal lifecycle.

Pairs v1 refits relationships monthly, monitors fitted spread z-scores daily,
and manages active long/short spread positions with deterministic constraints.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd

from strategies.cross_sectional import (
    PORTFOLIO_FIELD_NAMES,
    SYMBOL_FIELD_NAMES,
    formation_frame,
    is_first_trading_session,
    panel_symbols,
    validate_panel_inputs,
    write_weights,
)
from strategies.pairs.discovery import (
    PairRelationship,
    PairsParams,
    compute_spread,
    discover_pair_relationships,
    params_to_dict,
    select_candidate_symbols,
)

PairDirection = Literal[-1, 1]
PAIR_PORTFOLIO_FIELDS = PORTFOLIO_FIELD_NAMES + (
    "relationship_count",
    "active_pair_count",
    "entry_count",
    "exit_count",
    "stop_count",
)


@dataclass
class _ActivePair:
    relationship: PairRelationship
    direction: PairDirection
    entry_pos: int


def generate_signals(df: pd.DataFrame, params: PairsParams) -> pd.DataFrame:
    """Generate Pairs v1 target portfolio weights from a cross-sectional panel."""
    validate_inputs(df)
    symbols = panel_symbols(df)
    result = _empty_result(df.index, symbols)
    relationships: list[PairRelationship] = []
    active_pairs: dict[tuple[str, str], _ActivePair] = {}
    current_weights = pd.Series(0.0, index=symbols)

    for pos, ts in enumerate(df.index):
        is_refit = is_first_trading_session(ts, df.index, "monthly")
        result.loc[ts, ("portfolio", "is_rebalance")] = is_refit

        formation = formation_frame(df, ts)
        if is_refit:
            if len(formation) < params.formation_window_days:
                result.loc[ts, ("portfolio", "rebalance_skipped")] = True
                result.loc[ts, ("portfolio", "skip_reason")] = "insufficient_history"
                result.loc[ts, ("portfolio", "eligible_count")] = 0
                write_weights(result, ts, current_weights, current_weights * 0.0)
                continue
            candidate_symbols = select_candidate_symbols(formation, params)
            result.loc[ts, ("portfolio", "eligible_count")] = len(candidate_symbols)
            if len(candidate_symbols) < params.min_eligible_universe:
                result.loc[ts, ("portfolio", "rebalance_skipped")] = True
                result.loc[ts, ("portfolio", "skip_reason")] = "insufficient_eligible_universe"
                write_weights(result, ts, current_weights, current_weights * 0.0)
                continue
            relationships = discover_pair_relationships(
                formation,
                params,
                max_pairs=params.max_active_pairs,
            )
            active_pairs = _retain_refit_survivors(active_pairs, relationships)

        entry_count = 0
        exit_count = 0
        stop_count = 0
        used_symbols = _active_symbols(active_pairs)

        for key, active in list(active_pairs.items()):
            zscore = _current_zscore(df, pos, active.relationship, params)
            held = pos - active.entry_pos
            if abs(zscore) <= params.exit_zscore:
                del active_pairs[key]
                exit_count += 1
            elif abs(zscore) >= params.stop_zscore or held >= params.max_holding_days:
                del active_pairs[key]
                stop_count += 1

        used_symbols = _active_symbols(active_pairs)
        for relationship in relationships:
            if len(active_pairs) >= params.max_active_pairs:
                break
            key = relationship.symbols
            if key in active_pairs:
                continue
            if params.one_active_position_per_symbol and (
                relationship.y_symbol in used_symbols or relationship.x_symbol in used_symbols
            ):
                continue
            zscore = _current_zscore(df, pos, relationship, params)
            if abs(zscore) < params.entry_zscore or abs(zscore) >= params.stop_zscore:
                continue
            direction: PairDirection = -1 if zscore > 0 else 1
            active_pairs[key] = _ActivePair(
                relationship=relationship,
                direction=direction,
                entry_pos=pos,
            )
            used_symbols.update(key)
            entry_count += 1

        next_weights = _portfolio_weights(symbols, active_pairs, params)
        trades = next_weights - current_weights
        write_weights(result, ts, next_weights, trades)
        result.loc[ts, ("portfolio", "relationship_count")] = len(relationships)
        result.loc[ts, ("portfolio", "active_pair_count")] = len(active_pairs)
        result.loc[ts, ("portfolio", "entry_count")] = entry_count
        result.loc[ts, ("portfolio", "exit_count")] = exit_count
        result.loc[ts, ("portfolio", "stop_count")] = stop_count
        if not is_refit:
            result.loc[ts, ("portfolio", "eligible_count")] = len(relationships)
        current_weights = next_weights

    return result


def validate_inputs(df: pd.DataFrame) -> None:
    validate_panel_inputs(df, "Pairs")


def default_params() -> PairsParams:
    return PairsParams()


def sweep_grid() -> list[PairsParams]:
    """No tuning grid for v1; adjacent hypotheses become new Experiments."""
    return [default_params()]


def compact_sweep_grid() -> list[PairsParams]:
    return [default_params()]


def params_from_dict(data: dict[str, Any]) -> PairsParams:
    return PairsParams(
        candidate_pool_size=int(data.get("candidate_pool_size", 150)),
        formation_window_days=int(data.get("formation_window_days", 252)),
        liquidity_lookback_days=int(data.get("liquidity_lookback_days", 20)),
        min_history_days=int(data.get("min_history_days", 60)),
        min_eligible_universe=int(data.get("min_eligible_universe", 100)),
        min_price=float(data.get("min_price", 5.0)),
        min_median_dollar_volume=float(data.get("min_median_dollar_volume", 20_000_000.0)),
        coint_pvalue_threshold=float(data.get("coint_pvalue_threshold", 0.05)),
        entry_zscore=float(data.get("entry_zscore", 2.0)),
        exit_zscore=float(data.get("exit_zscore", 0.5)),
        stop_zscore=float(data.get("stop_zscore", 4.0)),
        max_holding_days=int(data.get("max_holding_days", 60)),
        max_active_pairs=int(data.get("max_active_pairs", 20)),
        one_active_position_per_symbol=bool(data.get("one_active_position_per_symbol", True)),
        equal_gross_budget_per_pair=bool(data.get("equal_gross_budget_per_pair", True)),
    )


def _empty_result(index: pd.DatetimeIndex, symbols: tuple[str, ...]) -> pd.DataFrame:
    symbol_columns = pd.MultiIndex.from_product(
        [symbols, SYMBOL_FIELD_NAMES],
        names=["symbol", "field"],
    )
    portfolio_columns = pd.MultiIndex.from_product(
        [["portfolio"], PAIR_PORTFOLIO_FIELDS],
        names=["symbol", "field"],
    )
    result = pd.DataFrame(index=index, columns=symbol_columns.append(portfolio_columns))
    result.loc[:, pd.IndexSlice[:, "weight"]] = 0.0
    result.loc[:, pd.IndexSlice[:, "trade"]] = 0.0
    result.loc[:, pd.IndexSlice[:, "eligible"]] = False
    result.loc[:, ("portfolio", "is_rebalance")] = False
    result.loc[:, ("portfolio", "rebalance_skipped")] = False
    result.loc[:, ("portfolio", "skip_reason")] = ""
    result.loc[:, ("portfolio", "eligible_count")] = 0
    result.loc[:, ("portfolio", "relationship_count")] = 0
    result.loc[:, ("portfolio", "active_pair_count")] = 0
    result.loc[:, ("portfolio", "entry_count")] = 0
    result.loc[:, ("portfolio", "exit_count")] = 0
    result.loc[:, ("portfolio", "stop_count")] = 0
    return result


def _current_zscore(
    df: pd.DataFrame,
    pos: int,
    relationship: PairRelationship,
    params: PairsParams,
) -> float:
    start = max(0, pos - params.formation_window_days)
    close = df.iloc[start:pos].xs("close", axis=1, level=1)
    if len(close) < params.formation_window_days:
        return 0.0
    pair_close = close[[relationship.y_symbol, relationship.x_symbol]].dropna()
    if len(pair_close) < params.formation_window_days:
        return 0.0
    log_y = np.log(pair_close[relationship.y_symbol].astype(float))
    log_x = np.log(pair_close[relationship.x_symbol].astype(float))
    spread = compute_spread(
        log_y,
        log_x,
        beta=relationship.hedge_beta,
        intercept=relationship.intercept,
    )
    std = float(spread.std())
    if std <= 0:
        return 0.0
    return float((spread.iloc[-1] - spread.mean()) / std)


def _portfolio_weights(
    symbols: tuple[str, ...],
    active_pairs: dict[tuple[str, str], _ActivePair],
    params: PairsParams,
) -> pd.Series:
    weights = pd.Series(0.0, index=symbols)
    if not active_pairs:
        return weights
    pair_gross = 2.0 / len(active_pairs) if params.equal_gross_budget_per_pair else 2.0 / params.max_active_pairs
    for active in active_pairs.values():
        relationship = active.relationship
        beta_abs = abs(relationship.hedge_beta)
        y_gross = pair_gross / (1.0 + beta_abs)
        x_gross = pair_gross - y_gross
        weights.loc[relationship.y_symbol] += active.direction * y_gross
        weights.loc[relationship.x_symbol] -= active.direction * x_gross
    return weights


def _retain_refit_survivors(
    active_pairs: dict[tuple[str, str], _ActivePair],
    relationships: list[PairRelationship],
) -> dict[tuple[str, str], _ActivePair]:
    relationship_by_key = {relationship.symbols: relationship for relationship in relationships}
    retained: dict[tuple[str, str], _ActivePair] = {}
    for key, active in active_pairs.items():
        if key not in relationship_by_key:
            continue
        retained[key] = _ActivePair(
            relationship=relationship_by_key[key],
            direction=active.direction,
            entry_pos=active.entry_pos,
        )
    return retained


def _active_symbols(active_pairs: dict[tuple[str, str], _ActivePair]) -> set[str]:
    symbols: set[str] = set()
    for key in active_pairs:
        symbols.update(key)
    return symbols


__all__ = [
    "PairsParams",
    "compact_sweep_grid",
    "default_params",
    "generate_signals",
    "params_from_dict",
    "params_to_dict",
    "sweep_grid",
    "validate_inputs",
]
