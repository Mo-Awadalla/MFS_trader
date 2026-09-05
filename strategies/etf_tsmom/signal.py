"""ETFTimeSeriesMomentumVolTarget-v1 signal construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from strategies.cross_sectional import empty_signal_result, panel_symbols, validate_panel_inputs

DEFAULT_UNIVERSE = ("DBC", "EEM", "EFA", "GLD", "IEF", "IWM", "QQQ", "SHY", "SPY", "TLT", "VNQ")


@dataclass(frozen=True)
class ETFTSMOMParams:
    lookback_days: int = 252
    realized_vol_days: int = 63
    top_k: int = 3
    max_weight: float = 0.50
    annual_vol_target: float = 0.10
    max_gross_exposure: float = 1.50
    cash_proxy: str = "SHY"


def default_params() -> ETFTSMOMParams:
    return ETFTSMOMParams()


def sweep_grid() -> list[ETFTSMOMParams]:
    return [default_params()]


def compact_sweep_grid() -> list[ETFTSMOMParams]:
    return [default_params()]


def params_to_dict(params: ETFTSMOMParams) -> dict[str, int | float | str]:
    return {
        "lookback_days": params.lookback_days,
        "realized_vol_days": params.realized_vol_days,
        "top_k": params.top_k,
        "max_weight": params.max_weight,
        "annual_vol_target": params.annual_vol_target,
        "max_gross_exposure": params.max_gross_exposure,
        "cash_proxy": params.cash_proxy,
    }


def params_from_dict(data: dict[str, Any]) -> ETFTSMOMParams:
    return ETFTSMOMParams(
        lookback_days=int(data.get("lookback_days", 252)),
        realized_vol_days=int(data.get("realized_vol_days", 63)),
        top_k=int(data.get("top_k", 3)),
        max_weight=float(data.get("max_weight", 0.50)),
        annual_vol_target=float(data.get("annual_vol_target", 0.10)),
        max_gross_exposure=float(data.get("max_gross_exposure", 1.50)),
        cash_proxy=str(data.get("cash_proxy", "SHY")),
    )


def validate_inputs(df: pd.DataFrame) -> None:
    validate_panel_inputs(df, "ETFTimeSeriesMomentumVolTarget")


def generate_signals(df: pd.DataFrame, params: ETFTSMOMParams | None = None) -> pd.DataFrame:
    params = params or default_params()
    weights, trades, portfolio = generate_weight_signals(df, params)
    symbols = tuple(weights.columns)
    result = empty_signal_result(df.index, symbols)
    for symbol in symbols:
        result[(symbol, "weight")] = weights[symbol].to_numpy(dtype=float)
        result[(symbol, "trade")] = trades[symbol].to_numpy(dtype=float)
    result[("portfolio", "is_rebalance")] = portfolio["is_rebalance"].to_numpy(dtype=bool)
    result[("portfolio", "rebalance_skipped")] = portfolio["rebalance_skipped"].to_numpy(dtype=bool)
    result[("portfolio", "skip_reason")] = portfolio["skip_reason"].to_numpy(dtype=object)
    result[("portfolio", "eligible_count")] = portfolio["eligible_count"].to_numpy(dtype=int)
    return result


def generate_weight_signals(
    df: pd.DataFrame,
    params: ETFTSMOMParams | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    params = params or default_params()
    validate_inputs(df)
    symbols = panel_symbols(df)
    if params.cash_proxy not in symbols:
        raise ValueError(f"cash proxy {params.cash_proxy} is not present in the ETF panel")
    close = df.xs("close", axis=1, level=1).astype(float)
    daily_returns = close.pct_change(fill_method=None)
    momentum = close.div(close.shift(params.lookback_days)).sub(1.0)
    realized_vol = daily_returns.rolling(params.realized_vol_days).std() * np.sqrt(252)

    weights = pd.DataFrame(0.0, index=df.index, columns=symbols)
    trades = pd.DataFrame(0.0, index=df.index, columns=symbols)
    portfolio = pd.DataFrame(
        {
            "is_rebalance": False,
            "rebalance_skipped": False,
            "skip_reason": "",
            "eligible_count": 0,
        },
        index=df.index,
    )
    current = pd.Series(0.0, index=symbols)
    for i, ts in enumerate(df.index):
        is_rebalance = _is_first_trading_day_of_month(i, df.index)
        portfolio.loc[ts, "is_rebalance"] = is_rebalance
        if not is_rebalance:
            weights.loc[ts] = current
            continue
        if i <= max(params.lookback_days, params.realized_vol_days):
            portfolio.loc[ts, ["rebalance_skipped", "skip_reason"]] = [True, "insufficient_history"]
            weights.loc[ts] = current
            continue
        signal_ts = df.index[i - 1]
        signal = momentum.loc[signal_ts].replace([np.inf, -np.inf], np.nan).dropna()
        vol = realized_vol.loc[signal_ts].replace([np.inf, -np.inf], np.nan).dropna()
        eligible = signal[signal > 0.0].sort_values(ascending=False, kind="mergesort")
        portfolio.loc[ts, "eligible_count"] = int(len(eligible))
        if eligible.empty:
            target = pd.Series(0.0, index=symbols)
            target.loc[params.cash_proxy] = 1.0
        else:
            selected = list(eligible.head(params.top_k).index)
            target = _inverse_vol_weights(vol.reindex(selected), symbols)
            target = _cap_and_redistribute(target, params.max_weight)
            target = _apply_vol_target(target, vol, params)
        trade = target - current
        trades.loc[ts] = trade
        weights.loc[ts] = target
        current = target
    return weights, trades, portfolio


def _is_first_trading_day_of_month(i: int, index: pd.DatetimeIndex) -> bool:
    if i == 0:
        return True
    return (index[i].year, index[i].month) != (index[i - 1].year, index[i - 1].month)


def _inverse_vol_weights(vol: pd.Series, symbols: tuple[str, ...]) -> pd.Series:
    weights = pd.Series(0.0, index=symbols)
    inv = 1.0 / vol.replace(0.0, np.nan).dropna()
    if inv.empty:
        return weights
    weights.loc[list(inv.index)] = inv / inv.sum()
    return weights


def _cap_and_redistribute(weights: pd.Series, cap: float) -> pd.Series:
    capped = weights.copy()
    for _ in range(len(capped)):
        over = capped > cap
        if not bool(over.any()):
            break
        excess = float((capped[over] - cap).sum())
        capped[over] = cap
        under = (capped > 0.0) & (capped < cap)
        if not bool(under.any()) or excess <= 0.0:
            break
        capped.loc[under] += excess * capped.loc[under] / capped.loc[under].sum()
    return capped


def _apply_vol_target(weights: pd.Series, vol: pd.Series, params: ETFTSMOMParams) -> pd.Series:
    selected = weights[weights > 0.0]
    if selected.empty:
        return weights
    selected_vol = vol.reindex(selected.index).dropna()
    if selected_vol.empty:
        return weights
    covariance = selected_vol.pow(2)
    portfolio_vol = float(np.sqrt((selected.pow(2) * covariance.reindex(selected.index)).sum()))
    if portfolio_vol <= 0.0:
        return weights
    scalar = min(params.max_gross_exposure, params.annual_vol_target / portfolio_vol)
    return weights * scalar
