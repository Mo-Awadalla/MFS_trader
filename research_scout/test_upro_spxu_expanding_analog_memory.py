"""Leak-free walk-forward test of preregistered expanding analog memory."""

from __future__ import annotations

import json
import math
from datetime import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_density_invariant_sync_2026 as forward
from research_scout import test_upro_spxu_pair_geometry as geo

ROOT = Path(__file__).resolve().parents[1]
OLD_SPY = (
    ROOT
    / "external_artifacts"
    / "databento_fractional_etf"
    / "ARCX.PILLAR"
    / "bars"
    / "spy_sh_ohlcv_1m_2021-01-01_2026-01-01.dbn.zst"
)
OLD_PAIR_BARS = (
    ROOT
    / "external_artifacts"
    / "databento_leveraged_etf"
    / "ARCX.PILLAR"
    / "bars"
    / "upro_spxu_ohlcv_1m_2021-01-01_2026-01-01.dbn.zst"
)
OLD_PAIR_BBO = (
    ROOT
    / "external_artifacts"
    / "databento_leveraged_etf"
    / "ARCX.PILLAR"
    / "bbo"
    / "upro_spxu_bbo_1m_2021-01-01_2026-01-01.dbn.zst"
)
NEW_BARS = (
    ROOT
    / "external_artifacts"
    / "databento_forward_2026"
    / "ARCX.PILLAR"
    / "bars"
    / "spy_upro_spxu_ohlcv_1m_2026-01-02_2026-07-25.dbn.zst"
)
NEW_BBO = (
    ROOT
    / "external_artifacts"
    / "databento_forward_2026"
    / "ARCX.PILLAR"
    / "bbo"
    / "upro_spxu_bbo_1m_2026-01-02_2026-07-25.dbn.zst"
)
OLD_CONDITIONS = (
    ROOT
    / "external_artifacts"
    / "databento_fractional_etf"
    / "ARCX.PILLAR"
    / "dataset_condition_2021_2025.json"
)
NEW_CONDITIONS = (
    ROOT
    / "external_artifacts"
    / "databento_forward_2026"
    / "ARCX.PILLAR"
    / "dataset_condition_2026.json"
)
OUTPUT = ROOT / "research_scout" / "upro_spxu_expanding_analog_memory_result_v7.json"
MINIMUM_MEMORY = 125
FEATURE_NAMES = [
    "spy_log_return",
    "spy_path_efficiency",
    "spy_log_range",
    "spy_realized_variance",
    "spy_late_log_return",
    "spy_volume_clock",
    "pair_tracking_residual_difference",
    "pair_joint_log_return",
    "upro_median_spread",
    "spxu_median_spread",
    "paired_depth_polarity",
    "paired_late_volume_share_difference",
]


def combined_sessions() -> tuple[
    dict[pd.Timestamp, pd.DataFrame],
    dict[pd.Timestamp, dict[str, pd.DataFrame]],
    dict[pd.Timestamp, dict[str, pd.DataFrame]],
]:
    old_spy = base.load_dbn(OLD_SPY, "SPY")
    new_bars = base.load_dbn(NEW_BARS)
    spy = pd.concat([old_spy, new_bars[new_bars.symbol == "SPY"]]).sort_index()
    old_pair_bars = base.load_dbn(OLD_PAIR_BARS)
    old_pair_bbo = base.load_dbn(OLD_PAIR_BBO)
    new_bbo = base.load_dbn(NEW_BBO)
    pair_bars_frame = pd.concat(
        [old_pair_bars, new_bars[new_bars.symbol.isin(["UPRO", "SPXU"])]]
    ).sort_index()
    pair_bbo_frame = pd.concat([old_pair_bbo, new_bbo]).sort_index()
    spy_sessions = base.split_sessions(spy)
    pair_bars: dict[pd.Timestamp, dict[str, pd.DataFrame]] = {}
    pair_bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]] = {}
    for symbol in ["UPRO", "SPXU"]:
        for day, frame in base.split_sessions(
            pair_bars_frame[pair_bars_frame.symbol == symbol]
        ).items():
            pair_bars.setdefault(day, {})[symbol] = frame
        for day, frame in base.split_sessions(
            pair_bbo_frame[pair_bbo_frame.symbol == symbol]
        ).items():
            pair_bbo.setdefault(day, {})[symbol] = frame
    return spy_sessions, pair_bars, pair_bbo


