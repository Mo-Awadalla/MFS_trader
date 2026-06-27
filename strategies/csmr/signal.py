"""Cross-sectional mean reversion v1 signal construction.

Canonical hypothesis: recent losers outperform recent winners. The strategy
forms a dollar-neutral long/short portfolio once per trading week.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from strategies.cross_sectional import (
    eligible_symbols,
    empty_signal_result,
    formation_frame,
    is_first_trading_session,
    panel_symbols,
    quartile_target_weights,
    validate_panel_inputs,
    write_signal_details,
    write_skip,
    write_weights,
)

Bucket = Literal["long", "middle", "short"]


@dataclass(frozen=True)
class CSMRParams:
    """Frozen CSMR v1 hypothesis parameters."""

    lookback_days: int = 5
    liquidity_lookback_days: int = 20
    min_history_days: int = 60
    min_price: float = 5.0
    min_median_dollar_volume: float = 20_000_000.0
    min_eligible_symbols: int = 100
    long_gross: float = 1.0
    short_gross: float = 1.0


def generate_signals(df: pd.DataFrame, params: CSMRParams) -> pd.DataFrame:
    """Generate CSMR target portfolio weights.

    Input columns must be a MultiIndex of ``(symbol, field)`` where each symbol
    has open/high/low/close/volume columns. For each rebalance date, signal
    formation uses data strictly before that date.
    """
    validate_inputs(df)
    symbols = panel_symbols(df)
    result = empty_signal_result(df.index, symbols)
    current_weights = pd.Series(0.0, index=symbols)

    for ts in df.index:
        is_rebalance = is_first_trading_session(ts, df.index, "weekly")
        result.loc[ts, ("portfolio", "is_rebalance")] = is_rebalance
        if not is_rebalance:
            write_weights(result, ts, current_weights, current_weights * 0.0)
            continue

        formation = formation_frame(df, ts)
        if len(formation) < _minimum_lookback(params):
            write_skip(result, ts, current_weights, "insufficient_history", 0)
            continue

        signal = _prior_returns(formation, params.lookback_days)
        eligible = eligible_symbols(
            formation,
            min_history_days=params.min_history_days,
            min_price=params.min_price,
            liquidity_lookback_days=params.liquidity_lookback_days,
            min_median_dollar_volume=params.min_median_dollar_volume,
            signal=signal,
        )
        eligible_signal = signal[eligible]
        result.loc[ts, ("portfolio", "eligible_count")] = int(len(eligible_signal))

        if len(eligible_signal) < params.min_eligible_symbols:
            write_skip(
                result,
                ts,
                current_weights,
                "insufficient_eligible_universe",
                len(eligible_signal),
            )
            continue

        next_weights, ranks, buckets = quartile_target_weights(
            eligible_signal,
            symbols,
            ranking="ascending",
            long_gross=params.long_gross,
            short_gross=params.short_gross,
        )
        trades = next_weights - current_weights
        write_weights(result, ts, next_weights, trades)
        write_signal_details(result, ts, symbols, signal, eligible_signal, ranks, buckets)
        current_weights = next_weights

    return result


def validate_inputs(df: pd.DataFrame) -> None:
    validate_panel_inputs(df, "CSMR")


def default_params() -> CSMRParams:
    return CSMRParams()


def sweep_grid() -> list[CSMRParams]:
    """No tuning grid for v1; adjacent hypotheses become new Experiments."""
    return [default_params()]


def compact_sweep_grid() -> list[CSMRParams]:
    return [default_params()]


def params_to_dict(params: CSMRParams) -> dict[str, int | float]:
    return {
        "lookback_days": params.lookback_days,
        "liquidity_lookback_days": params.liquidity_lookback_days,
        "min_history_days": params.min_history_days,
        "min_price": params.min_price,
        "min_median_dollar_volume": params.min_median_dollar_volume,
        "min_eligible_symbols": params.min_eligible_symbols,
        "long_gross": params.long_gross,
        "short_gross": params.short_gross,
    }


def params_from_dict(data: dict[str, Any]) -> CSMRParams:
    return CSMRParams(
        lookback_days=int(data.get("lookback_days", 5)),
        liquidity_lookback_days=int(data.get("liquidity_lookback_days", 20)),
        min_history_days=int(data.get("min_history_days", 60)),
        min_price=float(data.get("min_price", 5.0)),
        min_median_dollar_volume=float(data.get("min_median_dollar_volume", 20_000_000.0)),
        min_eligible_symbols=int(data.get("min_eligible_symbols", 100)),
        long_gross=float(data.get("long_gross", 1.0)),
        short_gross=float(data.get("short_gross", 1.0)),
    )

def _minimum_lookback(params: CSMRParams) -> int:
    return max(params.min_history_days, params.liquidity_lookback_days, params.lookback_days + 1)


def _prior_returns(formation: pd.DataFrame, lookback_days: int) -> pd.Series:
    close = formation.xs("close", axis=1, level=1)
    return close.iloc[-1] / close.iloc[-(lookback_days + 1)] - 1.0
