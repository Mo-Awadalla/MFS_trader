"""Causal, payoff-aware BTC research model, version 2.

Version 1 is kept intact for reproduction. This module separates decision-time
features, realized targets, model fitting, economic proposals, and admission.
It has no exchange client or order-submission capability.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

BAR_DELTA = pd.Timedelta(minutes=5)
LOOKBACK_BARS = 289
FEATURE_COLUMNS = (
    "log_return_1_bar",
    "log_return_3_bars",
    "log_return_6_bars",
    "log_return_12_bars",
    "log_range_1_bar",
    "volume_zscore_288_bars",
    "taker_flow_1_bar",
    "taker_flow_3_bar_mean",
    "realized_vol_12_bars",
    "realized_vol_288_bars",
    "flow_return_interaction",
    "open_interest_log_change_12_bars",
    "open_interest_log_change_48_bars",
    "oi_12_missing",
    "oi_48_missing",
)
OPTIONAL_COLUMNS = FEATURE_COLUMNS[11:13]
CORE_COLUMNS = FEATURE_COLUMNS[:11]


def validate_bars(bars: pd.DataFrame) -> pd.DataFrame:
    numeric = ["open", "high", "low", "close", "volume", "trade_count", "taker_buy_base_volume"]
    missing = {"open_time", *numeric}.difference(bars.columns)
    if missing:
        raise ValueError(f"missing bar columns: {sorted(missing)}")
    b = bars.copy()
    b["open_time"] = pd.to_datetime(b["open_time"], utc=True, errors="raise").astype(
        "datetime64[ns, UTC]"
    )
    if b.open_time.isna().any() or b.open_time.duplicated().any():
        raise ValueError("bar timestamps must be present and unique")
    if not b.open_time.eq(b.open_time.dt.floor("5min")).all():
        raise ValueError("bars must lie on the five-minute grid")
    b[numeric] = b[numeric].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(b[numeric].to_numpy(dtype=float)).all():
        raise ValueError("bar values must be finite")
    if b[["open", "high", "low", "close"]].le(0).any().any():
        raise ValueError("prices must be positive")
    if (b.high < b[["open", "close", "low"]].max(axis=1)).any() or (
        b.low > b[["open", "close", "high"]].min(axis=1)
    ).any():
        raise ValueError("inconsistent OHLC prices")
    if b[["volume", "trade_count", "taker_buy_base_volume"]].lt(0).any().any():
        raise ValueError("volume and trade counts must be nonnegative")
    if (b.taker_buy_base_volume > b.volume).any():
        raise ValueError("taker buy volume exceeds total volume")
    if not b.trade_count.eq(np.floor(b.trade_count)).all():
        raise ValueError("trade counts must be whole numbers")
    return b.sort_values("open_time", kind="stable").reset_index(drop=True)


def validate_metrics(metrics: pd.DataFrame | None) -> pd.DataFrame:
    if metrics is None:
        return pd.DataFrame(
            {
                "create_time": pd.Series(dtype="datetime64[ns, UTC]"),
                "sum_open_interest": pd.Series(dtype=float),
            }
        )
    if not {"create_time", "sum_open_interest"}.issubset(metrics.columns):
        raise ValueError("optional OI input requires create_time and sum_open_interest")
    m = metrics[["create_time", "sum_open_interest"]].copy()
    m["create_time"] = pd.to_datetime(m.create_time, utc=True, errors="raise").astype(
        "datetime64[ns, UTC]"
    )
    if m.create_time.isna().any() or m.create_time.duplicated().any():
        raise ValueError("metric timestamps must be present and unique")
    m["sum_open_interest"] = pd.to_numeric(m.sum_open_interest, errors="raise")
    if np.isinf(m.sum_open_interest.to_numpy(dtype=float)).any():
        raise ValueError("OI must not be infinite")
    # Null/zero OI means unavailable, not a reason to remove price observations.
    m["sum_open_interest"] = m.sum_open_interest.where(m.sum_open_interest > 0)
    return m.sort_values("create_time", kind="stable").reset_index(drop=True)


def build_decisions(bars: pd.DataFrame, metrics: pd.DataFrame | None = None) -> pd.DataFrame:
    """Features at bar-close time; no current/future candle or outcome is required.

    The row for t uses bars completed by t, ending with the candle opened at
    t-5 minutes. The final returned decision can be predicted before its target
    candle exists. Optional OI stays null with flags until training-only imputation.
    """
    b = validate_bars(bars)
    m = validate_metrics(metrics)
    times = b.open_time + BAR_DELTA
    log_close = np.log(b.close)
    returns = log_close.diff()
    flow = 2 * b.taker_buy_base_volume / b.volume.replace(0, np.nan) - 1
    f = pd.DataFrame({"open_time": times})
    for n in (1, 3, 6, 12):
        col = f"log_return_{n}_bar" if n == 1 else f"log_return_{n}_bars"
        f[col] = log_close.diff(n)
    f["log_range_1_bar"] = np.log(b.high / b.low)
    v = np.log1p(b.volume)
    f["volume_zscore_288_bars"] = (v - v.rolling(288, min_periods=288).mean()) / (
        v.rolling(288, min_periods=288).std(ddof=1).replace(0, np.nan)
    )
    f["taker_flow_1_bar"] = flow
    f["taker_flow_3_bar_mean"] = flow.rolling(3, min_periods=3).mean()
    f["realized_vol_12_bars"] = returns.rolling(12, min_periods=12).std(ddof=1)
    f["realized_vol_288_bars"] = returns.rolling(288, min_periods=288).std(ddof=1)
    f["flow_return_interaction"] = flow * returns
    left = pd.DataFrame({"open_time": times, "cutoff": times - BAR_DELTA})
    joined = pd.merge_asof(
        left, m, left_on="cutoff", right_on="create_time", direction="backward", tolerance=BAR_DELTA
    )
    available = (joined.open_time - joined.create_time).between(BAR_DELTA, 2 * BAR_DELTA)
    oi = np.log(joined.sum_open_interest.where(available))
    for n in (12, 48):
        col = f"open_interest_log_change_{n}_bars"
        f[col] = oi.diff(n)
        f[f"oi_{n}_missing"] = f[col].isna().astype(float)
    # Longest volatility feature uses 289 closes, so all 288 transitions matter.
    continuous = (
        b.open_time.diff()
        .eq(BAR_DELTA)
        .rolling(LOOKBACK_BARS - 1, min_periods=LOOKBACK_BARS - 1)
        .sum()
        .eq(LOOKBACK_BARS - 1)
    )
    eligible = continuous & np.isfinite(f[list(CORE_COLUMNS)].to_numpy(dtype=float)).all(axis=1)
    return f.loc[eligible, ["open_time", *FEATURE_COLUMNS]].reset_index(drop=True)


def attach_targets(decisions: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """Keep every decision; unavailable realized targets remain null, never filtered."""
    b = validate_bars(bars).set_index("open_time")
    frame = decisions.copy()
    entry_t = pd.DatetimeIndex(frame.open_time)
    exit_t = entry_t + BAR_DELTA
    entry = b.open.reindex(entry_t).to_numpy(dtype=float)
    exit_ = b.open.reindex(exit_t).to_numpy(dtype=float)
    frame["target_end"] = exit_t
    frame["target_return"] = exit_ / entry - 1
    frame["target_up"] = pd.array(
        np.where(np.isfinite(frame.target_return), frame.target_return.gt(0).astype(float), np.nan),
        dtype="Int64",
    )
    return frame


def chronological_partition(
    frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    """Fit only on labels realized strictly before the next partition boundary."""
    return frame.loc[
        (frame.open_time >= start)
        & (frame.open_time < end)
        & (frame.target_end < end)
        & frame.target_return.notna()
    ].reset_index(drop=True)


@dataclass(frozen=True)
class FitWindows:
    training_start: pd.Timestamp
    calibration_start: pd.Timestamp
    admission_start: pd.Timestamp
    update_time: pd.Timestamp


def fit_windows(update_time: pd.Timestamp) -> FitWindows:
    update_time = pd.Timestamp(update_time)
    if update_time.tz is None:
        raise ValueError("update time must have a timezone")
    update_time = update_time.tz_convert("UTC")
    if (
        update_time.day != 1
        or update_time.month not in (1, 4, 7, 10)
        or update_time != update_time.normalize()
    ):
        raise ValueError("updates must occur at a UTC calendar quarter start")
    admission_start = update_time - pd.DateOffset(months=1)
    calibration_start = admission_start - pd.DateOffset(months=2)
    return FitWindows(
        calibration_start - pd.DateOffset(months=24),
        calibration_start,
        admission_start,
        update_time,
    )


class PayoffAwareBitcoinModel:
    """Predict direction and conditional win/loss size with disjoint calibration."""

    def __init__(self) -> None:
        self.preprocessing = make_pipeline(
            SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler()
        )
        self.direction = LogisticRegression(C=0.1, max_iter=1000, random_state=42)
        self.calibrator = LogisticRegression(C=1, max_iter=1000)
        self.win_size = Ridge(alpha=100)
        self.loss_size = Ridge(alpha=100)
        self.magnitude_scales = np.ones(2)
        self.fitted = False
        self.last_calibration_target: pd.Timestamp | None = None

    @staticmethod
    def _check_features(frame: pd.DataFrame) -> None:
        if not {"open_time", *FEATURE_COLUMNS}.issubset(frame.columns):
            raise ValueError("missing model feature columns")
        if frame.open_time.isna().any() or frame.open_time.duplicated().any():
            raise ValueError("decision timestamps must be present and unique")
        values = frame[list(FEATURE_COLUMNS)].to_numpy(dtype=float)
        if (
            np.isinf(values).any()
            or not np.isfinite(frame[list(CORE_COLUMNS)].to_numpy(dtype=float)).all()
        ):
            raise ValueError("core features must be finite; only optional OI may be missing")
        if not np.isfinite(frame[["oi_12_missing", "oi_48_missing"]].to_numpy(dtype=float)).all():
            raise ValueError("missingness flags must be finite")
        for n in (12, 48):
            if (
                not frame[f"oi_{n}_missing"]
                .eq(frame[f"open_interest_log_change_{n}_bars"].isna().astype(float))
                .all()
            ):
                raise ValueError("missingness flag disagrees with optional feature")

    def fit(self, training: pd.DataFrame, calibration: pd.DataFrame) -> PayoffAwareBitcoinModel:
        self.fitted = False
        for frame in (training, calibration):
            if not {"target_end", "target_return"}.issubset(frame.columns):
                raise ValueError("fitting requires realized target columns")
            self._check_features(frame)
            if frame.empty or not np.isfinite(frame.target_return.to_numpy(dtype=float)).all():
                raise ValueError("fitting requires nonempty, realized finite targets")
            if not (frame.target_end - frame.open_time).eq(BAR_DELTA).all():
                raise ValueError("targets must end exactly five minutes after the decision")
            if frame.target_return.le(-1).any():
                raise ValueError("positive reference prices cannot lose 100% or more")
            if (frame.target_return > 0).nunique() < 2:
                raise ValueError("both positive and nonpositive outcomes are required")
        if training.target_end.max() >= calibration.open_time.min():
            raise ValueError("training labels overlap calibration decisions")
        z = self.preprocessing.fit_transform(training[list(FEATURE_COLUMNS)])
        cz = self.preprocessing.transform(calibration[list(FEATURE_COLUMNS)])
        y = training.target_return.to_numpy(dtype=float)
        cy = calibration.target_return.to_numpy(dtype=float)
        positive = y > 0
        self.direction.fit(z, positive.astype(int))
        self.calibrator.fit(
            self.direction.decision_function(cz).reshape(-1, 1), (cy > 0).astype(int)
        )
        self.win_size.fit(z[positive], y[positive] * 1e4)
        self.loss_size.fit(z[~positive], -y[~positive] * 1e4)
        for i, (estimator, selected) in enumerate(
            ((self.win_size, cy > 0), (self.loss_size, cy <= 0))
        ):
            magnitude = np.maximum(estimator.predict(cz[selected]), 0)
            expected_mean = float(magnitude.mean())
            actual_mean = float(np.abs(cy[selected]).mean() * 1e4)
            if expected_mean <= 0 and actual_mean > 0:
                raise ValueError("conditional magnitude model cannot be calibrated")
            self.magnitude_scales[i] = actual_mean / expected_mean if expected_mean > 0 else 0
        self.last_calibration_target = calibration.target_end.max()
        self.fitted = True
        return self

    def predict(self, decisions: pd.DataFrame) -> pd.DataFrame:
        if not self.fitted:
            raise RuntimeError("model is not fitted")
        self._check_features(decisions)
        if decisions.empty:
            return pd.DataFrame(
                columns=[
                    "open_time",
                    "p_up",
                    "expected_win_bps",
                    "expected_loss_bps",
                    "expected_return_bps",
                ]
            )
        if decisions.open_time.min() <= self.last_calibration_target:
            raise ValueError("forecast decisions must occur after the calibration labels")
        z = self.preprocessing.transform(decisions[list(FEATURE_COLUMNS)])
        p = self.calibrator.predict_proba(self.direction.decision_function(z).reshape(-1, 1))[:, 1]
        win = np.maximum(self.win_size.predict(z), 0) * self.magnitude_scales[0]
        loss = np.maximum(self.loss_size.predict(z), 0) * self.magnitude_scales[1]
        return pd.DataFrame(
            {
                "open_time": decisions.open_time.to_numpy(),
                "p_up": p,
                "expected_win_bps": win,
                "expected_loss_bps": loss,
                "expected_return_bps": p * win - (1 - p) * loss,
            }
        )


def propose_trades(
    predictions: pd.DataFrame, *, round_trip_cost_bps: float = 6, minimum_net_edge_bps: float = 2
) -> np.ndarray:
    """Propose a direction only when modeled monetary payoff exceeds total cost."""
    if not np.isfinite([round_trip_cost_bps, minimum_net_edge_bps]).all() or (
        round_trip_cost_bps < 0 or minimum_net_edge_bps < 0
    ):
        raise ValueError("cost and edge must be finite and nonnegative")
    mu = predictions.expected_return_bps.to_numpy(dtype=float)
    if not np.isfinite(mu).all():
        raise ValueError("expected returns must be finite")
    # Expected exit notional adjusts both sides' fees; funding is not forecast here.
    factor = 1 + mu / 2e4
    if (factor <= 0).any():
        raise ValueError("invalid predicted exit notional")
    long_edge = mu - round_trip_cost_bps * factor
    short_edge = -mu - round_trip_cost_bps * factor
    return np.where(
        (long_edge > 0) & (long_edge >= minimum_net_edge_bps),
        1,
        np.where((short_edge > 0) & (short_edge >= minimum_net_edge_bps), -1, 0),
    )


def actionable_signals(
    predictions: pd.DataFrame,
    *,
    admitted: bool = False,
    round_trip_cost_bps: float = 6,
    minimum_net_edge_bps: float = 2,
) -> np.ndarray:
    """Admission is explicit; missing or failed admission produces flat signals."""
    proposed = propose_trades(
        predictions,
        round_trip_cost_bps=round_trip_cost_bps,
        minimum_net_edge_bps=minimum_net_edge_bps,
    )
    return proposed if admitted else np.zeros(len(proposed), dtype=int)
