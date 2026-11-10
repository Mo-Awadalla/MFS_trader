"""Returns-blind audit of Treasury dealer dollar-years overhang v66."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from bisect import bisect_right
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import pandas as pd  # noqa: E402

from research_scout import audit_cftc_transfer_opening_acceptance_v65 as v65  # noqa: E402
from research_scout import audit_proshares_primary_market_flows_v60 as flowlib  # noqa: E402
from research_scout import audit_spy_ief_joint_macro_impulse_v56 as v56  # noqa: E402
from research_scout import audit_spy_ief_shy_duration_impulse_v58 as v58  # noqa: E402
from research_scout import audit_spy_vx_curve_confirmation_failure_v46 as v46  # noqa: E402
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay  # noqa: E402
from research_scout import test_upro_spxu_creative_hypotheses as base  # noqa: E402

SOURCE = (
    ROOT
    / "external_artifacts"
    / "treasury_auction_results"
    / "auctions_2020_2023.json"
)
OUTPUT = (
    ROOT
    / "research_scout"
    / "treasury_dealer_dollar_years_returns_blind_audit_v66.json"
)
REPORT = (
    ROOT
    / "research_scout"
    / "TREASURY_DEALER_DOLLAR_YEARS_AUDIT_V66.md"
)

START = pd.Timestamp("2021-01-01")
END = pd.Timestamp("2023-12-31")
ENTRY_CLOCK = "09:33"
YEARS = (2021, 2022, 2023)


def sign(value: float) -> int:
    return int(value > 0) - int(value < 0)


def source_sha256() -> str:
    return hashlib.sha256(SOURCE.read_bytes()).hexdigest()


def clean_string(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().replace({"null": ""})


def load_auctions() -> tuple[pd.DataFrame, dict[str, Any]]:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    frame = pd.DataFrame(payload["data"]).copy()
    frame["auction_date"] = pd.to_datetime(
        frame["auction_date"], errors="coerce"
    ).dt.normalize()
    frame["issue_date"] = pd.to_datetime(
        frame["issue_date"], errors="coerce"
    ).dt.normalize()
    frame["maturity_date"] = pd.to_datetime(
        frame["maturity_date"], errors="coerce"
    ).dt.normalize()
    for column in (
        "comp_accepted",
        "primary_dealer_accepted",
    ):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in (
        "security_type",
        "security_term",
        "floating_rate",
        "inflation_index_security",
        "closing_time_comp",
    ):
        frame[column] = clean_string(frame[column])
    frame["bucket"] = (
        frame["security_type"]
        + "|"
        + frame["security_term"]
        + "|FRN="
        + frame["floating_rate"]
        + "|TIPS="
        + frame["inflation_index_security"]
    )
    frame["dealer_share"] = (
        frame["primary_dealer_accepted"] / frame["comp_accepted"]
    )
    raw_year = frame["auction_date"].dt.year
    required_valid = (
        frame["auction_date"].notna()
        & frame["issue_date"].notna()
        & frame["maturity_date"].notna()
        & frame["comp_accepted"].notna()
        & (frame["comp_accepted"] > 0)
        & frame["primary_dealer_accepted"].notna()
        & (frame["primary_dealer_accepted"] >= 0)
        & frame["security_type"].ne("")
        & frame["security_term"].ne("")
    )
    dev_mask = raw_year.isin(YEARS)
    valid_fraction = float(required_valid[dev_mask].mean())
    frame = frame[required_valid].copy()
    frame["years_to_maturity"] = (
        (frame["maturity_date"] - frame["issue_date"]).dt.days / 365.25
    )
    frame.loc[
        frame["floating_rate"].str.casefold() == "yes",
        "years_to_maturity",
    ] = 0.25
    frame = frame[
        frame["years_to_maturity"].notna()
        & (frame["years_to_maturity"] > 0)
    ].sort_values(["bucket", "auction_date", "cusip"])
    frame["prior_dealer_share"] = frame.groupby(
        "bucket", sort=False
    )["dealer_share"].shift(1)
    frame["dealer_share_change"] = (
        frame["dealer_share"] - frame["prior_dealer_share"]
    )
    frame["shock_dollar_years"] = (
        frame["dealer_share_change"]
        * frame["comp_accepted"]
        * frame["years_to_maturity"]
    )
    frame["shock_notional_only"] = (
        frame["dealer_share_change"] * frame["comp_accepted"]
    )
    fixed_coupon = (
        frame["security_type"].isin(["Note", "Bond"])
        & (frame["floating_rate"].str.casefold() != "yes")
    )
    frame["shock_fixed_coupon"] = frame["shock_dollar_years"].where(
        fixed_coupon, 0.0
    )
    integrity = {
        "source_sha256": source_sha256(),
        "api_meta_total_count": int(payload["meta"]["total-count"]),
        "local_rows": int(len(payload["data"])),
        "required_valid_fraction_2021_2023": valid_fraction,
        "valid_rows_after_maturity_check": int(len(frame)),
        "auction_rows_by_year": {
            str(year): int((frame["auction_date"].dt.year == year).sum())
            for year in YEARS
        },
        "distinct_auction_dates_by_year": {
            str(year): int(
                frame.loc[
                    frame["auction_date"].dt.year == year, "auction_date"
                ].nunique()
            )
            for year in YEARS
        },
    }
    return frame, integrity


def aggregate_auction_days(frame: pd.DataFrame) -> pd.DataFrame:
    usable = frame[
        frame["auction_date"].between(START, END)
        & frame["dealer_share_change"].notna()
    ].copy()
    return (
        usable.groupby("auction_date", sort=True)
        .agg(
            shock_dollar_years=("shock_dollar_years", "sum"),
            shock_notional_only=("shock_notional_only", "sum"),
            shock_fixed_coupon=("shock_fixed_coupon", "sum"),
            auction_rows=("cusip", "size"),
        )
        .reset_index()
    )


def next_session(
    day: pd.Timestamp, expected: list[pd.Timestamp]
) -> pd.Timestamp | None:
    index = bisect_right(expected, pd.Timestamp(day).normalize())
    return expected[index] if index < len(expected) else None


def build_states(
    daily: pd.DataFrame, expected_index: pd.DatetimeIndex
) -> dict[pd.Timestamp, dict[str, Any]]:
    expected = [pd.Timestamp(day).normalize() for day in expected_index]
    mapped: dict[pd.Timestamp, dict[str, Any]] = {}
    for row in daily.itertuples(index=False):
        trade_day = next_session(pd.Timestamp(row.auction_date), expected)
        if trade_day is None or not START <= trade_day <= END:
            continue
        state = mapped.setdefault(
            trade_day,
            {
                "source_auction_dates": [],
                "shock_dollar_years": 0.0,
                "shock_notional_only": 0.0,
                "shock_fixed_coupon": 0.0,
                "auction_rows": 0,
            },
        )
        state["source_auction_dates"].append(
            pd.Timestamp(row.auction_date).normalize()
        )
        state["shock_dollar_years"] += float(row.shock_dollar_years)
        state["shock_notional_only"] += float(row.shock_notional_only)
        state["shock_fixed_coupon"] += float(row.shock_fixed_coupon)
        state["auction_rows"] += int(row.auction_rows)
    for row in mapped.values():
        direction = -sign(float(row["shock_dollar_years"]))
        notional_direction = -sign(float(row["shock_notional_only"]))
        coupon_direction = -sign(float(row["shock_fixed_coupon"]))
        row["direction"] = direction
        row["action"] = (
            "UPRO"
            if direction > 0
            else "SPXU"
            if direction < 0
            else "CASH"
        )
        row["notional_action"] = (
            "UPRO"
            if notional_direction > 0
            else "SPXU"
            if notional_direction < 0
            else "CASH"
        )
        row["coupon_action"] = (
            "UPRO"
            if coupon_direction > 0
            else "SPXU"
            if coupon_direction < 0
            else "CASH"
        )
    return mapped


def compare_actions(
    states: dict[pd.Timestamp, dict[str, Any]],
    control: dict[pd.Timestamp, str] | None = None,
    *,
    field: str = "action",
    conditional_control_nonzero: bool = False,
) -> dict[str, Any]:
    if control is None:
        days = sorted(states)
    else:
        days = sorted(set(states).intersection(control))
    if conditional_control_nonzero:
        days = [
            day
            for day in days
            if str(
                states[day][field] if control is None else control[day]
            )
            != "CASH"
        ]
    matches = 0
    for day in days:
        target = (
            str(states[day][field])
            if control is None
            else str(control[day])
        )
        matches += str(states[day]["action"]) == target
    return {
        "overlap": len(days),
        "identical_actions": matches,
        "identical_action_including_cash": matches / max(len(days), 1),
    }


def quote_coverage(
    states: dict[pd.Timestamp, dict[str, Any]],
    quotes: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
) -> dict[str, Any]:
    signals = {
        day: row
        for day, row in states.items()
        if row["action"] != "CASH" and day not in excluded
    }
    available = 0
    for day, row in signals.items():
        frame = quotes.get(day, {}).get(str(row["action"]))
        if frame is None:
            continue
        quote = base.exact_row(
            frame, v65.clock_stamp(day, ENTRY_CLOCK, frame.index.tz)
        )
        available += base.valid_quote(quote)
    return {
        "signals": len(signals),
        "available": available,
        "coverage": available / max(len(signals), 1),
    }


def prior_spy_actions(
    expected: pd.DatetimeIndex,
) -> dict[pd.Timestamp, str]:
    close = v56.load_daily(
        v58.YAHOO / "SPY_1d.parquet"
    ).sort_index()
    returns = close.pct_change(fill_method=None)
    next_map = {
        pd.Timestamp(expected[index]).normalize(): pd.Timestamp(
            expected[index + 1]
        ).normalize()
        for index in range(len(expected) - 1)
    }
    actions: dict[pd.Timestamp, str] = {}
    for signal_day, value in returns.items():
        signal_day = pd.Timestamp(signal_day).normalize()
        trade_day = next_map.get(signal_day)
        direction = sign(float(value)) if math.isfinite(float(value)) else 0
        if trade_day is not None:
            actions[trade_day] = (
                "UPRO"
                if direction > 0
                else "SPXU"
                if direction < 0
                else "CASH"
            )
    return actions


def v58_actions(
    expected: pd.DatetimeIndex,
) -> dict[pd.Timestamp, str]:
    states = v58.build_states(
        v56.load_daily(v58.YAHOO / "IEF_1d.parquet"),
        v56.load_daily(v58.YAHOO / "SHY_1d.parquet"),
    )
    next_map = {
        pd.Timestamp(expected[index]).normalize(): pd.Timestamp(
            expected[index + 1]
        ).normalize()
        for index in range(len(expected) - 1)
    }
    actions: dict[pd.Timestamp, str] = {}
    for signal_day, row in states.items():
        trade_day = next_map.get(pd.Timestamp(signal_day).normalize())
        if trade_day is None:
            continue
        direction = int(row["direction"])
        actions[trade_day] = (
            "UPRO"
            if direction > 0
            else "SPXU"
            if direction < 0
            else "CASH"
        )
    return actions


def render(payload: dict[str, Any]) -> str:
    development = payload["development_2021_2023"]
    failures = [
        name for name, passed in payload["gates"].items() if not passed
    ]
    lines = [
        "# Treasury Dealer Dollar-Years Audit v66",
        "",
        "## Verdict",
        "",
        (
            "**All returns-blind gates passed. Formal preregistration and a "
            "single frozen development P&L test are allowed.**"
            if payload["gate_passed"]
            else "**Rejected returns-blind. No strategy P&L was opened.**"
        ),
        "",
        "## Reachability",
        "",
        f"- Valid mapped event sessions: "
        f"{development['mapped_event_sessions']}",
        f"- Signals: {development['signals']} "
        f"({development['signals_per_week']:.3f}/week)",
        f"- UPRO / SPXU: {development['upro_signals']} / "
        f"{development['spxu_signals']}",
        "- Signals by year: "
        + ", ".join(
            f"{year}={count}"
            for year, count in development["signals_by_year"].items()
        ),
        f"- Valid auction-date mapping coverage: "
        f"{development['auction_date_mapping_coverage']:.3%}",
        "",
        "## Feature diagnostics",
        "",
        f"- Largest bucket absolute contribution: "
        f"{payload['feature_concentration']['largest_bucket_share']:.3%} "
        f"({payload['feature_concentration']['largest_bucket']})",
        f"- Bill absolute contribution: "
        f"{payload['feature_concentration']['security_type_shares'].get('Bill', 0.0):.3%}",
        f"- Notional-only agreement: "
        f"{payload['weighting_stability']['notional_only']['identical_action_including_cash']:.3%}",
        f"- Coupon-only conditional agreement: "
        f"{payload['weighting_stability']['fixed_coupon_conditional']['identical_action_including_cash']:.3%}",
        f"- Prior-SPY agreement: "
        f"{payload['distinctness']['prior_spy_direction']['identical_action_including_cash']:.3%}",
        f"- Rejected-v58 agreement: "
        f"{payload['distinctness']['v58_duration_impulse']['identical_action_including_cash']:.3%}",
        f"- Primary 09:33 quote coverage: "
        f"{payload['entry_quote_evidence']['primary']['coverage']:.3%}",
        f"- Independent 09:33 quote coverage: "
        f"{payload['entry_quote_evidence']['independent']['coverage']:.3%}",
        "",
        "## Gates",
        "",
    ]
    lines.extend(
        f"- {name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in payload["gates"].items()
    )
    lines.extend(
        [
            "",
            "Failed gates: " + (", ".join(failures) if failures else "none"),
            "",
            "No post-09:33 price, strategy P&L, or 2024–2025 outcome was read.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    expected = flowlib.load_spy_sessions()
    auctions, integrity = load_auctions()
    daily = aggregate_auction_days(auctions)
    states = build_states(daily, expected)
    signals = {
        day: row for day, row in states.items() if row["action"] != "CASH"
    }
    counts = Counter(str(row["action"]) for row in signals.values())
    signals_by_year = {
        str(year): sum(day.year == year for day in signals) for year in YEARS
    }
    source_dates = {
        date
        for row in states.values()
        for date in row["source_auction_dates"]
    }
    eligible_auction_dates = set(daily["auction_date"])
    mapping_coverage = len(source_dates) / max(len(eligible_auction_dates), 1)
    minority = min(counts["UPRO"], counts["SPXU"]) / max(len(signals), 1)
    ordered_actions = pd.Series(
        {day: row["action"] for day, row in sorted(signals.items())}
    )
    switches = {
        str(year): int(
            (
                ordered_actions[
                    ordered_actions.index.map(lambda day: day.year) == year
                ]
                != ordered_actions[
                    ordered_actions.index.map(lambda day: day.year) == year
                ].shift(1)
            )
            .iloc[1:]
            .sum()
        )
        for year in YEARS
    }
    development = {
        "expected_cash_sessions": len(expected),
        "eligible_auction_dates": len(eligible_auction_dates),
        "mapped_source_auction_dates": len(source_dates),
        "auction_date_mapping_coverage": mapping_coverage,
        "mapped_event_sessions": len(states),
        "signals": len(signals),
        "signals_per_week": len(signals) / (len(expected) / 5.0),
        "upro_signals": counts["UPRO"],
        "spxu_signals": counts["SPXU"],
        "minority_actuator_share": minority,
        "signals_by_year": signals_by_year,
        "direction_switches_by_year": switches,
    }

    usable = auctions[
        auctions["auction_date"].between(START, END)
        & auctions["shock_dollar_years"].notna()
    ].copy()
    bucket_abs = usable.groupby("bucket")["shock_dollar_years"].apply(
        lambda values: float(values.abs().sum())
    )
    type_abs = usable.groupby("security_type")["shock_dollar_years"].apply(
        lambda values: float(values.abs().sum())
    )
    total_abs = float(bucket_abs.sum())
    largest_bucket = str(bucket_abs.idxmax())
    concentration = {
        "largest_bucket": largest_bucket,
        "largest_bucket_share": float(bucket_abs.max() / total_abs),
        "security_type_shares": {
            str(name): float(value / total_abs)
            for name, value in type_abs.items()
        },
    }

    weighting = {
        "notional_only": compare_actions(states, field="notional_action"),
        "fixed_coupon_conditional": compare_actions(
            states,
            field="coupon_action",
            conditional_control_nonzero=True,
        ),
    }
    distinctness = {
        "prior_spy_direction": compare_actions(
            states, prior_spy_actions(expected)
        ),
        "v58_duration_impulse": compare_actions(
            states, v58_actions(expected)
        ),
    }

    arca = relay.sessions(relay.ARCA_PATH)
    equs = relay.sessions(relay.EQUS_PATH)
    arca_excluded = relay.degraded(relay.ARCA_CONDITIONS)
    equs_excluded = relay.degraded(relay.EQUS_CONDITIONS)
    primary_quotes = quote_coverage(states, arca, arca_excluded)
    states_2023 = {
        day: row for day, row in states.items() if day.year == 2023
    }
    independent_quotes = quote_coverage(
        states_2023, equs, equs_excluded
    )

    gates = {
        "required_source_fields_valid_at_least_95_percent": integrity[
            "required_valid_fraction_2021_2023"
        ]
        >= 0.95,
        "auction_date_mapping_coverage_at_least_90_percent": (
            mapping_coverage >= 0.90
        ),
        "at_least_two_signals_per_week": (
            development["signals_per_week"] >= 2.0
        ),
        "at_least_90_signals_each_year": all(
            signals_by_year[str(year)] >= 90 for year in YEARS
        ),
        "minority_actuator_share_at_least_35_percent": minority >= 0.35,
        "at_least_20_direction_switches_each_year": all(
            switches[str(year)] >= 20 for year in YEARS
        ),
        "largest_bucket_below_50_percent_absolute_shock": (
            concentration["largest_bucket_share"] < 0.50
        ),
        "notional_only_action_agreement_at_least_70_percent": weighting[
            "notional_only"
        ]["identical_action_including_cash"]
        >= 0.70,
        "coupon_only_conditional_agreement_at_least_70_percent": weighting[
            "fixed_coupon_conditional"
        ]["identical_action_including_cash"]
        >= 0.70,
        "primary_entry_quote_coverage_at_least_90_percent": (
            primary_quotes["coverage"] >= 0.90
        ),
        "prior_spy_action_agreement_below_80_percent": distinctness[
            "prior_spy_direction"
        ]["identical_action_including_cash"]
        < 0.80,
        "v58_action_agreement_below_80_percent": distinctness[
            "v58_duration_impulse"
        ]["identical_action_including_cash"]
        < 0.80,
    }
    payload = {
        "status": "returns_blind_no_post_entry_returns_read",
        "returns_read": False,
        "recent_years_read": False,
        "source_integrity": integrity,
        "development_2021_2023": development,
        "feature_concentration": concentration,
        "weighting_stability": weighting,
        "distinctness": distinctness,
        "entry_quote_evidence": {
            "primary": primary_quotes,
            "independent": independent_quotes,
        },
        "strict_causality": all(
            source_date < trade_day
            for trade_day, row in states.items()
            for source_date in row["source_auction_dates"]
        ),
        "gates": gates,
        "gate_passed": all(gates.values()),
    }
    OUTPUT.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    REPORT.write_text(render(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
