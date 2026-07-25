"""Frozen evaluation logic for Alpaca-IEX-OrderFlow-Predictiveness-v1."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any, cast

import pandas as pd
from scipy.stats import spearmanr

from research.alpaca_iex_l1_features import (
    attach_iex_execution_returns,
    build_iex_5min_features,
)

SPEC_PATH = Path("research_scout/alpaca_iex_orderflow_v1.json")


def load_spec(path: Path = SPEC_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("scout specification must be a JSON object")
    return cast(dict[str, Any], payload)


def prepare_session_features(
    trades: pd.DataFrame,
    quotes: pd.DataFrame,
    *,
    symbol: str,
    session_date: str,
) -> pd.DataFrame:
    """Build the frozen signal window and execution diagnostics for one symbol-session."""
    features = build_iex_5min_features(trades, quotes)
    features = attach_iex_execution_returns(features, quotes)
    if features.empty:
        return features.reset_index()
    eastern = features.index.tz_convert("America/New_York")
    in_session = eastern.strftime("%Y-%m-%d") == session_date
    time_text = eastern.strftime("%H:%M:%S")
    in_window = (time_text >= "09:35:00") & (time_text <= "10:25:00")
    selected = features.loc[in_session & in_window].copy()
    selected.insert(0, "symbol", symbol)
    selected.insert(1, "session_date", session_date)
    return selected.reset_index()


def _safe_spearman(x: pd.Series, y: pd.Series) -> dict[str, float | None]:
    paired = pd.concat([x, y], axis=1).dropna()
    if len(paired) < 3 or paired.iloc[:, 0].nunique() < 2 or paired.iloc[:, 1].nunique() < 2:
        return {"coefficient": None, "pvalue": None, "rows": int(len(paired))}
    result = spearmanr(paired.iloc[:, 0], paired.iloc[:, 1])
    return {
        "coefficient": float(result.statistic),
        "pvalue": float(result.pvalue),
        "rows": int(len(paired)),
    }


def _session_block_interval(
    selected: pd.DataFrame,
    *,
    resamples: int,
    seed: int,
) -> tuple[float, float]:
    grouped = selected.groupby("session_date")["signed_midpoint_return"].agg(["sum", "count"])
    if grouped.empty:
        return math.nan, math.nan
    rng = random.Random(seed)
    indices = list(range(len(grouped)))
    values: list[float] = []
    for _ in range(resamples):
        sampled = grouped.iloc[rng.choices(indices, k=len(indices))]
        values.append(float(sampled["sum"].sum() / sampled["count"].sum() * 10_000.0))
    lower = pd.Series(values).quantile(0.025)
    upper = pd.Series(values).quantile(0.975)
    return float(lower), float(upper)


def evaluate_scout(panel: pd.DataFrame, spec: dict[str, Any]) -> dict[str, Any]:
    """Evaluate exactly the frozen diagnostics and progression gates."""
    required = {
        "symbol",
        "session_date",
        "signal_timestamp",
        "signed_trade_imbalance",
        "terminal_quote_size_imbalance",
        "composite_score",
        "selected",
        "next_midpoint_return",
        "iex_crossing_return",
        "iex_crossing_net_return",
    }
    missing = required.difference(panel.columns)
    if missing:
        raise ValueError(f"panel missing required columns: {sorted(missing)}")

    valid = panel.dropna(subset=["composite_score", "next_midpoint_return"]).copy()
    direction = valid["composite_score"].astype(float).apply(
        lambda value: 1 if value > 0 else -1 if value < 0 else 0
    )
    valid["signed_midpoint_return"] = direction * valid["next_midpoint_return"].astype(float)
    valid["direction_correct"] = valid["signed_midpoint_return"] > 0
    selected = valid.loc[valid["selected"].astype(bool)].copy()

    bootstrap_spec = spec["bootstrap"]
    lower, upper = _session_block_interval(
        selected,
        resamples=int(bootstrap_spec["session_resamples"]),
        seed=int(bootstrap_spec["seed"]),
    )
    by_symbol = {
        str(symbol): {
            "selected_rows": int(len(group)),
            "mean_signed_midpoint_bps": float(group["signed_midpoint_return"].mean() * 10_000.0),
            "directional_accuracy": float(group["direction_correct"].mean()),
            "mean_iex_crossing_bps": float(group["iex_crossing_return"].mean() * 10_000.0),
            "mean_iex_crossing_net_bps": float(
                group["iex_crossing_net_return"].mean() * 10_000.0
            ),
        }
        for symbol, group in selected.groupby("symbol", sort=True)
    }
    month = pd.to_datetime(selected["session_date"]).dt.strftime("%Y-%m")
    by_month = {
        str(key): {
            "selected_rows": int(len(group)),
            "mean_signed_midpoint_bps": float(group["signed_midpoint_return"].mean() * 10_000.0),
        }
        for key, group in selected.groupby(month, sort=True)
    }

    session_extremes = valid.groupby("session_date")["next_midpoint_return"].apply(
        lambda series: float(series.abs().max())
    )
    remove_count = max(1, math.ceil(len(session_extremes) * 0.05)) if len(session_extremes) else 0
    removed_sessions = set(session_extremes.nlargest(remove_count).index)
    trimmed = selected.loc[~selected["session_date"].isin(removed_sessions)]

    mean_midpoint_bps = float(selected["signed_midpoint_return"].mean() * 10_000.0)
    mean_crossing_bps = float(selected["iex_crossing_return"].mean() * 10_000.0)
    mean_crossing_net_bps = float(selected["iex_crossing_net_return"].mean() * 10_000.0)
    trimmed_mean_bps = float(trimmed["signed_midpoint_return"].mean() * 10_000.0)
    gates_spec = spec["progression_gates"]
    symbols = [str(symbol) for symbol in spec["symbols"]]
    gates = {
        "minimum_selected_rows": int(len(selected)) >= int(gates_spec["minimum_selected_rows"]),
        "minimum_mean_signed_midpoint_bps": mean_midpoint_bps
        >= float(gates_spec["minimum_mean_signed_midpoint_bps"]),
        "bootstrap_lower_above_zero": lower
        > float(gates_spec["minimum_session_block_bootstrap_lower_95_bps"]),
        "positive_each_symbol": all(
            symbol in by_symbol and by_symbol[symbol]["mean_signed_midpoint_bps"] > 0
            for symbol in symbols
        ),
        "positive_after_top_5pct_sessions_removed": trimmed_mean_bps > 0,
        "positive_iex_crossing_after_extra_friction": mean_crossing_net_bps > 0,
    }

    diagnostics_columns = [
        "excluded_trade_condition_count",
        "excluded_quote_condition_count",
        "stale_or_unmatched_trade_count",
        "locked_quote_count",
        "crossed_quote_count",
        "one_sided_quote_count",
        "invalid_quote_count",
        "execution_quotes_missing",
    ]
    exclusions = {
        column: int(panel[column].fillna(0).sum())
        for column in diagnostics_columns
        if column in panel
    }
    return {
        "specification_id": spec["specification_id"],
        "rows": int(len(valid)),
        "selected_rows": int(len(selected)),
        "selected_fraction": float(len(selected) / len(valid)) if len(valid) else 0.0,
        "mean_signed_midpoint_bps": mean_midpoint_bps,
        "directional_accuracy": float(selected["direction_correct"].mean()),
        "mean_iex_crossing_bps": mean_crossing_bps,
        "mean_iex_crossing_net_bps": mean_crossing_net_bps,
        "bootstrap_95_bps": [lower, upper],
        "trimmed_mean_signed_midpoint_bps": trimmed_mean_bps,
        "removed_top_5pct_sessions": sorted(str(value) for value in removed_sessions),
        "information_coefficients": {
            "signed_trade_imbalance": _safe_spearman(
                valid["signed_trade_imbalance"], valid["next_midpoint_return"]
            ),
            "terminal_quote_size_imbalance": _safe_spearman(
                valid["terminal_quote_size_imbalance"], valid["next_midpoint_return"]
            ),
            "composite_score": _safe_spearman(
                valid["composite_score"], valid["next_midpoint_return"]
            ),
        },
        "by_symbol": by_symbol,
        "by_month": by_month,
        "exclusions": exclusions,
        "gates": gates,
        "passed": all(gates.values()),
    }


def format_report(report: dict[str, Any], *, partition: str) -> str:
    verdict = "PASS" if report["passed"] else "FAIL"
    lines = [
        f"# Alpaca IEX Order-Flow Scout — {partition}",
        "",
        f"Verdict: **{verdict}**",
        "",
        "This is a frozen venue-local information-content scout, not a Strategy or executable P&L claim.",
        "",
        f"- Valid rows: {report['rows']}",
        f"- Selected rows: {report['selected_rows']}",
        f"- Mean signed midpoint return: {report['mean_signed_midpoint_bps']:.4f} bps",
        f"- Directional accuracy: {report['directional_accuracy']:.4f}",
        f"- Mean IEX crossing return: {report['mean_iex_crossing_bps']:.4f} bps",
        f"- Mean IEX crossing after extra friction: {report['mean_iex_crossing_net_bps']:.4f} bps",
        f"- Session-block bootstrap 95% interval: [{report['bootstrap_95_bps'][0]:.4f}, {report['bootstrap_95_bps'][1]:.4f}] bps",
        f"- Trimmed mean: {report['trimmed_mean_signed_midpoint_bps']:.4f} bps",
        "",
        "## Gates",
        "",
    ]
    lines.extend(
        f"- {'PASS' if passed else 'FAIL'} — {name}" for name, passed in report["gates"].items()
    )
    lines.extend(["", "## By symbol", ""])
    for symbol, values in report["by_symbol"].items():
        lines.append(
            f"- {symbol}: n={values['selected_rows']}, midpoint={values['mean_signed_midpoint_bps']:.4f} bps, net IEX={values['mean_iex_crossing_net_bps']:.4f} bps"
        )
    lines.extend(
        [
            "",
            "If the verdict is FAIL, the frozen stopping rule prohibits opening the next partition or trying nearby variants.",
            "",
        ]
    )
    return "\n".join(lines)