def excluded_dates() -> set[pd.Timestamp]:
    dates: set[pd.Timestamp] = set()
    for path in [OLD_CONDITIONS, NEW_CONDITIONS]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        dates.update(
            pd.Timestamp(row["date"])
            for row in payload["conditions"]
            if row["condition"] == "degraded"
        )
    return dates


def sparse_volume_share(
    frame: pd.DataFrame,
) -> tuple[float, float] | None:
    morning = base.between(frame, "09:30", "10:59")
    total = float(morning.volume.astype(float).sum())
    if total <= 0:
        return None
    late = float(
        base.between(morning, "10:15", "10:59").volume.astype(float).sum()
    )
    return total, late / total


def morning_feature(
    day: pd.Timestamp,
    spy: pd.DataFrame,
    pair_bars: dict[str, pd.DataFrame],
    pair_bbo: dict[str, pd.DataFrame],
) -> np.ndarray | None:
    spy_window = geo.exact_window(spy, day, time(9, 30), 90)
    bbo_windows = geo.valid_bbo_windows(day, pair_bbo)
    if spy_window is None or bbo_windows is None:
        return None
    u_mid = geo.quote_midpoints(bbo_windows["UPRO"])
    s_mid = geo.quote_midpoints(bbo_windows["SPXU"])
    if u_mid is None or s_mid is None:
        return None
    start = float(spy_window.open.iloc[0])
    close = spy_window.close.astype(float).to_numpy()
    spy_returns = np.diff(np.log(np.r_[start, close]))
    net = float(np.log(close[-1] / start))
    path_distance = float(np.abs(spy_returns).sum())
    if path_distance <= 0:
        return None
    spy_range = float(
        np.log(
            float(spy_window.high.astype(float).max())
            / float(spy_window.low.astype(float).min())
        )
    )
    late_start = float(spy_window.iloc[60].open)
    late_return = float(np.log(close[-1] / late_start))
    spy_volume = spy_window.volume.astype(float).to_numpy()
    if float(spy_volume.sum()) <= 0:
        return None
    spy_clock = float(
        np.dot(np.arange(90, dtype=float), spy_volume) / spy_volume.sum() / 89.0
    )
    u_return = float(np.log(u_mid[-1] / u_mid[0]))
    s_return = float(np.log(s_mid[-1] / s_mid[0]))
    spreads: dict[str, float] = {}
    imbalances: dict[str, float] = {}
    late_shares: dict[str, float] = {}
    for symbol in ["UPRO", "SPXU"]:
        quotes = bbo_windows[symbol]
        spread = geo.quote_spreads(quotes)
        if spread is None:
            return None
        bid_size = quotes.bid_sz_00.astype(float).to_numpy()
        ask_size = quotes.ask_sz_00.astype(float).to_numpy()
        if np.any(bid_size <= 0) or np.any(ask_size <= 0):
            return None
        spreads[symbol] = float(np.median(spread))
        imbalances[symbol] = float(
            np.median((bid_size - ask_size) / (bid_size + ask_size))
        )
        volume_state = sparse_volume_share(pair_bars[symbol])
        if volume_state is None:
            return None
        _, late_shares[symbol] = volume_state
    values = np.array(
        [
            net,
            net / path_distance,
            spy_range,
            float(np.square(spy_returns).sum()),
            late_return,
            spy_clock,
            (u_return - 3.0 * net) - (s_return + 3.0 * net),
            u_return + s_return,
            spreads["UPRO"],
            spreads["SPXU"],
            imbalances["UPRO"] - imbalances["SPXU"],
            late_shares["UPRO"] - late_shares["SPXU"],
        ],
        dtype=float,
    )
    return values if np.isfinite(values).all() else None


def potential_trade(
    day: pd.Timestamp,
    direction: int,
    spy: pd.DataFrame,
    quotes: pd.DataFrame,
    delay_minutes: int = 0,
) -> dict[str, Any] | None:
    signal = {
        "hypothesis": "expanding_analog_memory",
        "date": day,
        "direction": direction,
        "score": 0.0,
    }
    return geo.simulate(signal, spy, quotes, delay_minutes)


