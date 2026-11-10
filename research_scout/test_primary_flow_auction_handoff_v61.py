"""Test the preregistered primary-flow/opening-auction handoff v61.

The 2024-2025 partition is evaluated only if every frozen 2021-2023
development gate passes. No parameter search is implemented.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import time, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

from research_scout import test_spy_btc_perpetual_fresh_position_v44 as v44  # noqa: E402
from research_scout import test_upro_spxu_creative_hypotheses as base  # noqa: E402
from research_scout import (  # noqa: E402
    test_upro_spxu_cross_inverse_aggressor_relay as v16,
)
from research_scout import test_upro_spxu_variance_state as common  # noqa: E402

PREREG = ROOT / "research_scout" / "primary_flow_auction_handoff_prereg_v61.json"
FEASIBILITY = (
    ROOT / "research_scout" / "primary_flow_auction_handoff_audit_v61.json"
)
FLOW_AUDIT = (
    ROOT / "research_scout" / "proshares_primary_market_flow_audit_v60.json"
)
AUCTION_STATES = ROOT / "research_scout" / "spy_auction_imbalance_states_v34.json"
NAV_PATH = (
    ROOT
    / "data"
    / "raw"
    / "proshares_inventory_v59"
    / "historical_nav.csv"
)
SPLIT_PATH = (
    ROOT / "data" / "raw" / "proshares_inventory_v59" / "split_history.csv"
)
OUTPUT = ROOT / "research_scout" / "primary_flow_auction_handoff_results_v61.json"
REPORT = ROOT / "research_scout" / "PRIMARY_FLOW_AUCTION_HANDOFF_REPORT_V61.md"

START = pd.Timestamp("2021-01-04")
DEVELOPMENT_END = pd.Timestamp("2023-12-29")
HOLDOUT_START = pd.Timestamp("2024-01-02")
HOLDOUT_END = pd.Timestamp("2025-12-31")
ENTRY = time(9, 31)
EXIT = time(10, 30)
BOOTSTRAP_RESAMPLES = 5000
BOOTSTRAP_BLOCK = 5
BOOTSTRAP_SEED = 610061


def sign(value: float) -> int:
    return int(value > 0) - int(value < 0)


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def load_development_flow() -> dict[pd.Timestamp, int]:
    payload = json.loads(FLOW_AUDIT.read_text(encoding="utf-8"))
    if not payload.get("admission_passed"):
        raise RuntimeError("Primary-market flow audit did not pass")
    return {
        pd.Timestamp(item["available_session"]).normalize(): (
            1 if item["direction"] == "B" else -1
        )
        for item in payload["paired_directional_flow"]["states"]
    }


def load_auction_states() -> dict[pd.Timestamp, int]:
    payload = json.loads(AUCTION_STATES.read_text(encoding="utf-8"))
    if payload.get("returns_read") is not False:
        raise RuntimeError("Auction state file is not returns-blind")
    return {
        pd.Timestamp(item["session_date"]).normalize(): (
            1 if item["side"] == "B" else -1
        )
        for item in payload["states"]
        if item["side"] in {"A", "B"}
    }


def load_spy_prior_directions() -> dict[pd.Timestamp, int]:
    frame = pd.read_parquet(v44.ADJUSTED_SPY).copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.set_index("timestamp")
    elif frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    frame = frame.sort_index()
    frame["session_date"] = (
        frame.index.tz_convert("America/New_York").tz_localize(None).normalize()
    )
    frame["prior_direction"] = frame["close"].astype(float).pct_change().map(sign)
    ordered = frame["session_date"].tolist()
    next_session = {
        ordered[index]: ordered[index + 1] for index in range(len(ordered) - 1)
    }
    return {
        next_session[row.session_date]: int(row.prior_direction)
        for row in frame.itertuples()
        if row.session_date in next_session and int(row.prior_direction) != 0
    }


def build_variants(
    flow: dict[pd.Timestamp, int],
    auction: dict[pd.Timestamp, int],
    spy_prior: dict[pd.Timestamp, int],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, dict[pd.Timestamp, int]]:
    variants: dict[str, dict[pd.Timestamp, int]] = {
        "actual": {},
        "flow_only": {},
        "auction_only": {},
        "failed_v34_buy_only": {},
        "extra_lag_flow_alignment": {},
        "prior_spy_direction": {},
    }
    flow_days = sorted(flow)
    previous_flow = {
        day: flow[flow_days[index - 1]]
        for index, day in enumerate(flow_days)
        if index
    }
    for day in sorted(set(flow).intersection(auction)):
        if not start <= day <= end:
            continue
        flow_direction = int(flow[day])
        auction_direction = int(auction[day])
        variants["actual"][day] = (
            flow_direction if flow_direction == auction_direction else 0
        )
        variants["flow_only"][day] = flow_direction
        variants["auction_only"][day] = auction_direction
        variants["failed_v34_buy_only"][day] = (
            1 if auction_direction > 0 else 0
        )
        lagged = previous_flow.get(day, 0)
        variants["extra_lag_flow_alignment"][day] = (
            lagged if lagged == auction_direction else 0
        )
        variants["prior_spy_direction"][day] = int(spy_prior.get(day, 0))
    return variants


def make_rows(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    directions: dict[pd.Timestamp, int],
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    adverse_cents: float = 0.0,
    delay_minutes: int = 0,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for day in sorted(directions):
        if day in excluded or not start <= day <= end:
            continue
        direction = int(directions[day])
        if direction == 0:
            continue
        symbol = "UPRO" if direction > 0 else "SPXU"
        quotes = sessions.get(day, {}).get(symbol)
        if quotes is None:
            continue
        entry_stamp = v16.stamp(day, ENTRY, quotes.index.tz) + timedelta(
            minutes=delay_minutes
        )
        exit_stamp = v16.stamp(day, EXIT, quotes.index.tz)
        entry = base.quote_at(quotes, entry_stamp, 0)
        exit_quote = base.quote_at(quotes, exit_stamp, 0)
        if entry is None or exit_quote is None:
            continue
        entry_ask = float(entry.ask_px_00) + adverse_cents
        exit_bid = float(exit_quote.bid_px_00) - adverse_cents
        if min(entry_ask, exit_bid) <= 0:
            continue
        realized = exit_bid / entry_ask - 1.0
        rows.append(
            {
                "date": day,
                "symbol": symbol,
                "direction": direction,
                "entry_time": entry_stamp,
                "exit_time": exit_stamp,
                "entry_ask": entry_ask,
                "exit_bid": exit_bid,
                "return": realized,
                "pnl_usd": 100.0 * realized,
            }
        )
    return rows


def moving_block_bootstrap_lower(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return math.nan
    values = np.asarray([row["return"] for row in rows], dtype=float)
    size = len(values)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    starts = np.arange(size)
    means = np.empty(BOOTSTRAP_RESAMPLES, dtype=float)
    blocks_needed = math.ceil(size / BOOTSTRAP_BLOCK)
    for sample_index in range(BOOTSTRAP_RESAMPLES):
        chosen = rng.choice(starts, size=blocks_needed, replace=True)
        sample = np.concatenate(
            [
                values[(start + np.arange(BOOTSTRAP_BLOCK)) % size]
                for start in chosen
            ]
        )[:size]
        means[sample_index] = float(sample.mean())
    return float(np.quantile(means, 0.025))


def summarize(rows: list[dict[str, Any]], remove_best: int) -> dict[str, Any]:
    result = common.summarize(rows, remove_best)
    result["moving_block_bootstrap_95pct_lower_mean_return"] = (
        moving_block_bootstrap_lower(rows)
    )
    return result


def evaluate(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    variants: dict[str, dict[pd.Timestamp, int]],
    start: pd.Timestamp,
    end: pd.Timestamp,
    remove_best: int,
) -> dict[str, Any]:
    actual = variants["actual"]
    observed_rows = make_rows(sessions, excluded, actual, start, end)
    return {
        "observed_bbo": summarize(observed_rows, remove_best),
        "extra_cent_each_fill": summarize(
            make_rows(
                sessions,
                excluded,
                actual,
                start,
                end,
                adverse_cents=0.01,
            ),
            remove_best,
        ),
        "five_minute_entry_delay": summarize(
            make_rows(
                sessions,
                excluded,
                actual,
                start,
                end,
                delay_minutes=5,
            ),
            remove_best,
        ),
        "controls": {
            name: summarize(
                make_rows(sessions, excluded, directions, start, end),
                remove_best,
            )
            for name, directions in variants.items()
            if name != "actual"
        },
        "spy_total_return_hurdle": v44.adjusted_spy_hurdle(start, end),
    }


def development_gates(
    result: dict[str, Any],
    independent: dict[str, Any],
) -> dict[str, bool]:
    observed = result["observed_bbo"]
    years = observed.get("year_pnl_usd", {})
    sleeves = observed.get("instrument_pnl_usd", {})
    controls = result["controls"]
    mean_return = float(observed["mean_session_pnl_usd"])
    return {
        "minimum_two_executed_trades_per_week": (
            observed["trades_per_week"] >= 2.0
        ),
        "profit_factor_strictly_above_1_10": observed["profit_factor"] > 1.10,
        "fixed_notional_pnl_positive_each_year": all(
            years.get(str(year), 0.0) > 0 for year in (2021, 2022, 2023)
        ),
        "both_upro_and_spxu_fixed_notional_pnl_positive": all(
            sleeves.get(symbol, 0.0) > 0 for symbol in ("UPRO", "SPXU")
        ),
        "compounded_ending_cash_above_adjusted_spy": (
            observed["ending_cash_usd"]
            > result["spy_total_return_hurdle"]["ending_cash_usd"]
        ),
        "positive_after_one_extra_cent_each_fill": (
            result["extra_cent_each_fill"]["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_five_minute_entry_delay": (
            result["five_minute_entry_delay"]["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_deleting_ten_best_sessions": (
            observed["pnl_without_best_10_sessions_usd"] > 0
        ),
        "moving_block_bootstrap_lower_mean_above_zero": (
            observed["moving_block_bootstrap_95pct_lower_mean_return"] > 0
        ),
        "independent_feed_overlap_positive": (
            independent["observed_bbo"]["fixed_notional_pnl_usd"] > 0
        ),
        "mean_trade_return_above_every_control": all(
            mean_return > float(item["mean_session_pnl_usd"])
            for item in controls.values()
        ),
    }


def holdout_gates(result: dict[str, Any]) -> dict[str, bool]:
    observed = result["observed_bbo"]
    years = observed.get("year_pnl_usd", {})
    sleeves = observed.get("instrument_pnl_usd", {})
    return {
        "minimum_two_executed_trades_per_week": (
            observed["trades_per_week"] >= 2.0
        ),
        "profit_factor_strictly_above_1_10": observed["profit_factor"] > 1.10,
        "each_holdout_year_positive": all(
            years.get(str(year), 0.0) > 0 for year in (2024, 2025)
        ),
        "both_sleeves_positive": all(
            sleeves.get(symbol, 0.0) > 0 for symbol in ("UPRO", "SPXU")
        ),
        "ending_cash_above_adjusted_spy": (
            observed["ending_cash_usd"]
            > result["spy_total_return_hurdle"]["ending_cash_usd"]
        ),
        "positive_after_extra_cent": (
            result["extra_cent_each_fill"]["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_five_minute_delay": (
            result["five_minute_entry_delay"]["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_deleting_five_best": (
            observed["pnl_without_best_5_sessions_usd"] > 0
        ),
    }


def build_full_flow(
    trade_sessions: list[pd.Timestamp],
) -> dict[pd.Timestamp, int]:
    nav = pd.read_csv(NAV_PATH)
    nav["date"] = pd.to_datetime(nav["Date"], errors="coerce")
    nav["shares_000"] = pd.to_numeric(
        nav["Shares Outstanding (000)"], errors="coerce"
    )
    nav["nav"] = pd.to_numeric(nav["NAV"], errors="coerce")
    nav = nav[nav["Ticker"].isin(["UPRO", "SPXU"])].copy()

    splits = pd.read_csv(SPLIT_PATH)
    splits["date"] = pd.to_datetime(splits["Date of Split"], errors="coerce")
    splits["ratio"] = pd.to_numeric(splits["Ratio"], errors="coerce")
    split_lookup = {
        (record["Symbol"], record["date"]): (
            record["Split Type"],
            record["ratio"],
        )
        for record in splits.to_dict(orient="records")
        if record["Symbol"] in {"UPRO", "SPXU"}
    }
    by_symbol: dict[str, pd.DataFrame] = {}
    for symbol in ("UPRO", "SPXU"):
        selected = nav[nav["Ticker"] == symbol].sort_values("date").copy()
        selected["prior_shares"] = selected["shares_000"].shift(1)
        expected: list[float] = []
        for row in selected.itertuples(index=False):
            value = row.prior_shares
            split_type, ratio = split_lookup.get((symbol, row.date), (None, None))
            if pd.notna(value) and split_type == "Forward":
                value *= ratio
            elif pd.notna(value) and split_type == "Reverse":
                value /= ratio
            expected.append(value)
        selected["flow_dollars"] = (
            (selected["shares_000"] - expected) * 1000.0 * selected["nav"]
        )
        by_symbol[symbol] = selected[["date", "flow_dollars"]]
    paired = by_symbol["UPRO"].merge(
        by_symbol["SPXU"],
        on="date",
        suffixes=("_upro", "_spxu"),
        validate="one_to_one",
    )
    paired["direction"] = (
        paired["flow_dollars_upro"] - paired["flow_dollars_spxu"]
    ).map(sign)
    ordered = sorted(set(trade_sessions))
    next_session = {
        ordered[index]: ordered[index + 1] for index in range(len(ordered) - 1)
    }
    return {
        next_session[row.date]: int(row.direction)
        for row in paired.itertuples(index=False)
        if row.date in next_session and int(row.direction) != 0
    }


def render(payload: dict[str, Any]) -> str:
    development = payload["development"]
    observed = development["observed_bbo"]
    failures = [
        name for name, passed in payload["development_gates"].items() if not passed
    ]
    verdict = (
        "**Development passed; the 2024-2025 holdout was opened.**"
        if payload["development_passed"]
        else "**Rejected in development; 2024-2025 remains locked.**"
    )
    lines = [
        "# Primary-Flow / Opening-Auction Handoff v61",
        "",
        "## Verdict",
        "",
        verdict,
        "",
        "## Development: 2021-2023",
        "",
        f"- Trades: {observed['sessions']} ({observed['trades_per_week']:.3f}/week)",
        f"- Fixed-$100 P&L: ${observed['fixed_notional_pnl_usd']:.2f}",
        f"- Compounded ending cash: ${observed['ending_cash_usd']:.2f}",
        f"- Profit factor: {observed['profit_factor']:.3f}",
        (
            "- Adjusted SPY ending cash: "
            f"${development['spy_total_return_hurdle']['ending_cash_usd']:.2f}"
        ),
        (
            "- P&L without ten best sessions: "
            f"${observed['pnl_without_best_10_sessions_usd']:.2f}"
        ),
        (
            "- Extra-cent stress P&L: "
            f"${development['extra_cent_each_fill']['fixed_notional_pnl_usd']:.2f}"
        ),
        (
            "- Five-minute-delay P&L: "
            f"${development['five_minute_entry_delay']['fixed_notional_pnl_usd']:.2f}"
        ),
        "",
        "Failed development gates: "
        + (", ".join(failures) if failures else "none"),
        "",
    ]
    if payload["development_passed"]:
        holdout = payload["holdout"]["observed_bbo"]
        lines.extend(
            [
                "## Holdout: 2024-2025",
                "",
                f"- Trades: {holdout['sessions']} ({holdout['trades_per_week']:.3f}/week)",
                f"- Fixed-$100 P&L: ${holdout['fixed_notional_pnl_usd']:.2f}",
                f"- Compounded ending cash: ${holdout['ending_cash_usd']:.2f}",
                f"- Profit factor: {holdout['profit_factor']:.3f}",
                "",
            ]
        )
    lines.extend(
        [
            "## Integrity boundary",
            "",
            "The official-flow definition, auction cutoff, clocks, sleeves, "
            "controls, and gates were frozen before return inspection. No "
            "threshold, sign, horizon, or sleeve repair was made.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    feasibility = json.loads(FEASIBILITY.read_text(encoding="utf-8"))
    if not feasibility.get("gate_passed"):
        raise RuntimeError("V61 returns-blind construction audit did not pass")
    prereg_hash = hashlib.sha256(PREREG.read_bytes()).hexdigest()

    flow = load_development_flow()
    auction = load_auction_states()
    spy_prior = load_spy_prior_directions()
    variants = build_variants(
        flow, auction, spy_prior, START, DEVELOPMENT_END
    )
    spy, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    development = evaluate(
        arca,
        arca_excluded,
        variants,
        START,
        DEVELOPMENT_END,
        10,
    )
    independent = evaluate(
        equs,
        equs_excluded,
        variants,
        pd.Timestamp("2023-03-28"),
        DEVELOPMENT_END,
        5,
    )
    prior_spy_directions = variants["prior_spy_direction"]
    development["outcome_exposed_prior_spy_control_diagnostic"] = {
        "status": "diagnostic_only_not_a_candidate",
        "observed_bbo": development["controls"]["prior_spy_direction"],
        "extra_cent_each_fill": summarize(
            make_rows(
                arca,
                arca_excluded,
                prior_spy_directions,
                START,
                DEVELOPMENT_END,
                adverse_cents=0.01,
            ),
            10,
        ),
        "five_minute_entry_delay": summarize(
            make_rows(
                arca,
                arca_excluded,
                prior_spy_directions,
                START,
                DEVELOPMENT_END,
                delay_minutes=5,
            ),
            10,
        ),
        "independent_overlap": independent["controls"]["prior_spy_direction"],
        "recent_year_return_status": "locked_not_read",
    }
    gates = development_gates(development, independent)
    passed = all(gates.values())
    payload: dict[str, Any] = {
        "specification": str(PREREG.relative_to(ROOT)).replace("\\", "/"),
        "specification_sha256": prereg_hash,
        "returns_blind_construction": feasibility,
        "development": development,
        "independent_overlap": independent,
        "development_gates": gates,
        "development_passed": passed,
        "holdout_status": "unlocked" if passed else "locked_not_read",
    }
    if passed:
        full_flow = build_full_flow(sorted(spy))
        holdout_variants = build_variants(
            full_flow,
            auction,
            spy_prior,
            HOLDOUT_START,
            HOLDOUT_END,
        )
        holdout = evaluate(
            arca,
            arca_excluded,
            holdout_variants,
            HOLDOUT_START,
            HOLDOUT_END,
            5,
        )
        holdout_gate = holdout_gates(holdout)
        payload["holdout"] = holdout
        payload["holdout_gates"] = holdout_gate
        payload["holdout_passed"] = all(holdout_gate.values())

    safe = json_safe(payload)
    OUTPUT.write_text(json.dumps(safe, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(render(safe), encoding="utf-8")
    print(json.dumps(safe, indent=2))


if __name__ == "__main__":
    main()
