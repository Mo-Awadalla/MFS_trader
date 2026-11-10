"""Evaluate the frozen SPY opening-auction residual buy-pressure hypothesis."""

from __future__ import annotations

import hashlib
import json
import math
import sys
import warnings
from datetime import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_variance_state as common

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import databento as db  # noqa: E402

PREREG = ROOT / "research_scout" / "spy_opening_auction_residual_buy_pressure_prereg_v34.json"
FEASIBILITY = ROOT / "research_scout" / "spy_auction_imbalance_feasibility_v34.json"
STATES = ROOT / "research_scout" / "spy_auction_imbalance_states_v34.json"
OUTPUT = ROOT / "research_scout" / "spy_opening_auction_residual_buy_pressure_results_v34.json"
REPORT = ROOT / "research_scout" / "SPY_OPENING_AUCTION_RESIDUAL_BUY_PRESSURE_REPORT_V34.md"
ARCA_CONDITIONS = ROOT / "external_artifacts" / "databento_cash_etf_budget_v1" / "ARCX.PILLAR" / "dataset_condition.json"
EQUS_CONDITIONS = ROOT / "external_artifacts" / "databento_cash_etf_budget_v1" / "EQUS.MINI" / "dataset_condition.json"
OLD_BBO = ROOT / "external_artifacts" / "databento_leveraged_etf" / "ARCX.PILLAR" / "bbo" / "upro_spxu_bbo_1m_2021-01-01_2026-01-01.dbn.zst"
NEW_BBO = ROOT / "external_artifacts" / "databento_forward_2026" / "ARCX.PILLAR" / "bbo" / "upro_spxu_bbo_1m_2026-01-02_2026-07-25.dbn.zst"
OLD_SPY = ROOT / "external_artifacts" / "databento_fractional_etf" / "ARCX.PILLAR" / "bars" / "spy_sh_ohlcv_1m_2021-01-01_2026-01-01.dbn.zst"
NEW_SPY = ROOT / "external_artifacts" / "databento_forward_2026" / "ARCX.PILLAR" / "bars" / "spy_upro_spxu_ohlcv_1m_2026-01-02_2026-07-25.dbn.zst"
TBBO_PREFIX = ROOT / "external_artifacts" / "databento_cash_etf_budget_v1" / "EQUS.MINI" / "tbbo" / "cash_etf_tbbo_2023-03-28_2026-07-27.dbn.partial.dbn.zst"
TBBO_TAIL = ROOT / "external_artifacts" / "databento_cash_etf_budget_v1" / "EQUS.MINI" / "tbbo" / "cash_etf_tbbo_tail_2024-10-03_2026-07-27.dbn.zst"

ENTRY = time(9, 31)
EXIT = time(10, 30)
START = pd.Timestamp("2021-01-04")
DEVELOPMENT_END = pd.Timestamp("2023-12-29")
HOLDOUT_START = pd.Timestamp("2024-01-02")
HOLDOUT_END = pd.Timestamp("2025-12-31")
EXTENSION_START = pd.Timestamp("2026-01-02")
EXTENSION_END = pd.Timestamp("2026-07-24")
BOOTSTRAP_RESAMPLES = 5000
BOOTSTRAP_SEED = 340034
NY = "America/New_York"


def degraded(path: Path) -> set[pd.Timestamp]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        pd.Timestamp(item["date"])
        for item in payload["conditions"]
        if item["condition"] != "available"
    }


def load_states() -> dict[pd.Timestamp, dict[str, Any]]:
    payload = json.loads(STATES.read_text(encoding="utf-8"))
    if payload.get("returns_read") is not False:
        raise RuntimeError("Returns-blind auction state artifact is invalid")
    return {
        pd.Timestamp(item["session_date"]): item for item in payload["states"]
    }


def weeks(start: pd.Timestamp, end: pd.Timestamp) -> float:
    return max((end - start).days / 7.0, 1.0)


