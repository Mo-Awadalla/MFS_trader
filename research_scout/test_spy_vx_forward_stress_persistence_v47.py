"""Evaluate the preregistered VX forward-stress persistence hypothesis v47.

The 2024-2025 partition is read only if every frozen 2021-2023 development
gate passes.  This module intentionally contains no parameter search.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import time, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_spy_vx_curve_confirmation_failure_v46 as v46
from research_scout import audit_spy_vx_forward_stress_persistence_v47 as audit
from research_scout import test_spy_btc_perpetual_fresh_position_v44 as v44
from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16
from research_scout import test_upro_spxu_variance_state as common

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "spy_vx_forward_stress_persistence_results_v47.json"
REPORT = ROOT / "research_scout" / "SPY_VX_FORWARD_STRESS_PERSISTENCE_REPORT_V47.md"
DEVELOPMENT_START = pd.Timestamp("2021-01-01")
DEVELOPMENT_END = pd.Timestamp("2023-12-31")
HOLDOUT_START = pd.Timestamp("2024-01-01")
HOLDOUT_END = pd.Timestamp("2025-12-31")
ENTRY = time(9, 31)
EXIT = time(15, 30)


def _repair_vendor_version_metadata() -> None:
    """Make the repo's vendored zstandard package legible to pandas.

    The vendored package used by Databento is importable but does not expose
    ``__version__``.  Pandas asks for it even while opening an ordinary CSV.
    This compatibility shim does not alter data or decompression behavior.
    """

    try:
        import zstandard  # type: ignore[import-not-found]
    except ImportError:
        return
    if not getattr(zstandard, "__version__", None):
        zstandard.__version__ = "0.25.0"


def load_contracts() -> dict[pd.Timestamp, dict[pd.Timestamp, float]]:
    """Load official VX CSVs without invoking pandas' optional zstd probe."""

    manifest = json.loads(v46.MANIFEST.read_text(encoding="utf-8"))
    by_date: dict[pd.Timestamp, dict[pd.Timestamp, float]] = defaultdict(dict)
    for item in manifest["files"]:
        expiration = pd.Timestamp(item["expiration"])
        with (ROOT / item["path"]).open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            expected = {
                "Trade Date",
                "Futures",
                "Open",
                "High",
                "Low",
                "Close",
                "Settle",
                "Change",
                "Total Volume",
                "EFP",
                "Open Interest",
            }
            if set(reader.fieldnames or []) != expected:
                raise RuntimeError(f"Unexpected VX schema: {item['path']}")
            for row in reader:
                settle = float(row["Settle"])
                if settle > 0:
                    by_date[pd.Timestamp(row["Trade Date"]).normalize()][expiration] = settle
    return dict(by_date)


def sign(value: float) -> int:
    return int(value > 0) - int(value < 0)


