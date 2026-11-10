"""Evaluate the preregistered cross-inverse aggressor relay hypothesis."""

from __future__ import annotations

import json
from datetime import time, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import (
    audit_upro_spxu_cross_inverse_aggressor_relay as audit,
)
from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_expanding_analog_memory as analog
from research_scout import test_upro_spxu_variance_state as common

ROOT = Path(__file__).resolve().parents[1]
PREREG = (
    ROOT
    / "research_scout"
    / "upro_spxu_cross_inverse_aggressor_relay_prereg_v16.json"
)
OUTPUT = (
    ROOT
    / "research_scout"
    / "upro_spxu_cross_inverse_aggressor_relay_results_v16.json"
)
REPORT = (
    ROOT / "research_scout" / "UPRO_SPXU_CROSS_INVERSE_AGGRESSOR_RELAY_REPORT_V16.md"
)
ENTRY = time(10, 16)
EXIT = time(15, 30)
START = pd.Timestamp("2021-01-04")
DEVELOPMENT_END = pd.Timestamp("2023-12-29")
HOLDOUT_START = pd.Timestamp("2024-01-02")
HOLDOUT_END = pd.Timestamp("2025-12-31")
EXTENSION_START = pd.Timestamp("2026-01-02")
EXTENSION_END = pd.Timestamp("2026-07-24")


def stamp(day: pd.Timestamp, clock: time, tz: Any) -> pd.Timestamp:
    return pd.Timestamp.combine(day.date(), clock).tz_localize(tz)


def unconfirmed_direction(pair: dict[str, pd.DataFrame]) -> int:
    if not {"UPRO", "SPXU"}.issubset(pair):
        return 0
    events = audit.fresh_events("UPRO", pair["UPRO"])
    events.extend(audit.fresh_events("SPXU", pair["SPXU"]))
    score = sum(event.underlying_sign for event in events)
    return int(score > 0) - int(score < 0)


def signal_for(
    pair: dict[str, pd.DataFrame],
    variant: str,
) -> tuple[int, int, int]:
    state = audit.session_signal(pair)
    if state is None:
        return 0, 0, 0
    relay_direction = int(state["direction"])
    if variant == "actual":
        direction = relay_direction
    elif variant == "flipped":
        direction = -relay_direction
    elif variant == "unconfirmed":
        direction = unconfirmed_direction(pair)
    else:
        raise ValueError(f"Unknown variant: {variant}")
    return direction, int(state["score"]), int(state["relays"])


def trade_row(
    day: pd.Timestamp,
    pair: dict[str, pd.DataFrame],
    variant: str,
    *,
    adverse_cents: float = 0.0,
    entry_delay_minutes: int = 0,
) -> dict[str, Any] | None:
    direction, score, relays = signal_for(pair, variant)
    if direction == 0:
        return None
    symbol = "UPRO" if direction > 0 else "SPXU"
    quotes = pair.get(symbol)
    if quotes is None:
        return None
    entry_stamp = stamp(day, ENTRY, quotes.index.tz) + timedelta(
        minutes=entry_delay_minutes
    )
    exit_stamp = stamp(day, EXIT, quotes.index.tz)
    entry = base.quote_at(quotes, entry_stamp, 0)
    exit_quote = base.quote_at(quotes, exit_stamp, 0)
    if entry is None or exit_quote is None:
        return None
    entry_ask = float(entry.ask_px_00) + adverse_cents
    exit_bid = float(exit_quote.bid_px_00) - adverse_cents
    if entry_ask <= 0 or exit_bid <= 0:
        return None
    realized = exit_bid / entry_ask - 1.0
    midpoint = (float(entry.bid_px_00) + float(entry.ask_px_00)) / 2.0
    return {
        "date": day,
        "symbol": symbol,
        "direction": "bullish" if direction > 0 else "bearish",
        "score": score,
        "relays": relays,
        "entry_time": entry_stamp,
        "exit_time": exit_stamp,
        "entry_bid": float(entry.bid_px_00),
        "entry_ask": entry_ask,
        "exit_bid": exit_bid,
        "exit_ask": float(exit_quote.ask_px_00),
        "entry_spread_bps": (
            (float(entry.ask_px_00) - float(entry.bid_px_00))
            / midpoint
            * 10_000.0
        ),
        "return": realized,
        "pnl_usd": 100.0 * realized,
    }


