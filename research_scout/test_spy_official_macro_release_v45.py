"""Evaluate preregistered official macro-release delayed discovery v45."""

from __future__ import annotations

import json
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_spy_official_macro_release_v45 as audit
from research_scout import test_spy_btc_perpetual_fresh_position_v44 as v44
from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16
from research_scout import test_upro_spxu_variance_state as common
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay_audit

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "spy_official_macro_release_results_v45.json"
REPORT = ROOT / "research_scout" / "SPY_OFFICIAL_MACRO_RELEASE_DELAYED_DISCOVERY_REPORT_V45.md"
DEVELOPMENT_START = pd.Timestamp("2021-01-01")
DEVELOPMENT_END = pd.Timestamp("2023-12-31")
HOLDOUT_START = pd.Timestamp("2024-01-01")
HOLDOUT_END = pd.Timestamp("2025-12-31")


def scoped_episodes(start: pd.Timestamp, end: pd.Timestamp) -> list[dict[str, Any]]:
    return [row for row in audit.load_episodes() if start <= row["date"] <= end]


def direction_records(
    episodes: list[dict[str, Any]],
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for episode in episodes:
        day = episode["date"]
        if day in excluded:
            continue
        direction = audit.signal_direction(spy_sessions, day, episode["release_clock"])
        if direction in (None, 0):
            continue
        rows.append({**episode, "direction": int(direction)})
    return rows


def shifted_non_event_episodes(
    episodes: list[dict[str, Any]],
    ordered_sessions: list[pd.Timestamp],
    end: pd.Timestamp,
) -> list[dict[str, Any]]:
    actual_dates = {row["date"] for row in audit.load_episodes()}
    positions = {day: index for index, day in enumerate(ordered_sessions)}
    shifted: dict[tuple[pd.Timestamp, str], dict[str, Any]] = {}
    for episode in episodes:
        position = positions.get(episode["date"])
        if position is None:
            continue
        target = None
        for day in ordered_sessions[position + 1 :]:
            if day > end:
                break
            if day not in actual_dates:
                target = day
                break
        if target is None:
            continue
        key = (target, episode["release_clock"])
        shifted.setdefault(
            key,
            {
                "date": target,
                "release_clock": episode["release_clock"],
                "families": [],
                "sources": [],
                "shifted_from": [],
            },
        )
        shifted[key]["families"] = sorted(
            set(shifted[key]["families"]).union(episode["families"])
        )
        shifted[key]["shifted_from"].append(str(episode["date"].date()))
    return [shifted[key] for key in sorted(shifted)]


def exact_execution_quote(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    day: pd.Timestamp,
    symbol: str,
    release_clock: str,
    which: str,
    delay_minutes: int = 0,
) -> Any | None:
    setup = audit.CLOCKS[release_clock]
    clock = setup[which]
    quotes = sessions.get(day, {}).get(symbol)
    if quotes is None:
        return None
    stamp = v16.stamp(day, clock, quotes.index.tz)
    if which == "entry":
        stamp += timedelta(minutes=delay_minutes)
    row = base.quote_at(quotes, stamp, 0)
    return row if audit.valid_quote(row) else None


def make_rows(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    records: list[dict[str, Any]],
    *,
    adverse_cents: float = 0.0,
    delay_minutes: int = 0,
    flip: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda row: (row["date"], row["release_clock"])):
        day = record["date"]
        if day in excluded:
            continue
        direction = -int(record["direction"]) if flip else int(record["direction"])
        symbol = "UPRO" if direction > 0 else "SPXU"
        entry = exact_execution_quote(
            sessions,
            day,
            symbol,
            record["release_clock"],
            "entry",
            delay_minutes,
        )
        exit_quote = exact_execution_quote(
            sessions,
            day,
            symbol,
            record["release_clock"],
            "exit",
        )
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
                "release_clock": record["release_clock"],
                "families": record["families"],
                "symbol": symbol,
                "direction": direction,
                "entry_ask": entry_ask,
                "exit_bid": exit_bid,
                "return": realized,
                "pnl_usd": 100.0 * realized,
            }
        )
    return rows


