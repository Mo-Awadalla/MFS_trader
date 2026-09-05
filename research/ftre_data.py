"""Point-in-time FTRE feature assembly from one-minute source-of-truth inputs."""

from __future__ import annotations

import numpy as np
import pandas as pd

from data.resample import resample_to

FIVE_MINUTES_PER_HOUR = 12
FIVE_MINUTES_PER_20_DAYS = 20 * 24 * FIVE_MINUTES_PER_HOUR


def build_ftre_features(
    *,
    perp_1m: pd.DataFrame,
    premium_index_1m: pd.DataFrame,
    spot_1m: pd.DataFrame,
    funding: pd.DataFrame,
    metrics: pd.DataFrame,
    btc_perp_1m: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build frozen v1 inputs without forward-looking joins or fabricated OI history."""
    perp = resample_to(perp_1m, "5min")
    premium = resample_to(premium_index_1m, "5min")
    spot = resample_to(spot_1m, "5min")
    btc = resample_to(btc_perp_1m, "5min") if btc_perp_1m is not None else perp
    index = perp.index.intersection(spot.index).intersection(premium.index)
    out = perp.reindex(index).copy()

    funding_values = funding["funding_rate"].copy()
    funding_values.index = funding_values.index.floor("5min")
    funding_values = funding_values[~funding_values.index.duplicated(keep="last")]
    scheduled = (funding_values.index.minute == 0) & funding_values.index.hour.isin([0, 8, 16])
    funding_values = funding_values.loc[scheduled]
    out["funding_rate"] = funding_values.reindex(index)
    out["funding_settlement"] = out["funding_rate"].notna()

    oi = metrics["open_interest"].sort_index().reindex(index, method="ffill")
    # Leave the pre-metrics era NaN. Forward fill is bounded to one 5-minute metrics interval.
    latest_metric_at_bar = pd.Series(metrics.index, index=metrics.index).reindex(index, method="ffill")
    stale = (index.to_series(index=index) - latest_metric_at_bar) > pd.Timedelta(minutes=5)
    oi = oi.mask(stale)
    oi_change = oi.pct_change(FIVE_MINUTES_PER_HOUR, fill_method=None)
    out["oi_change_z"] = _rolling_z(oi_change, FIVE_MINUTES_PER_20_DAYS)

    spot_close = spot["close"].reindex(index)
    premium_change = premium["close"].reindex(index).diff(FIVE_MINUTES_PER_HOUR)
    out["perp_discount_z"] = _rolling_z(premium_change, FIVE_MINUTES_PER_20_DAYS)
    out["perp_taker_sell_ratio"] = _taker_sell_ratio(perp).reindex(index)
    out["spot_taker_buy_ratio"] = _taker_buy_ratio(spot).reindex(index)
    out["btc_return_60m"] = btc["close"].pct_change(FIVE_MINUTES_PER_HOUR).reindex(index)
    out["perp_price_window_start"] = out["close"].shift(FIVE_MINUTES_PER_HOUR)
    out["spot_close"] = spot_close
    out["spot_vwap_60m"] = _rolling_vwap(spot).reindex(index)
    out["spot_atr_14"] = _atr(spot, 14).reindex(index)
    out["perp_atr_14"] = _atr(perp, 14).reindex(index)
    return out


def _rolling_z(values: pd.Series, window: int) -> pd.Series:
    mean = values.rolling(window, min_periods=window).mean()
    std = values.rolling(window, min_periods=window).std()
    return (values - mean) / std.replace(0.0, np.nan)


def _taker_buy_ratio(bars: pd.DataFrame) -> pd.Series:
    volume = bars["volume"].rolling(FIVE_MINUTES_PER_HOUR).sum()
    taker_buy = bars["taker_buy_volume"].rolling(FIVE_MINUTES_PER_HOUR).sum()
    return taker_buy / volume.replace(0.0, np.nan)


def _taker_sell_ratio(bars: pd.DataFrame) -> pd.Series:
    return 1.0 - _taker_buy_ratio(bars)


def _rolling_vwap(bars: pd.DataFrame) -> pd.Series:
    notional = (bars["close"] * bars["volume"]).rolling(FIVE_MINUTES_PER_HOUR).sum()
    volume = bars["volume"].rolling(FIVE_MINUTES_PER_HOUR).sum()
    return notional / volume.replace(0.0, np.nan)


def _atr(bars: pd.DataFrame, window: int) -> pd.Series:
    previous_close = bars["close"].shift(1)
    true_range = pd.concat(
        [bars["high"] - bars["low"], (bars["high"] - previous_close).abs(),
         (bars["low"] - previous_close).abs()], axis=1
    ).max(axis=1)
    return true_range.rolling(window).mean()