def make_rows(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
    variant: str = "actual",
    *,
    adverse_cents: float = 0.0,
    entry_delay_minutes: int = 0,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for day in sorted(sessions):
        if day in excluded or not start <= day <= end:
            continue
        row = trade_row(
            day,
            sessions[day],
            variant,
            adverse_cents=adverse_cents,
            entry_delay_minutes=entry_delay_minutes,
        )
        if row is not None:
            rows.append(row)
    return rows


def summarize(
    rows: list[dict[str, Any]],
    remove_best: int,
) -> dict[str, Any]:
    result = common.summarize(rows, remove_best=remove_best)
    if rows:
        result["median_entry_spread_bps"] = float(
            pd.Series([row["entry_spread_bps"] for row in rows]).median()
        )
        result["median_relay_count"] = float(
            pd.Series([row["relays"] for row in rows]).median()
        )
    return result


def development_gate(
    observed: dict[str, Any],
    extra_cent: dict[str, Any],
    delayed: dict[str, Any],
    spy: dict[str, Any],
    flipped: dict[str, Any],
    unconfirmed: dict[str, Any],
) -> dict[str, bool]:
    years = observed.get("year_pnl_usd", {})
    instruments = observed.get("instrument_pnl_usd", {})
    return {
        "minimum_two_trades_per_week": observed["trades_per_week"] >= 2.0,
        "profit_factor_strictly_above_one": observed["profit_factor"] > 1.0,
        "each_development_year_positive": all(
            years.get(str(year), 0.0) > 0 for year in [2021, 2022, 2023]
        ),
        "both_upro_and_spxu_positive": all(
            instruments.get(symbol, 0.0) > 0 for symbol in ["UPRO", "SPXU"]
        ),
        "ending_cash_above_spy": (
            observed["ending_cash_usd"] > spy["ending_cash_usd"]
        ),
        "positive_after_one_extra_cent_each_fill": (
            extra_cent["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_five_minute_entry_delay": (
            delayed["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_removing_ten_best_sessions": (
            observed["pnl_without_best_10_sessions_usd"] > 0
        ),
        "outperform_sign_flipped_placebo": (
            observed["fixed_notional_pnl_usd"]
            > flipped["fixed_notional_pnl_usd"]
        ),
        "outperform_unconfirmed_event_sign_placebo": (
            observed["fixed_notional_pnl_usd"]
            > unconfirmed["fixed_notional_pnl_usd"]
        ),
    }


def evaluate_development(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
) -> dict[str, Any]:
    observed_rows = make_rows(
        sessions, excluded, START, DEVELOPMENT_END, "actual"
    )
    extra_rows = make_rows(
        sessions,
        excluded,
        START,
        DEVELOPMENT_END,
        "actual",
        adverse_cents=0.01,
    )
    delayed_rows = make_rows(
        sessions,
        excluded,
        START,
        DEVELOPMENT_END,
        "actual",
        entry_delay_minutes=5,
    )
    flipped_rows = make_rows(
        sessions, excluded, START, DEVELOPMENT_END, "flipped"
    )
    unconfirmed_rows = make_rows(
        sessions, excluded, START, DEVELOPMENT_END, "unconfirmed"
    )
    observed = summarize(observed_rows, 10)
    extra = summarize(extra_rows, 10)
    delayed = summarize(delayed_rows, 10)
    flipped = summarize(flipped_rows, 10)
    unconfirmed = summarize(unconfirmed_rows, 10)
    spy = common.spy_hurdle(
        spy_sessions,
        excluded,
        START,
        DEVELOPMENT_END,
    )
    gate = development_gate(
        observed,
        extra,
        delayed,
        spy,
        flipped,
        unconfirmed,
    )
    return {
        "observed_bbo": observed,
        "one_extra_cent_each_fill": extra,
        "five_minute_entry_delay": delayed,
        "sign_flipped_placebo": flipped,
        "unconfirmed_all_event_sign_placebo": unconfirmed,
        "spy_price_only_hurdle": spy,
        "gate": gate,
        "gate_passed": all(gate.values()),
    }


def evaluate_period(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
    remove_best: int,
) -> dict[str, Any]:
    observed_rows = make_rows(sessions, excluded, start, end)
    extra_rows = make_rows(
        sessions,
        excluded,
        start,
        end,
        adverse_cents=0.01,
    )
    delayed_rows = make_rows(
        sessions,
        excluded,
        start,
        end,
        entry_delay_minutes=5,
    )
    return {
        "observed_bbo": summarize(observed_rows, remove_best),
        "one_extra_cent_each_fill": summarize(extra_rows, remove_best),
        "five_minute_entry_delay": summarize(delayed_rows, remove_best),
        "spy_price_only_hurdle": common.spy_hurdle(
            spy_sessions,
            excluded,
            start,
            end,
        ),
    }


def holdout_gate(
    holdout: dict[str, Any],
    consolidated: dict[str, Any],
) -> dict[str, bool]:
    observed = holdout["observed_bbo"]
    years = observed.get("year_pnl_usd", {})
    instruments = observed.get("instrument_pnl_usd", {})
    return {
        "each_holdout_year_positive": all(
            years.get(str(year), 0.0) > 0 for year in [2024, 2025]
        ),
        "both_upro_and_spxu_positive": all(
            instruments.get(symbol, 0.0) > 0 for symbol in ["UPRO", "SPXU"]
        ),
        "ending_cash_above_spy": (
            observed["ending_cash_usd"]
            > holdout["spy_price_only_hurdle"]["ending_cash_usd"]
        ),
        "positive_after_one_extra_cent_each_fill": (
            holdout["one_extra_cent_each_fill"]["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_removing_five_best_sessions": (
            observed["pnl_without_best_5_sessions_usd"] > 0
        ),
        "consolidated_holdout_positive": (
            consolidated["observed_bbo"]["fixed_notional_pnl_usd"] > 0
        ),
    }


def load_old() -> tuple[
    dict[pd.Timestamp, pd.DataFrame],
    dict[pd.Timestamp, dict[str, pd.DataFrame]],
    dict[pd.Timestamp, dict[str, pd.DataFrame]],
    set[pd.Timestamp],
    set[pd.Timestamp],
]:
    spy = base.split_sessions(base.load_dbn(analog.OLD_SPY, "SPY"))
    arca = audit.sessions(audit.ARCA_PATH)
    equs = audit.sessions(audit.EQUS_PATH)
    arca_excluded = audit.degraded(audit.ARCA_CONDITIONS)
    equs_excluded = audit.degraded(audit.EQUS_CONDITIONS)
    return spy, arca, equs, arca_excluded, equs_excluded


def load_extension() -> tuple[
    dict[pd.Timestamp, pd.DataFrame],
    dict[pd.Timestamp, dict[str, pd.DataFrame]],
    set[pd.Timestamp],
]:
    bars = base.load_dbn(analog.NEW_BARS)
    spy = base.split_sessions(bars[bars.symbol == "SPY"])
    frame = base.load_dbn(analog.NEW_BBO)
    pair: dict[pd.Timestamp, dict[str, pd.DataFrame]] = {}
    for symbol in ["UPRO", "SPXU"]:
        selected = frame[frame.symbol == symbol]
        for day, quotes in base.split_sessions(selected).items():
            pair.setdefault(day, {})[symbol] = quotes
    excluded = audit.degraded(analog.NEW_CONDITIONS)
    return spy, pair, excluded


def money(value: float) -> str:
    return f"${value:,.2f}"


def period_table(name: str, result: dict[str, Any]) -> list[str]:
    observed = result["observed_bbo"]
    spy = result["spy_price_only_hurdle"]
    return [
        f"## {name}",
        "",
        "| Trades/week | Ending cash | Fixed-$100 P&L | PF | SPY |",
        "|---:|---:|---:|---:|---:|",
        (
            f"| {observed['trades_per_week']:.2f} | "
            f"{money(observed['ending_cash_usd'])} | "
            f"{money(observed['fixed_notional_pnl_usd'])} | "
            f"{observed['profit_factor']:.3f} | "
            f"{money(spy['ending_cash_usd'])} |"
        ),
        "",
    ]


def render_report(payload: dict[str, Any]) -> str:
    dev = payload["development"]
    lines = [
        "# UPRO/SPXU Cross-Inverse Aggressor Relay v16",
        "",
        "## Verdict",
        "",
    ]
    if not dev["gate_passed"]:
        lines.extend(
            [
                "**Rejected in development. The 2024–2025 return holdout remains locked.**",
                "",
            ]
        )
    elif not payload["holdout"]["gate_passed"]:
        lines.extend(
            [
                "**Rejected on the untouched rule-specific holdout.**",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "**The frozen rule passed the historical gates but remains "
                "paper-only pending genuinely prospective validation.**",
                "",
            ]
        )
    lines.extend(period_table("Development: 2021–2023", dev))
    lines.extend(
        [
            "Development stress and identification:",
            "",
            (
                "- One extra cent per share at both fills: "
                f"{money(dev['one_extra_cent_each_fill']['fixed_notional_pnl_usd'])}."
            ),
            (
                "- Five-minute entry delay: "
                f"{money(dev['five_minute_entry_delay']['fixed_notional_pnl_usd'])}."
            ),
            (
                "- Sign-flipped placebo: "
                f"{money(dev['sign_flipped_placebo']['fixed_notional_pnl_usd'])}."
            ),
            (
                "- Unconfirmed event-sign placebo: "
                f"{money(dev['unconfirmed_all_event_sign_placebo']['fixed_notional_pnl_usd'])}."
            ),
            (
                "- Result without ten best sessions: "
                f"{money(dev['observed_bbo']['pnl_without_best_10_sessions_usd'])}."
            ),
            "",
            "Development gate failures:",
            "",
        ]
    )
    failures = [name for name, passed in dev["gate"].items() if not passed]
    lines.append(
        "- " + (", ".join(name.replace("_", " ") for name in failures) or "None")
    )
    lines.append("")
    if dev["gate_passed"]:
        lines.extend(period_table("Secondary holdout: 2024–2025", payload["holdout"]))
        lines.extend(period_table("Full 2021–2025", payload["full_2021_2025"]))
        lines.extend(period_table("2026 diagnostic extension", payload["extension_2026"]))
        holdout_failures = [
            name
            for name, passed in payload["holdout"]["gate"].items()
            if not passed
        ]
        lines.extend(
            [
                "Holdout gate failures:",
                "",
                "- "
                + (
                    ", ".join(
                        name.replace("_", " ") for name in holdout_failures
                    )
                    or "None"
                ),
                "",
                (
                    "EQUS.MINI holdout rebuild P&L: "
                    f"{money(payload['consolidated_holdout']['observed_bbo']['fixed_notional_pnl_usd'])}."
                ),
                "",
            ]
        )
    lines.extend(
        [
            "The returns-blind signal audit passed, but cross-feed score "
            "correlation was only 0.251 and remains an identification warning.",
            "",
            "No threshold, clock, sign, stop, or direction was repaired after "
            "outcomes.",
            "",
            "Preimplementation critique: "
            "`research_scout/UPRO_SPXU_CROSS_INVERSE_AGGRESSOR_RELAY_PREIMPLEMENTATION_CRITIQUE_V16.md`.",
            "",
            "Machine-readable results: "
            "`research_scout/upro_spxu_cross_inverse_aggressor_relay_results_v16.json`.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    if not PREREG.exists():
        raise FileNotFoundError("Preregistration is required before execution")
    spy, arca, equs, arca_excluded, equs_excluded = load_old()
    development = evaluate_development(arca, spy, arca_excluded)
    payload: dict[str, Any] = {
        "specification": str(PREREG.relative_to(ROOT)).replace("\\", "/"),
        "status": (
            "development_survivor"
            if development["gate_passed"]
            else "rejected_in_development_holdout_locked"
        ),
        "development": development,
        "holdout_return_status": (
            "unlocked" if development["gate_passed"] else "not_calculated"
        ),
    }
    if development["gate_passed"]:
        holdout = evaluate_period(
            arca,
            spy,
            arca_excluded,
            HOLDOUT_START,
            HOLDOUT_END,
            5,
        )
        consolidated_holdout = evaluate_period(
            equs,
            spy,
            equs_excluded,
            HOLDOUT_START,
            HOLDOUT_END,
            5,
        )
        holdout["gate"] = holdout_gate(holdout, consolidated_holdout)
        holdout["gate_passed"] = all(holdout["gate"].values())
        full = evaluate_period(
            arca,
            spy,
            arca_excluded,
            START,
            HOLDOUT_END,
            10,
        )
        extension_spy, extension_pair, extension_excluded = load_extension()
        extension = evaluate_period(
            extension_pair,
            extension_spy,
            extension_excluded,
            EXTENSION_START,
            EXTENSION_END,
            5,
        )
        payload.update(
            {
                "status": (
                    "historical_survivor_requires_forward_validation"
                    if holdout["gate_passed"]
                    else "rejected_on_secondary_holdout"
                ),
                "holdout": holdout,
                "consolidated_holdout": consolidated_holdout,
                "full_2021_2025": full,
                "extension_2026": extension,
            }
        )
    OUTPUT.write_text(
        json.dumps(payload, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    REPORT.write_text(render_report(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
