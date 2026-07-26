"""Frozen Binance-derivatives signal with Coinbase BTC-USD spot execution scout."""

from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
import requests

SPEC_PATH = Path("research_scout/bitcoin_binance_capitulation_coinbase_spot_v1.json")
BINANCE_ROOT = Path("data/parquet/binance_bitcoin_derivatives_public_v1/normalized")
COINBASE_PUBLIC_PRODUCT_URL = (
    "https://api.coinbase.com/api/v3/brokerage/market/products/BTC-USD/candles"
)


def load_spec(path: Path = SPEC_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("scout specification must be a JSON object")
    return cast(dict[str, Any], payload)


def load_binance_inputs(
    root: Path = BINANCE_ROOT,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        pd.read_parquet(root / "funding_rate.parquet"),
        pd.read_parquet(root / "futures_metrics_5m.parquet"),
        pd.read_parquet(root / "perp_klines_30m.parquet"),
        pd.read_parquet(root / "spot_klines_30m.parquet"),
    )


def _zscore(value: float, prior: pd.Series, minimum: int) -> float:
    clean = prior.dropna().astype(float)
    if len(clean) < minimum:
        return math.nan
    standard_deviation = float(clean.std(ddof=0))
    if standard_deviation <= 0:
        return math.nan
    return (value - float(clean.mean())) / standard_deviation


def _latest_index_at_or_before(times: pd.DatetimeIndex, cutoff: pd.Timestamp) -> int | None:
    index = int(times.searchsorted(cutoff, side="right")) - 1
    return index if index >= 0 else None


def _prepare_metrics(metrics: pd.DataFrame) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    ordered = metrics.sort_values("create_time", kind="stable").copy()
    if ordered["create_time"].duplicated().any():
        raise ValueError("duplicate Binance metrics create_time")
    times = pd.DatetimeIndex(pd.to_datetime(ordered["create_time"], utc=True))
    previous_times = pd.Series(times, index=ordered.index).shift(12)
    contiguous = pd.Series(times, index=ordered.index) - previous_times == pd.Timedelta(minutes=60)
    oi = ordered["sum_open_interest"].astype(float)
    ordered["oi_change_60m"] = (oi / oi.shift(12) - 1.0).where(contiguous.to_numpy())
    return ordered.reset_index(drop=True), times


def _prepare_completed_bars(perp: pd.DataFrame, spot: pd.DataFrame) -> pd.DataFrame:
    required = {"open_time", "open", "high", "low", "close", "volume", "taker_buy_base_volume"}
    for name, frame in (("perpetual", perp), ("spot", spot)):
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"missing {name} columns: {missing}")
        if frame["open_time"].duplicated().any():
            raise ValueError(f"duplicate {name} open_time")
    fields = sorted(required - {"open_time"})
    merged = perp[["open_time", *fields]].merge(
        spot[["open_time", *fields]],
        on="open_time",
        how="inner",
        suffixes=("_perp", "_spot"),
        validate="one_to_one",
    )
    merged = merged.sort_values("open_time", kind="stable").reset_index(drop=True)
    merged["boundary_time"] = pd.to_datetime(merged["open_time"], utc=True) + pd.Timedelta(
        minutes=30
    )
    merged["basis"] = np.log(merged["close_perp"].astype(float) / merged["close_spot"].astype(float))
    merged["perp_taker_sell_ratio"] = 1.0 - (
        merged["taker_buy_base_volume_perp"].astype(float) / merged["volume_perp"].astype(float)
    )
    merged["spot_taker_buy_ratio"] = (
        merged["taker_buy_base_volume_spot"].astype(float) / merged["volume_spot"].astype(float)
    )
    return merged.set_index("boundary_time", drop=False)