def build_trade_directions(
    states: dict[pd.Timestamp, dict[str, Any]],
    next_session: dict[pd.Timestamp, pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, dict[pd.Timestamp, int]]:
    ordered = sorted(states)
    previous_state = {day: states[ordered[index - 1]] for index, day in enumerate(ordered) if index}
    variants: dict[str, dict[pd.Timestamp, int]] = {
        "actual": {},
        "prior_spy_continuation": {},
        "prior_spy_reversal": {},
        "one_session_lagged_curve_change": {},
        "sign_flipped": {},
    }
    for signal_day in ordered:
        trade_day = next_session.get(signal_day)
        if trade_day is None or not start <= trade_day <= end:
            continue
        actual = audit.curve_action(states[signal_day])
        spy_direction = sign(float(states[signal_day]["spy_return"]))
        lagged = previous_state.get(signal_day)
        variants["actual"][trade_day] = actual
        variants["prior_spy_continuation"][trade_day] = spy_direction
        variants["prior_spy_reversal"][trade_day] = -spy_direction
        variants["one_session_lagged_curve_change"][trade_day] = (
            audit.curve_action(lagged) if lagged is not None else 0
        )
        variants["sign_flipped"][trade_day] = -actual
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


def evaluate(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
    variants: dict[str, dict[pd.Timestamp, int]],
    start: pd.Timestamp,
    end: pd.Timestamp,
    remove_best: int,
) -> dict[str, Any]:
    actual = variants["actual"]
    observed = make_rows(sessions, excluded, actual, start, end)
    controls = {
        name: common.summarize(
            make_rows(sessions, excluded, directions, start, end),
            remove_best,
        )
        for name, directions in variants.items()
        if name != "actual"
    }
    return {
        "observed_bbo": common.summarize(observed, remove_best),
        "extra_cent_each_fill": common.summarize(
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
        "five_minute_entry_delay": common.summarize(
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
        "controls": controls,
        "spy_price_only_hurdle": common.spy_hurdle(
            spy_sessions, excluded, start, end
        ),
        "spy_total_return_hurdle": v44.adjusted_spy_hurdle(start, end),
    }


def development_gates(
    result: dict[str, Any],
    independent: dict[str, Any],
) -> dict[str, bool]:
    observed = result["observed_bbo"]
    years = observed.get("year_pnl_usd", {})
    instruments = observed.get("instrument_pnl_usd", {})
    controls = result["controls"]
    mean_pnl = float(observed["mean_session_pnl_usd"])
    return {
        "minimum_two_trades_per_week": observed["trades_per_week"] >= 2.0,
        "profit_factor_at_least_1_05": observed["profit_factor"] >= 1.05,
        "positive_fixed_notional_pnl": observed["fixed_notional_pnl_usd"] > 0,
        "each_development_year_positive": all(
            years.get(str(year), 0.0) > 0 for year in [2021, 2022, 2023]
        ),
        "both_upro_and_spxu_positive": all(
            instruments.get(symbol, 0.0) > 0 for symbol in ["UPRO", "SPXU"]
        ),
        "ending_cash_above_spy_total_return": (
            observed["ending_cash_usd"]
            > result["spy_total_return_hurdle"]["ending_cash_usd"]
        ),
        "positive_after_extra_cent_each_fill": (
            result["extra_cent_each_fill"]["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_five_minute_entry_delay": (
            result["five_minute_entry_delay"]["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_deleting_ten_best_trades": (
            observed["pnl_without_best_10_sessions_usd"] > 0
        ),
        "positive_independent_overlap": (
            independent["observed_bbo"]["fixed_notional_pnl_usd"] > 0
        ),
        "mean_trade_pnl_above_prior_spy_continuation": (
            mean_pnl
            > controls["prior_spy_continuation"]["mean_session_pnl_usd"]
        ),
        "mean_trade_pnl_above_prior_spy_reversal": (
            mean_pnl > controls["prior_spy_reversal"]["mean_session_pnl_usd"]
        ),
        "mean_trade_pnl_above_lagged_curve_change": (
            mean_pnl
            > controls["one_session_lagged_curve_change"]["mean_session_pnl_usd"]
        ),
        "mean_trade_pnl_above_sign_flipped": (
            mean_pnl > controls["sign_flipped"]["mean_session_pnl_usd"]
        ),
    }


def holdout_gates(result: dict[str, Any]) -> dict[str, bool]:
    observed = result["observed_bbo"]
    years = observed.get("year_pnl_usd", {})
    instruments = observed.get("instrument_pnl_usd", {})
    return {
        "minimum_two_trades_per_week": observed["trades_per_week"] >= 2.0,
        "profit_factor_above_one": observed["profit_factor"] > 1.0,
        "each_holdout_year_positive": all(
            years.get(str(year), 0.0) > 0 for year in [2024, 2025]
        ),
        "both_upro_and_spxu_positive": all(
            instruments.get(symbol, 0.0) > 0 for symbol in ["UPRO", "SPXU"]
        ),
        "ending_cash_above_spy_total_return": (
            observed["ending_cash_usd"]
            > result["spy_total_return_hurdle"]["ending_cash_usd"]
        ),
        "positive_after_extra_cent_each_fill": (
            result["extra_cent_each_fill"]["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_deleting_five_best_trades": (
            observed["pnl_without_best_5_sessions_usd"] > 0
        ),
    }


def money(value: float) -> str:
    return f"${value:,.2f}"


def render(payload: dict[str, Any]) -> str:
    development = payload["development"]
    observed = development["observed_bbo"]
    gates = payload["development_gates"]
    failures = [name for name, passed in gates.items() if not passed]
    lines = [
        "# SPY VX Forward-Stress Persistence v47",
        "",
        "## Verdict",
        "",
        (
            "**Rejected in the 2024-2025 holdout after passing development.**"
            if payload["development_passed"] and not payload.get("holdout_passed", False)
            else (
                "**Development and holdout passed.**"
                if payload["development_passed"]
                else (
                    "**Rejected in development; the 2024-2025 return holdout "
                    "remains locked.**"
                )
            )
        ),
        "",
        "## Development: 2021-2023",
        "",
        f"- Trades: {observed['sessions']} ({observed['trades_per_week']:.3f}/week)",
        f"- Compounded cash: {money(observed['ending_cash_usd'])}",
        f"- Fixed-$100 P&L: {money(observed['fixed_notional_pnl_usd'])}",
        f"- Profit factor: {observed['profit_factor']:.3f}",
        (
            "- Split/dividend-adjusted SPY hurdle: "
            f"{money(development['spy_total_return_hurdle']['ending_cash_usd'])}"
        ),
        (
            "- P&L after deleting ten best trades: "
            f"{money(observed['pnl_without_best_10_sessions_usd'])}"
        ),
        (
            "- Extra-cent stress P&L: "
            f"{money(development['extra_cent_each_fill']['fixed_notional_pnl_usd'])}"
        ),
        (
            "- Five-minute delay P&L: "
            f"{money(development['five_minute_entry_delay']['fixed_notional_pnl_usd'])}"
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
                f"- Compounded cash: {money(holdout['ending_cash_usd'])}",
                f"- Fixed-$100 P&L: {money(holdout['fixed_notional_pnl_usd'])}",
                f"- Profit factor: {holdout['profit_factor']:.3f}",
                "",
            ]
        )
    lines.extend(
        [
            "## Integrity boundary",
            "",
            "The rule, clocks, controls, and gates were frozen before target-return "
            "inspection. No threshold, sign, contract, regime, or hold-time repair was "
            "made after seeing development returns.",
            "",
        ]
    )
    return "\n".join(lines)


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def main() -> None:
    feasibility = json.loads(audit.OUTPUT.read_text(encoding="utf-8"))
    if not feasibility.get("feasibility_passed"):
        raise RuntimeError("V47 returns-blind feasibility audit must pass before returns")

    _repair_vendor_version_metadata()
    contracts = load_contracts()
    spy, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    states = v46.build_states(spy, contracts, arca_excluded)
    next_session = v46.next_session_map(spy)

    development_variants = build_trade_directions(
        states, next_session, DEVELOPMENT_START, DEVELOPMENT_END
    )
    development = evaluate(
        arca,
        spy,
        arca_excluded,
        development_variants,
        DEVELOPMENT_START,
        DEVELOPMENT_END,
        10,
    )
    independent = evaluate(
        equs,
        spy,
        equs_excluded,
        development_variants,
        audit.EQUS_START,
        DEVELOPMENT_END,
        5,
    )
    gates = development_gates(development, independent)
    passed = all(gates.values())
    payload: dict[str, Any] = {
        "specification_id": "spy_vx_forward_stress_persistence_v47",
        "returns_blind_feasibility": feasibility,
        "development": development,
        "independent_overlap": independent,
        "development_gates": gates,
        "development_passed": passed,
        "holdout_status": "unlocked" if passed else "locked_not_read",
    }
    if passed:
        holdout_variants = build_trade_directions(
            states, next_session, HOLDOUT_START, HOLDOUT_END
        )
        holdout = evaluate(
            arca,
            spy,
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
