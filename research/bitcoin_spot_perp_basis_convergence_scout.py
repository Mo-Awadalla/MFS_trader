"""Frozen Binance BTCUSDT spot–perpetual basis-convergence scout."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

SPEC_PATH = Path("research_scout/bitcoin_spot_perp_basis_convergence_binance_v1.json")
DATA_ROOT = Path("data/parquet/binance_bitcoin_derivatives_public_v1/normalized")


def load_spec(path: Path = SPEC_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return cast(dict[str, Any], payload)


def load_inputs(root: Path = DATA_ROOT) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        pd.read_parquet(root / "spot_klines_30m.parquet"),
        pd.read_parquet(root / "perp_klines_30m.parquet"),
        pd.read_parquet(root / "funding_rate.parquet"),
    )


def _price_series(frame: pd.DataFrame, column: str) -> pd.Series:
    times = pd.DatetimeIndex(pd.to_datetime(frame["open_time"], utc=True))
    if times.duplicated().any():
        raise ValueError("duplicate kline timestamps")
    return pd.Series(frame[column].astype(float).to_numpy(), index=times)


def build_daily_panel(
    spot: pd.DataFrame,
    perp: pd.DataFrame,
    funding: pd.DataFrame,
    spec: dict[str, Any],
    *,
    start: str,
    end: str,
) -> pd.DataFrame:
    spot_open = _price_series(spot, "open")
    spot_close = _price_series(spot, "close")
    perp_open = _price_series(perp, "open")
    perp_close = _price_series(perp, "close")
    funding_times = pd.DatetimeIndex(pd.to_datetime(funding["calc_time"], utc=True)).sort_values()
    signal = spec["signal"]
    lookback = int(signal["lookback_days"])
    minimum = int(signal["minimum_prior_days"])
    quantile = float(signal["quantile"])
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    earliest = max(spot_open.index.min(), perp_open.index.min()).normalize()
    basis_history: list[float] = []
    rows: list[dict[str, Any]] = []
    for date in pd.date_range(earliest, end_ts, freq="D", tz="UTC"):
        signal_bar = date - pd.Timedelta(minutes=30)
        if signal_bar not in spot_close.index or signal_bar not in perp_close.index:
            continue
        basis = float(math.log(perp_close.loc[signal_bar] / spot_close.loc[signal_bar]))
        threshold = (
            float(pd.Series(basis_history[-lookback:]).quantile(quantile))
            if len(basis_history) >= minimum
            else math.nan
        )
        basis_history.append(basis)
        if date < start_ts or math.isnan(threshold):
            continue
        entry_time = date + pd.Timedelta(minutes=30)
        exit_time = date + pd.Timedelta(hours=7, minutes=30)
        if not all(
            timestamp in series.index
            for timestamp in (entry_time, exit_time)
            for series in (spot_open, perp_open)
        ):
            continue
        if ((funding_times > entry_time) & (funding_times <= exit_time)).any():
            continue
        spot_entry = float(spot_open.loc[entry_time])
        spot_exit = float(spot_open.loc[exit_time])
        perp_entry = float(perp_open.loc[entry_time])
        perp_exit = float(perp_open.loc[exit_time])
        spot_return = spot_exit / spot_entry - 1.0
        perp_short_return = 1.0 - perp_exit / perp_entry
        capital_return = 0.5 * spot_return + 0.5 * perp_short_return
        entry_basis = math.log(perp_entry / spot_entry)
        exit_basis = math.log(perp_exit / spot_exit)
        rows.append(
            {
                "session_date": date.date().isoformat(),
                "signal_timestamp": date,
                "entry_timestamp": entry_time,
                "exit_timestamp": exit_time,
                "signal_basis": basis,
                "basis_threshold": threshold,
                "entry_basis": entry_basis,
                "exit_basis": exit_basis,
                "basis_change": exit_basis - entry_basis,
                "spot_entry": spot_entry,
                "spot_exit": spot_exit,
                "perp_entry": perp_entry,
                "perp_exit": perp_exit,
                "spot_return": spot_return,
                "perp_short_return": perp_short_return,
                "capital_gross_return": capital_return,
                "selected": basis > 0.0 and basis > threshold,
                "timestamp_alignment_valid": date < entry_time < exit_time,
            }
        )
    panel = pd.DataFrame(rows)
    if panel.empty or panel["session_date"].duplicated().any():
        raise ValueError("invalid or empty basis panel")
    return panel


def _bootstrap(values: np.ndarray, *, resamples: int, seed: int) -> list[float]:
    rng = random.Random(seed)
    indices = list(range(len(values)))
    means = [float(np.mean(values[rng.choices(indices, k=len(indices))])) for _ in range(resamples)]
    return [float(x) for x in np.quantile(means, [0.025, 0.975])]


def _performance(returns: pd.Series) -> dict[str, float]:
    equity = (1.0 + returns.astype(float)).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    std = float(returns.std(ddof=1))
    return {
        "total_return": float(equity.iloc[-1] - 1.0),
        "annualized_return": float(equity.iloc[-1] ** (365.25 / len(returns)) - 1.0),
        "sharpe_zero_cash": float(returns.mean() / std * math.sqrt(365.25)) if std > 0 else math.nan,
        "max_drawdown": float(drawdown.min()),
    }


def evaluate_scout(panel: pd.DataFrame, spec: dict[str, Any]) -> dict[str, Any]:
    ordered = panel.sort_values("session_date", kind="stable").reset_index(drop=True).copy()
    fee = float(spec["costs"]["fee_only_capital_round_trip_bps"]) / 10_000.0
    conservative = float(spec["costs"]["conservative_capital_round_trip_bps"]) / 10_000.0
    ordered["strategy_gross_return"] = np.where(ordered["selected"], ordered["capital_gross_return"], 0.0)
    ordered["strategy_fee_return"] = np.where(
        ordered["selected"], ordered["capital_gross_return"] - fee, 0.0
    )
    ordered["strategy_conservative_return"] = np.where(
        ordered["selected"], ordered["capital_gross_return"] - conservative, 0.0
    )
    selected = ordered.loc[ordered["selected"]].copy()
    if selected.empty:
        raise ValueError("no selected basis days")
    values = selected["capital_gross_return"].to_numpy(float)
    interval = _bootstrap(
        values,
        resamples=int(spec["bootstrap"]["session_resamples"]),
        seed=int(spec["bootstrap"]["seed"]),
    )
    split = len(selected) // 2
    halves = [float(selected.iloc[:split]["capital_gross_return"].mean()), float(selected.iloc[split:]["capital_gross_return"].mean())]
    remove_count = max(1, math.ceil(len(selected) * 0.05))
    trimmed = selected.drop(selected["capital_gross_return"].abs().nlargest(remove_count).index)
    positive = selected.loc[selected["capital_gross_return"] > 0, "capital_gross_return"]
    top_count = max(1, math.ceil(len(positive) * 0.05)) if len(positive) else 0
    contribution = float(positive.nlargest(top_count).sum() / positive.sum()) if positive.sum() > 0 else math.nan
    gross = float(selected["capital_gross_return"].mean())
    net = float(selected["strategy_conservative_return"].mean())
    gates_spec = spec["progression_gates"]
    gates = {
        "minimum_selected_days": len(selected) >= int(gates_spec["minimum_selected_days"]),
        "positive_mean_gross": gross > float(gates_spec["minimum_mean_gross_bps"]) / 10_000.0,
        "positive_each_chronological_half_gross": halves[0] > 0 and halves[1] > 0,
        "bootstrap_lower_above_zero": interval[0] > float(gates_spec["minimum_bootstrap_lower_95_bps"]) / 10_000.0,
        "positive_after_conservative_costs": net > 0,
        "positive_after_top_5pct_absolute_removed": float(trimmed["capital_gross_return"].mean()) > 0,
        "top_5pct_profit_contribution_within_cap": contribution <= float(gates_spec["maximum_top_5pct_profit_contribution"]),
        "complete_timestamp_alignment": bool(ordered["timestamp_alignment_valid"].all()),
        "basis_contraction_on_average": float(selected["basis_change"].mean()) < 0,
    }
    return {
        "specification_id": spec["specification_id"],
        "days": len(ordered),
        "selected_days": len(selected),
        "mean_signal_basis_bps": float(selected["signal_basis"].mean() * 10_000.0),
        "mean_basis_change_bps": float(selected["basis_change"].mean() * 10_000.0),
        "mean_gross_capital_bps": gross * 10_000.0,
        "mean_fee_only_capital_bps": float(selected["strategy_fee_return"].mean() * 10_000.0),
        "mean_conservative_capital_bps": net * 10_000.0,
        "directional_accuracy": float((selected["capital_gross_return"] > 0).mean()),
        "bootstrap_95_gross_bps": [x * 10_000.0 for x in interval],
        "chronological_halves_gross_bps": [x * 10_000.0 for x in halves],
        "trimmed_mean_gross_bps": float(trimmed["capital_gross_return"].mean() * 10_000.0),
        "top_5pct_profit_contribution": contribution,
        "performance": {
            "gross": _performance(ordered["strategy_gross_return"]),
            "fee_only": _performance(ordered["strategy_fee_return"]),
            "conservative": _performance(ordered["strategy_conservative_return"]),
        },
        "gates": gates,
        "passed": all(gates.values()),
        "panel": ordered,
    }


def serializable_report(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "panel"}
