"""Returns-blind data and execution audit for VX-curve confirmation failure v46."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import time
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_spy_official_macro_release_v45 as macro_audit
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay_audit
from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "research_scout" / "spy_vx_curve_confirmation_failure_prereg_v46.json"
MANIFEST = ROOT / "data" / "raw" / "cboe_vx_monthly_v46" / "manifest.json"
OUTPUT = ROOT / "research_scout" / "spy_vx_curve_confirmation_failure_returns_blind_audit_v46.json"
START = pd.Timestamp("2021-01-01")
END = pd.Timestamp("2023-12-31")
EQUS_START = pd.Timestamp("2023-03-28")
ENTRY = time(9, 31)
EXIT = time(15, 30)


def load_contracts() -> dict[pd.Timestamp, dict[pd.Timestamp, float]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_date: dict[pd.Timestamp, dict[pd.Timestamp, float]] = defaultdict(dict)
    expected = {
        "Trade Date", "Futures", "Open", "High", "Low", "Close", "Settle",
        "Change", "Total Volume", "EFP", "Open Interest",
    }
    for item in manifest["files"]:
        expiration = pd.Timestamp(item["expiration"])
        frame = pd.read_csv(ROOT / item["path"])
        if set(frame.columns) != expected:
            raise RuntimeError(f"Unexpected VX schema: {item['path']}")
        frame["Trade Date"] = pd.to_datetime(frame["Trade Date"])
        frame["Settle"] = pd.to_numeric(frame["Settle"], errors="coerce")
        for row in frame.itertuples(index=False):
            day = pd.Timestamp(row[0]).normalize()
            settle = float(row[6])
            if settle > 0:
                by_date[day][expiration] = settle
    return dict(by_date)


def curve_for(
    contracts: dict[pd.Timestamp, dict[pd.Timestamp, float]],
    day: pd.Timestamp,
    *,
    skip_front: bool = False,
) -> dict[str, Any] | None:
    available = sorted(
        (expiration, settle)
        for expiration, settle in contracts.get(day, {}).items()
        if expiration > day and settle > 0
    )
    offset = 1 if skip_front else 0
    if len(available) < offset + 2:
        return None
    front_expiration, front = available[offset]
    second_expiration, second = available[offset + 1]
    return {
        "front_expiration": front_expiration,
        "second_expiration": second_expiration,
        "front_settle": front,
        "second_settle": second,
        "slope": (second - front) / front,
    }


def spy_cash_return(frame: pd.DataFrame) -> float | None:
    open_row = base.exact_row(frame, v16.stamp(frame.index[0].normalize(), time(9, 30), frame.index.tz))
    close_row = base.exact_row(frame, v16.stamp(frame.index[0].normalize(), time(15, 59), frame.index.tz))
    if open_row is None or close_row is None:
        return None
    opening = float(open_row.open)
    closing = float(close_row.close)
    if min(opening, closing) <= 0:
        return None
    return closing / opening - 1.0


def action(spy_return: float, curve_change: float) -> int:
    if spy_return > 0 and curve_change < 0:
        return -1
    if spy_return < 0 and curve_change > 0:
        return 1
    return 0


def build_states(
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    contracts: dict[pd.Timestamp, dict[pd.Timestamp, float]],
    excluded: set[pd.Timestamp],
    *,
    early_roll: bool = False,
) -> dict[pd.Timestamp, dict[str, Any]]:
    complete: list[dict[str, Any]] = []
    ordered_spy = sorted(spy_sessions)
    session_position = {day: index for index, day in enumerate(ordered_spy)}
    for day in ordered_spy:
        if day in excluded:
            continue
        spy_return = spy_cash_return(spy_sessions[day])
        standard = curve_for(contracts, day)
        if spy_return is None or standard is None:
            continue
        use_early = False
        if early_roll:
            position = session_position[day]
            next_two = set(ordered_spy[position + 1 : position + 3])
            use_early = standard["front_expiration"] in next_two
        curve = curve_for(contracts, day, skip_front=use_early)
        if curve is None:
            continue
        complete.append({"date": day, "spy_return": spy_return, **curve})
    states: dict[pd.Timestamp, dict[str, Any]] = {}
    for previous, current in zip(complete, complete[1:]):
        change = float(current["slope"]) - float(previous["slope"])
        states[current["date"]] = {
            **current,
            "previous_curve_date": previous["date"],
            "curve_change": change,
            "action": action(float(current["spy_return"]), change),
        }
    return states


def next_session_map(spy_sessions: dict[pd.Timestamp, pd.DataFrame]) -> dict[pd.Timestamp, pd.Timestamp]:
    ordered = sorted(spy_sessions)
    return {left: right for left, right in zip(ordered, ordered[1:])}


def execution_available(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    day: pd.Timestamp,
    symbol: str,
) -> bool:
    quotes = sessions.get(day, {}).get(symbol)
    if quotes is None:
        return False
    entry = base.quote_at(quotes, v16.stamp(day, ENTRY, quotes.index.tz), 0)
    exit_quote = base.quote_at(quotes, v16.stamp(day, EXIT, quotes.index.tz), 0)
    return macro_audit.valid_quote(entry) and macro_audit.valid_quote(exit_quote)


def main() -> None:
    if not PREREG.exists():
        raise FileNotFoundError("V46 preregistration is required before audit")
    contracts = load_contracts()
    spy, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    equs_spy = base.split_sessions(base.load_dbn(macro_audit.EQUS_SPY, "SPY"))
    equs_spy_excluded = relay_audit.degraded(relay_audit.EQUS_CONDITIONS)
    next_spy = next_session_map(spy)

    eligible_signal_days = [
        day for day in sorted(spy)
        if START <= day <= END and day not in arca_excluded
    ]
    states = build_states(spy, contracts, arca_excluded)
    early_states = build_states(spy, contracts, arca_excluded, early_roll=True)
    candidate_rows: list[dict[str, Any]] = []
    for signal_day in eligible_signal_days:
        state = states.get(signal_day)
        if state is None or state["action"] == 0:
            continue
        trade_day = next_spy.get(signal_day)
        if trade_day is None or not START <= trade_day <= END:
            continue
        direction = int(state["action"])
        symbol = "UPRO" if direction > 0 else "SPXU"
        candidate_rows.append(
            {
                "signal_day": signal_day,
                "trade_day": trade_day,
                "direction": direction,
                "symbol": symbol,
                "execution_available": (
                    trade_day not in arca_excluded
                    and execution_available(arca, trade_day, symbol)
                ),
            }
        )
    frame = pd.DataFrame(candidate_rows)
    executable = frame[frame.execution_available].copy() if len(frame) else frame

    complete_state_days = sum(day in states for day in eligible_signal_days)
    signal_coverage = complete_state_days / max(len(eligible_signal_days), 1)
    execution_coverage = len(executable) / max(len(frame), 1)
    weeks = (END - START).days / 7.0
    cadence = len(executable) / weeks
    year_counts = {
        str(year): int((executable.trade_day.dt.year == year).sum()) if len(executable) else 0
        for year in [2021, 2022, 2023]
    }
    direction_counts = Counter(executable.symbol) if len(executable) else Counter()
    minority = min(direction_counts.get("UPRO", 0), direction_counts.get("SPXU", 0)) / max(len(executable), 1)

    roll_comparisons = roll_agreements = 0
    for day in eligible_signal_days:
        standard = states.get(day)
        alternate = early_states.get(day)
        if standard is None or alternate is None:
            continue
        roll_comparisons += 1
        roll_agreements += int(standard["action"] == alternate["action"])
    roll_agreement = roll_agreements / max(roll_comparisons, 1)

    eq_states = build_states(equs_spy, contracts, equs_spy_excluded)
    feed_comparisons = feed_agreements = 0
    independent_candidates = independent_executable = 0
    for day in sorted(set(states).intersection(eq_states)):
        if not EQUS_START <= day <= END:
            continue
        feed_comparisons += 1
        feed_agreements += int(states[day]["action"] == eq_states[day]["action"])
        eq_action = int(eq_states[day]["action"])
        if eq_action == 0:
            continue
        trade_day = next_spy.get(day)
        if trade_day is None or trade_day > END:
            continue
        independent_candidates += 1
        symbol = "UPRO" if eq_action > 0 else "SPXU"
        if trade_day not in equs_excluded and execution_available(equs, trade_day, symbol):
            independent_executable += 1
    feed_agreement = feed_agreements / max(feed_comparisons, 1)
    independent_execution_coverage = independent_executable / max(independent_candidates, 1)
    causality = all(row["signal_day"] < row["trade_day"] for row in candidate_rows)

    gates = {
        "signal_coverage_at_least_98_percent": signal_coverage >= 0.98,
        "at_least_two_executable_trades_per_calendar_week": cadence >= 2.0,
        "at_least_100_executable_trades_each_development_year": all(
            count >= 100 for count in year_counts.values()
        ),
        "minority_direction_at_least_20_percent": minority >= 0.20,
        "primary_execution_coverage_at_least_95_percent": execution_coverage >= 0.95,
        "independent_action_agreement_at_least_90_percent": feed_agreement >= 0.90,
        "independent_execution_coverage_at_least_95_percent": independent_execution_coverage >= 0.95,
        "early_roll_action_agreement_at_least_80_percent": roll_agreement >= 0.80,
        "strict_signal_before_trade_causality": causality,
    }
    payload = {
        "status": "returns_blind_no_post_entry_return_or_pnl_computed",
        "eligible_development_signal_sessions": len(eligible_signal_days),
        "complete_curve_and_spy_states": complete_state_days,
        "signal_coverage": signal_coverage,
        "candidate_signals": len(frame),
        "executable_trades": len(executable),
        "executable_trades_per_calendar_week": cadence,
        "primary_execution_coverage": execution_coverage,
        "year_counts": year_counts,
        "direction_counts": dict(direction_counts),
        "minority_direction_fraction": minority,
        "roll_policy_comparisons": roll_comparisons,
        "early_roll_action_agreement_including_cash": roll_agreement,
        "independent_action_comparisons": feed_comparisons,
        "independent_action_agreement_including_cash": feed_agreement,
        "independent_candidate_signals": independent_candidates,
        "independent_executable_signals": independent_executable,
        "independent_execution_coverage": independent_execution_coverage,
        "predeclared_feasibility_gates": gates,
        "feasibility_passed": all(gates.values()),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