def feasibility_gate(
    audit: dict[str, Any], states: dict[pd.Timestamp, dict[str, Any]]
) -> dict[str, bool]:
    dev_buy = [
        day
        for day, state in states.items()
        if START <= day <= DEVELOPMENT_END and state["side"] == "B"
    ]
    by_year = {
        year: sum(day.year == year for day in dev_buy) for year in [2021, 2022, 2023]
    }
    return {
        "audit_did_not_read_returns": audit.get("returns_read") is False,
        "signal_type_is_market_open": audit.get(
            "selected_opening_auction_type_for_reachability"
        )
        == "M",
        "development_frequency_at_least_two_per_week": (
            len(dev_buy) / weeks(START, DEVELOPMENT_END) >= 2.0
        ),
        "each_development_year_has_at_least_90_signals": all(
            by_year[year] >= 90 for year in by_year
        ),
    }


def load_primary(
    include_extension: bool = False,
) -> tuple[
    dict[pd.Timestamp, pd.DataFrame],
    dict[pd.Timestamp, pd.DataFrame],
]:
    spy_frames = [base.load_dbn(OLD_SPY, "SPY")]
    bbo_frames = [base.load_dbn(OLD_BBO, "UPRO")]
    if include_extension:
        spy_frames.append(base.load_dbn(NEW_SPY, "SPY"))
        bbo_frames.append(base.load_dbn(NEW_BBO, "UPRO"))
    spy = base.split_sessions(pd.concat(spy_frames).sort_index())
    bbo = base.split_sessions(pd.concat(bbo_frames).sort_index())
    return spy, bbo


def stamp(day: pd.Timestamp, clock: time, tz: Any) -> pd.Timestamp:
    return pd.Timestamp.combine(day.date(), clock).tz_localize(tz)


def prior_close(
    day: pd.Timestamp,
    spy: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
) -> float | None:
    candidates = sorted(d for d in spy if d < day and d not in excluded)
    if not candidates:
        return None
    prior_day = candidates[-1]
    frame = spy[prior_day]
    row = base.exact_row(frame, stamp(prior_day, time(15, 59), frame.index.tz))
    if row is None:
        return None
    value = float(row.close)
    return value if value > 0 else None


def primary_return(
    day: pd.Timestamp,
    bbo: dict[pd.Timestamp, pd.DataFrame],
    *,
    entry_delay_minutes: int = 0,
    adverse_cents: float = 0.0,
) -> tuple[float, float] | None:
    quotes = bbo.get(day)
    if quotes is None:
        return None
    entry_clock = (
        pd.Timestamp.combine(day.date(), ENTRY)
        + pd.Timedelta(minutes=entry_delay_minutes)
    ).time()
    entry = base.quote_at(quotes, stamp(day, entry_clock, quotes.index.tz), 0)
    exit_row = base.quote_at(quotes, stamp(day, EXIT, quotes.index.tz), 0)
    if entry is None or exit_row is None:
        return None
    buy = float(entry.ask_px_00) + adverse_cents
    sell = float(exit_row.bid_px_00) - adverse_cents
    if buy <= 0 or sell <= 0:
        return None
    midpoint = (float(entry.bid_px_00) + float(entry.ask_px_00)) / 2.0
    spread_bps = (
        (float(entry.ask_px_00) - float(entry.bid_px_00)) / midpoint * 10_000.0
    )
    return sell / buy - 1.0, spread_bps


def selection_map(
    states: dict[pd.Timestamp, dict[str, Any]], variant: str
) -> dict[pd.Timestamp, bool]:
    days = sorted(states)
    selected: dict[pd.Timestamp, bool] = {}
    for position, day in enumerate(days):
        if variant == "actual":
            selected[day] = states[day]["side"] == "B"
        elif variant == "flipped":
            selected[day] = states[day]["side"] == "A"
        elif variant == "lagged":
            selected[day] = position > 0 and states[days[position - 1]]["side"] == "B"
        else:
            raise ValueError(f"Unknown variant: {variant}")
    return selected


