"""Run the single preregistered 2026 density-invariant synchronization test."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_inventory_state as inventory
from research_scout import test_upro_spxu_pair_geometry as geo

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "external_artifacts" / "databento_forward_2026"
BARS = (
    DATA_ROOT
    / "ARCX.PILLAR"
    / "bars"
    / "spy_upro_spxu_ohlcv_1m_2026-01-02_2026-07-25.dbn.zst"
)
BBO = (
    DATA_ROOT
    / "ARCX.PILLAR"
    / "bbo"
    / "upro_spxu_bbo_1m_2026-01-02_2026-07-25.dbn.zst"
)
CONDITIONS = DATA_ROOT / "ARCX.PILLAR" / "dataset_condition_2026.json"
OUTPUT = ROOT / "research_scout" / "upro_spxu_density_invariant_sync_2026_result.json"
HYPOTHESIS = "density_invariant_synchronization_shock"


def load_sessions() -> tuple[
    dict[pd.Timestamp, pd.DataFrame],
    dict[pd.Timestamp, dict[str, pd.DataFrame]],
    dict[pd.Timestamp, dict[str, pd.DataFrame]],
]:
    bars = base.load_dbn(BARS)
    bbo = base.load_dbn(BBO)
    spy_sessions = base.split_sessions(bars[bars.symbol == "SPY"])
    pair_bars: dict[pd.Timestamp, dict[str, pd.DataFrame]] = {}
    pair_bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]] = {}
    for symbol in ["UPRO", "SPXU"]:
        for day, frame in base.split_sessions(bars[bars.symbol == symbol]).items():
            pair_bars.setdefault(day, {})[symbol] = frame
        for day, frame in base.split_sessions(bbo[bbo.symbol == symbol]).items():
            pair_bbo.setdefault(day, {})[symbol] = frame
    return spy_sessions, pair_bars, pair_bbo


def degraded_dates() -> set[pd.Timestamp]:
    payload = json.loads(CONDITIONS.read_text(encoding="utf-8"))
    return {
        pd.Timestamp(row["date"])
        for row in payload["conditions"]
        if row["condition"] == "degraded"
    }


def active_mask(day: pd.Timestamp, bars: pd.DataFrame) -> np.ndarray:
    window = base.between(bars, "09:30", "10:59")
    mask = np.zeros(90, dtype=bool)
    if window.empty:
        return mask
    origin = base.clock_timestamp(day, pd.Timestamp("09:30").time(), window.index.tz)
    offsets = ((window.index - origin).total_seconds() / 60.0).astype(int)
    valid = (offsets >= 0) & (offsets <= 89)
    mask[offsets[valid]] = True
    return mask


def make_signal(
    day: pd.Timestamp,
    pair_bars: dict[str, pd.DataFrame],
) -> dict[str, Any] | None:
    if not {"UPRO", "SPXU"}.issubset(pair_bars):
        return None
    u = active_mask(day, pair_bars["UPRO"])
    s = active_mask(day, pair_bars["SPXU"])
    similarities: list[float] = []
    upro_shares: list[float] = []
    for block in range(6):
        section = slice(block * 15, (block + 1) * 15)
        u_block = u[section]
        s_block = s[section]
        union = int((u_block | s_block).sum())
        combined = int(u_block.sum() + s_block.sum())
        if union == 0 or combined == 0:
            return None
        similarities.append(float((u_block & s_block).sum() / union))
        upro_shares.append(float(u_block.sum() / combined))
    synchronization_shock = float(
        np.median(similarities[3:]) - np.median(similarities[:3])
    )
    if synchronization_shock <= 0:
        return None
    directional_acceleration = float(
        np.median(upro_shares[3:]) - np.median(upro_shares[:3])
    )
    direction = int(directional_acceleration > 0) - int(
        directional_acceleration < 0
    )
    if direction == 0:
        return None
    return {
        "hypothesis": HYPOTHESIS,
        "date": day,
        "direction": direction,
        "score": directional_acceleration,
        "synchronization_shock": synchronization_shock,
    }


def run_period(
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    pair_bars: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    pair_bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    additional_delay_minutes: int = 0,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for day in sorted(spy_sessions):
        if day in excluded:
            continue
        bars = pair_bars.get(day)
        quotes = pair_bbo.get(day)
        if bars is None or quotes is None:
            continue
        signal = make_signal(day, bars)
        if signal is None:
            continue
        symbol = "UPRO" if signal["direction"] == 1 else "SPXU"
        if symbol not in quotes:
            continue
        trade = geo.simulate(
            signal,
            spy_sessions[day],
            quotes[symbol],
            additional_delay_minutes,
        )
        if trade is not None:
            trade["synchronization_shock"] = signal["synchronization_shock"]
            records.append(trade)
    return pd.DataFrame(records)


def summarize(
    trades: pd.DataFrame,
    eligible_days: list[pd.Timestamp],
    extra_cents_each_fill: float = 0.0,
    midpoint_execution: bool = False,
) -> dict[str, Any]:
    if trades.empty:
        return {"trades": 0, "trades_per_week": 0.0, "net_pnl_usd": 0.0}
    pnl = base.trade_pnl(
        trades,
        extra_cents_each_fill,
        midpoint_execution=midpoint_execution,
    )
    dates = trades.date
    years = trades.date.dt.year
    directions = trades.direction
    without_five = pnl.drop(pnl.nlargest(min(5, len(pnl))).index)
    split = len(eligible_days) // 2
    first_half_days = set(eligible_days[:split])
    first_half = dates.isin(first_half_days)
    entry_mid = (trades.entry_ask + trades.entry_bid) / 2.0
    spread_bps = (trades.entry_ask - trades.entry_bid) / entry_mid * 10000.0
    return {
        "trades": int(len(trades)),
        "eligible_sessions": len(eligible_days),
        "trades_per_week": round(float(len(trades) / (len(eligible_days) / 5.0)), 3),
        "net_pnl_usd": round(float(pnl.sum()), 4),
        "mean_trade_usd": round(float(pnl.mean()), 5),
        "median_trade_usd": round(float(pnl.median()), 5),
        "win_rate": round(float((pnl > 0).mean()), 4),
        "profit_factor": round(float(base.profit_factor(pnl)), 4),
        "fixed_notional_max_drawdown_usd": round(
            float(base.fixed_notional_drawdown(pnl, dates)),
            4,
        ),
        "cash_account": base.cash_path(trades, pnl),
        "worst_trade_usd": round(float(pnl.min()), 4),
        "net_without_five_best_usd": round(float(without_five.sum()), 4),
        "year_pnl_usd": {
            str(int(year)): round(float(pnl[years == year].sum()), 4)
            for year in sorted(years.unique())
        },
        "direction_pnl_usd": {
            str(direction): round(float(pnl[directions == direction].sum()), 4)
            for direction in sorted(directions.unique())
        },
        "chronological_half_pnl_usd": {
            "first": round(float(pnl[first_half].sum()), 4),
            "second": round(float(pnl[~first_half].sum()), 4),
        },
        "reason_counts": {
            str(reason): int(count)
            for reason, count in trades.reason.value_counts().items()
        },
        "entry_spread_bps": {
            "median": round(float(spread_bps.median()), 4),
            "p95": round(float(spread_bps.quantile(0.95)), 4),
        },
    }


def monthly_diagnostic(trades: pd.DataFrame) -> dict[str, float]:
    if trades.empty:
        return {}
    pnl = base.trade_pnl(trades)
    months = trades.date.dt.to_period("M")
    return {
        str(month): round(float(pnl[months == month].sum()), 4)
        for month in sorted(months.unique())
    }


def main() -> int:
    spy_sessions, pair_bars, pair_bbo = load_sessions()
    excluded = degraded_dates()
    eligible_days = [day for day in sorted(spy_sessions) if day not in excluded]
    trades = run_period(spy_sessions, pair_bars, pair_bbo, excluded)
    delay_one = run_period(spy_sessions, pair_bars, pair_bbo, excluded, 1)
    delay_five = run_period(spy_sessions, pair_bars, pair_bbo, excluded, 5)
    observed = summarize(trades, eligible_days)
    one_cent = summarize(trades, eligible_days, 0.01)
    spy_hurdle = inventory.spy_price_hurdle(
        spy_sessions,
        excluded,
        range(2026, 2027),
    )
    bootstrap = (
        base.moving_block_bootstrap(trades, eligible_days)
        if not trades.empty
        else {"trades": 0}
    )
    criteria = {
        "minimum_two_trades_per_week": observed["trades_per_week"] >= 2.0,
        "positive_observed_bbo_pnl": observed["net_pnl_usd"] > 0,
        "profit_factor_at_least_1_1": observed.get("profit_factor", 0.0) >= 1.1,
        "both_directions_positive": (
            set(observed.get("direction_pnl_usd", {})) == {"bearish", "bullish"}
            and all(value > 0 for value in observed["direction_pnl_usd"].values())
        ),
        "both_chronological_halves_positive": (
            set(observed.get("chronological_half_pnl_usd", {}))
            == {"first", "second"}
            and all(
                value > 0
                for value in observed["chronological_half_pnl_usd"].values()
            )
        ),
        "positive_after_one_extra_cent_each_fill": one_cent["net_pnl_usd"] > 0,
        "positive_after_five_minute_delay": (
            summarize(delay_five, eligible_days)["net_pnl_usd"] > 0
        ),
        "positive_after_removing_five_best": (
            observed.get("net_without_five_best_usd", 0.0) > 0
        ),
        "beats_same_period_spy_price_only": (
            observed.get("cash_account", {}).get("ending_equity_usd", 0.0)
            > spy_hurdle["ending_value_usd"]
        ),
        "bootstrap_probability_nonpositive_below_0_25": (
            bootstrap.get("probability_total_not_positive", 1.0) < 0.25
        ),
    }
    result = {
        "status": "prospective_test_complete_rule_frozen_no_repairs",
        "specification": (
            "research_scout/upro_spxu_density_invariant_sync_prereg_v6.json"
        ),
        "data_validation": (
            "external_artifacts/databento_forward_2026/validation_report.json"
        ),
        "excluded_degraded_dates": sorted(str(day.date()) for day in excluded),
        "period": {
            "first_session": str(eligible_days[0].date()),
            "last_session": str(eligible_days[-1].date()),
            "eligible_sessions": len(eligible_days),
        },
        "observed_bbo": observed,
        "midpoint_diagnostic": summarize(
            trades,
            eligible_days,
            midpoint_execution=True,
        ),
        "one_extra_cent_each_fill": one_cent,
        "two_extra_cents_each_fill": summarize(trades, eligible_days, 0.02),
        "one_additional_minute_delay": summarize(delay_one, eligible_days),
        "five_additional_minutes_delay": summarize(delay_five, eligible_days),
        "spy_price_only_hurdle": spy_hurdle,
        "five_session_block_bootstrap": bootstrap,
        "monthly_pnl_non_actionable": monthly_diagnostic(trades),
        "acceptance_criteria": criteria,
        "all_acceptance_criteria_passed": all(criteria.values()),
    }
    OUTPUT.write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