def clock_pnl(rows: list[dict[str, Any]]) -> dict[str, float]:
    result = {clock: 0.0 for clock in audit.CLOCKS}
    for row in rows:
        result[row["release_clock"]] += float(row["pnl_usd"])
    return result


def family_diagnostics(rows: list[dict[str, Any]]) -> dict[str, dict[str, float | int]]:
    families = sorted({family for row in rows for family in row["families"]})
    result: dict[str, dict[str, float | int]] = {}
    for family in families:
        selected = [row for row in rows if family in row["families"]]
        result[family] = {
            "trades_inclusive": len(selected),
            "fixed_notional_pnl_usd_inclusive": float(
                sum(float(row["pnl_usd"]) for row in selected)
            ),
        }
    return result


def evaluate_period(
    episodes: list[dict[str, Any]],
    spy_signal: dict[pd.Timestamp, pd.DataFrame],
    execution: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    spy_hurdle_sessions: dict[pd.Timestamp, pd.DataFrame],
    start: pd.Timestamp,
    end: pd.Timestamp,
    remove_best: int,
    *,
    shifted_control: bool = True,
) -> dict[str, Any]:
    records = direction_records(episodes, spy_signal, excluded)
    actual_rows = make_rows(execution, excluded, records)
    cent_rows = make_rows(execution, excluded, records, adverse_cents=0.01)
    delayed_rows = make_rows(execution, excluded, records, delay_minutes=5)
    flipped_rows = make_rows(execution, excluded, records, flip=True)
    controls: dict[str, Any] = {
        "direction_flipped": common.summarize(flipped_rows, remove_best),
    }
    if shifted_control:
        ordered = sorted(
            day for day in spy_signal if start <= day <= end and day not in excluded
        )
        shifted = shifted_non_event_episodes(episodes, ordered, end)
        shifted_records = direction_records(shifted, spy_signal, excluded)
        shifted_rows = make_rows(execution, excluded, shifted_records)
        controls["next_non_event_session_same_clock"] = common.summarize(
            shifted_rows, remove_best
        )
    return {
        "observed_bbo": common.summarize(actual_rows, remove_best),
        "clock_pnl_usd": clock_pnl(actual_rows),
        "family_diagnostics": family_diagnostics(actual_rows),
        "extra_cent_each_fill": common.summarize(cent_rows, remove_best),
        "five_minute_entry_delay": common.summarize(delayed_rows, remove_best),
        "controls": controls,
        "spy_price_only_hurdle": common.spy_hurdle(
            spy_hurdle_sessions, excluded, start, end
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
    clocks = result["clock_pnl_usd"]
    shifted = result["controls"]["next_non_event_session_same_clock"]
    flipped = result["controls"]["direction_flipped"]
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
        "each_release_clock_positive": all(value > 0 for value in clocks.values()),
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
        "positive_after_removing_ten_best_trades": (
            observed["pnl_without_best_10_sessions_usd"] > 0
        ),
        "positive_independent_feed_overlap": (
            independent["observed_bbo"]["fixed_notional_pnl_usd"] > 0
        ),
        "outperform_next_non_event_same_clock_control": (
            observed["fixed_notional_pnl_usd"]
            > shifted["fixed_notional_pnl_usd"]
        ),
        "outperform_direction_flipped_control": (
            observed["fixed_notional_pnl_usd"]
            > flipped["fixed_notional_pnl_usd"]
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
        "each_release_clock_positive": all(
            value > 0 for value in result["clock_pnl_usd"].values()
        ),
        "ending_cash_above_spy_total_return": (
            observed["ending_cash_usd"]
            > result["spy_total_return_hurdle"]["ending_cash_usd"]
        ),
        "positive_after_extra_cent_each_fill": (
            result["extra_cent_each_fill"]["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_removing_five_best_trades": (
            observed["pnl_without_best_5_sessions_usd"] > 0
        ),
    }


def money(value: float) -> str:
    return f"${value:,.2f}"


def render(payload: dict[str, Any]) -> str:
    dev = payload["development"]
    observed = dev["observed_bbo"]
    lines = [
        "# SPY Official Macro-Release Delayed Discovery v45",
        "",
        "## Verdict",
        "",
        (
            "**Development passed; holdout was unlocked.**"
            if payload["development_passed"]
            else "**Rejected in development. The 2024-2025 return holdout remains locked.**"
        ),
        "",
        "## Development",
        "",
        f"- Trades: {observed['sessions']} ({observed['trades_per_week']:.4f}/week)",
        f"- Fixed-$100 P&L: {money(observed['fixed_notional_pnl_usd'])}",
        f"- Ending cash: {money(observed['ending_cash_usd'])}",
        f"- Profit factor: {observed['profit_factor']:.4f}",
        f"- SPY total-return ending value: {money(dev['spy_total_return_hurdle']['ending_cash_usd'])}",
        f"- Annual P&L: {observed.get('year_pnl_usd', {})}",
        f"- Instrument P&L: {observed.get('instrument_pnl_usd', {})}",
        f"- Release-clock P&L: {dev['clock_pnl_usd']}",
        f"- Independent overlap P&L: {money(payload['independent_overlap']['observed_bbo']['fixed_notional_pnl_usd'])}",
        "",
        "## Development gates",
        "",
    ]
    lines.extend(
        f"- {'PASS' if passed else 'FAIL'} — {name}"
        for name, passed in payload["development_gates"].items()
    )
    if payload.get("holdout"):
        holdout = payload["holdout"]["observed_bbo"]
        lines.extend(
            [
                "",
                "## Holdout",
                "",
                f"- Fixed-$100 P&L: {money(holdout['fixed_notional_pnl_usd'])}",
                f"- Ending cash: {money(holdout['ending_cash_usd'])}",
                f"- Profit factor: {holdout['profit_factor']:.4f}",
            ]
        )
    lines.extend(
        [
            "",
            "No event family, clock, year, direction, or threshold may be repaired from these results.",
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
        return str(value)
    return value


def main() -> None:
    feasibility = json.loads(audit.OUTPUT.read_text(encoding="utf-8"))
    if not feasibility.get("feasibility_passed"):
        raise RuntimeError("V45 returns-blind feasibility audit must pass before returns")
    spy, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    equs_spy = base.split_sessions(base.load_dbn(audit.EQUS_SPY, "SPY"))
    equs_spy_excluded = relay_audit.degraded(relay_audit.EQUS_CONDITIONS)

    development_episodes = scoped_episodes(DEVELOPMENT_START, DEVELOPMENT_END)
    development = evaluate_period(
        development_episodes,
        spy,
        arca,
        arca_excluded,
        spy,
        DEVELOPMENT_START,
        DEVELOPMENT_END,
        10,
    )
    overlap_episodes = scoped_episodes(audit.EQUS_START, DEVELOPMENT_END)
    independent = evaluate_period(
        overlap_episodes,
        equs_spy,
        equs,
        equs_excluded.union(equs_spy_excluded),
        equs_spy,
        audit.EQUS_START,
        DEVELOPMENT_END,
        5,
        shifted_control=False,
    )
    gates = development_gates(development, independent)
    passed = all(gates.values())
    payload: dict[str, Any] = {
        "specification_id": "spy_official_macro_release_delayed_discovery_v45",
        "returns_blind_feasibility": feasibility,
        "development": development,
        "independent_overlap": independent,
        "development_gates": gates,
        "development_passed": passed,
        "holdout_status": "unlocked" if passed else "locked_not_read",
    }
    if passed:
        holdout_episodes = scoped_episodes(HOLDOUT_START, HOLDOUT_END)
        holdout = evaluate_period(
            holdout_episodes,
            spy,
            arca,
            arca_excluded,
            spy,
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