def make_primary_rows(
    states: dict[pd.Timestamp, dict[str, Any]],
    spy: dict[pd.Timestamp, pd.DataFrame],
    bbo: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
    variant: str = "actual",
    *,
    entry_delay_minutes: int = 0,
    adverse_cents: float = 0.0,
) -> list[dict[str, Any]]:
    selected = selection_map(states, variant)
    rows: list[dict[str, Any]] = []
    for day in sorted(states):
        if day in excluded or not start <= day <= end or not selected[day]:
            continue
        realized = primary_return(
            day,
            bbo,
            entry_delay_minutes=entry_delay_minutes,
            adverse_cents=adverse_cents,
        )
        if realized is None:
            continue
        value, spread_bps = realized
        previous_close = prior_close(day, spy, excluded)
        reference_gap = (
            float(states[day]["ref_price"]) / previous_close - 1.0
            if previous_close is not None
            else math.nan
        )
        rows.append(
            {
                "date": day,
                "symbol": "UPRO",
                "return": value,
                "pnl_usd": 100.0 * value,
                "reference_gap": reference_gap,
                "entry_spread_bps": spread_bps,
            }
        )
    return rows


def bootstrap_lower(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return math.nan
    values = np.array([row["return"] for row in rows], dtype=float)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    means = np.empty(BOOTSTRAP_RESAMPLES, dtype=float)
    for index in range(BOOTSTRAP_RESAMPLES):
        means[index] = float(rng.choice(values, size=len(values), replace=True).mean())
    return float(np.quantile(means, 0.025))


def summarize_rows(rows: list[dict[str, Any]], remove_best: int) -> dict[str, Any]:
    result = common.summarize(rows, remove_best=remove_best)
    result["bootstrap_95pct_lower_mean_return"] = bootstrap_lower(rows)
    result["median_entry_spread_bps"] = (
        float(np.median([row["entry_spread_bps"] for row in rows]))
        if rows
        else math.nan
    )
    return result


def evaluate_primary_period(
    states: dict[pd.Timestamp, dict[str, Any]],
    spy: dict[pd.Timestamp, pd.DataFrame],
    bbo: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
    remove_best: int,
) -> dict[str, Any]:
    actual_rows = make_primary_rows(states, spy, bbo, excluded, start, end)
    cent_rows = make_primary_rows(
        states, spy, bbo, excluded, start, end, adverse_cents=0.01
    )
    delayed_rows = make_primary_rows(
        states, spy, bbo, excluded, start, end, entry_delay_minutes=5
    )
    flipped_rows = make_primary_rows(
        states, spy, bbo, excluded, start, end, variant="flipped"
    )
    lagged_rows = make_primary_rows(
        states, spy, bbo, excluded, start, end, variant="lagged"
    )
    nonnegative_gap = [
        row for row in actual_rows if row["reference_gap"] >= 0
    ]
    negative_gap = [row for row in actual_rows if row["reference_gap"] < 0]
    return {
        "observed_bbo": summarize_rows(actual_rows, remove_best),
        "one_extra_cent_each_fill": summarize_rows(cent_rows, remove_best),
        "five_minute_entry_delay": summarize_rows(delayed_rows, remove_best),
        "sell_side_sign_flip_placebo": summarize_rows(flipped_rows, remove_best),
        "previous_session_signal_placebo": summarize_rows(lagged_rows, remove_best),
        "nonnegative_reference_gap_subset": summarize_rows(
            nonnegative_gap, remove_best
        ),
        "negative_reference_gap_subset": summarize_rows(negative_gap, remove_best),
        "spy_price_only_hurdle": common.spy_hurdle(spy, excluded, start, end),
    }


def development_gate(result: dict[str, Any]) -> dict[str, bool]:
    observed = result["observed_bbo"]
    years = observed.get("year_pnl_usd", {})
    spy = result["spy_price_only_hurdle"]
    return {
        "minimum_two_trades_per_week": observed["trades_per_week"] >= 2.0,
        "profit_factor_strictly_above_1_1": observed["profit_factor"] > 1.1,
        "each_development_year_positive": all(
            years.get(str(year), 0.0) > 0 for year in [2021, 2022, 2023]
        ),
        "ending_cash_at_least_110_percent_of_spy": (
            observed["ending_cash_usd"] >= 1.10 * spy["ending_cash_usd"]
        ),
        "positive_after_one_extra_cent_each_fill": (
            result["one_extra_cent_each_fill"]["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_five_minute_entry_delay": (
            result["five_minute_entry_delay"]["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_removing_ten_best_sessions": (
            observed["pnl_without_best_10_sessions_usd"] > 0
        ),
        "bootstrap_lower_mean_above_zero": (
            observed["bootstrap_95pct_lower_mean_return"] > 0
        ),
        "positive_on_nonnegative_reference_gaps": (
            result["nonnegative_reference_gap_subset"]["fixed_notional_pnl_usd"]
            > 0
        ),
        "positive_on_negative_reference_gaps": (
            result["negative_reference_gap_subset"]["fixed_notional_pnl_usd"] > 0
        ),
        "outperform_sell_side_placebo": (
            observed["fixed_notional_pnl_usd"]
            > result["sell_side_sign_flip_placebo"]["fixed_notional_pnl_usd"]
        ),
        "outperform_previous_session_placebo": (
            observed["fixed_notional_pnl_usd"]
            > result["previous_session_signal_placebo"]["fixed_notional_pnl_usd"]
        ),
    }


def load_tbbo_boundaries(excluded: set[pd.Timestamp]) -> dict[pd.Timestamp, dict[str, tuple[float, float]]]:
    boundaries: dict[pd.Timestamp, dict[str, tuple[pd.Timestamp, float, float]]] = {}
    sources = [
        (TBBO_PREFIX, pd.Timestamp("1900-01-01"), pd.Timestamp("2024-10-02")),
        (TBBO_TAIL, pd.Timestamp("2024-10-03"), pd.Timestamp("2100-01-01")),
    ]
    targets = {
        "entry": 9 * 3600 + 31 * 60 + 1,
        "exit": 10 * 3600 + 30 * 60 + 1,
    }
    for path, min_day, max_day in sources:
        store = db.read_dbn(path)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for frame in store.to_df(count=1_000_000, map_symbols=True):
                frame = frame.loc[frame["symbol"].eq("UPRO")].copy()
                if frame.empty:
                    continue
                event = pd.to_datetime(frame["ts_event"], utc=True).dt.tz_convert(NY)
                days = event.dt.tz_localize(None).dt.normalize()
                seconds = (
                    event.dt.hour * 3600
                    + event.dt.minute * 60
                    + event.dt.second
                    + event.dt.microsecond / 1_000_000.0
                )
                frame = frame.assign(event_ny=event, day=days, second=seconds)
                frame = frame.loc[
                    frame["day"].between(min_day, max_day)
                    & ~frame["day"].isin(excluded)
                ]
                for name, target in targets.items():
                    selected = frame.loc[
                        frame["second"].between(target, target + 59.999999)
                        & frame["bid_px_00"].gt(0)
                        & frame["ask_px_00"].gt(0)
                        & frame["ask_px_00"].ge(frame["bid_px_00"])
                    ]
                    if selected.empty:
                        continue
                    first = (
                        selected.sort_values("event_ny")
                        .groupby("day", sort=False, as_index=False)
                        .first()
                    )
                    for row in first.itertuples(index=False):
                        day = pd.Timestamp(row.day)
                        candidate = (
                            pd.Timestamp(row.event_ny),
                            float(row.bid_px_00),
                            float(row.ask_px_00),
                        )
                        old = boundaries.setdefault(day, {}).get(name)
                        if old is None or candidate[0] < old[0]:
                            boundaries[day][name] = candidate
    return {
        day: {
            name: (values[1], values[2]) for name, values in rows.items()
        }
        for day, rows in boundaries.items()
        if {"entry", "exit"}.issubset(rows)
    }


def tbbo_summary(
    states: dict[pd.Timestamp, dict[str, Any]],
    excluded: set[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Any]:
    boundaries = load_tbbo_boundaries(excluded)
    rows: list[dict[str, Any]] = []
    for day, state in sorted(states.items()):
        if not start <= day <= end or state["side"] != "B" or day not in boundaries:
            continue
        entry_bid, entry_ask = boundaries[day]["entry"]
        exit_bid, _ = boundaries[day]["exit"]
        value = exit_bid / entry_ask - 1.0
        midpoint = (entry_bid + entry_ask) / 2.0
        rows.append(
            {
                "date": day,
                "symbol": "UPRO",
                "return": value,
                "pnl_usd": 100.0 * value,
                "entry_spread_bps": (entry_ask - entry_bid) / midpoint * 10_000.0,
            }
        )
    return summarize_rows(rows, 5)


def holdout_gate(result: dict[str, Any], consolidated: dict[str, Any]) -> dict[str, bool]:
    observed = result["observed_bbo"]
    years = observed.get("year_pnl_usd", {})
    spy = result["spy_price_only_hurdle"]
    return {
        "minimum_two_trades_per_week": observed["trades_per_week"] >= 2.0,
        "profit_factor_strictly_above_1_1": observed["profit_factor"] > 1.1,
        "each_holdout_year_positive": all(
            years.get(str(year), 0.0) > 0 for year in [2024, 2025]
        ),
        "ending_cash_at_least_110_percent_of_spy": (
            observed["ending_cash_usd"] >= 1.10 * spy["ending_cash_usd"]
        ),
        "positive_after_one_extra_cent_each_fill": (
            result["one_extra_cent_each_fill"]["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_five_minute_entry_delay": (
            result["five_minute_entry_delay"]["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_removing_five_best_sessions": (
            observed["pnl_without_best_5_sessions_usd"] > 0
        ),
        "positive_on_both_reference_gap_subsets": (
            result["nonnegative_reference_gap_subset"]["fixed_notional_pnl_usd"] > 0
            and result["negative_reference_gap_subset"]["fixed_notional_pnl_usd"] > 0
        ),
        "outperform_both_placebos": (
            observed["fixed_notional_pnl_usd"]
            > result["sell_side_sign_flip_placebo"]["fixed_notional_pnl_usd"]
            and observed["fixed_notional_pnl_usd"]
            > result["previous_session_signal_placebo"]["fixed_notional_pnl_usd"]
        ),
        "consolidated_tbbo_positive": consolidated["fixed_notional_pnl_usd"] > 0,
    }


def render(payload: dict[str, Any]) -> str:
    lines = [
        "# SPY Opening-Auction Residual Buy Pressure v34",
        "",
        "## Verdict",
        "",
    ]
    status = payload["status"]
    if status == "blocked_by_returns_blind_feasibility":
        lines.append("**Blocked before P&L because the returns-blind feasibility gate failed.**")
    elif status == "rejected_in_development_holdout_locked":
        lines.append("**Rejected in development. The 2024–2026 return partitions remain locked.**")
    elif status == "rejected_on_secondary_holdout":
        lines.append("**Rejected on the conditional 2024–2025 secondary holdout.**")
    else:
        lines.append("**Historical survivor only; prospective paper validation is required.**")
    lines.extend(["", f"Specification SHA-256: `{payload['specification_sha256']}`", ""])
    if "development" in payload:
        dev = payload["development"]
        observed = dev["observed_bbo"]
        spy = dev["spy_price_only_hurdle"]
        lines.extend(
            [
                "## Development: 2021–2023",
                "",
                f"- Trades/week: {observed['trades_per_week']:.2f}",
                f"- Ending cash: ${observed['ending_cash_usd']:.2f}",
                f"- Price-only SPY: ${spy['ending_cash_usd']:.2f}",
                f"- Profit factor: {observed['profit_factor']:.3f}",
                f"- Fixed-$100 P&L: ${observed['fixed_notional_pnl_usd']:.2f}",
                f"- P&L without ten best sessions: ${observed['pnl_without_best_10_sessions_usd']:.2f}",
                f"- Bootstrap lower mean return: {observed['bootstrap_95pct_lower_mean_return']:.6f}",
                "",
                "Failed development gates:",
                "",
                "- " + (", ".join(name for name, passed in dev["gate"].items() if not passed) or "None"),
                "",
            ]
        )
    lines.extend(
        [
            "No result-driven threshold, sign, clock, stop, actuator, or sleeve change was made.",
            "",
            "Preimplementation critique: `research_scout/SPY_OPENING_AUCTION_RESIDUAL_BUY_PRESSURE_PREIMPLEMENTATION_CRITIQUE_V34.md`.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    spec_bytes = PREREG.read_bytes()
    spec_hash = hashlib.sha256(spec_bytes).hexdigest()
    audit = json.loads(FEASIBILITY.read_text(encoding="utf-8"))
    states = load_states()
    reachability = feasibility_gate(audit, states)
    payload: dict[str, Any] = {
        "specification": PREREG.relative_to(ROOT).as_posix(),
        "specification_sha256": spec_hash,
        "returns_blind_feasibility_gate": reachability,
        "returns_blind_feasibility_passed": all(reachability.values()),
    }
    if not payload["returns_blind_feasibility_passed"]:
        payload.update(
            {
                "status": "blocked_by_returns_blind_feasibility",
                "development_return_status": "not_calculated",
                "holdout_return_status": "not_calculated",
            }
        )
    else:
        excluded = degraded(ARCA_CONDITIONS)
        spy, bbo = load_primary(False)
        development = evaluate_primary_period(
            states,
            spy,
            bbo,
            excluded,
            START,
            DEVELOPMENT_END,
            10,
        )
        development["gate"] = development_gate(development)
        development["gate_passed"] = all(development["gate"].values())
        payload["development"] = development
        if not development["gate_passed"]:
            payload.update(
                {
                    "status": "rejected_in_development_holdout_locked",
                    "holdout_return_status": "not_calculated",
                    "extension_return_status": "not_calculated",
                }
            )
        else:
            holdout = evaluate_primary_period(
                states,
                spy,
                bbo,
                excluded,
                HOLDOUT_START,
                HOLDOUT_END,
                5,
            )
            consolidated = tbbo_summary(
                states,
                degraded(EQUS_CONDITIONS),
                HOLDOUT_START,
                HOLDOUT_END,
            )
            holdout["consolidated_tbbo"] = consolidated
            holdout["gate"] = holdout_gate(holdout, consolidated)
            holdout["gate_passed"] = all(holdout["gate"].values())
            payload["holdout"] = holdout
            if not holdout["gate_passed"]:
                payload.update(
                    {
                        "status": "rejected_on_secondary_holdout",
                        "holdout_return_status": "calculated_after_development_pass",
                        "extension_return_status": "not_calculated",
                    }
                )
            else:
                full_spy, full_bbo = load_primary(True)
                extension = evaluate_primary_period(
                    states,
                    full_spy,
                    full_bbo,
                    excluded,
                    EXTENSION_START,
                    EXTENSION_END,
                    5,
                )
                payload.update(
                    {
                        "status": "historical_survivor_requires_prospective_paper_validation",
                        "holdout_return_status": "calculated_after_development_pass",
                        "extension_return_status": "calculated_after_holdout_pass",
                        "extension_2026": extension,
                    }
                )
    OUTPUT.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    REPORT.write_text(render(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
