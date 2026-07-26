"""Frozen Binance BTCUSDT crowded-long unwind falsification scout."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

SPEC_PATH = Path("research_scout/bitcoin_crowded_long_unwind_binance_v1.json")
DATA_ROOT = Path("data/parquet/binance_bitcoin_derivatives_public_v1/normalized")


def load_spec(path: Path = SPEC_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("scout specification must be a JSON object")
    return cast(dict[str, Any], payload)


def load_inputs(root: Path = DATA_ROOT) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        pd.read_parquet(root / "perp_klines_30m.parquet"),
        pd.read_parquet(root / "funding_rate.parquet"),
        pd.read_parquet(root / "futures_metrics_5m.parquet"),
    )


def load_premium(root: Path = DATA_ROOT) -> pd.DataFrame:
    return pd.read_parquet(root / "premium_index_klines_30m.parquet")


def _latest_index_at_or_before(times: pd.DatetimeIndex, cutoff: pd.Timestamp) -> int | None:
    position = int(times.searchsorted(cutoff, side="right")) - 1
    return position if position >= 0 else None


def _quantile_strict_prior(
    values: pd.Series, *, index: int, lookback: int, minimum: int, quantile: float
) -> float:
    start = max(0, index - lookback)
    prior = values.iloc[start:index].dropna().astype(float)
    if len(prior) < minimum:
        return math.nan
    return float(prior.quantile(quantile))


def build_daily_panel(
    perp: pd.DataFrame,
    funding: pd.DataFrame,
    metrics: pd.DataFrame,
    premium: pd.DataFrame,
    spec: dict[str, Any],
    *,
    start: str,
    end: str,
) -> pd.DataFrame:
    """Build one point-in-time row per UTC day without inspecting later partitions."""
    for frame, timestamp in (
        (perp, "open_time"),
        (funding, "calc_time"),
        (metrics, "create_time"),
        (premium, "open_time"),
    ):
        if timestamp not in frame:
            raise ValueError(f"missing timestamp column: {timestamp}")
        if frame[timestamp].duplicated().any():
            raise ValueError(f"duplicate timestamps in {timestamp}")

    perp = perp.sort_values("open_time", kind="stable").copy()
    funding = funding.sort_values("calc_time", kind="stable").copy()
    metrics = metrics.sort_values("create_time", kind="stable").copy()
    premium = premium.sort_values("open_time", kind="stable").copy()
    perp_times = pd.DatetimeIndex(pd.to_datetime(perp["open_time"], utc=True))
    funding_times = pd.DatetimeIndex(pd.to_datetime(funding["calc_time"], utc=True))
    metrics_times = pd.DatetimeIndex(pd.to_datetime(metrics["create_time"], utc=True))
    premium_boundaries = pd.DatetimeIndex(pd.to_datetime(premium["open_time"], utc=True)) + pd.Timedelta(
        minutes=30
    )
    perp_open = pd.Series(perp["open"].astype(float).to_numpy(), index=perp_times)
    premium_close = pd.Series(premium["close"].astype(float).to_numpy(), index=premium_boundaries)

    signal = spec["primary_signal"]
    decision = spec["decision"]
    lookback = int(signal["funding_lookback_settlements"])
    minimum = int(signal["minimum_prior_funding_observations"])
    quantile = float(signal["funding_quantile"])
    funding_staleness = pd.Timedelta(minutes=float(decision["maximum_funding_staleness_minutes"]))
    oi_staleness = pd.Timedelta(minutes=float(decision["maximum_oi_staleness_minutes"]))
    lag = pd.Timedelta(hours=float(decision["oi_comparison_lag_hours"]))
    daily_premium_history: list[float] = []
    rows: list[dict[str, Any]] = []

    for date in pd.date_range(start, end, freq="D", tz="UTC"):
        date_text = date.date().isoformat()
        cutoff = date + pd.Timedelta(minutes=10)
        publication_lag = pd.Timedelta(minutes=float(decision["fixed_publication_lag_minutes"]))
        event_cutoff = cutoff - publication_lag
        entry_time = date + pd.Timedelta(minutes=30)
        exit_time = date + pd.Timedelta(hours=7, minutes=30)
        premium_boundary = date
        premium_value = (
            float(premium_close.loc[premium_boundary]) if premium_boundary in premium_close.index else math.nan
        )
        basis_threshold = (
            float(pd.Series(daily_premium_history[-270:]).quantile(0.90))
            if len(daily_premium_history) >= 180
            else math.nan
        )
        if not math.isnan(premium_value):
            daily_premium_history.append(premium_value)

        funding_index = _latest_index_at_or_before(funding_times, event_cutoff)
        current_oi_index = _latest_index_at_or_before(metrics_times, event_cutoff)
        lag_cutoff = event_cutoff - lag
        lag_oi_index = _latest_index_at_or_before(metrics_times, lag_cutoff)
        if funding_index is None or current_oi_index is None or lag_oi_index is None:
            continue
        funding_time = funding_times[funding_index]
        current_oi_time = metrics_times[current_oi_index]
        lag_oi_time = metrics_times[lag_oi_index]
        if event_cutoff - funding_time > funding_staleness:
            continue
        if event_cutoff - current_oi_time > oi_staleness or lag_cutoff - lag_oi_time > oi_staleness:
            continue
        if entry_time not in perp_open.index or exit_time not in perp_open.index:
            continue
        funding_crossed = bool(((funding_times > entry_time) & (funding_times <= exit_time)).any())
        if funding_crossed:
            continue
        funding_threshold = _quantile_strict_prior(
            funding["last_funding_rate"],
            index=funding_index,
            lookback=lookback,
            minimum=minimum,
            quantile=quantile,
        )
        if math.isnan(funding_threshold):
            continue

        funding_rate = float(funding.iloc[funding_index]["last_funding_rate"])
        current_oi = float(metrics.iloc[current_oi_index]["sum_open_interest"])
        lag_oi = float(metrics.iloc[lag_oi_index]["sum_open_interest"])
        if current_oi <= 0 or lag_oi <= 0:
            continue
        oi_change = current_oi / lag_oi - 1.0
        funding_extreme = funding_rate > 0.0 and funding_rate > funding_threshold
        oi_expanding = oi_change > 0.0
        basis_extreme = (
            not math.isnan(premium_value)
            and not math.isnan(basis_threshold)
            and premium_value > 0.0
            and premium_value > basis_threshold
        )
        entry_price = float(perp_open.loc[entry_time])
        exit_price = float(perp_open.loc[exit_time])
        underlying_return = exit_price / entry_price - 1.0
        short_return = 1.0 - exit_price / entry_price
        rows.append(
            {
                "session_date": date_text,
                "cutoff_timestamp": cutoff,
                "funding_timestamp": funding_time,
                "current_oi_timestamp": current_oi_time,
                "lag_oi_timestamp": lag_oi_time,
                "entry_timestamp": entry_time,
                "exit_timestamp": exit_time,
                "funding_rate": funding_rate,
                "funding_threshold": funding_threshold,
                "oi_current_btc": current_oi,
                "oi_lag_btc": lag_oi,
                "oi_change_8h": oi_change,
                "premium_close": premium_value,
                "premium_threshold": basis_threshold,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "underlying_return": underlying_return,
                "short_return": short_return,
                "funding_extreme": funding_extreme,
                "oi_expanding": oi_expanding,
                "basis_extreme": basis_extreme,
                "selected": funding_extreme and oi_expanding,
                "timestamp_alignment_valid": bool(
                    funding_time + publication_lag <= cutoff < entry_time < exit_time
                    and current_oi_time + publication_lag <= cutoff
                    and lag_oi_time <= lag_cutoff
                ),
            }
        )
    panel = pd.DataFrame(rows)
    if panel.empty:
        raise ValueError("no complete daily observations")
    if panel["session_date"].duplicated().any():
        raise ValueError("duplicate daily observations")
    return panel


def _bootstrap_interval(values: pd.Series, *, resamples: int, seed: int) -> tuple[float, float]:
    clean = values.dropna().astype(float).to_numpy()
    if len(clean) == 0:
        return math.nan, math.nan
    rng = random.Random(seed)
    indices = list(range(len(clean)))
    means = [float(np.mean(clean[rng.choices(indices, k=len(indices))])) for _ in range(resamples)]
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def _performance(returns: pd.Series) -> dict[str, float]:
    values = returns.astype(float)
    equity = (1.0 + values).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    standard_deviation = float(values.std(ddof=1))
    return {
        "total_return": float(equity.iloc[-1] - 1.0),
        "annualized_return": float(equity.iloc[-1] ** (365.25 / len(values)) - 1.0),
        "annualized_volatility": standard_deviation * math.sqrt(365.25),
        "sharpe_zero_cash": (
            float(values.mean() / standard_deviation * math.sqrt(365.25))
            if standard_deviation > 0
            else math.nan
        ),
        "max_drawdown": float(drawdown.min()),
    }


def _control_summary(panel: pd.DataFrame, mask: pd.Series) -> dict[str, float | int]:
    selected = panel.loc[mask.astype(bool), "short_return"]
    return {
        "days": int(len(selected)),
        "mean_short_gross_bps": float(selected.mean() * 10_000.0),
        "short_directional_accuracy": float((selected > 0).mean()),
    }


def evaluate_scout(panel: pd.DataFrame, spec: dict[str, Any]) -> dict[str, Any]:
    ordered = panel.sort_values("session_date", kind="stable").reset_index(drop=True).copy()
    selected = ordered.loc[ordered["selected"]].copy()
    if selected.empty:
        raise ValueError("no primary selected days")
    fee_cost = float(spec["costs"]["fee_only_round_trip_bps"]) / 10_000.0
    conservative_cost = float(spec["costs"]["conservative_round_trip_bps"]) / 10_000.0
    ordered["strategy_gross_return"] = np.where(ordered["selected"], ordered["short_return"], 0.0)
    ordered["strategy_fee_only_return"] = np.where(
        ordered["selected"], ordered["short_return"] - fee_cost, 0.0
    )
    ordered["strategy_conservative_return"] = np.where(
        ordered["selected"], ordered["short_return"] - conservative_cost, 0.0
    )
    selected = ordered.loc[ordered["selected"]].copy()
    lower, upper = _bootstrap_interval(
        selected["short_return"],
        resamples=int(spec["bootstrap"]["session_resamples"]),
        seed=int(spec["bootstrap"]["seed"]),
    )
    split = len(selected) // 2
    first_half = selected.iloc[:split]
    second_half = selected.iloc[split:]
    remove_count = max(1, math.ceil(len(selected) * 0.05))
    removed = selected["short_return"].abs().nlargest(remove_count).index
    trimmed = selected.drop(index=removed)
    profitable = selected.loc[selected["short_return"] > 0, "short_return"]
    top_count = max(1, math.ceil(len(profitable) * 0.05)) if len(profitable) else 0
    contribution = (
        float(profitable.nlargest(top_count).sum() / profitable.sum())
        if len(profitable) and profitable.sum() > 0
        else math.nan
    )
    controls = {
        "funding_only": _control_summary(ordered, ordered["funding_extreme"]),
        "oi_only": _control_summary(ordered, ordered["oi_expanding"]),
        "basis_only": _control_summary(ordered, ordered["basis_extreme"]),
    }
    mean_gross = float(selected["short_return"].mean())
    mean_fee = float(selected["strategy_fee_only_return"].mean())
    mean_conservative = float(selected["strategy_conservative_return"].mean())
    directional_accuracy = float((selected["short_return"] > 0).mean())
    gate_spec = spec["progression_gates"]
    gates = {
        "minimum_selected_days": len(selected) >= int(gate_spec["minimum_selected_days"]),
        "positive_mean_short_gross": mean_gross
        > float(gate_spec["minimum_mean_short_gross_bps"]) / 10_000.0,
        "short_directional_accuracy_above_50pct": directional_accuracy
        > float(gate_spec["minimum_short_directional_accuracy"]),
        "positive_each_chronological_half_gross": float(first_half["short_return"].mean()) > 0
        and float(second_half["short_return"].mean()) > 0,
        "bootstrap_lower_above_zero": lower
        > float(gate_spec["minimum_session_bootstrap_lower_95_bps"]) / 10_000.0,
        "positive_after_conservative_costs": mean_conservative > 0,
        "positive_after_top_5pct_absolute_removed": float(trimmed["short_return"].mean()) > 0,
        "top_5pct_profit_contribution_within_cap": contribution
        <= float(gate_spec["maximum_top_5pct_profit_contribution"]),
        "complete_timestamp_alignment": bool(ordered["timestamp_alignment_valid"].all()),
        "primary_incremental_vs_funding_only": mean_gross
        > float(controls["funding_only"]["mean_short_gross_bps"]) / 10_000.0,
    }
    by_year = {
        str(year): {
            "days": int(len(group)),
            "selected_days": int(group["selected"].sum()),
            "mean_selected_short_gross_bps": float(
                group.loc[group["selected"], "short_return"].mean() * 10_000.0
            ),
            "mean_selected_conservative_bps": float(
                group.loc[group["selected"], "strategy_conservative_return"].mean() * 10_000.0
            ),
        }
        for year, group in ordered.groupby(pd.to_datetime(ordered["session_date"]).dt.year)
    }
    return {
        "specification_id": spec["specification_id"],
        "days": len(ordered),
        "selected_days": len(selected),
        "exposure_fraction": float(len(selected) / len(ordered)),
        "mean_selected_short_gross_bps": mean_gross * 10_000.0,
        "mean_selected_fee_only_bps": mean_fee * 10_000.0,
        "mean_selected_conservative_bps": mean_conservative * 10_000.0,
        "short_directional_accuracy": directional_accuracy,
        "chronological_halves_gross_bps": [
            float(first_half["short_return"].mean() * 10_000.0),
            float(second_half["short_return"].mean() * 10_000.0),
        ],
        "bootstrap_95_gross_bps": [lower * 10_000.0, upper * 10_000.0],
        "trimmed_mean_gross_bps": float(trimmed["short_return"].mean() * 10_000.0),
        "top_5pct_profit_contribution": contribution,
        "controls": controls,
        "performance": {
            "gross": _performance(ordered["strategy_gross_return"]),
            "fee_only": _performance(ordered["strategy_fee_only_return"]),
            "conservative": _performance(ordered["strategy_conservative_return"]),
        },
        "by_year": by_year,
        "gates": gates,
        "passed": all(gates.values()),
        "panel": ordered,
    }


def serializable_report(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "panel"}
