"""Frozen public-data scout for cross-asset futures carry plus trend.

This module is intentionally research-only. The source panel is curated and lacks
raw volume/open-interest roll evidence, so its results cannot authorize trading.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from research.runner import compute_metrics

SOURCE_COMMIT = "883c8681cf880d83acad5c39b842403a8eac5676"
SOURCE_NORMALIZATION = (
    "Source-compatible business-day last observation. Carry price, carry contract, "
    "held price, and held contract coexist on one source timestamp; no forward filling."
)
INSTRUMENTS = (
    "SP500",
    "NASDAQ",
    "US2",
    "US5",
    "US10",
    "US20",
    "EUR",
    "JPY",
    "GBP",
    "CRUDE_W",
    "GAS_US",
    "GOLD",
    "COPPER",
    "CORN",
    "SOYBEAN",
)
ASSET_CLASSES = {
    "equity_index": ("SP500", "NASDAQ"),
    "rates": ("US2", "US5", "US10", "US20"),
    "fx": ("EUR", "JPY", "GBP"),
    "energy": ("CRUDE_W", "GAS_US"),
    "metals": ("GOLD", "COPPER"),
    "agriculture": ("CORN", "SOYBEAN"),
}
Component = Literal["carry", "trend", "combined"]


@dataclass(frozen=True)
class CrossAssetCarryTrendParams:
    """Parameters frozen in CrossAssetCarryTrendScout-v1."""

    start: str = "2010-01-04"
    end: str = "2024-03-28"
    trend_lookback_days: int = 252
    vol_lookback_days: int = 63
    vol_min_periods: int = 42
    target_volatility: float = 0.10
    min_active_markets: int = 8
    max_market_notional: float = 0.35
    max_gross_notional: float = 3.0
    execution_lag_sessions: int = 2
    default_cost_bps: float = 2.0
    overlay_primary_scale: float = 0.50
    overlay_diagnostic_scale: float = 0.20


@dataclass
class FuturesScoutPath:
    """One component/cost simulation path."""

    component: str
    cost_bps: float
    returns: pd.Series
    gross_returns: pd.Series
    costs: pd.Series
    equity: pd.Series
    point_exposure: pd.DataFrame
    notional_exposure: pd.DataFrame
    market_gross_returns: pd.DataFrame
    market_costs: pd.DataFrame
    active_markets: pd.Series
    turnover: pd.Series
    roll_count: int
    rebalance_count: int
    signal_calendar: pd.DatetimeIndex


@dataclass
class CrossAssetCarryTrendScoutReport:
    """Serializable output from the one frozen scout."""

    strategy_name: str
    source_commit: str
    params: dict[str, Any]
    analysis_start: str
    analysis_end: str
    component_metrics: dict[str, dict[str, dict[str, float]]]
    subperiod_metrics: dict[str, dict[str, float]]
    asset_class_diagnostics: dict[str, Any]
    leave_one_asset_class_out: dict[str, dict[str, float]]
    cost_sensitivity_bps: dict[str, dict[str, float]]
    spy_metrics: dict[str, float]
    overlay_metrics: dict[str, dict[str, float]]
    portfolio_diagnostics: dict[str, float]
    monthly_concentration: dict[str, float]
    gates: dict[str, bool]
    scout_passed: bool
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def contract_month_gap(price_contract: pd.Series, carry_contract: pd.Series) -> pd.Series:
    """Return signed carry-minus-price maturity spacing in whole months."""

    price = pd.to_numeric(price_contract, errors="coerce")
    carry = pd.to_numeric(carry_contract, errors="coerce")

    def decode(values: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
        rounded = values.round()
        integer = rounded.astype("Int64")
        year = integer // 10_000
        month = (integer // 100) % 100
        valid = (
            values.notna()
            & np.isclose(values, rounded, equal_nan=False)
            & integer.mod(100).eq(0)
            & year.between(1900, 2100)
            & month.between(1, 12)
        )
        return year.astype(float), month.astype(float), valid

    price_year, price_month, price_valid = decode(price)
    carry_year, carry_month, carry_valid = decode(carry)
    gap = (carry_year * 12.0 + carry_month) - (price_year * 12.0 + price_month)
    valid = price_valid & carry_valid & gap.ne(0.0) & gap.abs().le(24.0)
    return gap.where(valid)


def build_market_features(
    frame: pd.DataFrame,
    params: CrossAssetCarryTrendParams,
) -> pd.DataFrame:
    """Build frozen carry, trend, point-P&L, and risk features for one market."""

    required = {
        "CARRY",
        "CARRY_CONTRACT",
        "PRICE",
        "PRICE_CONTRACT",
        "ADJUSTED",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"market frame is missing columns: {sorted(missing)}")

    data = frame.copy()
    data.index = pd.DatetimeIndex(data.index).tz_localize(None).normalize()
    data = data.loc[~data.index.duplicated(keep="last")].sort_index()
    for column in required:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=["ADJUSTED"])

    gap = contract_month_gap(data["PRICE_CONTRACT"], data["CARRY_CONTRACT"])
    carry_points = (data["PRICE"] - data["CARRY"]) / (gap / 12.0)
    carry_signal = np.sign(carry_points).where(carry_points.notna())

    point_change = data["ADJUSTED"].diff()
    trend_points = data["ADJUSTED"] - data["ADJUSTED"].shift(params.trend_lookback_days)
    trend_signal = np.sign(trend_points).where(trend_points.notna())
    point_volatility = (
        point_change.rolling(
            params.vol_lookback_days,
            min_periods=params.vol_min_periods,
        ).std()
        * np.sqrt(252.0)
    )
    point_volatility = point_volatility.where(point_volatility > 0.0)

    combined_signal = (0.5 * carry_signal + 0.5 * trend_signal).where(
        carry_signal.notna() & trend_signal.notna()
    )
    return pd.DataFrame(
        {
            "price": data["PRICE"],
            "price_contract": data["PRICE_CONTRACT"],
            "carry_contract": data["CARRY_CONTRACT"],
            "month_gap": gap,
            "annualized_carry_points": carry_points,
            "carry_signal": carry_signal,
            "trend_points": trend_points,
            "trend_signal": trend_signal,
            "combined_signal": combined_signal,
            "point_change": point_change,
            "point_volatility": point_volatility,
        },
        index=data.index,
    )


def _scale_point_exposures(
    signals: pd.Series,
    volatility: pd.Series,
    prices: pd.Series,
    *,
    target_volatility: float,
    max_market_notional: float,
    max_gross_notional: float,
) -> pd.Series:
    """Convert directional signals to capped point exposure per dollar of equity."""

    signals = pd.to_numeric(signals, errors="coerce")
    volatility = pd.to_numeric(volatility, errors="coerce")
    prices = pd.to_numeric(prices, errors="coerce")
    valid = signals.notna() & volatility.gt(0.0) & prices.notna() & prices.ne(0.0)
    active = signals.where(valid).dropna()
    signal_norm = float(np.sqrt(np.square(active).sum()))
    output = pd.Series(0.0, index=signals.index, dtype=float)
    if signal_norm == 0.0:
        return output

    raw = target_volatility * active / (volatility.loc[active.index] * signal_norm)
    market_cap = max_market_notional / prices.loc[active.index].abs()
    output.loc[active.index] = raw.clip(lower=-market_cap, upper=market_cap)
    gross = float((output * prices).abs().sum())
    if gross > max_gross_notional:
        output *= max_gross_notional / gross
    return output


def _transition_turnover_by_market(
    old_exposure: pd.Series,
    new_exposure: pd.Series,
    old_price: pd.Series,
    new_price: pd.Series,
    contract_changed: pd.Series,
) -> pd.Series:
    """Return one-way notional turnover, charging both legs on contract rolls."""

    indexes = old_exposure.index
    old_exposure = old_exposure.reindex(indexes).fillna(0.0)
    new_exposure = new_exposure.reindex(indexes).fillna(0.0)
    old_price = old_price.reindex(indexes).abs().fillna(0.0)
    new_price = new_price.reindex(indexes).abs().fillna(0.0)
    changed = contract_changed.reindex(indexes).fillna(False).astype(bool)
    ordinary = (new_exposure - old_exposure).abs() * new_price
    rolled = old_exposure.abs() * old_price + new_exposure.abs() * new_price
    return ordinary.where(~changed, rolled)


def _transition_turnover(
    old_exposure: pd.Series,
    new_exposure: pd.Series,
    old_price: pd.Series,
    new_price: pd.Series,
    contract_changed: pd.Series,
) -> float:
    return float(
        _transition_turnover_by_market(
            old_exposure,
            new_exposure,
            old_price,
            new_price,
            contract_changed,
        ).sum()
    )


def _common_calendar(features: dict[str, pd.DataFrame], params: CrossAssetCarryTrendParams) -> pd.DatetimeIndex:
    calendar: pd.DatetimeIndex | None = None
    for frame in features.values():
        index = pd.DatetimeIndex(frame.loc[params.start : params.end].index)
        calendar = index if calendar is None else calendar.intersection(index)
    if calendar is None or calendar.empty:
        raise ValueError("no common futures calendar in the frozen analysis window")
    return calendar.sort_values()


def _union_calendar(
    features: dict[str, pd.DataFrame],
    params: CrossAssetCarryTrendParams,
) -> pd.DatetimeIndex:
    calendar = pd.DatetimeIndex([])
    for frame in features.values():
        index = pd.DatetimeIndex(frame.loc[params.start : params.end].index)
        calendar = calendar.union(index)
    if calendar.empty:
        raise ValueError("no futures observations in the frozen analysis window")
    return calendar.sort_values()


def _target_schedule(
    features: dict[str, pd.DataFrame],
    params: CrossAssetCarryTrendParams,
    component: Component,
    calendar: pd.DatetimeIndex,
    signal_calendar: pd.DatetimeIndex,
) -> tuple[pd.DatetimeIndex, pd.DataFrame, pd.Series]:
    markets = sorted(features)
    signal_column = f"{component}_signal"
    schedule = pd.DataFrame(np.nan, index=calendar, columns=markets, dtype=float)
    rebalance = pd.Series(False, index=calendar, dtype=bool)
    known_month_ends = pd.date_range(
        signal_calendar.min(),
        signal_calendar.max(),
        freq="BME",
    )
    rebalance_dates = signal_calendar.intersection(known_month_ends)

    for signal_date in rebalance_dates:
        signal_location = signal_calendar.get_loc(signal_date)
        execution_location = signal_location + params.execution_lag_sessions
        if execution_location >= len(signal_calendar):
            continue
        execution_date = signal_calendar[execution_location]
        signals = pd.Series(
            {market: features[market].at[signal_date, signal_column] for market in markets},
            dtype=float,
        )
        volatility = pd.Series(
            {market: features[market].at[signal_date, "point_volatility"] for market in markets},
            dtype=float,
        )
        prices = pd.Series(
            {market: features[market].at[signal_date, "price"] for market in markets},
            dtype=float,
        )
        eligible = signals.notna() & volatility.gt(0.0) & prices.notna()
        if int(eligible.sum()) < params.min_active_markets:
            target = pd.Series(0.0, index=markets)
        else:
            target = _scale_point_exposures(
                signals.where(eligible),
                volatility,
                prices,
                target_volatility=params.target_volatility,
                max_market_notional=params.max_market_notional,
                max_gross_notional=params.max_gross_notional,
            )
        schedule.loc[execution_date] = target
        rebalance.loc[execution_date] = True
    return calendar, schedule, rebalance


def simulate_component(
    panels: dict[str, pd.DataFrame],
    params: CrossAssetCarryTrendParams,
    *,
    component: Component,
    cost_bps: float,
    calendar_override: pd.DatetimeIndex | None = None,
    signal_calendar_override: pd.DatetimeIndex | None = None,
) -> FuturesScoutPath:
    """Simulate one frozen signal component using recursive point exposure."""

    if cost_bps < 0.0:
        raise ValueError("cost_bps must be non-negative")
    features = {market: build_market_features(frame, params) for market, frame in panels.items()}
    calendar = (
        _union_calendar(features, params)
        if calendar_override is None
        else pd.DatetimeIndex(calendar_override).sort_values()
    )
    signal_calendar = (
        _common_calendar(features, params)
        if signal_calendar_override is None
        else pd.DatetimeIndex(signal_calendar_override).sort_values()
    )
    calendar, schedule, rebalance = _target_schedule(
        features,
        params,
        component,
        calendar,
        signal_calendar,
    )
    markets = sorted(features)

    def matrix(column: str) -> pd.DataFrame:
        return pd.DataFrame(
            {market: features[market][column].reindex(calendar) for market in markets},
            index=calendar,
        )

    point_change = matrix("point_change")
    price = matrix("price")
    contract = matrix("price_contract")
    exposures = pd.DataFrame(0.0, index=calendar, columns=markets)
    notionals = pd.DataFrame(0.0, index=calendar, columns=markets)
    market_gross = pd.DataFrame(0.0, index=calendar, columns=markets)
    market_cost = pd.DataFrame(0.0, index=calendar, columns=markets)
    gross_returns = pd.Series(0.0, index=calendar)
    costs = pd.Series(0.0, index=calendar)
    net_returns = pd.Series(0.0, index=calendar)
    turnover = pd.Series(0.0, index=calendar)
    active_markets = pd.Series(0, index=calendar, dtype=int)
    equity = pd.Series(1.0, index=calendar)

    state = pd.Series(0.0, index=markets)
    previous_price = pd.Series(float("nan"), index=markets)
    previous_contract = pd.Series(float("nan"), index=markets)
    roll_count = 0
    equity_value = 1.0

    for date in calendar:
        observed_price = price.loc[date]
        observed_contract = contract.loc[date]
        # These are held-position state variables, not forward-filled signal inputs.
        current_price = observed_price.combine_first(previous_price)
        current_contract = observed_contract.combine_first(previous_contract)
        changed = (
            observed_contract.notna()
            & previous_contract.notna()
            & observed_contract.ne(previous_contract)
        )
        if bool((changed & observed_price.isna()).any()):
            raise ValueError(f"contract roll lacks an observed price on {date.date()}")
        entering_state = state.copy()
        if bool(rebalance.loc[date]):
            desired = schedule.loc[date].fillna(0.0)
            turnover_by_market = _transition_turnover_by_market(
                state,
                desired,
                previous_price,
                current_price,
                changed,
            )
            state = desired
        elif bool(changed.any()):
            turnover_by_market = _transition_turnover_by_market(
                state,
                state,
                previous_price,
                current_price,
                changed,
            )
        else:
            turnover_by_market = pd.Series(0.0, index=markets)

        roll_count += int((changed & entering_state.ne(0.0)).sum())
        cost_by_market = turnover_by_market * (cost_bps / 10_000.0)
        pnl_by_market = state * point_change.loc[date].fillna(0.0)
        gross_return = float(pnl_by_market.sum())
        cost = float(cost_by_market.sum())
        net_return = gross_return - cost
        if 1.0 + net_return <= 0.0:
            raise ValueError(f"strategy equity became non-positive on {date.date()}")

        exposures.loc[date] = state
        notionals.loc[date] = state * current_price
        market_gross.loc[date] = pnl_by_market
        market_cost.loc[date] = cost_by_market
        gross_returns.loc[date] = gross_return
        costs.loc[date] = cost
        net_returns.loc[date] = net_return
        turnover.loc[date] = float(turnover_by_market.sum())
        active_markets.loc[date] = int(state.ne(0.0).sum())
        equity_value *= 1.0 + net_return
        equity.loc[date] = equity_value

        state = state / (1.0 + net_return)
        previous_price = current_price
        previous_contract = current_contract

    return FuturesScoutPath(
        component=component,
        cost_bps=cost_bps,
        returns=net_returns,
        gross_returns=gross_returns,
        costs=costs,
        equity=equity,
        point_exposure=exposures,
        notional_exposure=notionals,
        market_gross_returns=market_gross,
        market_costs=market_cost,
        active_markets=active_markets,
        turnover=turnover,
        roll_count=roll_count,
        rebalance_count=int(rebalance.sum()),
        signal_calendar=signal_calendar,
    )


def load_public_panels(data_dir: Path) -> dict[str, pd.DataFrame]:
    """Load the exact pinned 15-market normalized public artifact."""

    import json

    manifest_path = data_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("source_commit") != SOURCE_COMMIT:
        raise ValueError("public futures source commit does not match frozen specification")
    if manifest.get("normalization") != SOURCE_NORMALIZATION:
        raise ValueError("public futures normalization does not match frozen specification")
    manifest_markets = {item["instrument"] for item in manifest.get("instruments", [])}
    if manifest_markets != set(INSTRUMENTS):
        raise ValueError("public futures manifest universe does not match frozen specification")

    panels: dict[str, pd.DataFrame] = {}
    for market in INSTRUMENTS:
        path = data_dir / "daily" / f"{market}.parquet"
        frame = pd.read_parquet(path)
        frame.index = pd.DatetimeIndex(frame.index).tz_localize(None).normalize()
        panels[market] = frame.loc[~frame.index.duplicated(keep="last")].sort_index()
    return panels


def _path_metrics(path: FuturesScoutPath) -> dict[str, float]:
    return _return_metrics(path.returns)


def _return_metrics(returns: pd.Series) -> dict[str, float]:
    clean = returns.fillna(0.0).astype(float)
    if clean.empty:
        return {
            "total_return": 0.0,
            "cagr": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_drawdown": 0.0,
            "ann_volatility": 0.0,
            "win_rate": 0.0,
            "total_bars": 0.0,
            "final_equity": 10_000.0,
            "annualized_return": 0.0,
        }
    equity = (1.0 + clean).cumprod() * 10_000.0
    metrics = compute_metrics(clean, equity, 10_000.0)
    metrics["annualized_return"] = float(clean.mean() * 252.0)
    return metrics