def build_memory_rows(
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    pair_bars: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    pair_bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for day in sorted(spy_sessions):
        if day in excluded:
            continue
        bars = pair_bars.get(day)
        quotes = pair_bbo.get(day)
        if bars is None or quotes is None:
            continue
        if not {"UPRO", "SPXU"}.issubset(bars) or not {
            "UPRO",
            "SPXU",
        }.issubset(quotes):
            continue
        feature = morning_feature(day, spy_sessions[day], bars, quotes)
        if feature is None:
            continue
        upro = potential_trade(day, 1, spy_sessions[day], quotes["UPRO"])
        spxu = potential_trade(day, -1, spy_sessions[day], quotes["SPXU"])
        if upro is None or spxu is None:
            continue
        upro_return = float(base.trade_pnl(pd.DataFrame([upro])).iloc[0] / 100.0)
        spxu_return = float(base.trade_pnl(pd.DataFrame([spxu])).iloc[0] / 100.0)
        rows.append(
            {
                "date": day,
                "feature": feature,
                "UPRO": upro,
                "SPXU": spxu,
                "upro_return": upro_return,
                "spxu_return": spxu_return,
            }
        )
    return rows


def choose_trades(
    rows: list[dict[str, Any]],
) -> tuple[pd.DataFrame, list[dict[str, Any]], list[pd.Timestamp]]:
    selected: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    evaluation_days = [row["date"] for row in rows[MINIMUM_MEMORY:]]
    matrix = np.stack([row["feature"] for row in rows])
    u_returns = np.array([row["upro_return"] for row in rows])
    s_returns = np.array([row["spxu_return"] for row in rows])
    for idx in range(MINIMUM_MEMORY, len(rows)):
        prior = matrix[:idx]
        median = np.median(prior, axis=0)
        scale = np.quantile(prior, 0.75, axis=0) - np.quantile(
            prior,
            0.25,
            axis=0,
        )
        scale[scale == 0] = 1.0
        prior_scaled = (prior - median) / scale
        current_scaled = (matrix[idx] - median) / scale
        distances = (
            np.sqrt(np.square(prior_scaled - current_scaled).sum(axis=1))
            / math.sqrt(len(FEATURE_NAMES))
        )
        k = int(math.ceil(math.sqrt(idx)))
        neighbors = np.argsort(distances, kind="stable")[:k]
        u_mean = float(u_returns[neighbors].mean())
        s_mean = float(s_returns[neighbors].mean())
        u_vote = float((u_returns[neighbors] > 0).mean())
        s_vote = float((s_returns[neighbors] > 0).mean())
        if u_mean == s_mean:
            continue
        symbol = "UPRO" if u_mean > s_mean else "SPXU"
        forecast = u_mean if symbol == "UPRO" else s_mean
        vote = u_vote if symbol == "UPRO" else s_vote
        traded = forecast > 0 and vote > 0.5
        decisions.append(
            {
                "date": rows[idx]["date"],
                "symbol": symbol,
                "forecast_return": forecast,
                "positive_neighbor_fraction": vote,
                "neighbor_count": k,
                "traded": traded,
            }
        )
        if not traded:
            continue
        trade = dict(rows[idx][symbol])
        trade["forecast_return"] = forecast
        trade["positive_neighbor_fraction"] = vote
        trade["neighbor_count"] = k
        selected.append(trade)
    return pd.DataFrame(selected), decisions, evaluation_days


def delayed_selected_trades(
    decisions: list[dict[str, Any]],
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    pair_bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    delay_minutes: int,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for decision in decisions:
        if not decision["traded"]:
            continue
        day = decision["date"]
        symbol = decision["symbol"]
        direction = 1 if symbol == "UPRO" else -1
        trade = potential_trade(
            day,
            direction,
            spy_sessions[day],
            pair_bbo[day][symbol],
            delay_minutes,
        )
        if trade is not None:
            records.append(trade)
    return pd.DataFrame(records)


def benchmark_between(
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    first: pd.Timestamp,
    last: pd.Timestamp,
) -> dict[str, Any]:
    first_frame = spy_sessions[first]
    last_frame = spy_sessions[last]
    start = base.exact_row(
        first_frame,
        base.clock_timestamp(first, time(9, 30), first_frame.index.tz),
    )
    end = base.exact_row(
        last_frame,
        base.clock_timestamp(last, time(15, 59), last_frame.index.tz),
    )
    if start is None or end is None:
        raise RuntimeError("Unable to construct analog evaluation SPY benchmark")
    start_price = float(start.open)
    end_price = float(end.close)
    ending = 100.0 * end_price / start_price
    return {
        "start_date": str(first.date()),
        "end_date": str(last.date()),
        "start_price": round(start_price, 6),
        "end_price": round(end_price, 6),
        "ending_value_usd": round(ending, 4),
        "price_return_pct": round(ending - 100.0, 4),
        "dividends_included": False,
    }


def main() -> int:
    spy_sessions, pair_bars, pair_bbo = combined_sessions()
    excluded = excluded_dates()
    rows = build_memory_rows(spy_sessions, pair_bars, pair_bbo, excluded)
    trades, decisions, evaluation_days = choose_trades(rows)
    delayed_five = delayed_selected_trades(
        decisions,
        spy_sessions,
        pair_bbo,
        5,
    )
    observed = forward.summarize(trades, evaluation_days)
    one_cent = forward.summarize(trades, evaluation_days, 0.01)
    five_delay_summary = forward.summarize(delayed_five, evaluation_days)
    spy = benchmark_between(
        spy_sessions,
        evaluation_days[0],
        evaluation_days[-1],
    )
    years = observed.get("year_pnl_usd", {})
    directions = observed.get("direction_pnl_usd", {})
    criteria = {
        "minimum_two_trades_per_week": observed["trades_per_week"] >= 2.0,
        "profit_factor_at_least_1_15": observed.get("profit_factor", 0.0) >= 1.15,
        "each_2022_through_2026_ytd_positive": (
            set(years) >= {"2022", "2023", "2024", "2025", "2026"}
            and all(years[year] > 0 for year in ["2022", "2023", "2024", "2025", "2026"])
        ),
        "both_instruments_positive": (
            set(directions) == {"bearish", "bullish"}
            and all(value > 0 for value in directions.values())
        ),
        "positive_after_one_extra_cent_each_fill": one_cent["net_pnl_usd"] > 0,
        "positive_after_five_minute_delay": five_delay_summary["net_pnl_usd"] > 0,
        "positive_after_removing_five_best": (
            observed.get("net_without_five_best_usd", 0.0) > 0
        ),
        "beats_same_period_spy_price_only": (
            observed.get("cash_account", {}).get("ending_equity_usd", 0.0)
            > spy["ending_value_usd"]
        ),
    }
    result = {
        "status": "walk_forward_research_complete_no_repairs",
        "specification": (
            "research_scout/upro_spxu_expanding_analog_memory_prereg_v7.json"
        ),
        "evidence_warning": (
            "Feature family designed after exposure to the historical sample; "
            "passing would still require future paper validation."
        ),
        "feature_names": FEATURE_NAMES,
        "valid_memory_sessions": len(rows),
        "evaluation_period": {
            "first": str(evaluation_days[0].date()),
            "last": str(evaluation_days[-1].date()),
            "eligible_sessions": len(evaluation_days),
        },
        "observed_bbo": observed,
        "midpoint_diagnostic": forward.summarize(
            trades,
            evaluation_days,
            midpoint_execution=True,
        ),
        "one_extra_cent_each_fill": one_cent,
        "two_extra_cents_each_fill": forward.summarize(
            trades,
            evaluation_days,
            0.02,
        ),
        "five_additional_minutes_delay": five_delay_summary,
        "spy_price_only_hurdle": spy,
        "acceptance_criteria": criteria,
        "all_acceptance_criteria_passed": all(criteria.values()),
        "decision_counts": {
            "evaluated": len(decisions),
            "traded": int(sum(bool(row["traded"]) for row in decisions)),
            "skipped": int(sum(not bool(row["traded"]) for row in decisions)),
        },
    }
    OUTPUT.write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
