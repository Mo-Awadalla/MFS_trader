"""Frozen FTRE v1 signal construction for one USDⓈ-M perpetual."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from strategies.contract import validate_ohlcv_inputs


@dataclass(frozen=True)
class FTREParams:
    funding_threshold: float = 0.002
    oi_collapse_z_threshold: float = -2.0
    perp_discount_z_threshold: float = -1.5
    perp_taker_sell_ratio_threshold: float = 0.55
    spot_taker_buy_ratio_threshold: float = 0.50
    btc_return_60m_threshold: float = -0.01
    target_dislocation_fraction: float = 0.5
    time_stop_bars: int = 18
    spot_failure_atr_multiple: float = 1.0
    vol_stop_atr_multiple: float = 1.5
    position_size: float = 0.05


REQUIRED_COLUMNS = (
    "open", "high", "low", "close", "volume", "funding_settlement",
    "funding_rate", "oi_change_z", "perp_discount_z", "perp_taker_sell_ratio",
    "spot_taker_buy_ratio", "btc_return_60m", "perp_price_window_start",
    "spot_close", "spot_vwap_60m", "spot_atr_14", "perp_atr_14",
)


def default_params() -> FTREParams:
    return FTREParams()


def params_to_dict(params: FTREParams) -> dict[str, int | float]:
    return asdict(params)


def params_from_dict(data: dict[str, Any]) -> FTREParams:
    defaults = asdict(default_params())
    return FTREParams(**{key: data.get(key, value) for key, value in defaults.items()})


def sweep_grid() -> list[FTREParams]:
    return [default_params()]


def compact_sweep_grid() -> list[FTREParams]:
    return [default_params()]


def validate_inputs(df: pd.DataFrame) -> None:
    validate_ohlcv_inputs(df, REQUIRED_COLUMNS)
    if df.index.tz is None or str(df.index.tz) != "UTC":
        raise ValueError("FTRE inputs must use a UTC DatetimeIndex")


def trigger_mask(df: pd.DataFrame, params: FTREParams | None = None) -> pd.Series:
    """Return qualifying settlement observations; every frozen condition is strict as specified."""
    params = params or default_params()
    return (
        df["funding_settlement"].fillna(False).astype(bool)
        & (df["funding_rate"] > params.funding_threshold)
        & (df["oi_change_z"] < params.oi_collapse_z_threshold)
        & (df["perp_discount_z"] < params.perp_discount_z_threshold)
        & (df["perp_taker_sell_ratio"] > params.perp_taker_sell_ratio_threshold)
        & (df["spot_taker_buy_ratio"] >= params.spot_taker_buy_ratio_threshold)
        & (df["btc_return_60m"] > params.btc_return_60m_threshold)
    )


def dislocation(window_start_price: float, entry_price: float) -> float:
    return window_start_price - entry_price


def target_price(window_start_price: float, entry_price: float, fraction: float = 0.5) -> float:
    return entry_price + fraction * dislocation(window_start_price, entry_price)


def spot_failure_stop(spot_price: float, spot_vwap_60m: float, spot_atr_14: float) -> bool:
    return spot_price < spot_vwap_60m - spot_atr_14


def volatility_stop(perp_price: float, entry_price: float, perp_atr_14: float, multiple: float = 1.5) -> bool:
    return perp_price <= entry_price - multiple * perp_atr_14


def generate_signals(df: pd.DataFrame, params: FTREParams | None = None) -> pd.DataFrame:
    """Generate close-time decisions; consumers execute them at the next 5-minute open."""
    params = params or default_params()
    validate_inputs(df)
    out = df.copy()
    out["raw_entry"] = trigger_mask(df, params)
    out["raw_exit"] = False
    out["exit_reason"] = ""
    out["signal"] = 0
    out["position"] = 0.0
    out["entry_price"] = np.nan
    out["target_price"] = np.nan

    in_position = False
    entry = np.nan
    target = np.nan
    bars_held = 0
    for i in range(len(out)):
        if not in_position and bool(out.iloc[i]["raw_entry"]):
            # The settlement-close decision is filled at the next bar open by the runtime.
            entry = float(out.iloc[i + 1]["open"]) if i + 1 < len(out) else float(out.iloc[i]["close"])
            target = target_price(float(out.iloc[i]["perp_price_window_start"]), entry,
                                  params.target_dislocation_fraction)
            in_position = True
            bars_held = 0
            out.iat[i, out.columns.get_loc("signal")] = 1
        elif in_position:
            bars_held += 1
            row = out.iloc[i]
            reason = ""
            if float(row["high"]) >= target:
                reason = "target"
            elif spot_failure_stop(float(row["spot_close"]), float(row["spot_vwap_60m"]),
                                   float(row["spot_atr_14"])):
                reason = "spot_failure"
            elif volatility_stop(float(row["low"]), entry, float(row["perp_atr_14"]),
                                 params.vol_stop_atr_multiple):
                reason = "vol_stop"
            elif bars_held >= params.time_stop_bars:
                reason = "time_stop"
            if reason:
                out.iat[i, out.columns.get_loc("raw_exit")] = True
                out.iat[i, out.columns.get_loc("exit_reason")] = reason
                out.iat[i, out.columns.get_loc("signal")] = -1
                in_position = False
        out.iat[i, out.columns.get_loc("position")] = 1.0 if in_position else 0.0
        if in_position:
            out.iat[i, out.columns.get_loc("entry_price")] = entry
            out.iat[i, out.columns.get_loc("target_price")] = target
    return out
