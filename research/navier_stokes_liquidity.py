"""Liquidity-concentration features for event-level top-of-book data.

The module deliberately calls these quantities *proxies*.  MBP-1 observes every
event affecting the best level, but it does not observe the full price-space
liquidity profile required for literal spatial derivatives or core widths.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pandas as pd

BASELINE_FEATURES = [
    "spread_bps_mean",
    "spread_bps_last",
    "top_depth_mean",
    "top_depth_min",
    "top_imbalance_mean",
    "top_imbalance_last",
    "pre_realized_vol_bps",
    "gross_trade_volume",
    "signed_trade_imbalance",
    "event_rate_per_second",
]

CONCENTRATION_FEATURES = [
    "u_linf_l2",
    "u_l4_l2",
    "u_l8_l2",
    "u_shear_max",
    "u_enstrophy",
    "u_core_fraction",
    "max_price_sensitivity",
    "gross_to_net_flow",
    "opposing_flow_stress",
    "spectral_cascade_ratio",
    "reynolds_proxy",
]


def _lp(values: np.ndarray, order: float) -> float:
    clean = np.abs(values[np.isfinite(values)])
    if clean.size == 0:
        return 0.0
    if math.isinf(order):
        return float(clean.max())
    return float(np.mean(clean**order) ** (1.0 / order))


def _safe_ratio(numerator: float, denominator: float, epsilon: float = 1e-12) -> float:
    return float(numerator / max(abs(denominator), epsilon))


def _spectral_ratio(values: np.ndarray) -> float:
    """Power at periods <=10s divided by power at periods >=30s."""
    if len(values) < 60 or not np.isfinite(values).all():
        return 0.0
    centered = values - values.mean()
    power = np.abs(np.fft.rfft(centered)) ** 2
    frequency = np.fft.rfftfreq(len(centered), d=1.0)
    high = power[frequency >= 0.1].sum()
    low = power[(frequency > 0.0) & (frequency <= 1.0 / 30.0)].sum()
    return _safe_ratio(float(high), float(low))


def concentration_features(
    snapshots: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    event_count: int,
    duration_seconds: int,
) -> dict[str, float]:
    """Calculate baseline and concentration proxies on one fixed signal window.

    ``snapshots`` must be one-second, forward-filled BBO states. Trade ``side``
    follows Databento semantics: B is a buy aggressor and A a sell aggressor.
    """
    required = {"bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00"}
    missing = required.difference(snapshots.columns)
    if missing:
        raise ValueError(f"snapshots missing columns: {sorted(missing)}")
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")

    state = snapshots.copy()
    bid = pd.to_numeric(state["bid_px_00"], errors="coerce")
    ask = pd.to_numeric(state["ask_px_00"], errors="coerce")
    bid_size = pd.to_numeric(state["bid_sz_00"], errors="coerce")
    ask_size = pd.to_numeric(state["ask_sz_00"], errors="coerce")
    valid = (bid > 0) & (ask >= bid) & (bid_size >= 0) & (ask_size >= 0)
    state = state.loc[valid]
    if len(state) < max(30, duration_seconds // 2):
        raise ValueError("insufficient valid one-second BBO snapshots")

    bid = pd.to_numeric(state["bid_px_00"])
    ask = pd.to_numeric(state["ask_px_00"])
    bid_size = pd.to_numeric(state["bid_sz_00"])
    ask_size = pd.to_numeric(state["ask_sz_00"])
    midpoint = (bid + ask) / 2.0
    depth = bid_size + ask_size
    imbalance = (bid_size - ask_size) / depth.replace(0, np.nan)
    spread_bps = 10_000.0 * (ask - bid) / midpoint

    flow = pd.DataFrame(0.0, index=state.index, columns=["buy", "sell"])
    if not trades.empty:
        needed = {"ts_recv", "side", "size"}
        missing_trades = needed.difference(trades.columns)
        if missing_trades:
            raise ValueError(f"trades missing columns: {sorted(missing_trades)}")
        trade_frame = trades.copy()
        trade_frame["ts_recv"] = pd.to_datetime(trade_frame["ts_recv"], utc=True)
        trade_frame["second"] = trade_frame["ts_recv"].dt.floor("s")
        trade_frame["size"] = pd.to_numeric(trade_frame["size"], errors="coerce").fillna(0.0)
        for side, column in (("B", "buy"), ("A", "sell")):
            totals = trade_frame.loc[trade_frame["side"] == side].groupby("second")["size"].sum()
            flow[column] = totals.reindex(flow.index, fill_value=0.0)

    signed_flow = flow["buy"] - flow["sell"]
    gross_flow = flow["buy"] + flow["sell"]
    safe_depth = depth.replace(0, np.nan)
    velocity = (signed_flow / safe_depth).fillna(0.0).to_numpy(dtype=float)
    l2 = _lp(velocity, 2.0)
    shear = np.diff(velocity)
    participation = _safe_ratio(float(np.abs(velocity).sum()) ** 2, float(np.square(velocity).sum()))
    core_fraction = min(1.0, participation / max(len(velocity), 1))

    midpoint_change_bps = 10_000.0 * np.log(midpoint).diff().abs()
    normalized_gross = gross_flow / safe_depth
    sensitivity = midpoint_change_bps / normalized_gross.replace(0, np.nan)

    relative_depth_change = depth.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    replenish_rate = relative_depth_change.clip(lower=0).median()
    replenish_rate = float(replenish_rate) if pd.notna(replenish_rate) else 0.0
    reynolds = _safe_ratio(l2 * core_fraction, replenish_rate)

    midpoint_log_change = np.diff(np.log(midpoint.to_numpy(dtype=float))) * 10_000.0
    gross = float(gross_flow.sum())
    net = float(signed_flow.sum())
    opposing = np.sqrt(flow["buy"] * flow["sell"]) / safe_depth
    return {
        "spread_bps_mean": float(spread_bps.mean()),
        "spread_bps_last": float(spread_bps.iloc[-1]),
        "top_depth_mean": float(depth.mean()),
        "top_depth_min": float(depth.min()),
        "top_imbalance_mean": float(imbalance.mean()),
        "top_imbalance_last": float(imbalance.iloc[-1]),
        "pre_realized_vol_bps": float(np.sqrt(np.square(midpoint_log_change).sum())),
        "gross_trade_volume": gross,
        "signed_trade_imbalance": _safe_ratio(net, gross),
        "event_rate_per_second": float(event_count / duration_seconds),
        "u_linf_l2": _safe_ratio(_lp(velocity, math.inf), l2),
        "u_l4_l2": _safe_ratio(_lp(velocity, 4.0), l2),
        "u_l8_l2": _safe_ratio(_lp(velocity, 8.0), l2),
        "u_shear_max": float(np.abs(shear).max()) if shear.size else 0.0,
        "u_enstrophy": float(np.square(shear).mean()) if shear.size else 0.0,
        "u_core_fraction": core_fraction,
        "max_price_sensitivity": float(sensitivity.replace([np.inf, -np.inf], np.nan).max())
        if sensitivity.notna().any()
        else 0.0,
        "gross_to_net_flow": _safe_ratio(gross, abs(net) + 1.0),
        "opposing_flow_stress": float(opposing.fillna(0.0).mean()),
        "spectral_cascade_ratio": _spectral_ratio(velocity),
        "reynolds_proxy": reynolds,
    }


def future_jump_outcomes(snapshots: pd.DataFrame) -> dict[str, float]:
    """Absolute end displacement and maximum excursion from the first midpoint."""
    bid = pd.to_numeric(snapshots["bid_px_00"], errors="coerce")
    ask = pd.to_numeric(snapshots["ask_px_00"], errors="coerce")
    midpoint = ((bid + ask) / 2.0).where((bid > 0) & (ask >= bid)).dropna()
    if len(midpoint) < 2:
        raise ValueError("insufficient valid outcome snapshots")
    path_bps = 10_000.0 * np.log(midpoint / midpoint.iloc[0])
    return {
        "future_abs_return_bps": float(abs(path_bps.iloc[-1])),
        "future_max_excursion_bps": float(path_bps.abs().max()),
    }


def second_snapshots(
    frame: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    columns: Sequence[str] = ("bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00"),
) -> pd.DataFrame:
    """Create causally available one-second states on ``[start, end)``."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")
    work = frame.copy()
    work["ts_recv"] = pd.to_datetime(work["ts_recv"], utc=True)
    work = work.loc[work["ts_recv"] < end, ["ts_recv", *columns]].sort_values("ts_recv")
    if work.empty:
        return pd.DataFrame(columns=columns)
    work = work.set_index("ts_recv").resample("1s").last().ffill()
    wanted = pd.date_range(start=start.floor("s"), end=end.floor("s"), freq="1s", inclusive="left")
    return work.reindex(wanted).ffill()
