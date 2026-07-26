"""Frozen Bitcoin U.S.-session close-momentum scout."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
from scipy.stats import linregress

SPEC_PATH = Path("research_scout/bitcoin_us_session_close_momentum_binance_v1.json")


def load_spec(path: Path = SPEC_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("scout specification must be a JSON object")
    return cast(dict[str, Any], payload)


def build_session_panel(bars: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    """Construct explicit source-shaped signal and final-half-hour returns."""
    required = {"open_time", "open", "close", "symbol", "interval"}
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"bars missing required columns: {sorted(missing)}")
    if bars["open_time"].duplicated().any():
        raise ValueError("bar timestamps must be unique")
    instrument = str(spec["instrument"])
    interval = str(spec["interval"])
    if set(bars["symbol"].astype(str).unique()) != {instrument}:
        raise ValueError("bars do not match frozen instrument")
    if set(bars["interval"].astype(str).unique()) != {interval}:
        raise ValueError("bars do not match frozen interval")

    times = pd.DatetimeIndex(pd.to_datetime(bars["open_time"], utc=True))
    close_boundary = times + pd.Timedelta(minutes=30)
    closes = pd.Series(bars["close"].astype(float).to_numpy(), index=close_boundary)
    opens = pd.Series(bars["open"].astype(float).to_numpy(), index=times)
    if closes.index.duplicated().any():
        raise ValueError("close-boundary timestamps must be unique")

    zone = str(spec["session"]["timezone"])
    local = close_boundary.tz_convert(zone)
    first_date = local.min().date() + pd.Timedelta(days=1)
    last_date = local.max().date()
    rows: list[dict[str, Any]] = []
    for session_date in pd.date_range(first_date, last_date, freq="D"):
        date_text = session_date.date().isoformat()
        previous_text = (session_date - pd.Timedelta(days=1)).date().isoformat()
        prior_close = pd.Timestamp(
            f"{previous_text} {spec['session']['close_time']}", tz=zone
        ).tz_convert("UTC")
        signal_end = pd.Timestamp(
            f"{date_text} {spec['session']['first_half_hour_end']}", tz=zone
        ).tz_convert("UTC")
        entry = pd.Timestamp(
            f"{date_text} {spec['session']['last_half_hour_start']}", tz=zone
        ).tz_convert("UTC")
        exit_ = pd.Timestamp(
            f"{date_text} {spec['session']['close_time']}", tz=zone
        ).tz_convert("UTC")
        close_timestamps = [prior_close, signal_end, exit_]
        complete = all(timestamp in closes.index for timestamp in close_timestamps)
        complete = complete and entry in opens.index
        if not complete:
            continue
        signal_return = float(closes.loc[signal_end] / closes.loc[prior_close] - 1.0)
        held_return = float(closes.loc[exit_] / opens.loc[entry] - 1.0)
        rows.append(
            {
                "session_date": date_text,
                "prior_close_timestamp": prior_close,
                "signal_timestamp": signal_end,
                "entry_timestamp": entry,
                "exit_timestamp": exit_,
                "prior_close_price": float(closes.loc[prior_close]),
                "signal_price": float(closes.loc[signal_end]),
                "entry_price": float(opens.loc[entry]),
                "exit_price": float(closes.loc[exit_]),
                "signal_return": signal_return,
                "last_half_hour_return": held_return,
                "selected": signal_return > 0.0,
                "timestamp_alignment_valid": signal_end < entry < exit_,
            }
        )
    panel = pd.DataFrame(rows)
    if panel.empty:
        raise ValueError("no complete sessions could be constructed")
    if panel["session_date"].duplicated().any():
        raise ValueError("duplicate session dates")
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
    std = float(values.std(ddof=1))
    return {
        "total_return": float(equity.iloc[-1] - 1.0),
        "annualized_return": float(equity.iloc[-1] ** (365.25 / len(values)) - 1.0),
        "annualized_volatility": std * math.sqrt(365.25),
        "sharpe_zero_cash": float(values.mean() / std * math.sqrt(365.25)) if std > 0 else math.nan,
        "max_drawdown": float(drawdown.min()),
    }


def evaluate_scout(panel: pd.DataFrame, spec: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the frozen descriptive tests, costs, and progression gates."""
    required = {
        "session_date",
        "signal_timestamp",
        "entry_timestamp",
        "exit_timestamp",
        "signal_return",
        "last_half_hour_return",
        "selected",
        "timestamp_alignment_valid",
    }
    missing = required.difference(panel.columns)
    if missing:
        raise ValueError(f"panel missing required columns: {sorted(missing)}")
    ordered = panel.sort_values("session_date", kind="stable").reset_index(drop=True).copy()
    selected = ordered.loc[ordered["selected"].astype(bool)].copy()
    if selected.empty:
        raise ValueError("no selected sessions")

    costs = spec["costs"]
    fee_only = float(costs["fee_only_per_side_bps"]) * 2.0 / 10_000.0
    conservative = float(costs["conservative_round_trip_bps"]) / 10_000.0
    ordered["strategy_gross_return"] = np.where(
        ordered["selected"], ordered["last_half_hour_return"], 0.0
    )
    ordered["strategy_fee_only_return"] = np.where(
        ordered["selected"], ordered["last_half_hour_return"] - fee_only, 0.0
    )
    ordered["strategy_conservative_return"] = np.where(
        ordered["selected"], ordered["last_half_hour_return"] - conservative, 0.0
    )
    selected = ordered.loc[ordered["selected"]].copy()

    regression = linregress(ordered["signal_return"], ordered["last_half_hour_return"])
    bootstrap = spec["bootstrap"]
    lower, upper = _bootstrap_interval(
        selected["last_half_hour_return"],
        resamples=int(bootstrap["session_resamples"]),
        seed=int(bootstrap["seed"]),
    )
    split = len(selected) // 2
    first_half = selected.iloc[:split]
    second_half = selected.iloc[split:]
    remove_count = max(1, math.ceil(len(selected) * 0.05))
    removed = selected["last_half_hour_return"].abs().nlargest(remove_count).index
    trimmed = selected.drop(index=removed)
    profitable = selected.loc[selected["last_half_hour_return"] > 0, "last_half_hour_return"]
    top_profit_count = max(1, math.ceil(len(profitable) * 0.05)) if len(profitable) else 0
    top_profit_contribution = (
        float(profitable.nlargest(top_profit_count).sum() / profitable.sum())
        if len(profitable) and profitable.sum() > 0
        else math.nan
    )

    mean_gross = float(selected["last_half_hour_return"].mean())
    mean_fee = float(selected["strategy_fee_only_return"].mean())
    mean_conservative = float(selected["strategy_conservative_return"].mean())
    directional_accuracy = float((selected["last_half_hour_return"] > 0).mean())
    gates_spec = spec["progression_gates"]
    gates = {
        "minimum_selected_sessions": len(selected) >= int(gates_spec["minimum_selected_sessions"]),
        "positive_mean_gross": mean_gross > float(gates_spec["minimum_mean_gross_bps"]) / 10_000.0,
        "directional_accuracy_above_50pct": directional_accuracy
        > float(gates_spec["minimum_directional_accuracy"]),
        "positive_each_chronological_half_gross": float(first_half["last_half_hour_return"].mean()) > 0
        and float(second_half["last_half_hour_return"].mean()) > 0,
        "bootstrap_lower_above_zero": lower
        > float(gates_spec["minimum_session_bootstrap_lower_95_bps"]) / 10_000.0,
        "positive_after_conservative_costs": mean_conservative > 0,
        "positive_after_top_5pct_absolute_removed": float(trimmed["last_half_hour_return"].mean()) > 0,
        "top_5pct_profit_contribution_within_cap": top_profit_contribution
        <= float(gates_spec["maximum_top_5pct_profit_contribution"]),
        "complete_timestamp_alignment": bool(ordered["timestamp_alignment_valid"].all()),
    }

    by_year = {
        str(year): {
            "sessions": int(len(group)),
            "selected_sessions": int(group["selected"].sum()),
            "mean_selected_gross_bps": float(
                group.loc[group["selected"], "last_half_hour_return"].mean() * 10_000.0
            ),
            "mean_selected_conservative_bps": float(
                group.loc[group["selected"], "strategy_conservative_return"].mean() * 10_000.0
            ),
        }
        for year, group in ordered.groupby(pd.to_datetime(ordered["session_date"]).dt.year)
    }
    return {
        "specification_id": spec["specification_id"],
        "sessions": len(ordered),
        "selected_sessions": len(selected),
        "exposure_fraction": float(len(selected) / len(ordered)),
        "mean_signal_bps": float(ordered["signal_return"].mean() * 10_000.0),
        "mean_last_half_hour_all_bps": float(ordered["last_half_hour_return"].mean() * 10_000.0),
        "mean_selected_gross_bps": mean_gross * 10_000.0,
        "mean_selected_fee_only_bps": mean_fee * 10_000.0,
        "mean_selected_conservative_bps": mean_conservative * 10_000.0,
        "directional_accuracy": directional_accuracy,
        "chronological_halves_gross_bps": [
            float(first_half["last_half_hour_return"].mean() * 10_000.0),
            float(second_half["last_half_hour_return"].mean() * 10_000.0),
        ],
        "bootstrap_95_gross_bps": [lower * 10_000.0, upper * 10_000.0],
        "trimmed_mean_gross_bps": float(trimmed["last_half_hour_return"].mean() * 10_000.0),
        "top_5pct_profit_contribution": top_profit_contribution,
        "predictive_regression": {
            "slope": float(regression.slope),
            "intercept": float(regression.intercept),
            "r_squared": float(regression.rvalue**2),
            "pvalue_iid": float(regression.pvalue),
            "note": "IID diagnostic only; the source paper uses pooled/Newey-West and recursive OOS tests.",
        },
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


def format_report(report: dict[str, Any], *, partition: str) -> str:
    verdict = "PASS" if report["passed"] else "FAIL"
    lines = [
        f"# Bitcoin U.S.-Session Close Momentum — {partition}",
        "",
        f"Verdict: **{verdict}**",
        "",
        "Frozen Binance spot BTCUSDT long/flat falsification scout; not a validated Strategy.",
        "",
        f"- Complete sessions: {report['sessions']}",
        f"- Triggered sessions: {report['selected_sessions']}",
        f"- Exposure fraction: {report['exposure_fraction']:.4f}",
        f"- Mean selected gross return: {report['mean_selected_gross_bps']:.4f} bps",
        f"- Mean after fee-only costs: {report['mean_selected_fee_only_bps']:.4f} bps",
        f"- Mean after conservative costs: {report['mean_selected_conservative_bps']:.4f} bps",
        f"- Directional accuracy: {report['directional_accuracy']:.4f}",
        f"- Chronological halves gross: {report['chronological_halves_gross_bps']}",
        f"- Session-bootstrap 95% gross interval: {report['bootstrap_95_gross_bps']}",
        f"- Trimmed mean gross: {report['trimmed_mean_gross_bps']:.4f} bps",
        f"- Top 5% profitable-session contribution: {report['top_5pct_profit_contribution']:.4f}",
        "",
        "## Predictive regression diagnostic",
        "",
        f"- ONFH slope: {report['predictive_regression']['slope']:.6f}",
        f"- R-squared: {report['predictive_regression']['r_squared']:.6f}",
        f"- IID p-value: {report['predictive_regression']['pvalue_iid']:.6g}",
        "- This is not the paper's pooled Newey-West or recursive out-of-sample regression.",
        "",
        "## Gates",
        "",
    ]
    lines.extend(f"- {'PASS' if passed else 'FAIL'} — {name}" for name, passed in report["gates"].items())
    lines.extend(["", "## Year decomposition", ""])
    for year, values in report["by_year"].items():
        lines.append(
            f"- {year}: selected={values['selected_sessions']}, gross={values['mean_selected_gross_bps']:.4f} bps, conservative={values['mean_selected_conservative_bps']:.4f} bps"
        )
    lines.extend(
        [
            "",
            "If this report fails, later partitions remain locked and nearby variants are prohibited by the frozen stopping rule.",
            "",
        ]
    )
    return "\n".join(lines)
