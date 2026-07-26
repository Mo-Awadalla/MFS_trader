"""Frozen SEC Item 2.02 premarket-continuation falsification scout.

The module deliberately stops before Strategy registration and the Validation
Gauntlet. The frozen static-universe/IEX design can falsify the mechanism, but a
pass only justifies a point-in-time-universe and SIP-quality replication.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

SPEC_PATH = Path("research_scout/sec_item_202_premarket_continuation_v1.json")
EVENT_REQUIRED_COLUMNS = {
    "symbol",
    "cik",
    "accession_number",
    "acceptance_datetime",
    "form",
    "items",
}
BAR_REQUIRED_COLUMNS = {"symbol", "timestamp", "open", "close"}


def load_spec(path: Path = SPEC_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("scout specification must be a JSON object")
    return cast(dict[str, Any], payload)


def _item_tokens(value: Any) -> set[str]:
    return {token for token in re.split(r"[,;\s]+", str(value).strip()) if token}


def select_eligible_events(
    events: pd.DataFrame,
    spec: dict[str, Any],
    *,
    partition: str,
    universe: tuple[str, ...] | list[str] | set[str] | None = None,
) -> pd.DataFrame:
    """Select point-in-time premarket Item 2.02 events for one frozen partition."""
    missing = EVENT_REQUIRED_COLUMNS.difference(events.columns)
    if missing:
        raise ValueError(f"events missing required columns: {sorted(missing)}")
    if partition not in spec["partitions"]:
        raise ValueError(f"unknown partition: {partition}")

    selected = events.copy()
    selected["symbol"] = selected["symbol"].astype(str).str.upper()
    selected["form"] = selected["form"].astype(str).str.upper()
    selected["acceptance_datetime"] = pd.to_datetime(
        selected["acceptance_datetime"], utc=True, errors="coerce"
    )
    selected = selected.dropna(subset=["acceptance_datetime"])

    event_spec = spec["event"]
    forms = {str(value).upper() for value in event_spec["forms"]}
    required_item = str(event_spec["required_item"])
    selected = selected.loc[selected["form"].isin(forms)]
    selected = selected.loc[
        selected["items"].map(lambda value: required_item in _item_tokens(value))
    ]
    if universe is not None:
        allowed = {str(symbol).strip().upper() for symbol in universe}
        selected = selected.loc[selected["symbol"].isin(allowed)]

    zone = str(event_spec["timezone"])
    local = selected["acceptance_datetime"].dt.tz_convert(zone)
    selected["acceptance_local"] = local
    selected["session_date"] = local.dt.date.astype(str)
    local_clock = local.dt.hour * 3600 + local.dt.minute * 60 + local.dt.second
    start_clock = _clock_seconds(str(event_spec["acceptance_start_time"]))
    cutoff_clock = _clock_seconds(str(event_spec["acceptance_cutoff_time"]))
    selected = selected.loc[local_clock.between(start_clock, cutoff_clock, inclusive="both")]

    bounds = spec["partitions"][partition]
    selected = selected.loc[
        selected["session_date"].between(str(bounds["start"]), str(bounds["end"]), inclusive="both")
    ]
    selected = selected.sort_values(
        ["session_date", "symbol", "acceptance_datetime", "accession_number"],
        kind="stable",
    )
    selected = selected.drop_duplicates(["session_date", "symbol"], keep="first")
    return selected.reset_index(drop=True)


def _clock_seconds(value: str) -> int:
    parts = value.split(":")
    if len(parts) != 3:
        raise ValueError(f"clock must be HH:MM:SS: {value}")
    hour, minute, second = (int(part) for part in parts)
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        raise ValueError(f"invalid clock: {value}")
    return hour * 3600 + minute * 60 + second


def _local_timestamp(session_date: str, clock: str, zone: str) -> pd.Timestamp:
    return pd.Timestamp(f"{session_date} {clock}", tz=zone).tz_convert("UTC")


def _bar_value(
    indexed: pd.DataFrame,
    symbol: str,
    timestamp: pd.Timestamp,
    field: str,
) -> float | None:
    key = (symbol, timestamp)
    if key not in indexed.index:
        return None
    value = indexed.at[key, field]
    if isinstance(value, pd.Series):
        raise ValueError(f"duplicate bar for {symbol} at {timestamp}")
    number = float(value)
    return number if math.isfinite(number) and number > 0.0 else None


def build_event_panel(
    eligible_events: pd.DataFrame,
    bars: pd.DataFrame,
    spec: dict[str, Any],
) -> pd.DataFrame:
    """Join frozen event timestamps to exact signal, entry, and exit bars.

    Every eligible event remains in the returned panel. Missing or invalid bars
    are represented by ``complete_window=False`` plus a diagnostic string.
    """
    event_missing = EVENT_REQUIRED_COLUMNS.difference(eligible_events.columns)
    if event_missing:
        raise ValueError(f"eligible_events missing required columns: {sorted(event_missing)}")
    bar_missing = BAR_REQUIRED_COLUMNS.difference(bars.columns)
    if bar_missing:
        raise ValueError(f"bars missing required columns: {sorted(bar_missing)}")

    normalized = bars.copy()
    normalized["symbol"] = normalized["symbol"].astype(str).str.upper()
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], utc=True, errors="coerce")
    if normalized["timestamp"].isna().any():
        raise ValueError("bars contain invalid timestamps")
    if normalized.duplicated(["symbol", "timestamp"]).any():
        raise ValueError("bars contain duplicate symbol/timestamp rows")
    normalized = normalized.set_index(["symbol", "timestamp"]).sort_index()

    benchmark = str(spec["universe"]["benchmark"]).upper()
    clocks = spec["clocks"]
    zone = str(clocks["timezone"])
    rows: list[dict[str, Any]] = []
    ordered_events = eligible_events.sort_values(
        ["session_date", "symbol", "acceptance_datetime"], kind="stable"
    )
    for event in ordered_events.itertuples(index=False):
        session_date = str(event.session_date)
        symbol = str(event.symbol).upper()
        signal_open_ts = _local_timestamp(session_date, clocks["signal_open_bar"], zone)
        signal_last_bar_ts = _local_timestamp(session_date, clocks["signal_last_bar"], zone)
        signal_known_ts = _local_timestamp(session_date, clocks["signal_known_time"], zone)
        entry_ts = _local_timestamp(session_date, clocks["entry_bar"], zone)
        exit_ts = _local_timestamp(session_date, clocks["exit_bar"], zone)

        required_prices = {
            "stock_signal_open": _bar_value(normalized, symbol, signal_open_ts, "open"),
            "stock_signal_close": _bar_value(normalized, symbol, signal_last_bar_ts, "close"),
            "benchmark_signal_open": _bar_value(normalized, benchmark, signal_open_ts, "open"),
            "benchmark_signal_close": _bar_value(
                normalized, benchmark, signal_last_bar_ts, "close"
            ),
            "stock_entry": _bar_value(normalized, symbol, entry_ts, "open"),
            "stock_exit": _bar_value(normalized, symbol, exit_ts, "open"),
            "benchmark_entry": _bar_value(normalized, benchmark, entry_ts, "open"),
            "benchmark_exit": _bar_value(normalized, benchmark, exit_ts, "open"),
        }
        missing_prices = sorted(name for name, value in required_prices.items() if value is None)
        complete = not missing_prices
        acceptance = pd.Timestamp(event.acceptance_datetime)
        cutoff = _local_timestamp(session_date, spec["event"]["acceptance_cutoff_time"], zone)
        aligned = (
            acceptance <= cutoff
            and cutoff < signal_open_ts
            and signal_open_ts < signal_known_ts < entry_ts < exit_ts
        )

        stock_signal = benchmark_signal = residual_signal = math.nan
        stock_gross = benchmark_holding = residual_gross = math.nan
        selected = False
        if complete:
            prices = cast(dict[str, float], required_prices)
            stock_signal = prices["stock_signal_close"] / prices["stock_signal_open"] - 1.0
            benchmark_signal = (
                prices["benchmark_signal_close"] / prices["benchmark_signal_open"] - 1.0
            )
            residual_signal = stock_signal - benchmark_signal
            stock_gross = prices["stock_exit"] / prices["stock_entry"] - 1.0
            benchmark_holding = prices["benchmark_exit"] / prices["benchmark_entry"] - 1.0
            residual_gross = stock_gross - benchmark_holding
            selected = residual_signal > float(spec["signal"]["threshold"])

        rows.append(
            {
                "session_date": session_date,
                "symbol": symbol,
                "cik": str(event.cik),
                "accession_number": str(event.accession_number),
                "acceptance_datetime": acceptance,
                "signal_open_timestamp": signal_open_ts,
                "signal_known_timestamp": signal_known_ts,
                "entry_timestamp": entry_ts,
                "exit_timestamp": exit_ts,
                **required_prices,
                "stock_signal_return": stock_signal,
                "benchmark_signal_return": benchmark_signal,
                "residual_signal_return": residual_signal,
                "stock_gross_return": stock_gross,
                "benchmark_holding_return": benchmark_holding,
                "residual_gross_return": residual_gross,
                "selected": selected,
                "complete_window": complete,
                "missing_inputs": ",".join(missing_prices),
                "timestamp_alignment_valid": aligned,
            }
        )
    return pd.DataFrame(rows)


def _bootstrap_interval(
    values: pd.Series,
    *,
    resamples: int,
    seed: int,
) -> tuple[float, float]:
    clean = values.dropna().astype(float).to_numpy()
    if len(clean) == 0:
        return math.nan, math.nan
    rng = np.random.default_rng(seed)
    sampled = rng.choice(clean, size=(resamples, len(clean)), replace=True).mean(axis=1)
    return float(np.quantile(sampled, 0.025)), float(np.quantile(sampled, 0.975))


def _profit_factor(values: pd.Series) -> float:
    clean = values.dropna().astype(float)
    positive = float(clean.loc[clean > 0.0].sum())
    negative = float(-clean.loc[clean < 0.0].sum())
    if negative == 0.0:
        return math.inf if positive > 0.0 else 0.0
    return positive / negative


def _top_profit_contribution(values: pd.Series, fraction: float = 0.05) -> float:
    profitable = values.dropna().astype(float)
    profitable = profitable.loc[profitable > 0.0]
    if profitable.empty or float(profitable.sum()) <= 0.0:
        return math.inf
    count = max(1, math.ceil(len(profitable) * fraction))
    return float(profitable.nlargest(count).sum() / profitable.sum())


def _issuer_absolute_share(selected: pd.DataFrame) -> float:
    absolute = selected.groupby("symbol")["residual_fixed_net_return"].apply(
        lambda values: float(values.abs().sum())
    )
    total = float(absolute.sum())
    return float(absolute.max() / total) if total > 0.0 else math.inf


def evaluate_scout(
    panel: pd.DataFrame,
    spec: dict[str, Any],
    *,
    partition: str,
) -> dict[str, Any]:
    """Evaluate the frozen event-level and whole-session progression gates."""
    required = {
        "session_date",
        "symbol",
        "acceptance_datetime",
        "signal_known_timestamp",
        "entry_timestamp",
        "exit_timestamp",
        "residual_signal_return",
        "stock_gross_return",
        "residual_gross_return",
        "selected",
        "complete_window",
        "timestamp_alignment_valid",
    }
    missing = required.difference(panel.columns)
    if missing:
        raise ValueError(f"panel missing required columns: {sorted(missing)}")
    if partition not in spec["partitions"]:
        raise ValueError(f"unknown partition: {partition}")
    if panel.empty:
        raise ValueError("panel has no eligible events")

    ordered = panel.sort_values(["session_date", "symbol"], kind="stable").reset_index(drop=True)
    complete = ordered.loc[ordered["complete_window"].astype(bool)].copy()
    selected = complete.loc[complete["selected"].astype(bool)].copy()
    if selected.empty:
        raise ValueError("panel has no selected complete events")

    fixed_cost = float(spec["costs"]["fixed_round_trip_bps"]) / 10_000.0
    stress_cost = float(spec["costs"]["stress_round_trip_bps"]) / 10_000.0
    for frame in (ordered, complete, selected):
        frame["stock_fixed_net_return"] = np.where(
            frame["selected"], frame["stock_gross_return"] - fixed_cost, 0.0
        )
        frame["residual_fixed_net_return"] = np.where(
            frame["selected"], frame["residual_gross_return"] - fixed_cost, 0.0
        )
        frame["residual_stress_net_return"] = np.where(
            frame["selected"], frame["residual_gross_return"] - stress_cost, 0.0
        )

    active_sessions = (
        selected.groupby("session_date", sort=True)
        .agg(
            trade_count=("symbol", "size"),
            stock_gross_return=("stock_gross_return", "mean"),
            stock_fixed_net_return=("stock_fixed_net_return", "mean"),
            residual_gross_return=("residual_gross_return", "mean"),
            residual_fixed_net_return=("residual_fixed_net_return", "mean"),
            residual_stress_net_return=("residual_stress_net_return", "mean"),
        )
        .reset_index()
    )
    all_sessions = pd.DataFrame(
        {"session_date": sorted(complete["session_date"].astype(str).unique())}
    )
    session_returns = all_sessions.merge(active_sessions, on="session_date", how="left")
    return_columns = [
        "stock_gross_return",
        "stock_fixed_net_return",
        "residual_gross_return",
        "residual_fixed_net_return",
        "residual_stress_net_return",
    ]
    session_returns[return_columns] = session_returns[return_columns].fillna(0.0)
    session_returns["trade_count"] = session_returns["trade_count"].fillna(0).astype(int)

    net_event = selected["residual_fixed_net_return"]
    net_session = active_sessions["residual_fixed_net_return"]
    bootstrap_spec = spec["bootstrap"]
    bootstrap_low, bootstrap_high = _bootstrap_interval(
        net_session,
        resamples=int(bootstrap_spec["session_resamples"]),
        seed=int(bootstrap_spec["seed"]),
    )
    split = len(active_sessions) // 2
    first_half = active_sessions.iloc[:split]
    second_half = active_sessions.iloc[split:]
    remove_count = max(1, math.ceil(len(active_sessions) * 0.05))
    removed = net_session.abs().nlargest(remove_count).index
    trimmed = active_sessions.drop(index=removed)

    complete_fraction = float(len(complete) / len(ordered))
    mean_stock_net = float(selected["stock_fixed_net_return"].mean())
    mean_gross_residual = float(selected["residual_gross_return"].mean())
    mean_net_residual = float(net_event.mean())
    mean_stress_residual = float(selected["residual_stress_net_return"].mean())
    profit_factor = _profit_factor(net_event)
    top_profit_contribution = _top_profit_contribution(net_session)
    issuer_share = _issuer_absolute_share(selected)
    partition_spec = spec["partitions"][partition]
    gate_spec = spec["progression_gates"]
    gates = {
        "minimum_complete_event_fraction": complete_fraction
        >= float(gate_spec["minimum_complete_event_fraction"]),
        "minimum_selected_events": len(selected) >= int(partition_spec["minimum_selected_events"]),
        "minimum_selected_sessions": len(active_sessions)
        >= int(partition_spec["minimum_selected_sessions"]),
        "positive_mean_gross_residual": mean_gross_residual > 0.0,
        "minimum_mean_net_residual": mean_net_residual
        >= float(gate_spec["minimum_mean_net_residual_bps"]) / 10_000.0,
        "positive_mean_stock_net": mean_stock_net > 0.0,
        "positive_each_chronological_half_net": (
            not first_half.empty
            and not second_half.empty
            and float(first_half["residual_fixed_net_return"].mean()) > 0.0
            and float(second_half["residual_fixed_net_return"].mean()) > 0.0
        ),
        "session_bootstrap_lower_above_zero": bootstrap_low
        > float(gate_spec["minimum_session_bootstrap_lower_95_bps"]) / 10_000.0,
        "minimum_profit_factor": profit_factor >= float(gate_spec["minimum_profit_factor"]),
        "positive_after_top_5pct_absolute_sessions_removed": (
            not trimmed.empty and float(trimmed["residual_fixed_net_return"].mean()) > 0.0
        ),
        "positive_under_stress_costs": mean_stress_residual > 0.0,
        "top_5pct_profitable_session_contribution_within_cap": top_profit_contribution
        <= float(gate_spec["maximum_top_5pct_profitable_session_contribution"]),
        "single_issuer_absolute_pnl_share_within_cap": issuer_share
        <= float(gate_spec["maximum_single_issuer_absolute_pnl_share"]),
        "complete_timestamp_alignment": bool(
            complete["timestamp_alignment_valid"].astype(bool).all()
        ),
    }

    by_year: dict[str, dict[str, float | int]] = {}
    selected_years = pd.to_datetime(selected["session_date"]).dt.year
    for year, group in selected.groupby(selected_years, sort=True):
        by_year[str(year)] = {
            "selected_events": int(len(group)),
            "active_sessions": int(group["session_date"].nunique()),
            "mean_stock_net_bps": float(group["stock_fixed_net_return"].mean() * 10_000.0),
            "mean_residual_net_bps": float(group["residual_fixed_net_return"].mean() * 10_000.0),
        }

    return {
        "specification_id": spec["specification_id"],
        "partition": partition,
        "eligible_events": int(len(ordered)),
        "complete_events": int(len(complete)),
        "complete_event_fraction": complete_fraction,
        "selected_events": int(len(selected)),
        "selected_sessions": int(len(active_sessions)),
        "selection_fraction": float(len(selected) / len(complete)),
        "mean_stock_gross_bps": float(selected["stock_gross_return"].mean() * 10_000.0),
        "mean_stock_fixed_net_bps": mean_stock_net * 10_000.0,
        "mean_residual_gross_bps": mean_gross_residual * 10_000.0,
        "mean_residual_fixed_net_bps": mean_net_residual * 10_000.0,
        "mean_residual_stress_net_bps": mean_stress_residual * 10_000.0,
        "directional_accuracy_residual": float((selected["residual_gross_return"] > 0.0).mean()),
        "profit_factor_residual_fixed_net": profit_factor,
        "chronological_halves_residual_fixed_net_bps": [
            float(first_half["residual_fixed_net_return"].mean() * 10_000.0),
            float(second_half["residual_fixed_net_return"].mean() * 10_000.0),
        ],
        "session_bootstrap_95_residual_fixed_net_bps": [
            bootstrap_low * 10_000.0,
            bootstrap_high * 10_000.0,
        ],
        "trimmed_mean_residual_fixed_net_bps": float(
            trimmed["residual_fixed_net_return"].mean() * 10_000.0
        ),
        "top_5pct_profitable_session_contribution": top_profit_contribution,
        "maximum_single_issuer_absolute_pnl_share": issuer_share,
        "by_year": by_year,
        "missing_input_counts": {
            str(key): int(value)
            for key, value in ordered.loc[~ordered["complete_window"], "missing_inputs"]
            .value_counts()
            .items()
        },
        "gates": gates,
        "passed": all(gates.values()),
        "panel": ordered,
        "session_returns": session_returns,
    }


def serializable_report(report: dict[str, Any]) -> dict[str, Any]:
    payload = {
        key: value for key, value in report.items() if key not in {"panel", "session_returns"}
    }
    return cast(dict[str, Any], _json_safe(payload))


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def format_report(report: dict[str, Any]) -> str:
    verdict = "PASS" if report["passed"] else "FAIL"
    lines = [
        f"# SEC Item 2.02 Premarket Continuation — {report['partition']}",
        "",
        f"Verdict: **{verdict}**",
        "",
        "Frozen static-universe Alpaca IEX falsification scout. A pass does not authorize paper or live trading.",
        "",
        f"- Eligible events: {report['eligible_events']}",
        f"- Complete events: {report['complete_events']} ({report['complete_event_fraction']:.2%})",
        f"- Selected events / sessions: {report['selected_events']} / {report['selected_sessions']}",
        f"- Mean stock gross: {report['mean_stock_gross_bps']:.4f} bps",
        f"- Mean stock after fixed costs: {report['mean_stock_fixed_net_bps']:.4f} bps",
        f"- Mean residual gross: {report['mean_residual_gross_bps']:.4f} bps",
        f"- Mean residual after fixed costs: {report['mean_residual_fixed_net_bps']:.4f} bps",
        f"- Mean residual after stress costs: {report['mean_residual_stress_net_bps']:.4f} bps",
        f"- Residual directional accuracy: {report['directional_accuracy_residual']:.4f}",
        f"- Residual net profit factor: {report['profit_factor_residual_fixed_net']:.4f}",
        f"- Chronological halves residual net: {report['chronological_halves_residual_fixed_net_bps']}",
        f"- Session-bootstrap 95% residual net interval: {report['session_bootstrap_95_residual_fixed_net_bps']}",
        f"- Trimmed residual net mean: {report['trimmed_mean_residual_fixed_net_bps']:.4f} bps",
        "",
        "## Gates",
        "",
    ]
    lines.extend(
        f"- {'PASS' if passed else 'FAIL'} — {name}" for name, passed in report["gates"].items()
    )
    lines.extend(["", "## Year decomposition", ""])
    for year, values in report["by_year"].items():
        lines.append(
            f"- {year}: events={values['selected_events']}, sessions={values['active_sessions']}, "
            f"stock net={values['mean_stock_net_bps']:.4f} bps, "
            f"residual net={values['mean_residual_net_bps']:.4f} bps"
        )
    if report["missing_input_counts"]:
        lines.extend(["", "## Missing event windows", ""])
        lines.extend(
            f"- {reason}: {count}" for reason, count in report["missing_input_counts"].items()
        )
    lines.extend(
        [
            "",
            "If this partition fails, later partitions remain locked and nearby thresholds, clocks, filters, or an inverted short rule are prohibited.",
            "",
        ]
    )
    return "\n".join(lines)
