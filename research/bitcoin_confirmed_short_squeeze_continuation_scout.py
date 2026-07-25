"""Point-in-time BTC confirmed short-squeeze continuation research scout."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

SPEC_PATH = Path("research_scout/bitcoin_confirmed_short_squeeze_continuation_v1.json")

_RAW_FEATURES = (
    "funding_crowding",
    "premium_crowding",
    "positioning_crowding",
    "oi_change_6h",
    "spot_return_1h",
    "oi_change_1h",
    "taker_buy_ratio_1h",
)
_STATE_FEATURES = (
    "short_crowding_score",
    "oi_buildup_6h",
    "price_resistance",
    "oi_contraction_1h",
    "taker_buy_imbalance",
    "volatility_expansion",
)


def load_spec(path: Path = SPEC_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("short-squeeze specification must be a JSON object")
    return cast(dict[str, Any], payload)


def load_inputs(
    spec: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    data = spec["data"]
    return (
        pd.read_parquet(data["spot_5m"]),
        pd.read_parquet(data["metrics_5m"]),
        pd.read_parquet(data["funding"]),
        pd.read_parquet(data["premium_30m"]),
    )


def _utc(values: pd.Series) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(values, utc=True))


def _validate_frame(
    frame: pd.DataFrame, *, name: str, timestamp: str, required: set[str]
) -> pd.DataFrame:
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{name} missing required columns: {sorted(missing)}")
    result = frame.sort_values(timestamp, kind="stable").copy()
    result[timestamp] = pd.to_datetime(result[timestamp], utc=True)
    if result[timestamp].duplicated().any():
        raise ValueError(f"{name} contains duplicate {timestamp} values")
    return result


def audit_inputs(
    spot: pd.DataFrame,
    metrics: pd.DataFrame,
    funding: pd.DataFrame,
    premium: pd.DataFrame,
) -> dict[str, Any]:
    """Return schema, coverage, and missingness diagnostics without inspecting outcomes."""
    definitions = (
        ("spot_5m", spot, "open_time"),
        ("metrics_5m", metrics, "create_time"),
        ("funding", funding, "calc_time"),
        ("premium_30m", premium, "open_time"),
    )
    report: dict[str, Any] = {}
    for name, frame, timestamp in definitions:
        if timestamp not in frame:
            raise ValueError(f"{name} missing timestamp column {timestamp}")
        times = _utc(frame[timestamp])
        report[name] = {
            "rows": int(len(frame)),
            "start": times.min().isoformat(),
            "end": times.max().isoformat(),
            "duplicate_timestamps": int(times.duplicated().sum()),
            "nulls": {column: int(value) for column, value in frame.isna().sum().items()},
            "columns": list(frame.columns),
        }
    return report


def _position_at_or_before(times: pd.DatetimeIndex, cutoff: pd.Timestamp) -> int | None:
    position = int(times.searchsorted(cutoff, side="right")) - 1
    return position if position >= 0 else None


def _exact_bar_window(
    indexed: pd.DataFrame, *, start: pd.Timestamp, periods: int
) -> pd.DataFrame | None:
    expected = pd.date_range(start, periods=periods, freq="5min", tz="UTC")
    window = indexed.reindex(expected)
    return None if window.isna().any().any() else window


def _decision_timestamps(start: str, end: str, times: list[str]) -> pd.DatetimeIndex:
    days = pd.date_range(start, end, freq="D", tz="UTC")
    values = [
        pd.Timestamp(f"{day.date().isoformat()} {clock}", tz="UTC")
        for day in days
        for clock in times
    ]
    return pd.DatetimeIndex(values).sort_values()


def _raw_decision_rows(
    spot: pd.DataFrame,
    metrics: pd.DataFrame,
    funding: pd.DataFrame,
    premium: pd.DataFrame,
    spec: dict[str, Any],
    *,
    start: str,
    end: str,
    include_outcomes: bool,
) -> pd.DataFrame:
    spot = _validate_frame(
        spot,
        name="spot",
        timestamp="open_time",
        required={
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "taker_buy_base_volume",
        },
    )
    metrics = _validate_frame(
        metrics,
        name="metrics",
        timestamp="create_time",
        required={"create_time", "sum_open_interest", "count_long_short_ratio"},
    )
    funding = _validate_frame(
        funding,
        name="funding",
        timestamp="calc_time",
        required={"calc_time", "last_funding_rate"},
    )
    premium = _validate_frame(
        premium,
        name="premium",
        timestamp="open_time",
        required={"open_time", "close"},
    )
    spot_indexed = spot.set_index("open_time")
    metric_lag = pd.Timedelta(minutes=float(spec["data"]["metrics_publication_lag_minutes"]))
    funding_lag = pd.Timedelta(minutes=float(spec["data"]["funding_publication_lag_minutes"]))
    metric_available = _utc(metrics["create_time"]) + metric_lag
    funding_available = _utc(funding["calc_time"]) + funding_lag
    premium_available = _utc(premium["open_time"]) + pd.Timedelta(minutes=30)
    max_metric_stale = pd.Timedelta(
        minutes=float(spec["data"]["maximum_metrics_staleness_minutes"])
    )
    max_funding_stale = pd.Timedelta(
        minutes=float(spec["data"]["maximum_funding_staleness_minutes"])
    )
    max_premium_stale = pd.Timedelta(
        minutes=float(spec["data"]["maximum_premium_staleness_minutes"])
    )
    entry_delay = pd.Timedelta(minutes=float(spec["decision"]["entry_delay_minutes"]))
    holding = pd.Timedelta(hours=float(spec["decision"]["holding_hours"]))
    rows: list[dict[str, Any]] = []

    for decision in _decision_timestamps(start, end, list(spec["decision"]["times"])):
        history = _exact_bar_window(
            spot_indexed, start=decision - pd.Timedelta(hours=6, minutes=5), periods=73
        )
        prior_breakout = _exact_bar_window(
            spot_indexed, start=decision - pd.Timedelta(hours=5), periods=48
        )
        if history is None or prior_breakout is None:
            continue
        closes = history["close"].astype(float).to_numpy()
        log_returns = np.diff(np.log(closes))
        if not np.isfinite(log_returns).all():
            continue
        six_hour_rv = float(np.sqrt(np.square(log_returns).sum()))
        one_hour_rv = float(np.sqrt(np.square(log_returns[-12:]).sum()))
        if six_hour_rv <= 0 or one_hour_rv <= 0:
            continue
        latest_hour = history.iloc[-12:]
        volume = float(latest_hour["volume"].astype(float).sum())
        if volume <= 0:
            continue

        metric_now = _position_at_or_before(metric_available, decision)
        metric_6h = _position_at_or_before(metric_available, decision - pd.Timedelta(hours=6))
        metric_1h = _position_at_or_before(metric_available, decision - pd.Timedelta(hours=1))
        funding_now = _position_at_or_before(funding_available, decision)
        premium_now = _position_at_or_before(premium_available, decision)
        if None in (metric_now, metric_6h, metric_1h, funding_now, premium_now):
            continue
        assert metric_now is not None and metric_6h is not None and metric_1h is not None
        assert funding_now is not None and premium_now is not None
        if (
            decision - metric_available[metric_now] > max_metric_stale
            or decision - pd.Timedelta(hours=6) - metric_available[metric_6h] > max_metric_stale
            or decision - pd.Timedelta(hours=1) - metric_available[metric_1h] > max_metric_stale
            or decision - funding_available[funding_now] > max_funding_stale
            or decision - premium_available[premium_now] > max_premium_stale
        ):
            continue
        if funding_now < 2 or premium_now < 7:
            continue
        funding_slice = funding.iloc[funding_now - 2 : funding_now + 1]
        premium_slice = premium.iloc[premium_now - 7 : premium_now + 1]
        expected_premium = pd.date_range(
            premium_available[premium_now] - pd.Timedelta(hours=3, minutes=30),
            periods=8,
            freq="30min",
            tz="UTC",
        )
        if not premium_available[premium_now - 7 : premium_now + 1].equals(expected_premium):
            continue
        current_oi = float(metrics.iloc[metric_now]["sum_open_interest"])
        oi_6h = float(metrics.iloc[metric_6h]["sum_open_interest"])
        oi_1h = float(metrics.iloc[metric_1h]["sum_open_interest"])
        positioning = float(metrics.iloc[metric_now]["count_long_short_ratio"])
        if (
            min(current_oi, oi_6h, oi_1h, positioning) <= 0
            or funding_slice["last_funding_rate"].isna().any()
            or premium_slice["close"].isna().any()
        ):
            continue

        entry_time = decision + entry_delay
        exit_time = entry_time + holding
        entry_price = math.nan
        outcome = math.nan
        if include_outcomes:
            if entry_time not in spot_indexed.index or exit_time not in spot_indexed.index:
                continue
            entry_price = float(spot_indexed.loc[entry_time, "open"])
            exit_price = float(spot_indexed.loc[exit_time, "open"])
            outcome = exit_price / entry_price - 1.0
        last_close = float(closes[-1])
        spot_return_6h = last_close / float(closes[0]) - 1.0
        spot_return_1h = last_close / float(closes[-13]) - 1.0
        oi_change_6h = math.log(current_oi / oi_6h)
        oi_change_1h = math.log(current_oi / oi_1h)
        taker_ratio = float(latest_hour["taker_buy_base_volume"].astype(float).sum()) / volume
        true_ranges = np.maximum.reduce(
            [
                latest_hour["high"].astype(float).to_numpy()
                - latest_hour["low"].astype(float).to_numpy(),
                np.abs(
                    latest_hour["high"].astype(float).to_numpy()
                    - history["close"].astype(float).to_numpy()[-13:-1]
                ),
                np.abs(
                    latest_hour["low"].astype(float).to_numpy()
                    - history["close"].astype(float).to_numpy()[-13:-1]
                ),
            ]
        )
        rows.append(
            {
                "decision_timestamp": decision,
                "decision_clock": decision.strftime("%H:%M"),
                "entry_timestamp": entry_time,
                "scheduled_exit_timestamp": exit_time,
                "latest_spot_close_timestamp": decision,
                "latest_metrics_available_at": metric_available[metric_now],
                "latest_funding_available_at": funding_available[funding_now],
                "latest_premium_available_at": premium_available[premium_now],
                "funding_crowding": -float(funding_slice["last_funding_rate"].astype(float).mean()),
                "premium_crowding": -float(premium_slice["close"].astype(float).median()),
                "positioning_crowding": -math.log(positioning),
                "oi_change_6h": oi_change_6h,
                "spot_return_6h": spot_return_6h,
                "realized_volatility_6h": six_hour_rv,
                "spot_return_1h": spot_return_1h,
                "oi_change_1h": oi_change_1h,
                "taker_buy_ratio_1h": taker_ratio,
                "realized_volatility_1h": one_hour_rv,
                "breakout": last_close > float(prior_breakout["high"].astype(float).max()),
                "atr_1h": float(np.mean(true_ranges)),
                "entry_open": entry_price,
                "forward_gross_return_6h": outcome,
                "timestamp_alignment_valid": bool(
                    metric_available[metric_now] <= decision < entry_time < exit_time
                    and funding_available[funding_now] <= decision
                    and premium_available[premium_now] <= decision
                ),
            }
        )
    result = pd.DataFrame(rows)
    if result.empty:
        raise ValueError("no complete point-in-time decision rows")
    return result.sort_values("decision_timestamp", kind="stable").reset_index(drop=True)


def _strict_prior(series: pd.Series, times: pd.Series, index: int, days: int) -> pd.Series:
    cutoff = pd.Timestamp(times.iloc[index])
    start = cutoff - pd.Timedelta(days=days)
    mask = (times.iloc[:index] >= start) & (times.iloc[:index] < cutoff)
    return series.iloc[:index].loc[mask].dropna().astype(float)


def _percentile_rank(prior: pd.Series, value: float) -> float:
    if prior.empty or not math.isfinite(value):
        return math.nan
    return float(((prior < value).sum() + 0.5 * (prior == value).sum()) / len(prior))


def build_decision_panel(
    spot: pd.DataFrame,
    metrics: pd.DataFrame,
    funding: pd.DataFrame,
    premium: pd.DataFrame,
    spec: dict[str, Any],
    *,
    start: str,
    end: str,
    include_outcomes: bool = True,
) -> pd.DataFrame:
    """Build strict point-in-time features and the two mechanical stages."""
    panel = _raw_decision_rows(
        spot,
        metrics,
        funding,
        premium,
        spec,
        start=start,
        end=end,
        include_outcomes=include_outcomes,
    )
    days = int(spec["rolling"]["lookback_calendar_days"])
    minimum = int(spec["rolling"]["minimum_prior_decisions"])
    times = panel["decision_timestamp"]
    quantiles = {
        "funding_crowding": float(spec["stage_1"]["crowding_quantile"]),
        "premium_crowding": float(spec["stage_1"]["crowding_quantile"]),
        "positioning_crowding": float(spec["stage_1"]["crowding_quantile"]),
        "oi_change_6h": float(spec["stage_1"]["oi_buildup_quantile"]),
        "spot_return_1h": float(spec["stage_2"]["positive_spot_return_quantile"]),
        "oi_change_1h": float(spec["stage_2"]["oi_contraction_quantile"]),
        "taker_buy_ratio_1h": float(spec["stage_2"]["spot_taker_buy_ratio_quantile"]),
    }
    for feature in _RAW_FEATURES:
        panel[f"{feature}_threshold"] = math.nan
        panel[f"{feature}_percentile"] = math.nan
    panel["rolling_observations"] = 0
    for index in range(len(panel)):
        priors = {
            feature: _strict_prior(panel[feature], times, index, days) for feature in _RAW_FEATURES
        }
        panel.at[index, "rolling_observations"] = min(len(value) for value in priors.values())
        if min(len(value) for value in priors.values()) < minimum:
            continue
        for feature, prior in priors.items():
            value = float(panel.at[index, feature])
            panel.at[index, f"{feature}_threshold"] = float(
                prior.quantile(quantiles[feature], interpolation="linear")
            )
            panel.at[index, f"{feature}_percentile"] = _percentile_rank(prior, value)

    ready = panel["rolling_observations"] >= minimum
    crowd_columns = [
        "funding_crowding",
        "premium_crowding",
        "positioning_crowding",
    ]
    votes = sum(panel[feature] > panel[f"{feature}_threshold"] for feature in crowd_columns)
    panel["crowding_votes"] = votes.astype(int)
    panel["short_crowding_score"] = panel[
        [f"{feature}_percentile" for feature in crowd_columns]
    ].mean(axis=1)
    panel["price_resistance"] = panel["spot_return_6h"] / panel["realized_volatility_6h"]
    panel["oi_buildup_6h"] = panel["oi_change_6h"]
    panel["oi_contraction_1h"] = -panel["oi_change_1h"]
    panel["taker_buy_imbalance"] = panel["taker_buy_ratio_1h"] - 0.5
    panel["volatility_expansion"] = np.log(
        panel["realized_volatility_1h"] / (panel["realized_volatility_6h"] / math.sqrt(6.0))
    )
    panel["stage_1"] = (
        ready
        & (panel["crowding_votes"] >= int(spec["stage_1"]["minimum_crowding_votes"]))
        & (panel["oi_change_6h"] > panel["oi_change_6h_threshold"])
        & (panel["spot_return_6h"] > -0.5 * panel["realized_volatility_6h"])
    )
    panel["stage_2"] = (
        panel["stage_1"]
        & (panel["spot_return_1h"] > 0)
        & (panel["spot_return_1h"] > panel["spot_return_1h_threshold"])
        & (panel["oi_change_1h"] < panel["oi_change_1h_threshold"])
        & (panel["taker_buy_ratio_1h"] > panel["taker_buy_ratio_1h_threshold"])
        & panel["breakout"].astype(bool)
    )
    return panel


def _bootstrap_mean_interval(
    values: np.ndarray, *, confidence: float, resamples: int, seed: int
) -> tuple[float, float]:
    if len(values) == 0:
        return math.nan, math.nan
    rng = np.random.default_rng(seed)
    means = rng.choice(values, size=(resamples, len(values)), replace=True).mean(axis=1)
    tail = (1.0 - confidence) / 2.0
    return float(np.quantile(means, tail)), float(np.quantile(means, 1.0 - tail))


def apply_analogue_model(panel: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    """Apply robust trailing normalization, 24-hour embargo, and frozen KNN hurdles."""
    result = panel.sort_values("decision_timestamp", kind="stable").reset_index(drop=True).copy()
    for column in (
        "analogue_count",
        "analogue_mean_gross_return",
        "analogue_bootstrap_lower",
        "analogue_bootstrap_upper",
        "analogue_probability_above_cost",
        "analogue_mean_distance",
        "analogue_max_distance",
        "analogue_effective_sample_size",
        "analogue_top_outcome_contribution",
    ):
        result[column] = math.nan
    result["analogue_pass"] = False
    model = spec["analogue_model"]
    neighbors = int(model["neighbors"])
    days = int(spec["rolling"]["lookback_calendar_days"])
    minimum = int(spec["rolling"]["minimum_prior_decisions"])
    embargo = pd.Timedelta(hours=float(model["embargo_hours"]))
    confidence = float(model["bootstrap_confidence"])
    resamples = int(model["bootstrap_resamples"])
    seed = int(model["bootstrap_seed"])
    cost_hurdle = float(model["cost_hurdle_bps"]) / 10_000.0

    for index, row in result.loc[result["stage_2"].astype(bool)].iterrows():
        decision = pd.Timestamp(row["decision_timestamp"])
        window_start = decision - pd.Timedelta(days=days)
        normalizer_mask = (result["decision_timestamp"] >= window_start) & (
            result["decision_timestamp"] < decision
        )
        training_mask = (
            normalizer_mask
            & (result["decision_timestamp"] <= decision - embargo)
            & result["forward_gross_return_6h"].notna()
        )
        normalizer = result.loc[normalizer_mask, list(_STATE_FEATURES)].dropna()
        training = result.loc[training_mask, list(_STATE_FEATURES)].dropna()
        if len(normalizer) < minimum or len(training) < neighbors:
            continue
        medians = normalizer.median()
        mads = (normalizer - medians).abs().median() * 1.4826
        if (mads <= 0).any() or not np.isfinite(mads.to_numpy()).all():
            continue
        current = (row[list(_STATE_FEATURES)].astype(float) - medians) / mads
        normalized = (training - medians) / mads
        distances = np.sqrt(np.square(normalized - current).sum(axis=1))
        nearest_indices = distances.nsmallest(neighbors).index
        outcomes = result.loc[nearest_indices, "forward_gross_return_6h"].astype(float).to_numpy()
        neighbor_distances = distances.loc[nearest_indices].astype(float).to_numpy()
        lower, upper = _bootstrap_mean_interval(
            outcomes,
            confidence=confidence,
            resamples=resamples,
            seed=seed + index,
        )
        positive = np.sort(outcomes[outcomes > 0])[::-1]
        count = int(model["largest_positive_outcomes_count"])
        contribution = (
            float(positive[:count].sum() / positive.sum())
            if len(positive) and positive.sum() > 0
            else math.inf
        )
        mean = float(outcomes.mean())
        probability = float(np.mean(outcomes > cost_hurdle))
        result.at[index, "analogue_count"] = neighbors
        result.at[index, "analogue_mean_gross_return"] = mean
        result.at[index, "analogue_bootstrap_lower"] = lower
        result.at[index, "analogue_bootstrap_upper"] = upper
        result.at[index, "analogue_probability_above_cost"] = probability
        result.at[index, "analogue_mean_distance"] = float(neighbor_distances.mean())
        result.at[index, "analogue_max_distance"] = float(neighbor_distances.max())
        result.at[index, "analogue_effective_sample_size"] = float(neighbors)
        result.at[index, "analogue_top_outcome_contribution"] = contribution
        result.at[index, "analogue_pass"] = bool(
            mean > float(model["minimum_mean_gross_bps"]) / 10_000.0
            and lower > float(model["minimum_lower_bound_gross_bps"]) / 10_000.0
            and probability > float(model["minimum_probability_above_cost"])
            and contribution <= float(model["maximum_largest_positive_outcome_contribution"])
        )
    return result


def _trade_path(
    bars: pd.DataFrame,
    row: pd.Series,
    spec: dict[str, Any],
    *,
    round_trip_cost_bps: float,
) -> dict[str, Any] | None:
    indexed = bars.set_index(pd.to_datetime(bars["open_time"], utc=True)).sort_index()
    entry_time = pd.Timestamp(row["entry_timestamp"])
    exit_time = pd.Timestamp(row["scheduled_exit_timestamp"])
    expected = pd.date_range(entry_time, exit_time, freq="5min", inclusive="left", tz="UTC")
    path = indexed.reindex(expected)
    if path[["open", "high", "low"]].isna().any().any() or exit_time not in indexed.index:
        return None
    entry_open = float(indexed.loc[entry_time, "open"])
    atr = float(row["atr_1h"])
    stop = entry_open - float(spec["execution"]["atr_multiplier"]) * atr
    if stop <= 0 or stop >= entry_open:
        return None
    stop_hits = path["low"].astype(float) <= stop
    stopped = bool(stop_hits.any())
    if stopped:
        exit_timestamp = stop_hits.idxmax()
        bar_open = float(path.loc[exit_timestamp, "open"])
        raw_exit = min(stop, bar_open)
        exit_reason = "stop"
    else:
        exit_timestamp = exit_time
        raw_exit = float(indexed.loc[exit_time, "open"])
        exit_reason = "time"
    half_cost = round_trip_cost_bps / 20_000.0
    entry_fill = entry_open * (1.0 + half_cost)
    exit_fill = raw_exit * (1.0 - half_cost)
    gross_return = raw_exit / entry_open - 1.0
    net_return = exit_fill / entry_fill - 1.0
    stop_fraction = (entry_open - stop) / entry_open
    notional = min(
        float(spec["execution"]["maximum_notional_fraction"]),
        float(spec["execution"]["maximum_risk_fraction"]) / stop_fraction,
    )
    return {
        "entry_timestamp": entry_time,
        "exit_timestamp": exit_timestamp,
        "exit_reason": exit_reason,
        "entry_open": entry_open,
        "raw_exit_price": raw_exit,
        "stop_price": stop,
        "notional_fraction": notional,
        "gross_instrument_return": gross_return,
        "net_instrument_return": net_return,
        "gross_portfolio_return": notional * gross_return,
        "net_portfolio_return": notional * net_return,
        "maximum_adverse_excursion": float(path["low"].astype(float).min() / entry_open - 1.0),
        "maximum_favorable_excursion": float(path["high"].astype(float).max() / entry_open - 1.0),
        "round_trip_cost_bps": round_trip_cost_bps,
        "timestamp_alignment_valid": bool(
            pd.Timestamp(row["decision_timestamp"]) < entry_time <= exit_timestamp <= exit_time
        ),
    }


def simulate_trades(
    panel: pd.DataFrame,
    spot: pd.DataFrame,
    spec: dict[str, Any],
    *,
    round_trip_cost_bps: float | None = None,
) -> pd.DataFrame:
    """Enforce the 24-hour entry throttle and simulate conservative stop/time exits."""
    cost = (
        float(spec["execution"]["ordinary_round_trip_cost_bps"])
        if round_trip_cost_bps is None
        else float(round_trip_cost_bps)
    )
    minimum_gap = pd.Timedelta(hours=float(spec["decision"]["minimum_hours_between_entries"]))
    rows: list[dict[str, Any]] = []
    last_entry: pd.Timestamp | None = None
    candidates = panel.loc[panel["analogue_pass"].astype(bool)].sort_values(
        "decision_timestamp", kind="stable"
    )
    for _, candidate in candidates.iterrows():
        entry = pd.Timestamp(candidate["entry_timestamp"])
        if last_entry is not None and entry < last_entry + minimum_gap:
            continue
        trade = _trade_path(spot, candidate, spec, round_trip_cost_bps=cost)
        if trade is None:
            continue
        trade["decision_timestamp"] = candidate["decision_timestamp"]
        trade["decision_clock"] = candidate["decision_clock"]
        trade["analogue_probability_above_cost"] = candidate.get(
            "analogue_probability_above_cost", math.nan
        )
        trade["forward_gross_return_6h"] = candidate.get("forward_gross_return_6h", math.nan)
        rows.append(trade)
        last_entry = entry
    return pd.DataFrame(rows)


def _profit_factor(values: pd.Series) -> float:
    profits = float(values.loc[values > 0].sum())
    losses = float(-values.loc[values < 0].sum())
    return profits / losses if losses > 0 else math.inf


def _trade_summary(trades: pd.DataFrame) -> dict[str, Any]:
    if trades.empty:
        return {
            "trades": 0,
            "mean_gross_bps": math.nan,
            "mean_net_bps": math.nan,
            "hit_rate": math.nan,
            "payoff_ratio": math.nan,
            "profit_factor": math.nan,
            "compounded_return": 0.0,
            "maximum_drawdown": 0.0,
        }
    net = trades["net_instrument_return"].astype(float)
    gross = trades["gross_instrument_return"].astype(float)
    portfolio = trades["net_portfolio_return"].astype(float)
    equity = (1.0 + portfolio).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    wins = net.loc[net > 0]
    losses = net.loc[net < 0]
    payoff = (
        float(wins.mean() / -losses.mean())
        if len(wins) and len(losses) and losses.mean() < 0
        else math.nan
    )
    return {
        "trades": int(len(trades)),
        "mean_gross_bps": float(gross.mean() * 10_000.0),
        "mean_net_bps": float(net.mean() * 10_000.0),
        "mean_portfolio_net_bps": float(portfolio.mean() * 10_000.0),
        "hit_rate": float((net > 0).mean()),
        "payoff_ratio": payoff,
        "profit_factor": _profit_factor(net),
        "compounded_return": float(equity.iloc[-1] - 1.0),
        "maximum_drawdown": float(drawdown.min()),
        "mean_mae_bps": float(trades["maximum_adverse_excursion"].mean() * 10_000.0),
        "mean_mfe_bps": float(trades["maximum_favorable_excursion"].mean() * 10_000.0),
        "stop_rate": float((trades["exit_reason"] == "stop").mean()),
        "turnover_notional": float(2.0 * trades["notional_fraction"].sum()),
        "cost_drag_portfolio_bps": float(
            (trades["gross_portfolio_return"] - trades["net_portfolio_return"]).sum() * 10_000.0
        ),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def evaluate_partition(
    panel: pd.DataFrame,
    spot: pd.DataFrame,
    spec: dict[str, Any],
    *,
    partition: str,
) -> dict[str, Any]:
    """Evaluate a frozen partition and emit required diagnostics and progression gates."""
    bounds = spec["partitions"][partition]
    start = pd.Timestamp(bounds["start"], tz="UTC")
    end = pd.Timestamp(bounds["end"], tz="UTC") + pd.Timedelta(days=1)
    expected_decisions = int((end - start) / pd.Timedelta(days=1)) * len(spec["decision"]["times"])
    scoped = panel.loc[
        (panel["decision_timestamp"] >= start) & (panel["decision_timestamp"] < end)
    ].copy()
    costs = [float(value) for value in spec["execution"]["cost_sensitivity_bps"]]
    trade_sets = {
        str(int(cost)): simulate_trades(scoped, spot, spec, round_trip_cost_bps=cost)
        for cost in costs
    }
    ordinary_key = str(int(float(spec["execution"]["ordinary_round_trip_cost_bps"])))
    stress_key = str(int(float(spec["execution"]["stress_round_trip_cost_bps"])))
    ordinary = trade_sets[ordinary_key]
    stress = trade_sets[stress_key]
    summary = _trade_summary(ordinary)
    stress_summary = _trade_summary(stress)
    net = (
        ordinary["net_instrument_return"].astype(float)
        if not ordinary.empty
        else pd.Series(dtype=float)
    )
    split = len(net) // 2
    lower, upper = _bootstrap_mean_interval(
        net.to_numpy(),
        confidence=float(spec["development_gates"]["event_bootstrap_confidence"]),
        resamples=int(spec["bootstrap"]["event_resamples"]),
        seed=int(spec["bootstrap"]["seed"]),
    )
    profitable = net.loc[net > 0]
    top_count = max(1, math.ceil(len(profitable) * 0.05)) if len(profitable) else 0
    concentration = (
        float(profitable.nlargest(top_count).sum() / profitable.sum())
        if len(profitable) and profitable.sum() > 0
        else math.inf
    )
    trimmed = net.drop(index=profitable.nlargest(top_count).index) if top_count else net.copy()
    calibration_brier = math.nan
    if not ordinary.empty:
        hurdle = float(spec["analogue_model"]["cost_hurdle_bps"]) / 10_000.0
        probabilities = ordinary["analogue_probability_above_cost"].astype(float)
        realized = (ordinary["forward_gross_return_6h"].astype(float) > hurdle).astype(float)
        calibration_brier = float(np.square(probabilities - realized).mean())
    by_year: dict[str, Any] = {}
    if not ordinary.empty:
        years = pd.to_datetime(ordinary["entry_timestamp"], utc=True).dt.year
        for year, group in ordinary.groupby(years):
            by_year[str(year)] = _trade_summary(group)
    positive_year_profit = {
        year: max(0.0, float(values["mean_net_bps"]) * int(values["trades"]))
        for year, values in by_year.items()
    }
    year_total = sum(positive_year_profit.values())
    max_year_contribution = (
        max(positive_year_profit.values()) / year_total if year_total > 0 else math.inf
    )
    gates_spec = (
        spec["development_gates"]
        if partition == "development"
        else spec["internal_validation_gates"]
    )
    if partition == "development":
        gates = {
            "minimum_completed_trades": len(ordinary)
            >= int(gates_spec["minimum_completed_trades"]),
            "positive_mean_after_30bps": len(net) > 0
            and float(net.mean() * 10_000.0) > float(gates_spec["minimum_net_mean_bps"]),
            "positive_chronological_halves": split > 0
            and float(net.iloc[:split].mean()) > 0
            and float(net.iloc[split:].mean()) > 0,
            "event_bootstrap_lower_above_zero": lower * 10_000.0
            > float(gates_spec["minimum_bootstrap_lower_net_bps"]),
            "net_profit_factor": _profit_factor(net)
            > float(gates_spec["minimum_net_profit_factor"]),
            "top_5pct_profit_contribution": concentration
            <= float(gates_spec["maximum_top_5pct_profit_contribution"]),
            "positive_after_50bps": not stress.empty
            and float(stress["net_instrument_return"].mean()) > 0,
            "timestamp_alignment": not ordinary.empty
            and bool(ordinary["timestamp_alignment_valid"].all())
            and bool(scoped["timestamp_alignment_valid"].all()),
            "year_concentration": max_year_contribution
            <= float(gates_spec["maximum_profitable_year_contribution"]),
        }
    else:
        gates = {
            "minimum_completed_trades": len(ordinary)
            >= int(gates_spec["minimum_completed_trades"]),
            "positive_after_30bps": len(net) > 0 and float(net.mean()) > 0,
            "positive_after_50bps": not stress.empty
            and float(stress["net_instrument_return"].mean()) > 0,
            "probability_calibration": math.isfinite(calibration_brier)
            and calibration_brier <= float(gates_spec["maximum_probability_brier_score"]),
            "top_5pct_profit_contribution": concentration
            <= float(gates_spec["maximum_top_5pct_profit_contribution"]),
            "positive_trimmed_mean": len(trimmed) > 0 and float(trimmed.mean()) > 0,
            "timestamp_alignment": not ordinary.empty
            and bool(ordinary["timestamp_alignment_valid"].all()),
        }
    diagnostic_by_clock = (
        {str(clock): _trade_summary(group) for clock, group in ordinary.groupby("decision_clock")}
        if not ordinary.empty
        else {}
    )
    analogue_rows = scoped.loc[scoped["analogue_pass"].astype(bool)]
    report = {
        "specification_id": spec["specification_id"],
        "partition": partition,
        "partition_bounds": bounds,
        "candidate_counts": {
            "complete_decisions": int(len(scoped)),
            "stage_1": int(scoped["stage_1"].sum()),
            "stage_2": int(scoped["stage_2"].sum()),
            "analogue_pass": int(scoped["analogue_pass"].sum()),
            "completed_trades_after_24h_throttle": int(len(ordinary)),
        },
        "ordinary": summary,
        "stress": stress_summary,
        "cost_sensitivity": {key: _trade_summary(value) for key, value in trade_sets.items()},
        "event_bootstrap_95_net_bps": [lower * 10_000.0, upper * 10_000.0],
        "chronological_halves_net_bps": [
            float(net.iloc[:split].mean() * 10_000.0) if split else math.nan,
            float(net.iloc[split:].mean() * 10_000.0) if split else math.nan,
        ],
        "top_5pct_profit_contribution": concentration,
        "trimmed_mean_net_bps": float(trimmed.mean() * 10_000.0) if len(trimmed) else math.nan,
        "probability_brier_score": calibration_brier,
        "maximum_profitable_year_contribution": max_year_contribution,
        "by_year": by_year,
        "by_decision_clock": diagnostic_by_clock,
        "analogue_diagnostics": {
            "mean_distance": float(analogue_rows["analogue_mean_distance"].mean()),
            "mean_effective_sample_size": float(
                analogue_rows["analogue_effective_sample_size"].mean()
            ),
            "mean_bootstrap_lower_bps": float(
                analogue_rows["analogue_bootstrap_lower"].mean() * 10_000.0
            ),
        },
        "feature_availability": {
            "complete_decisions": int(len(scoped)),
            "expected_decisions": expected_decisions,
            "eligible_decision_fraction": float(len(scoped) / max(1, expected_decisions)),
            "timestamp_alignment_valid": bool(scoped["timestamp_alignment_valid"].all()),
        },
        "unconditional_same_clock_6h_gross_bps": float(
            scoped["forward_gross_return_6h"].mean() * 10_000.0
        ),
        "gates": gates,
        "passed": all(gates.values()),
        "trades": ordinary,
        "panel": scoped,
    }
    return cast(dict[str, Any], _json_safe(report))


def serializable_report(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key not in {"trades", "panel"}}
