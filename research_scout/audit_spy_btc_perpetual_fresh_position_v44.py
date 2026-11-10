"""Returns-blind audit for SPY BTC-perpetual fresh-position risk transfer v44."""

from __future__ import annotations

import json
from datetime import time
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16

ROOT = Path(__file__).resolve().parents[1]
PREREG = (
    ROOT
    / "research_scout"
    / "spy_btc_perpetual_fresh_position_risk_transfer_prereg_v44.json"
)
PERP_PATH = (
    ROOT
    / "data"
    / "parquet"
    / "binance_bitcoin_derivatives_public_v1"
    / "normalized"
    / "perp_klines_30m.parquet"
)
METRICS_PATH = (
    ROOT
    / "data"
    / "parquet"
    / "binance_bitcoin_derivatives_public_v1"
    / "normalized"
    / "futures_metrics_5m.parquet"
)
OUTPUT = (
    ROOT
    / "research_scout"
    / "spy_btc_perpetual_fresh_position_returns_blind_audit_v44.json"
)
NY = "America/New_York"
PUBLICATION_LAG = pd.Timedelta(minutes=5)
MAX_STALENESS = pd.Timedelta(minutes=10)
PRIMARY_END = time(9, 0)
ADJACENT_END = time(8, 30)
DECISION = time(9, 5)
ENTRY = time(9, 31)


def load_btc() -> tuple[pd.DataFrame, pd.DataFrame]:
    perp = pd.read_parquet(PERP_PATH).copy()
    metrics = pd.read_parquet(METRICS_PATH).copy()
    required_perp = {
        "open_time",
        "close",
        "quote_volume",
        "taker_buy_quote_volume",
    }
    required_metrics = {"create_time", "sum_open_interest"}
    if missing := required_perp.difference(perp.columns):
        raise ValueError(f"perpetual bars missing columns: {sorted(missing)}")
    if missing := required_metrics.difference(metrics.columns):
        raise ValueError(f"futures metrics missing columns: {sorted(missing)}")
    if "product" in perp and not (perp["product"] == "perp_klines_30m").all():
        raise AssertionError("V44 may use BTCUSDT perpetual bars only")
    perp["open_time"] = pd.to_datetime(perp.open_time, utc=True)
    metrics["create_time"] = pd.to_datetime(metrics.create_time, utc=True)
    if perp.open_time.duplicated().any():
        raise ValueError("duplicate perpetual open_time values")
    if metrics.create_time.duplicated().any():
        raise ValueError("duplicate futures-metrics create_time values")
    perp = perp.sort_values("open_time", kind="stable").set_index("open_time")
    metrics = metrics.sort_values("create_time", kind="stable").reset_index(drop=True)
    return perp, metrics


def local_stamp(day: pd.Timestamp, clock: time) -> pd.Timestamp:
    return pd.Timestamp.combine(day.date(), clock).tz_localize(NY)


def exact_completed_close(
    perp: pd.DataFrame,
    boundary: pd.Timestamp,
) -> tuple[float, pd.Timestamp] | None:
    open_time = boundary.tz_convert("UTC") - pd.Timedelta(minutes=30)
    if open_time not in perp.index:
        return None
    row = perp.loc[open_time]
    if isinstance(row, pd.DataFrame):
        return None
    close = float(row.close)
    if close <= 0:
        return None
    return close, boundary


def metric_at_boundary(
    metrics: pd.DataFrame,
    boundary: pd.Timestamp,
    decision: pd.Timestamp,
) -> dict[str, Any] | None:
    boundary_utc = boundary.tz_convert("UTC")
    decision_utc = decision.tz_convert("UTC")
    times = pd.DatetimeIndex(metrics.create_time)
    position = int(times.searchsorted(boundary_utc, side="right")) - 1
    if position < 0:
        return None
    row = metrics.iloc[position]
    created = pd.Timestamp(row.create_time)
    available = created + PUBLICATION_LAG
    value = float(row.sum_open_interest)
    if (
        value <= 0
        or created > boundary_utc
        or boundary_utc - created > MAX_STALENESS
        or available > decision_utc
    ):
        return None
    return {
        "value": value,
        "created": created,
        "available": available,
        "staleness_minutes": (boundary_utc - created).total_seconds() / 60.0,
    }