def build_binance_signal_panel(
    funding: pd.DataFrame,
    metrics: pd.DataFrame,
    perp: pd.DataFrame,
    spot: pd.DataFrame,
    spec: dict[str, Any],
    *,
    start: str,
    end: str,
) -> pd.DataFrame:
    """Build event-time features without loading any Coinbase outcome prices."""
    funding = funding.sort_values("calc_time", kind="stable").copy()
    if funding["calc_time"].duplicated().any():
        raise ValueError("duplicate Binance funding calc_time")
    funding_times = pd.DatetimeIndex(pd.to_datetime(funding["calc_time"], utc=True))
    metrics, metrics_times = _prepare_metrics(metrics)
    bars = _prepare_completed_bars(perp, spot)
    bar_times = pd.DatetimeIndex(bars.index)
    signal = spec["signal"]
    oi_lookback = int(signal["oi_z_reference_observations"])
    oi_minimum = int(signal["oi_z_minimum_prior_observations"])
    basis_lookback = int(signal["basis_z_reference_observations"])
    basis_minimum = int(signal["basis_z_minimum_prior_observations"])
    start_time = pd.Timestamp(start, tz="UTC")
    end_time = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    rows: list[dict[str, Any]] = []

    for funding_index, raw_event_time in enumerate(funding_times):
        event_time = raw_event_time.floor("5min")
        if event_time < start_time or event_time >= end_time:
            continue
        current_oi_index = _latest_index_at_or_before(metrics_times, event_time)
        current_bar_index = _latest_index_at_or_before(bar_times, event_time)
        if current_oi_index is None or current_bar_index is None:
            continue
        if metrics_times[current_oi_index] != event_time or bar_times[current_bar_index] != event_time:
            continue
        current_oi_change = float(metrics.iloc[current_oi_index]["oi_change_60m"])
        current_basis = float(bars.iloc[current_bar_index]["basis"])
        if math.isnan(current_oi_change) or math.isnan(current_basis):
            continue
        oi_prior = metrics["oi_change_60m"].iloc[
            max(0, current_oi_index - oi_lookback) : current_oi_index
        ]
        basis_prior = bars["basis"].iloc[
            max(0, current_bar_index - basis_lookback) : current_bar_index
        ]
        oi_change_z = _zscore(current_oi_change, oi_prior, oi_minimum)
        basis_z = _zscore(current_basis, basis_prior, basis_minimum)
        prior_bar_time = event_time - pd.Timedelta(minutes=60)
        if prior_bar_time not in bars.index or math.isnan(oi_change_z) or math.isnan(basis_z):
            continue
        bar = bars.loc[event_time]
        prior_bar = bars.loc[prior_bar_time]
        btc_return_60m = float(bar["close_spot"] / prior_bar["close_spot"] - 1.0)
        funding_rate = float(funding.iloc[funding_index]["last_funding_rate"])
        perp_sell_ratio = float(bar["perp_taker_sell_ratio"])
        spot_buy_ratio = float(bar["spot_taker_buy_ratio"])
        selected = bool(
            funding_rate > float(signal["funding_rate_strictly_above"])
            and oi_change_z < float(signal["oi_change_z_strictly_below"])
            and basis_z < float(signal["perp_discount_z_strictly_below"])
            and perp_sell_ratio > float(signal["perp_taker_sell_ratio_strictly_above"])
            and spot_buy_ratio >= float(signal["spot_taker_buy_ratio_minimum"])
            and btc_return_60m > float(signal["btc_return_60m_strictly_above"])
        )
        rows.append(
            {
                "funding_timestamp_raw": raw_event_time,
                "funding_timestamp": event_time,
                "decision_timestamp": event_time
                + pd.Timedelta(minutes=float(spec["decision"]["fixed_publication_lag_minutes"])),
                "planned_entry_timestamp": event_time
                + pd.Timedelta(minutes=float(spec["decision"]["fixed_publication_lag_minutes"]) + 5),
                "funding_rate": funding_rate,
                "oi_change_60m": current_oi_change,
                "oi_change_z": oi_change_z,
                "basis": current_basis,
                "perp_discount_z": basis_z,
                "perp_taker_sell_ratio": perp_sell_ratio,
                "spot_taker_buy_ratio": spot_buy_ratio,
                "btc_return_60m": btc_return_60m,
                "selected": selected,
                "signal_timestamp_alignment_valid": bool(
                    metrics_times[current_oi_index] <= event_time
                    and bar_times[current_bar_index] == event_time
                    and event_time < event_time + pd.Timedelta(minutes=5)
                ),
            }
        )
    panel = pd.DataFrame(rows)
    if panel.empty:
        raise ValueError("no complete Binance funding-event observations")
    if panel["funding_timestamp"].duplicated().any():
        raise ValueError("duplicate funding events in signal panel")
    return panel.sort_values("funding_timestamp", kind="stable").reset_index(drop=True)


