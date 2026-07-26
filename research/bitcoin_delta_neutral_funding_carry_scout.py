"""Frozen seven-day Binance BTCUSDT delta-neutral funding-carry scout."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

SPEC_PATH = Path("research_scout/bitcoin_delta_neutral_funding_carry_binance_v1.json")
DATA_ROOT = Path("data/parquet/binance_bitcoin_derivatives_public_v1/normalized")


def load_spec(path: Path = SPEC_PATH) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def load_inputs(root: Path = DATA_ROOT) -> tuple[pd.DataFrame, ...]:
    return tuple(
        pd.read_parquet(root / name)
        for name in (
            "spot_klines_30m.parquet",
            "perp_klines_30m.parquet",
            "mark_price_klines_30m.parquet",
            "funding_rate.parquet",
        )
    )


def _series(frame: pd.DataFrame, column: str) -> pd.Series:
    index = pd.DatetimeIndex(pd.to_datetime(frame["open_time"], utc=True))
    if index.duplicated().any():
        raise ValueError("duplicate kline timestamps")
    return pd.Series(frame[column].astype(float).to_numpy(), index=index)


def build_trades(
    spot: pd.DataFrame,
    perp: pd.DataFrame,
    mark: pd.DataFrame,
    funding: pd.DataFrame,
    spec: dict[str, Any],
    *,
    start: str,
    end: str,
) -> pd.DataFrame:
    spot_open, spot_close = _series(spot, "open"), _series(spot, "close")
    perp_open, perp_close = _series(perp, "open"), _series(perp, "close")
    mark_open = _series(mark, "open")
    funding = funding.copy()
    funding["calc_time"] = pd.to_datetime(funding["calc_time"], utc=True)
    funding = funding.sort_values("calc_time", kind="stable").reset_index(drop=True)
    times = pd.DatetimeIndex(funding["calc_time"])
    rates = funding["last_funding_rate"].astype(float).to_numpy()
    start_ts, end_ts = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    decision = spec["decision"]
    lag = pd.Timedelta(minutes=float(decision["fixed_publication_lag_minutes"]))
    max_stale = pd.Timedelta(minutes=float(decision["maximum_latest_funding_staleness_minutes"]))
    hold = pd.Timedelta(days=int(spec["position"]["holding_days"]))
    minimum_rate = float(spec["entry_signal"]["minimum_trailing_three_mean_rate"])
    next_available_entry = start_ts
    rows: list[dict[str, Any]] = []
    for date in pd.date_range(start_ts, end_ts, freq="D", tz="UTC"):
        entry = date + pd.Timedelta(minutes=30)
        exit_time = entry + hold
        if entry < next_available_entry or exit_time > end_ts + pd.Timedelta(days=1):
            continue
        cutoff = date + pd.Timedelta(minutes=10)
        event_cutoff = cutoff - lag
        index = int(times.searchsorted(event_cutoff, side="right")) - 1
        if index < 2 or event_cutoff - times[index] > max_stale:
            continue
        trailing_times = times[index - 2 : index + 1]
        trailing_rates = rates[index - 2 : index + 1]
        signal_bar = date - pd.Timedelta(minutes=30)
        required = (
            signal_bar in spot_close.index,
            signal_bar in perp_close.index,
            entry in spot_open.index,
            entry in perp_open.index,
            exit_time in spot_open.index,
            exit_time in perp_open.index,
        )
        if not all(required):
            continue
        basis = math.log(float(perp_close.loc[signal_bar]) / float(spot_close.loc[signal_bar]))
        trailing_mean = float(np.mean(trailing_rates))
        selected = bool(np.all(trailing_rates > 0) and trailing_mean >= minimum_rate and basis >= 0)
        if not selected:
            continue
        crossed = funding.loc[(funding["calc_time"] > entry) & (funding["calc_time"] <= exit_time)].copy()
        mark_times = crossed["calc_time"].dt.floor("30min")
        if crossed.empty or not mark_times.isin(mark_open.index).all():
            continue
        spot_entry, spot_exit = float(spot_open.loc[entry]), float(spot_open.loc[exit_time])
        perp_entry, perp_exit = float(perp_open.loc[entry]), float(perp_open.loc[exit_time])
        quantity = 1.0 / (spot_entry + perp_entry)
        spot_pnl = quantity * (spot_exit - spot_entry)
        perp_pnl = quantity * (perp_entry - perp_exit)
        funding_pnl = float(
            np.sum(
                quantity
                * mark_open.loc[pd.DatetimeIndex(mark_times)].to_numpy(float)
                * crossed["last_funding_rate"].to_numpy(float)
            )
        )
        gross = spot_pnl + perp_pnl + funding_pnl
        spot_fee = quantity * (spot_entry + spot_exit) * 0.001
        perp_fee = quantity * (perp_entry + perp_exit) * 0.0005
        slippage = quantity * (spot_entry + spot_exit + perp_entry + perp_exit) * 0.0005
        rows.append(
            {
                "signal_date": date.date().isoformat(),
                "decision_timestamp": cutoff,
                "latest_funding_timestamp": trailing_times[-1],
                "entry_timestamp": entry,
                "exit_timestamp": exit_time,
                "signal_basis": basis,
                "trailing_funding_mean": trailing_mean,
                "quantity_per_capital": quantity,
                "funding_event_count": len(crossed),
                "realized_funding_sum": float(crossed["last_funding_rate"].sum()),
                "spot_pnl": spot_pnl,
                "perp_pnl": perp_pnl,
                "basis_pnl": spot_pnl + perp_pnl,
                "funding_pnl": funding_pnl,
                "gross_return": gross,
                "fee_cost": spot_fee + perp_fee,
                "slippage_cost": slippage,
                "fee_only_return": gross - spot_fee - perp_fee,
                "conservative_return": gross - spot_fee - perp_fee - slippage,
                "cashflow_accounting_valid": bool(
                    trailing_times[-1] + lag <= cutoff < entry < exit_time
                    and len(crossed) == len(mark_times)
                ),
            }
        )
        next_available_entry = exit_time
    trades = pd.DataFrame(rows)
    if trades.empty or trades["signal_date"].duplicated().any():
        raise ValueError("invalid or empty carry trades")
    return trades


def _bootstrap(values: np.ndarray, resamples: int, seed: int) -> list[float]:
    rng = random.Random(seed)
    indices = list(range(len(values)))
    means = [float(np.mean(values[rng.choices(indices, k=len(indices))])) for _ in range(resamples)]
    return [float(x) for x in np.quantile(means, [0.025, 0.975])]


def evaluate(trades: pd.DataFrame, spec: dict[str, Any]) -> dict[str, Any]:
    ordered = trades.sort_values("entry_timestamp", kind="stable").reset_index(drop=True)
    conservative = ordered["conservative_return"].to_numpy(float)
    interval = _bootstrap(conservative, int(spec["bootstrap"]["trade_resamples"]), int(spec["bootstrap"]["seed"]))
    split = len(ordered) // 2
    halves = [float(ordered.iloc[:split]["conservative_return"].mean()), float(ordered.iloc[split:]["conservative_return"].mean())]
    remove_count = max(1, math.ceil(len(ordered) * 0.05))
    trimmed = ordered.drop(ordered["conservative_return"].abs().nlargest(remove_count).index)
    positive = ordered.loc[ordered["conservative_return"] > 0, "conservative_return"]
    top_count = max(1, math.ceil(len(positive) * 0.05)) if len(positive) else 0
    contribution = float(positive.nlargest(top_count).sum() / positive.sum()) if positive.sum() > 0 else math.nan
    equity = (1.0 + ordered["conservative_return"]).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    gates_spec = spec["progression_gates"]
    gates = {
        "minimum_trades": len(ordered) >= int(gates_spec["minimum_trades"]),
        "positive_mean_gross": float(ordered["gross_return"].mean()) > 0,
        "positive_mean_fee_only": float(ordered["fee_only_return"].mean()) > 0,
        "positive_mean_conservative": float(ordered["conservative_return"].mean()) > 0,
        "positive_each_chronological_half_conservative": halves[0] > 0 and halves[1] > 0,
        "bootstrap_lower_conservative_above_zero": interval[0] > 0,
        "drawdown_within_cap": float(drawdown.min()) >= -float(gates_spec["maximum_conservative_drawdown"]),
        "positive_after_largest_5pct_absolute_removed": float(trimmed["conservative_return"].mean()) > 0,
        "top_5pct_profit_contribution_within_cap": contribution <= float(gates_spec["maximum_top_5pct_profit_contribution"]),
        "complete_cashflow_accounting": bool(ordered["cashflow_accounting_valid"].all()),
    }
    return {
        "specification_id": spec["specification_id"],
        "trade_count": len(ordered),
        "mean_holding_days": 7.0,
        "mean_funding_events": float(ordered["funding_event_count"].mean()),
        "mean_realized_funding_sum_bps": float(ordered["realized_funding_sum"].mean() * 10_000),
        "mean_basis_pnl_bps": float(ordered["basis_pnl"].mean() * 10_000),
        "mean_funding_pnl_bps": float(ordered["funding_pnl"].mean() * 10_000),
        "mean_gross_bps": float(ordered["gross_return"].mean() * 10_000),
        "mean_fee_cost_bps": float(ordered["fee_cost"].mean() * 10_000),
        "mean_slippage_cost_bps": float(ordered["slippage_cost"].mean() * 10_000),
        "mean_fee_only_bps": float(ordered["fee_only_return"].mean() * 10_000),
        "mean_conservative_bps": float(ordered["conservative_return"].mean() * 10_000),
        "conservative_accuracy": float((ordered["conservative_return"] > 0).mean()),
        "bootstrap_95_conservative_bps": [x * 10_000 for x in interval],
        "chronological_halves_conservative_bps": [x * 10_000 for x in halves],
        "trimmed_conservative_bps": float(trimmed["conservative_return"].mean() * 10_000),
        "top_5pct_profit_contribution": contribution,
        "conservative_total_return": float(equity.iloc[-1] - 1),
        "conservative_max_drawdown": float(drawdown.min()),
        "gates": gates,
        "passed": all(gates.values()),
        "trades": ordered,
    }


def serializable(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "trades"}