def taker_flow_direction(
    perp: pd.DataFrame,
    start_boundary: pd.Timestamp,
    end_boundary: pd.Timestamp,
) -> tuple[int, float] | None:
    start = start_boundary.tz_convert("UTC")
    end = end_boundary.tz_convert("UTC")
    expected = pd.date_range(start, end, freq="30min", inclusive="left", tz="UTC")
    window = perp.reindex(expected)
    columns = ["quote_volume", "taker_buy_quote_volume"]
    if window[columns].isna().any().any():
        return None
    total = float(window.quote_volume.astype(float).sum())
    if total <= 0:
        return None
    signed = float(
        (2.0 * window.taker_buy_quote_volume.astype(float) - window.quote_volume.astype(float)).sum()
    )
    normalized = signed / total
    direction = int(normalized > 0) - int(normalized < 0)
    return direction, normalized


def signal_for(
    perp: pd.DataFrame,
    metrics: pd.DataFrame,
    prior_day: pd.Timestamp,
    day: pd.Timestamp,
    end_clock: time = PRIMARY_END,
) -> dict[str, Any] | None:
    start_boundary = local_stamp(prior_day, time(16, 0))
    end_boundary = local_stamp(day, end_clock)
    decision = local_stamp(day, DECISION)
    start_price = exact_completed_close(perp, start_boundary)
    end_price = exact_completed_close(perp, end_boundary)
    start_oi = metric_at_boundary(metrics, start_boundary, decision)
    end_oi = metric_at_boundary(metrics, end_boundary, decision)
    flow = taker_flow_direction(perp, start_boundary, end_boundary)
    if None in (start_price, end_price, start_oi, end_oi, flow):
        return None
    assert start_price is not None and end_price is not None
    assert start_oi is not None and end_oi is not None and flow is not None
    price_return = end_price[0] / start_price[0] - 1.0
    oi_change = end_oi["value"] / start_oi["value"] - 1.0
    price_direction = int(price_return > 0) - int(price_return < 0)
    direction = price_direction if oi_change > 0 and price_direction else 0
    latest_available = max(
        pd.Timestamp(start_price[1]).tz_convert("UTC"),
        pd.Timestamp(end_price[1]).tz_convert("UTC"),
        pd.Timestamp(start_oi["available"]),
        pd.Timestamp(end_oi["available"]),
    )
    return {
        "date": day,
        "prior_equity_date": prior_day,
        "direction": direction,
        "price_direction": price_direction,
        "price_return": price_return,
        "oi_change": oi_change,
        "start_oi": start_oi["value"],
        "end_oi": end_oi["value"],
        "start_oi_staleness_minutes": start_oi["staleness_minutes"],
        "end_oi_staleness_minutes": end_oi["staleness_minutes"],
        "taker_flow_direction": flow[0],
        "normalized_taker_flow": flow[1],
        "latest_input_available_at": latest_available,
        "decision_at": decision.tz_convert("UTC"),
        "causal": latest_available <= decision.tz_convert("UTC"),
    }


def quote_exists(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    day: pd.Timestamp,
    symbol: str,
) -> bool:
    quotes = sessions.get(day, {}).get(symbol)
    if quotes is None:
        return False
    stamp = v16.stamp(day, ENTRY, quotes.index.tz)
    return base.quote_at(quotes, stamp, 0) is not None


