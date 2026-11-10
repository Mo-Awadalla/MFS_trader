"""Evaluate preregistered cross-inverse signed-impact asymmetry."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import (
    audit_upro_spxu_cross_inverse_aggressor_relay as relay,
)
from research_scout import audit_upro_spxu_signed_impact_asymmetry as impact
from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16
from research_scout import test_upro_spxu_variance_state as common

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "research_scout" / "upro_spxu_signed_impact_asymmetry_prereg_v18.json"
OUTPUT = ROOT / "research_scout" / "upro_spxu_signed_impact_asymmetry_results_v18.json"
REPORT = ROOT / "research_scout" / "UPRO_SPXU_SIGNED_IMPACT_ASYMMETRY_REPORT_V18.md"


def raw_direction(pair: dict[str, pd.DataFrame]) -> int:
    if not {"UPRO", "SPXU"}.issubset(pair):
        return 0
    events = relay.fresh_events("UPRO", pair["UPRO"])
    events.extend(relay.fresh_events("SPXU", pair["SPXU"]))
    score = sum(event.underlying_sign for event in events)
    return int(score > 0) - int(score < 0)


def signal_for(
    pair: dict[str, pd.DataFrame],
    variant: str,
) -> tuple[int, float]:
    state = impact.session_signal(pair)
    if state is None:
        return 0, 0.0
    actual = int(state["direction"])
    if variant == "actual":
        return actual, float(state["score"])
    if variant == "flipped":
        return -actual, -float(state["score"])
    if variant == "raw":
        return raw_direction(pair), 0.0
    raise ValueError(f"Unknown variant: {variant}")


def trade_row(
    day: pd.Timestamp,
    pair: dict[str, pd.DataFrame],
    variant: str,
    *,
    adverse_cents: float = 0.0,
    entry_delay_minutes: int = 0,
) -> dict[str, Any] | None:
    direction, score = signal_for(pair, variant)
    if direction == 0:
        return None
    symbol = "UPRO" if direction > 0 else "SPXU"
    quotes = pair.get(symbol)
    if quotes is None:
        return None
    entry_stamp = v16.stamp(day, v16.ENTRY, quotes.index.tz) + timedelta(
        minutes=entry_delay_minutes
    )
    exit_stamp = v16.stamp(day, v16.EXIT, quotes.index.tz)
    entry = base.quote_at(quotes, entry_stamp, 0)
    exit_quote = base.quote_at(quotes, exit_stamp, 0)
    if entry is None or exit_quote is None:
        return None
    entry_ask = float(entry.ask_px_00) + adverse_cents
    exit_bid = float(exit_quote.bid_px_00) - adverse_cents
    if min(entry_ask, exit_bid) <= 0:
        return None
    realized = exit_bid / entry_ask - 1.0
    midpoint = (float(entry.bid_px_00) + float(entry.ask_px_00)) / 2.0
    return {
        "date": day,
        "symbol": symbol,
        "direction": "bullish" if direction > 0 else "bearish",
        "score": score,
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


def summarized(
    rows: list[dict[str, Any]],
    remove_best: int,
) -> dict[str, Any]:
    result = common.summarize(rows, remove_best=remove_best)
    if rows:
        result["median_entry_spread_bps"] = float(
            pd.Series([row["entry_spread_bps"] for row in rows]).median()
        )
    return result


def development(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    spy: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
) -> dict[str, Any]:
    arguments = (sessions, excluded, v16.START, v16.DEVELOPMENT_END)
    observed = summarized(make_rows(*arguments), 10)
    extra = summarized(make_rows(*arguments, adverse_cents=0.01), 10)
    delayed = summarized(make_rows(*arguments, entry_delay_minutes=5), 10)
    flipped = summarized(make_rows(*arguments, variant="flipped"), 10)
    raw = summarized(make_rows(*arguments, variant="raw"), 10)
    spy_hurdle = common.spy_hurdle(
        spy,
        excluded,
        v16.START,
        v16.DEVELOPMENT_END,
    )
    gate = v16.development_gate(
        observed,
        extra,
        delayed,
        spy_hurdle,
        flipped,
        raw,
    )
    return {
        "observed_bbo": observed,
        "one_extra_cent_each_fill": extra,
        "five_minute_entry_delay": delayed,
        "sign_flipped_placebo": flipped,
        "raw_aggressor_count_placebo": raw,
        "spy_price_only_hurdle": spy_hurdle,
        "gate": gate,
        "gate_passed": all(gate.values()),
    }


def period(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    spy: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
    remove_best: int,
) -> dict[str, Any]:
    arguments = (sessions, excluded, start, end)
    return {
        "observed_bbo": summarized(make_rows(*arguments), remove_best),
        "one_extra_cent_each_fill": summarized(
            make_rows(*arguments, adverse_cents=0.01),
            remove_best,
        ),
        "five_minute_entry_delay": summarized(
            make_rows(*arguments, entry_delay_minutes=5),
            remove_best,
        ),
        "spy_price_only_hurdle": common.spy_hurdle(
            spy,
            excluded,
            start,
            end,
        ),
    }


def money(value: float) -> str:
    return f"${value:,.2f}"


def summary_line(label: str, result: dict[str, Any]) -> str:
    observed = result["observed_bbo"]
    spy = result["spy_price_only_hurdle"]
    return (
        f"| {label} | {observed['trades_per_week']:.2f} | "
        f"{money(observed['ending_cash_usd'])} | "
        f"{money(observed['fixed_notional_pnl_usd'])} | "
        f"{observed['profit_factor']:.3f} | "
        f"{money(spy['ending_cash_usd'])} |"
    )


def render(payload: dict[str, Any]) -> str:
    dev = payload["development"]
    if not dev["gate_passed"]:
        verdict = "**Rejected in development; 2024–2026 returns remain locked.**"
    elif not payload["holdout"]["gate_passed"]:
        verdict = "**Rejected on the untouched 2024–2025 holdout.**"
    else:
        verdict = (
            "**Historical survivor only; forward paper validation remains "
            "mandatory.**"
        )
    lines = [
        "# UPRO/SPXU Cross-Inverse Signed-Impact Asymmetry v18",
        "",
        "## Verdict",
        "",
        verdict,
        "",
        "| Period | Trades/week | Ending cash | Fixed-$100 P&L | PF | SPY |",
        "|---|---:|---:|---:|---:|---:|",
        summary_line("Development 2021–2023", dev),
    ]
    if dev["gate_passed"]:
        lines.extend(
            [
                summary_line("Holdout 2024–2025", payload["holdout"]),
                summary_line("Full 2021–2025", payload["full_2021_2025"]),
                summary_line("2026 diagnostic", payload["extension_2026"]),
            ]
        )
    lines.extend(
        [
            "",
            "## Development stress",
            "",
            (
                "- Extra cent at both fills: "
                f"{money(dev['one_extra_cent_each_fill']['fixed_notional_pnl_usd'])}"
            ),
            (
                "- Five-minute delay: "
                f"{money(dev['five_minute_entry_delay']['fixed_notional_pnl_usd'])}"
            ),
            (
                "- Without ten best sessions: "
                f"{money(dev['observed_bbo']['pnl_without_best_10_sessions_usd'])}"
            ),
            (
                "- Sign-flipped placebo: "
                f"{money(dev['sign_flipped_placebo']['fixed_notional_pnl_usd'])}"
            ),
            (
                "- Raw aggressor-count placebo: "
                f"{money(dev['raw_aggressor_count_placebo']['fixed_notional_pnl_usd'])}"
            ),
            "",
            "Development failures: "
            + (
                ", ".join(
                    name.replace("_", " ")
                    for name, passed in dev["gate"].items()
                    if not passed
                )
                or "none"
            )
            + ".",
            "",
        ]
    )
    if dev["gate_passed"]:
        lines.extend(
            [
                "Holdout failures: "
                + (
                    ", ".join(
                        name.replace("_", " ")
                        for name, passed in payload["holdout"]["gate"].items()
                        if not passed
                    )
                    or "none"
                )
                + ".",
                "",
                (
                    "EQUS.MINI holdout rebuild: "
                    f"{money(payload['consolidated_holdout']['observed_bbo']['fixed_notional_pnl_usd'])}."
                ),
                "",
            ]
        )
    lines.extend(
        [
            "No outcome-driven repair was made.",
            "",
            "Machine-readable results: "
            "`research_scout/upro_spxu_signed_impact_asymmetry_results_v18.json`.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    if not PREREG.exists():
        raise FileNotFoundError("Missing preregistration")
    spy, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    dev = development(arca, spy, arca_excluded)
    payload: dict[str, Any] = {
        "specification": str(PREREG.relative_to(ROOT)).replace("\\", "/"),
        "status": (
            "development_survivor"
            if dev["gate_passed"]
            else "rejected_in_development_holdout_locked"
        ),
        "development": dev,
        "holdout_return_status": (
            "unlocked" if dev["gate_passed"] else "not_calculated"
        ),
    }
    if dev["gate_passed"]:
        holdout = period(
            arca,
            spy,
            arca_excluded,
            v16.HOLDOUT_START,
            v16.HOLDOUT_END,
            5,
        )
        consolidated = period(
            equs,
            spy,
            equs_excluded,
            v16.HOLDOUT_START,
            v16.HOLDOUT_END,
            5,
        )
        holdout["gate"] = v16.holdout_gate(holdout, consolidated)
        holdout["gate_passed"] = all(holdout["gate"].values())
        full = period(
            arca,
            spy,
            arca_excluded,
            v16.START,
            v16.HOLDOUT_END,
            10,
        )
        extension_spy, extension_pair, extension_excluded = v16.load_extension()
        extension = period(
            extension_pair,
            extension_spy,
            extension_excluded,
            v16.EXTENSION_START,
            v16.EXTENSION_END,
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
                "consolidated_holdout": consolidated,
                "full_2021_2025": full,
                "extension_2026": extension,
            }
        )
    OUTPUT.write_text(
        json.dumps(payload, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    REPORT.write_text(render(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
