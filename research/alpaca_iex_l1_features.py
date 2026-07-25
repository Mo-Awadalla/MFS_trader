"""Leakage-controlled interval features from Alpaca IEX Level-1 events."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

FREQUENCY = "5min"
MAXIMUM_QUOTE_AGE_MS = 2_000.0
SELECTION_THRESHOLD = 0.20
TRADE_REQUIRED = {"timestamp", "price", "size", "conditions", "tape"}
QUOTE_REQUIRED = {
    "timestamp",
    "ask_price",
    "ask_size",
    "bid_price",
    "bid_size",
    "conditions",
}
_TRADE_POLICY = {
    "A": ({" "}, {" ", "E", "F", "I"}),
    "B": ({" "}, {" ", "E", "F", "I"}),
    "C": ({"@"}, {"@", "F", "I"}),
}


def _condition_set(value: Any) -> frozenset[str]:
    if isinstance(value, str):
        parsed = json.loads(value)
    elif isinstance(value, list):
        parsed = value
    else:
        return frozenset()
    if not isinstance(parsed, list):
        raise ValueError("condition payload must decode to a list")
    return frozenset(str(item) for item in parsed)


def _eligible_trade_conditions(tape: Any, conditions: Any) -> bool:
    policy = _TRADE_POLICY.get(str(tape))
    if policy is None:
        return False
    required, allowed = policy
    observed = _condition_set(conditions)
    return required.issubset(observed) and observed.issubset(allowed)


def _quote_states(frame: pd.DataFrame) -> pd.Series:
    nonnegative = (
        frame[["ask_price", "bid_price", "ask_size", "bid_size"]].notna().all(axis=1)
        & (frame[["ask_price", "bid_price", "ask_size", "bid_size"]] >= 0).all(axis=1)
    )
    two_sided = nonnegative & (frame["ask_price"] > 0) & (frame["bid_price"] > 0)
    states = pd.Series("invalid", index=frame.index, dtype="string")
    states.loc[nonnegative & ~two_sided] = "one_sided"
    states.loc[two_sided & (frame["ask_price"] > frame["bid_price"])] = "normal"
    states.loc[two_sided & (frame["ask_price"] == frame["bid_price"])] = "locked"
    states.loc[two_sided & (frame["ask_price"] < frame["bid_price"])] = "crossed"
    return states


def eligible_quotes(quotes: pd.DataFrame) -> pd.DataFrame:
    """Return normal regular-open quotes eligible under the frozen scout policy."""
    _require_columns(quotes, QUOTE_REQUIRED, "quotes")
    frame = quotes.sort_values("timestamp", kind="stable").copy()
    frame["quote_state"] = _quote_states(frame)
    eligible_condition = frame["conditions"].map(
        lambda value: _condition_set(value) == frozenset({"R"})
    )
    return frame.loc[(frame["quote_state"] == "normal") & eligible_condition].copy()


def build_iex_5min_features(trades: pd.DataFrame, quotes: pd.DataFrame) -> pd.DataFrame:
    """Build five-minute features using only quotes available at each event timestamp.

    Rows are labeled by signal availability time (the right edge of a left-closed interval).
    ``next_midpoint_return`` is a forward diagnostic target, never an input feature.
    """
    _require_columns(trades, TRADE_REQUIRED, "trades")
    _require_columns(quotes, QUOTE_REQUIRED, "quotes")
    if trades.empty or quotes.empty:
        return _empty_features()

    trade_frame = trades.sort_values("timestamp", kind="stable").copy()
    quote_frame = quotes.sort_values("timestamp", kind="stable").copy()
    quote_frame["quote_state"] = _quote_states(quote_frame)
    quote_frame["eligible_condition"] = quote_frame["conditions"].map(
        lambda value: _condition_set(value) == frozenset({"R"})
    )
    quote_frame["interval_start"] = quote_frame["timestamp"].dt.floor(FREQUENCY)
    quote_state_counts = (
        quote_frame.groupby(["interval_start", "quote_state"], sort=True)
        .size()
        .unstack(fill_value=0)
        .rename(columns=lambda state: f"{state}_quote_count")
    )
    for state in ("normal", "locked", "crossed", "one_sided", "invalid"):
        column = f"{state}_quote_count"
        if column not in quote_state_counts:
            quote_state_counts[column] = 0

    excluded_quote_conditions = (
        quote_frame.loc[quote_frame["quote_state"] == "normal"]
        .assign(excluded=lambda frame: ~frame["eligible_condition"])
        .groupby("interval_start")["excluded"]
        .sum()
        .rename("excluded_quote_condition_count")
    )
    quote_frame = quote_frame.loc[
        (quote_frame["quote_state"] == "normal") & quote_frame["eligible_condition"]
    ].copy()
    if quote_frame.empty:
        return _empty_features()

    quote_frame["midpoint"] = (quote_frame["ask_price"] + quote_frame["bid_price"]) / 2.0
    quote_frame["spread_bps"] = (
        (quote_frame["ask_price"] - quote_frame["bid_price"])
        / quote_frame["midpoint"]
        * 10_000.0
    )
    depth = quote_frame["bid_size"] + quote_frame["ask_size"]
    quote_frame["quote_size_imbalance"] = (
        (quote_frame["bid_size"] - quote_frame["ask_size"]) / depth
    ).where(depth > 0)

    trade_frame["interval_start"] = trade_frame["timestamp"].dt.floor(FREQUENCY)
    trade_frame["eligible_condition"] = [
        _eligible_trade_conditions(tape, conditions)
        for tape, conditions in zip(
            trade_frame["tape"], trade_frame["conditions"], strict=False
        )
    ]
    trade_diagnostics = trade_frame.groupby("interval_start", sort=True).agg(
        raw_trade_count=("timestamp", "size"),
        eligible_condition_trade_count=("eligible_condition", "sum"),
    )
    trade_diagnostics["excluded_trade_condition_count"] = (
        trade_diagnostics["raw_trade_count"]
        - trade_diagnostics["eligible_condition_trade_count"]
    )
    trade_frame = trade_frame.loc[trade_frame["eligible_condition"]].copy()

    quote_lookup = quote_frame[["timestamp", "midpoint"]].rename(
        columns={"timestamp": "quote_timestamp"}
    )
    matched = pd.merge_asof(
        trade_frame,
        quote_lookup,
        left_on="timestamp",
        right_on="quote_timestamp",
        direction="backward",
        allow_exact_matches=False,
    )
    matched["quote_age_ms"] = (
        matched["timestamp"] - matched["quote_timestamp"]
    ).dt.total_seconds() * 1_000.0
    matched["quote_matched"] = (
        matched["midpoint"].notna()
        & matched["quote_age_ms"].ge(0)
        & matched["quote_age_ms"].le(MAXIMUM_QUOTE_AGE_MS)
    )
    matched["trade_sign"] = 0
    matched.loc[
        matched["quote_matched"] & (matched["price"] > matched["midpoint"]), "trade_sign"
    ] = 1
    matched.loc[
        matched["quote_matched"] & (matched["price"] < matched["midpoint"]), "trade_sign"
    ] = -1
    matched["signed_volume"] = matched["trade_sign"] * matched["size"]
    matched["classified_volume"] = matched["size"].where(matched["quote_matched"], 0)
    matched["buy_volume"] = matched["size"].where(matched["trade_sign"] > 0, 0)
    matched["sell_volume"] = matched["size"].where(matched["trade_sign"] < 0, 0)
    trade_aggregates = matched.groupby("interval_start", sort=True).agg(
        trade_count=("timestamp", "size"),
        total_volume=("size", "sum"),
        classified_volume=("classified_volume", "sum"),
        signed_volume=("signed_volume", "sum"),
        buy_volume=("buy_volume", "sum"),
        sell_volume=("sell_volume", "sum"),
        quote_matched_trades=("quote_matched", "sum"),
        maximum_trade_quote_age_ms=("quote_age_ms", "max"),
    )
    trade_aggregates["stale_or_unmatched_trade_count"] = (
        trade_aggregates["trade_count"] - trade_aggregates["quote_matched_trades"]
    )
    trade_aggregates["signed_trade_imbalance"] = (
        trade_aggregates["signed_volume"] / trade_aggregates["classified_volume"]
    ).where(trade_aggregates["classified_volume"] > 0)
    trade_aggregates["quote_match_fraction"] = (
        trade_aggregates["quote_matched_trades"] / trade_aggregates["trade_count"]
    )

    terminal_quotes = quote_frame.groupby("interval_start", sort=True).agg(
        quote_count=("timestamp", "size"),
        terminal_quote_timestamp=("timestamp", "last"),
        terminal_midpoint=("midpoint", "last"),
        terminal_spread_bps=("spread_bps", "last"),
        terminal_quote_size_imbalance=("quote_size_imbalance", "last"),
    )

    features = (
        terminal_quotes.join(quote_state_counts, how="outer")
        .join(excluded_quote_conditions, how="outer")
        .join(trade_diagnostics, how="outer")
        .join(trade_aggregates, how="outer")
        .sort_index()
    )
    for column in (
        "trade_count",
        "raw_trade_count",
        "eligible_condition_trade_count",
        "excluded_trade_condition_count",
        "total_volume",
        "classified_volume",
        "signed_volume",
        "buy_volume",
        "sell_volume",
        "quote_matched_trades",
        "stale_or_unmatched_trade_count",
        "normal_quote_count",
        "locked_quote_count",
        "crossed_quote_count",
        "one_sided_quote_count",
        "invalid_quote_count",
        "excluded_quote_condition_count",
    ):
        features[column] = features[column].fillna(0).astype("int64")
    features["quote_match_fraction"] = features["quote_match_fraction"].fillna(0.0)

    interval = pd.Timedelta(FREQUENCY)
    interval_end = features.index.to_series() + interval
    features["terminal_quote_age_ms"] = (
        interval_end - features["terminal_quote_timestamp"]
    ).dt.total_seconds() * 1_000.0
    next_midpoint = features["terminal_midpoint"].shift(-1)
    contiguous = features.index.to_series().shift(-1) == features.index.to_series() + interval
    features["next_midpoint_return"] = (
        next_midpoint / features["terminal_midpoint"] - 1.0
    ).where(contiguous)
    previous_midpoint = features["terminal_midpoint"].shift(1)
    contiguous_previous = (
        features.index.to_series().shift(1) == features.index.to_series() - interval
    )
    features["current_midpoint_return"] = (
        features["terminal_midpoint"] / previous_midpoint - 1.0
    ).where(contiguous_previous)
    features["composite_score"] = 0.5 * (
        features["signed_trade_imbalance"]
        + features["terminal_quote_size_imbalance"]
    )
    features["selected"] = features["composite_score"].abs() >= SELECTION_THRESHOLD
    features.index = pd.DatetimeIndex(features.index + interval, name="signal_timestamp")
    return features


def attach_iex_execution_returns(
    features: pd.DataFrame,
    quotes: pd.DataFrame,
    *,
    latency_seconds: int = 1,
    additional_round_trip_friction_bps: float = 2.0,
) -> pd.DataFrame:
    """Attach frozen one-second-latency IEX bid/ask crossing diagnostics."""
    result = features.copy()
    if result.empty:
        return result
    eligible = eligible_quotes(quotes)[["timestamp", "bid_price", "ask_price"]]
    if eligible.empty:
        result["iex_crossing_return"] = pd.NA
        result["iex_crossing_net_return"] = pd.NA
        result["execution_quotes_missing"] = True
        return result

    latency = pd.Timedelta(seconds=latency_seconds)
    schedule = pd.DataFrame(
        {
            "row_id": range(len(result)),
            "entry_requested": result.index + latency,
            "exit_requested": result.index + pd.Timedelta(FREQUENCY) + latency,
        }
    )
    entry_quotes = eligible.rename(
        columns={
            "timestamp": "entry_quote_timestamp",
            "bid_price": "entry_bid",
            "ask_price": "entry_ask",
        }
    )
    exit_quotes = eligible.rename(
        columns={
            "timestamp": "exit_quote_timestamp",
            "bid_price": "exit_bid",
            "ask_price": "exit_ask",
        }
    )
    schedule = pd.merge_asof(
        schedule.sort_values("entry_requested"),
        entry_quotes,
        left_on="entry_requested",
        right_on="entry_quote_timestamp",
        direction="forward",
    )
    schedule = pd.merge_asof(
        schedule.sort_values("exit_requested"),
        exit_quotes,
        left_on="exit_requested",
        right_on="exit_quote_timestamp",
        direction="forward",
    ).sort_values("row_id")
    schedule.index = result.index
    for column in (
        "entry_quote_timestamp",
        "entry_bid",
        "entry_ask",
        "exit_quote_timestamp",
        "exit_bid",
        "exit_ask",
    ):
        result[column] = schedule[column]

    missing = schedule[["entry_bid", "entry_ask", "exit_bid", "exit_ask"]].isna().any(axis=1)
    direction = result["composite_score"].apply(lambda value: 1 if value > 0 else -1 if value < 0 else 0)
    crossing_return = pd.Series(pd.NA, index=result.index, dtype="Float64")
    long = (direction > 0) & ~missing
    short = (direction < 0) & ~missing
    crossing_return.loc[long] = schedule.loc[long, "exit_bid"] / schedule.loc[long, "entry_ask"] - 1.0
    crossing_return.loc[short] = schedule.loc[short, "entry_bid"] / schedule.loc[short, "exit_ask"] - 1.0
    result["iex_crossing_return"] = crossing_return
    result["iex_crossing_net_return"] = crossing_return - (
        additional_round_trip_friction_bps / 10_000.0
    )
    result["execution_quotes_missing"] = missing
    return result


def _require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{label} missing required columns: {sorted(missing)}")
    if (
        not isinstance(frame["timestamp"].dtype, pd.DatetimeTZDtype)
        or str(frame["timestamp"].dt.tz) != "UTC"
    ):
        raise ValueError(f"{label} timestamp must be timezone-aware UTC")


def _empty_features() -> pd.DataFrame:
    columns = [
        "quote_count",
        "normal_quote_count",
        "locked_quote_count",
        "crossed_quote_count",
        "one_sided_quote_count",
        "invalid_quote_count",
        "excluded_quote_condition_count",
        "terminal_quote_timestamp",
        "terminal_midpoint",
        "terminal_quote_age_ms",
        "terminal_spread_bps",
        "terminal_quote_size_imbalance",
        "trade_count",
        "raw_trade_count",
        "eligible_condition_trade_count",
        "excluded_trade_condition_count",
        "total_volume",
        "classified_volume",
        "signed_volume",
        "buy_volume",
        "sell_volume",
        "quote_matched_trades",
        "stale_or_unmatched_trade_count",
        "maximum_trade_quote_age_ms",
        "signed_trade_imbalance",
        "quote_match_fraction",
        "next_midpoint_return",
        "current_midpoint_return",
        "composite_score",
        "selected",
    ]
    frame = pd.DataFrame(columns=columns)
    frame.index = pd.DatetimeIndex([], name="signal_timestamp", tz="UTC")
    return frame