def main() -> None:
    if not PREREG.exists():
        raise FileNotFoundError("V44 preregistration is required before audit")
    perp, metrics = load_btc()
    spy, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    eligible_days = [
        day
        for day in sorted(spy)
        if v16.START <= day <= v16.DEVELOPMENT_END and day not in arca_excluded
    ]
    measured: list[dict[str, Any]] = []
    signal_rows: list[dict[str, Any]] = []
    stability_matches = 0
    stability_total = 0
    for index, day in enumerate(eligible_days):
        if index == 0:
            continue
        prior_day = eligible_days[index - 1]
        state = signal_for(perp, metrics, prior_day, day, PRIMARY_END)
        adjacent = signal_for(perp, metrics, prior_day, day, ADJACENT_END)
        if state is None:
            continue
        measured.append(state)
        if adjacent is not None:
            stability_total += 1
            stability_matches += int(state["direction"] == adjacent["direction"])
        direction = int(state["direction"])
        if direction == 0:
            continue
        symbol = "UPRO" if direction > 0 else "SPXU"
        signal_rows.append(
            {
                **state,
                "symbol": symbol,
                "arca_entry": quote_exists(arca, day, symbol),
                "equs_entry": (
                    day not in equs_excluded and quote_exists(equs, day, symbol)
                ),
            }
        )

    measured_frame = pd.DataFrame(measured)
    frame = pd.DataFrame(signal_rows)
    executable = frame.loc[frame.arca_entry].copy() if len(frame) else frame.copy()
    weeks = max((v16.DEVELOPMENT_END - v16.START).days / 7.0, 1.0)
    entries_per_week = len(executable) / weeks
    direction_counts = {
        "UPRO": int((executable.direction > 0).sum()) if len(executable) else 0,
        "SPXU": int((executable.direction < 0).sum()) if len(executable) else 0,
    }
    minority = min(direction_counts.values()) / max(len(executable), 1)
    year_counts = {
        str(year): int((executable.date.dt.year == year).sum()) if len(executable) else 0
        for year in [2021, 2022, 2023]
    }
    eligible_measurements = max(len(eligible_days) - 1, 1)
    measurement_coverage = len(measured_frame) / eligible_measurements
    arca_availability = float(frame.arca_entry.mean()) if len(frame) else 0.0
    overlap = frame.loc[frame.date >= pd.Timestamp("2023-03-28")].copy() if len(frame) else frame
    equs_availability = float(overlap.equs_entry.mean()) if len(overlap) else 0.0
    coherence = (
        float((frame.price_direction == frame.taker_flow_direction).mean())
        if len(frame)
        else 0.0
    )
    adjacent_agreement = stability_matches / max(stability_total, 1)
    causality = float(measured_frame.causal.mean()) if len(measured_frame) else 0.0
    gates = {
        "btc_measurement_coverage_at_least_98_percent": measurement_coverage >= 0.98,
        "at_least_two_executable_entries_per_week": entries_per_week >= 2.0,
        "every_development_year_at_least_100_entries": all(
            value >= 100 for value in year_counts.values()
        ),
        "minority_direction_at_least_20_percent": minority >= 0.20,
        "arca_entry_availability_at_least_95_percent": arca_availability >= 0.95,
        "equs_overlap_entry_availability_at_least_95_percent": equs_availability >= 0.95,
        "btc_price_taker_flow_sign_agreement_at_least_52_percent": coherence >= 0.52,
        "adjacent_0830_action_agreement_at_least_75_percent": adjacent_agreement >= 0.75,
        "all_inputs_causal_by_0905": causality == 1.0,
    }
    payload = {
        "status": "returns_blind_no_post_entry_etf_prices_or_pnl_read",
        "specification": str(PREREG.relative_to(ROOT)).replace("\\", "/"),
        "eligible_development_sessions_after_first": eligible_measurements,
        "complete_btc_measurements": int(len(measured_frame)),
        "btc_measurement_coverage": measurement_coverage,
        "candidate_signals": int(len(frame)),
        "executable_entries": int(len(executable)),
        "entries_per_calendar_week": entries_per_week,
        "direction_counts": direction_counts,
        "minority_direction_fraction": minority,
        "year_counts": year_counts,
        "arca_entry_availability": arca_availability,
        "equs_overlap_signal_count": int(len(overlap)),
        "equs_overlap_entry_availability": equs_availability,
        "btc_price_taker_flow_sign_agreement": coherence,
        "adjacent_0830": {
            "comparable_sessions": stability_total,
            "identical_action_including_cash": stability_matches,
            "agreement_fraction": adjacent_agreement,
        },
        "timestamp_causality_fraction": causality,
        "predeclared_feasibility_gates": gates,
        "feasibility_passed": all(gates.values()),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
