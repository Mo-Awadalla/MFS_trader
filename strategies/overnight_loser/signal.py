"""Overnight loser open-to-close reversal v1 signal construction.

Canonical hypothesis: the worst overnight losers revert intraday.

Source basis:
  - Lou, Polk, Skouras, "A tug of war: Overnight versus intraday expected
    returns," JFE 2019. DOI: 10.1016/j.jfineco.2019.03.011
  - Bogousslavsky, "The cross-section of intraday and overnight returns,"
    JFE 2021. DOI: 10.1016/j.jfineco.2020.07.020

Execution model: the signal forms at the regular-session open using only the
same-bar open and prior-bar close (overnight return = open_t / close_{t-1} - 1).
Positions are entered at that open and fully liquidated at the same bar close.
The book is flat every night.

Delay limitation: ``delay_bps`` models entering slightly after the open (e.g.
1 minute late) as a fixed cost penalty. With daily bars this is only a proxy;
precise delay sensitivity analysis requires 1-minute bars.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from strategies.cross_sectional import (
    eligible_symbols,
    empty_signal_result,
    formation_frame,
    panel_symbols,
    validate_panel_inputs,
    write_signal_details,
    write_skip,
    write_weights,
)

UNIVERSES: dict[str, tuple[str, ...]] = {
    "sector_spdrs": (
        "XLB",
        "XLC",
        "XLE",
        "XLF",
        "XLI",
        "XLK",
        "XLP",
        "XLU",
        "XLV",
        "XLY",
        "XLRE",
        "XHB",
    ),
}
TEMPLATE_VERSION = "overnight_loser:v1"


def universe_symbols(universe: str) -> tuple[str, ...]:
    if universe not in UNIVERSES:
        known = ", ".join(sorted(UNIVERSES))
        raise KeyError(f"unknown overnight_loser universe {universe!r}; known: {known}")
    return UNIVERSES[universe]


@dataclass(frozen=True)
class OvernightLoserParams:
    """Frozen overnight loser v1 hypothesis parameters.

    ``universe`` selects the ETF set at data-load time; signal generation
    operates on whatever panel it receives. ``spread_bps`` and ``delay_bps``
    are cost-model inputs consumed by the research pipeline, not by signal
    construction.
    """

    universe: str = "sector_spdrs"
    num_long_positions: int = 4
    num_short_positions: int = 0
    min_history_days: int = 20
    min_price: float = 10.0
    min_median_dollar_volume: float = 50_000_000.0
    liquidity_lookback_days: int = 20
    long_gross: float = 1.0
    short_gross: float = 0.0
    spread_bps: float = 3.0
    delay_bps: float = 0.0


def generate_signals(df: pd.DataFrame, params: OvernightLoserParams) -> pd.DataFrame:
    """Generate daily overnight-loser target portfolio weights.

    Input columns must be a MultiIndex of ``(symbol, field)``. Every trading
    session is a rebalance: the overnight return uses the same-bar open and
    the prior bar close; all other filters use data strictly before the bar.
    The ``trade`` field holds the entry trade at the open; the exit at the
    close is implied (the book is flat at every open).
    """
    validate_inputs(df)
    symbols = panel_symbols(df)
    result = empty_signal_result(df.index, symbols)
    flat = pd.Series(0.0, index=symbols)
    open_prices = df.xs("open", axis=1, level=1)

    for ts in df.index:
        result.loc[ts, ("portfolio", "is_rebalance")] = True

        formation = formation_frame(df, ts)
        if len(formation) < _minimum_lookback(params):
            write_skip(result, ts, flat, "insufficient_history", 0)
            continue

        prior_close = formation.xs("close", axis=1, level=1).iloc[-1]
        signal = open_prices.loc[ts] / prior_close - 1.0
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

        required = params.num_long_positions + params.num_short_positions
        if required == 0 or len(eligible_signal) < required:
            write_skip(
                result,
                ts,
                flat,
                "insufficient_eligible_universe",
                len(eligible_signal),
            )
            continue

        next_weights, ranks, buckets = _fixed_count_target_weights(
            eligible_signal, symbols, params
        )
        write_weights(result, ts, next_weights, next_weights)
        write_signal_details(result, ts, symbols, signal, eligible_signal, ranks, buckets)

    return result


def validate_inputs(df: pd.DataFrame) -> None:
    validate_panel_inputs(df, "OvernightLoser")


def default_params() -> OvernightLoserParams:
    return OvernightLoserParams()


def sweep_grid() -> list[OvernightLoserParams]:
    """No tuning grid for v1; adjacent hypotheses become new Experiments."""
    return [default_params()]


def compact_sweep_grid() -> list[OvernightLoserParams]:
    return [default_params()]


def params_to_dict(params: OvernightLoserParams) -> dict[str, Any]:
    return {
        "universe": params.universe,
        "num_long_positions": params.num_long_positions,
        "num_short_positions": params.num_short_positions,
        "min_history_days": params.min_history_days,
        "min_price": params.min_price,
        "min_median_dollar_volume": params.min_median_dollar_volume,
        "liquidity_lookback_days": params.liquidity_lookback_days,
        "long_gross": params.long_gross,
        "short_gross": params.short_gross,
        "spread_bps": params.spread_bps,
        "delay_bps": params.delay_bps,
    }


def params_from_dict(data: dict[str, Any]) -> OvernightLoserParams:
    return OvernightLoserParams(
        universe=str(data.get("universe", "sector_spdrs")),
        num_long_positions=int(data.get("num_long_positions", 4)),
        num_short_positions=int(data.get("num_short_positions", 0)),
        min_history_days=int(data.get("min_history_days", 20)),
        min_price=float(data.get("min_price", 10.0)),
        min_median_dollar_volume=float(data.get("min_median_dollar_volume", 50_000_000.0)),
        liquidity_lookback_days=int(data.get("liquidity_lookback_days", 20)),
        long_gross=float(data.get("long_gross", 1.0)),
        short_gross=float(data.get("short_gross", 0.0)),
        spread_bps=float(data.get("spread_bps", 3.0)),
        delay_bps=float(data.get("delay_bps", 0.0)),
    )


def _minimum_lookback(params: OvernightLoserParams) -> int:
    return max(params.min_history_days, params.liquidity_lookback_days, 1)


def _fixed_count_target_weights(
    signal: pd.Series,
    all_symbols: tuple[str, ...],
    params: OvernightLoserParams,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Equal-weight the worst N overnight losers (and best N gainers if short)."""
    rank_frame = pd.DataFrame(
        {
            "symbol": [str(symbol) for symbol in signal.index],
            "signal": signal.to_numpy(),
        }
    ).sort_values(["signal", "symbol"], ascending=[True, True], kind="mergesort")
    ranked_symbols = rank_frame["symbol"].to_numpy()

    long_symbols = tuple(str(s) for s in ranked_symbols[: params.num_long_positions])
    short_symbols: tuple[str, ...] = ()
    if params.num_short_positions > 0:
        short_symbols = tuple(str(s) for s in ranked_symbols[-params.num_short_positions :])

    weights = pd.Series(0.0, index=all_symbols)
    if long_symbols:
        weights.loc[list(long_symbols)] = params.long_gross / len(long_symbols)
    if short_symbols:
        weights.loc[list(short_symbols)] = -params.short_gross / len(short_symbols)

    ranks = pd.Series(np.nan, index=all_symbols)
    for rank, symbol in enumerate(ranked_symbols, start=1):
        ranks.loc[str(symbol)] = rank

    buckets = pd.Series("", index=all_symbols, dtype=object)
    middle = {str(s) for s in ranked_symbols} - set(long_symbols) - set(short_symbols)
    buckets.loc[list(long_symbols)] = "long"
    if short_symbols:
        buckets.loc[list(short_symbols)] = "short"
    if middle:
        buckets.loc[sorted(middle)] = "middle"
    return weights, ranks, buckets