def download_coinbase_window(
    event_time: pd.Timestamp,
    cache_root: Path,
    *,
    session: requests.Session | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Download and cache the bounded Coinbase window needed for one selected event."""
    cache_root.mkdir(parents=True, exist_ok=True)
    key = event_time.strftime("%Y%m%dT%H%M%SZ")
    parquet_path = cache_root / f"{key}.parquet"
    metadata_path = cache_root / f"{key}.json"
    if parquet_path.exists() and metadata_path.exists():
        return pd.read_parquet(parquet_path), json.loads(metadata_path.read_text(encoding="utf-8"))

    start = event_time - pd.Timedelta(minutes=120)
    end = event_time + pd.Timedelta(minutes=120)
    params = {
        "start": str(int(start.timestamp())),
        "end": str(int(end.timestamp())),
        "granularity": "FIVE_MINUTE",
    }
    client = session or requests.Session()
    response: requests.Response | None = None
    for attempt in range(4):
        response = client.get(
            COINBASE_PUBLIC_PRODUCT_URL,
            params=params,
            headers={"User-Agent": "mfs-trader-cross-venue-research/1.0"},
            timeout=30,
        )
        if response.status_code == 200:
            break
        if response.status_code not in {429, 500, 502, 503, 504} or attempt == 3:
            response.raise_for_status()
        time.sleep(2**attempt)
    if response is None:
        raise RuntimeError("Coinbase request did not execute")
    payload = response.json()
    candles = payload.get("candles")
    if not isinstance(candles, list):
        raise ValueError("Coinbase response missing candles")
    frame = pd.DataFrame(candles)
    required = ["start", "open", "high", "low", "close", "volume"]
    if frame.empty or any(column not in frame for column in required):
        raise ValueError(f"Coinbase returned no usable candles for {event_time}")
    frame = frame[required].copy()
    frame["start"] = pd.to_datetime(frame["start"].astype("int64"), unit="s", utc=True)
    for column in required[1:]:
        frame[column] = frame[column].astype(float)
    frame = frame.sort_values("start", kind="stable").drop_duplicates("start", keep=False)
    frame.to_parquet(parquet_path, index=False)
    metadata = {
        "event_time": event_time.isoformat(),
        "url": response.url,
        "rows": len(frame),
        "first_start": frame["start"].min().isoformat(),
        "last_start": frame["start"].max().isoformat(),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return frame, metadata


def _decision_indicators(candles: pd.DataFrame, event_time: pd.Timestamp, spec: dict[str, Any]) -> tuple[float, float]:
    indexed = candles.set_index("start").sort_index()
    completed = indexed.loc[indexed.index <= event_time].copy()
    atr_bars = int(spec["coinbase_transfer_and_execution"]["atr_bars"])
    vwap_bars = int(spec["coinbase_transfer_and_execution"]["vwap_bars"])
    if len(completed) < max(atr_bars + 1, vwap_bars):
        return math.nan, math.nan
    previous_close = completed["close"].shift(1)
    true_range = pd.concat(
        [
            completed["high"] - completed["low"],
            (completed["high"] - previous_close).abs(),
            (completed["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = float(true_range.iloc[-atr_bars:].mean())
    recent = completed.iloc[-vwap_bars:]
    volume_sum = float(recent["volume"].sum())
    vwap = float((recent["close"] * recent["volume"]).sum() / volume_sum) if volume_sum > 0 else math.nan
    return atr, vwap


def simulate_coinbase_execution(
    candidate: pd.Series,
    candles: pd.DataFrame,
    spec: dict[str, Any],
) -> dict[str, Any]:
    event_time = pd.Timestamp(candidate["funding_timestamp"])
    indexed = candles.set_index("start").sort_index()
    entry_time = pd.Timestamp(candidate["planned_entry_timestamp"])
    time_exit = entry_time + pd.Timedelta(minutes=float(spec["decision"]["maximum_hold_minutes"]))
    window_start = event_time - pd.Timedelta(
        minutes=float(
            spec["coinbase_transfer_and_execution"][
                "coinbase_dislocation_window_start_minutes_before_funding"
            ]
        )
    )
    required_times = pd.date_range(event_time - pd.Timedelta(minutes=75), time_exit, freq="5min", tz="UTC")
    if not required_times.isin(indexed.index).all():
        return {"executed": False, "exclusion_reason": "missing_or_noncontiguous_coinbase_candles"}
    if entry_time not in indexed.index or time_exit not in indexed.index or window_start not in indexed.index:
        return {"executed": False, "exclusion_reason": "missing_execution_boundary"}

    atr, vwap = _decision_indicators(candles, event_time, spec)
    if math.isnan(atr) or math.isnan(vwap) or atr <= 0:
        return {"executed": False, "exclusion_reason": "invalid_decision_indicators"}
    entry_price = float(indexed.loc[entry_time, "open"])
    window_start_price = float(indexed.loc[window_start, "open"])
    if entry_price >= window_start_price:
        return {"executed": False, "exclusion_reason": "no_coinbase_spot_dislocation"}

    execution = spec["coinbase_transfer_and_execution"]
    target = entry_price + float(execution["target_dislocation_fraction"]) * (
        window_start_price - entry_price
    )
    spot_failure_stop = vwap - atr
    volatility_stop = entry_price - 1.5 * atr
    stop = max(spot_failure_stop, volatility_stop)
    if entry_price <= stop:
        return {"executed": False, "exclusion_reason": "entry_already_below_stop"}
    stop_reason = "spot_failure" if spot_failure_stop >= volatility_stop else "volatility_stop"

    exit_price = math.nan
    exit_time: pd.Timestamp | None = None
    exit_reason = ""
    for timestamp in pd.date_range(entry_time, time_exit - pd.Timedelta(minutes=5), freq="5min", tz="UTC"):
        bar = indexed.loc[timestamp]
        bar_open = float(bar["open"])
        stop_crossed = bar_open <= stop or float(bar["low"]) <= stop
        target_crossed = bar_open >= target or float(bar["high"]) >= target
        if stop_crossed:
            exit_price = min(bar_open, stop)
            exit_time = timestamp
            exit_reason = stop_reason
            break
        if target_crossed:
            exit_price = max(bar_open, target)
            exit_time = timestamp
            exit_reason = "target"
            break
    if math.isnan(exit_price):
        exit_price = float(indexed.loc[time_exit, "open"])
        exit_time = time_exit
        exit_reason = "time_stop"

    gross_return = exit_price / entry_price - 1.0
    costs = spec["position_and_costs"]
    fee_only_return = gross_return - float(costs["fee_only_round_trip_bps"]) / 10_000.0
    conservative_return = gross_return - float(costs["conservative_round_trip_bps"]) / 10_000.0
    capital_fraction = float(costs["capital_fraction"])
    return {
        "executed": True,
        "exclusion_reason": "",
        "coinbase_window_start_price": window_start_price,
        "coinbase_entry_timestamp": entry_time,
        "coinbase_entry_price": entry_price,
        "coinbase_exit_timestamp": exit_time,
        "coinbase_exit_price": exit_price,
        "coinbase_target_price": target,
        "coinbase_spot_failure_stop": spot_failure_stop,
        "coinbase_volatility_stop": volatility_stop,
        "coinbase_atr": atr,
        "coinbase_vwap": vwap,
        "exit_reason": exit_reason,
        "gross_trade_return": gross_return,
        "fee_only_trade_return": fee_only_return,
        "conservative_trade_return": conservative_return,
        "gross_capital_return": gross_return * capital_fraction,
        "fee_only_capital_return": fee_only_return * capital_fraction,
        "conservative_capital_return": conservative_return * capital_fraction,
        "execution_timestamp_alignment_valid": bool(
            pd.Timestamp(candidate["decision_timestamp"]) < entry_time <= exit_time <= time_exit
        ),
    }


def attach_coinbase_execution(
    signal_panel: pd.DataFrame,
    spec: dict[str, Any],
    cache_root: Path,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    selected = signal_panel.loc[signal_panel["selected"]].copy()
    results: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    client = requests.Session()
    last_exit: pd.Timestamp | None = None
    for _, candidate in selected.iterrows():
        planned_entry = pd.Timestamp(candidate["planned_entry_timestamp"])
        if last_exit is not None and planned_entry < last_exit:
            execution = {"executed": False, "exclusion_reason": "overlapping_position"}
        else:
            candles, metadata = download_coinbase_window(
                pd.Timestamp(candidate["funding_timestamp"]), cache_root, session=client
            )
            sources.append(metadata)
            execution = simulate_coinbase_execution(candidate, candles, spec)
        combined = candidate.to_dict()
        combined.update(execution)
        results.append(combined)
        if execution.get("executed"):
            last_exit = pd.Timestamp(execution["coinbase_exit_timestamp"])
    return pd.DataFrame(results), sources


def _bootstrap_interval(values: pd.Series, *, resamples: int, seed: int) -> tuple[float, float]:
    clean = values.dropna().astype(float).to_numpy()
    if len(clean) == 0:
        return math.nan, math.nan
    rng = random.Random(seed)
    indexes = list(range(len(clean)))
    means = [float(np.mean(clean[rng.choices(indexes, k=len(indexes))])) for _ in range(resamples)]
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def evaluate_cross_venue_scout(
    signal_panel: pd.DataFrame,
    transfer_panel: pd.DataFrame,
    spec: dict[str, Any],
) -> dict[str, Any]:
    executed = transfer_panel.loc[transfer_panel.get("executed", False).astype(bool)].copy()
    gates_spec = spec["progression_gates"]
    if executed.empty:
        halves = [math.nan, math.nan]
        bootstrap = [math.nan, math.nan]
        years = 0
        mean_gross = mean_fee = mean_conservative = accuracy = math.nan
        timestamp_valid = bool(signal_panel["signal_timestamp_alignment_valid"].all())
    else:
        executed = executed.sort_values("coinbase_entry_timestamp", kind="stable").reset_index(drop=True)
        split = len(executed) // 2
        halves = [
            float(executed.iloc[:split]["gross_trade_return"].mean() * 10_000.0)
            if split
            else math.nan,
            float(executed.iloc[split:]["gross_trade_return"].mean() * 10_000.0),
        ]
        lower, upper = _bootstrap_interval(
            executed["conservative_trade_return"],
            resamples=int(spec["bootstrap"]["trade_resamples"]),
            seed=int(spec["bootstrap"]["seed"]),
        )
        bootstrap = [lower * 10_000.0, upper * 10_000.0]
        years = int(pd.to_datetime(executed["coinbase_entry_timestamp"], utc=True).dt.year.nunique())
        mean_gross = float(executed["gross_trade_return"].mean() * 10_000.0)
        mean_fee = float(executed["fee_only_trade_return"].mean() * 10_000.0)
        mean_conservative = float(executed["conservative_trade_return"].mean() * 10_000.0)
        accuracy = float((executed["gross_trade_return"] > 0).mean())
        timestamp_valid = bool(
            signal_panel["signal_timestamp_alignment_valid"].all()
            and executed["execution_timestamp_alignment_valid"].all()
        )

    gates = {
        "minimum_executed_trades": len(executed) >= int(gates_spec["minimum_executed_trades"]),
        "positive_mean_gross": bool(mean_gross > float(gates_spec["minimum_mean_gross_trade_bps"])),
        "directional_accuracy": bool(accuracy > float(gates_spec["minimum_directional_accuracy"])),
        "positive_each_chronological_half_gross": bool(halves[0] > 0 and halves[1] > 0),
        "bootstrap_lower_conservative_positive": bool(
            bootstrap[0] > float(gates_spec["minimum_bootstrap_lower_95_conservative_bps"])
        ),
        "positive_after_conservative_costs": bool(mean_conservative > 0),
        "minimum_active_calendar_years": years >= int(gates_spec["minimum_active_calendar_years"]),
        "complete_timestamp_alignment": timestamp_valid,
    }
    exclusions = (
        transfer_panel.loc[~transfer_panel.get("executed", False).astype(bool), "exclusion_reason"]
        .value_counts()
        .to_dict()
        if not transfer_panel.empty
        else {}
    )
    return {
        "signal_complete_events": int(len(signal_panel)),
        "binance_selected_events": int(signal_panel["selected"].sum()),
        "coinbase_executed_trades": int(len(executed)),
        "coinbase_exclusions": {str(key): int(value) for key, value in exclusions.items()},
        "mean_gross_trade_bps": mean_gross,
        "mean_fee_only_trade_bps": mean_fee,
        "mean_conservative_trade_bps": mean_conservative,
        "gross_directional_accuracy": accuracy,
        "chronological_halves_gross_bps": halves,
        "bootstrap_95_conservative_bps": bootstrap,
        "active_calendar_years": years,
        "exit_reasons": (
            {str(key): int(value) for key, value in executed["exit_reason"].value_counts().to_dict().items()}
            if not executed.empty
            else {}
        ),
        "gross_total_capital_return": (
            float((1.0 + executed["gross_capital_return"]).prod() - 1.0) if not executed.empty else 0.0
        ),
        "conservative_total_capital_return": (
            float((1.0 + executed["conservative_capital_return"]).prod() - 1.0)
            if not executed.empty
            else 0.0
        ),
        "gates": gates,
        "passed": all(gates.values()),
    }
