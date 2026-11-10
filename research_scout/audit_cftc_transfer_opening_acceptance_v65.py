"""Returns-blind audit of CFTC relative transfer plus ES opening acceptance.

This module may read CFTC fields, session calendars, prices through the
completed 09:34 bar (09:35 for the later adjacent diagnostic), and the exact
09:36 entry quote solely for availability. It must not inspect any later price,
strategy return, or 2024-2025 outcome.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import pandas as pd  # noqa: E402

from research_scout import (  # noqa: E402
    audit_proshares_primary_market_flows_v60 as flowlib,
)
from research_scout import (  # noqa: E402
    audit_upro_spxu_cross_inverse_aggressor_relay as relay,
)
from research_scout import (  # noqa: E402
    audit_upro_spxu_premarket_wrapper_premium as v19,
)
from research_scout import test_es_auction_polarity_transfer as eslib  # noqa: E402
from research_scout import test_upro_spxu_creative_hypotheses as base  # noqa: E402

CFTC_ROOT = ROOT / "external_artifacts" / "cftc_tff_futures_only"
OUTPUT = (
    ROOT
    / "research_scout"
    / "cftc_transfer_opening_acceptance_returns_blind_audit_v65.json"
)
REPORT = (
    ROOT
    / "research_scout"
    / "CFTC_TRANSFER_OPENING_ACCEPTANCE_AUDIT_V65.md"
)

MARKET_NAME = "S&P 500 Consolidated - CHICAGO MERCANTILE EXCHANGE"
MARKET_CODE = "13874+"
PRIMARY_END = "09:34"
ADJACENT_ENDS = {
    "four_minute": "09:33",
    "six_minute": "09:35",
}
ENTRY_CLOCK = "09:36"
YEARS = (2021, 2022, 2023)


def sign(value: float) -> int:
    return int(value > 0) - int(value < 0)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_cftc() -> tuple[pd.DataFrame, dict[str, Any]]:
    frames: list[pd.DataFrame] = []
    hashes: dict[str, str] = {}
    for year in YEARS:
        archive = CFTC_ROOT / f"fut_fin_txt_{year}.zip"
        source = CFTC_ROOT / f"fut_fin_txt_{year}" / "FinFutYY.txt"
        hashes[archive.name] = sha256(archive)
        frame = pd.read_csv(source, low_memory=False)
        frame["archive_year"] = year
        frames.append(frame)
    raw = pd.concat(frames, ignore_index=True)
    selected = raw[
        (raw["Market_and_Exchange_Names"].astype(str).str.strip() == MARKET_NAME)
        & (
            raw["CFTC_Contract_Market_Code"].astype(str).str.strip()
            == MARKET_CODE
        )
        & (raw["FutOnly_or_Combined"].astype(str).str.strip() == "FutOnly")
    ].copy()
    selected["report_date"] = pd.to_datetime(
        selected["Report_Date_as_YYYY-MM-DD"], errors="coerce"
    ).dt.normalize()
    numeric = [
        "Change_in_Asset_Mgr_Long_All",
        "Change_in_Asset_Mgr_Short_All",
        "Change_in_Lev_Money_Long_All",
        "Change_in_Lev_Money_Short_All",
    ]
    for column in numeric:
        selected[column] = pd.to_numeric(selected[column], errors="coerce")
    selected["asset_manager_net_change"] = (
        selected["Change_in_Asset_Mgr_Long_All"]
        - selected["Change_in_Asset_Mgr_Short_All"]
    )
    selected["leveraged_fund_net_change"] = (
        selected["Change_in_Lev_Money_Long_All"]
        - selected["Change_in_Lev_Money_Short_All"]
    )
    selected["relative_transfer"] = (
        selected["asset_manager_net_change"]
        - selected["leveraged_fund_net_change"]
    )
    selected["direction"] = selected["relative_transfer"].map(sign)
    selected["asset_manager_direction"] = selected[
        "asset_manager_net_change"
    ].map(sign)
    selected["leveraged_fund_direction"] = selected[
        "leveraged_fund_net_change"
    ].map(sign)
    selected["strict_collision"] = (
        selected["asset_manager_direction"]
        == -selected["leveraged_fund_direction"]
    ) & (selected["asset_manager_direction"] != 0)
    selected["safe_available_date"] = (
        selected["report_date"] + pd.Timedelta(days=7)
    )
    selected = selected.sort_values("report_date").reset_index(drop=True)

    duplicate_dates = int(selected["report_date"].duplicated(keep=False).sum())
    missing_numeric = int(selected[numeric].isna().any(axis=1).sum())
    year_counts = {
        str(year): int((selected["report_date"].dt.year == year).sum())
        for year in YEARS
    }
    integrity = {
        "market_name": MARKET_NAME,
        "market_code": MARKET_CODE,
        "rows": int(len(selected)),
        "records_by_year": year_counts,
        "duplicate_report_date_rows": duplicate_dates,
        "rows_missing_required_changes": missing_numeric,
        "archive_sha256": hashes,
    }
    if duplicate_dates or missing_numeric:
        raise RuntimeError(f"CFTC integrity failure: {integrity}")
    return selected, integrity


def source_states(
    expected: pd.DatetimeIndex, reports: pd.DataFrame
) -> dict[pd.Timestamp, dict[str, Any]]:
    states: dict[pd.Timestamp, dict[str, Any]] = {}
    available = reports["safe_available_date"].to_numpy()
    for raw_day in expected:
        day = pd.Timestamp(raw_day).normalize()
        index = int(available.searchsorted(day.to_datetime64(), side="right")) - 1
        if index < 0:
            continue
        row = reports.iloc[index]
        if int(row["direction"]) == 0:
            continue
        states[day] = {
            "report_date": pd.Timestamp(row["report_date"]).normalize(),
            "safe_available_date": pd.Timestamp(
                row["safe_available_date"]
            ).normalize(),
            "direction": int(row["direction"]),
            "relative_transfer": float(row["relative_transfer"]),
            "asset_manager_net_change": float(
                row["asset_manager_net_change"]
            ),
            "leveraged_fund_net_change": float(
                row["leveraged_fund_net_change"]
            ),
            "strict_collision": bool(row["strict_collision"]),
        }
    return states


def clock_stamp(
    day: pd.Timestamp, clock: str, timezone: Any
) -> pd.Timestamp:
    hour, minute = (int(item) for item in clock.split(":"))
    return (
        day.tz_localize(timezone)
        + pd.Timedelta(hours=hour, minutes=minute)
    )


def opening_direction(
    frame: pd.DataFrame | None, day: pd.Timestamp, end_clock: str
) -> int | None:
    if frame is None or frame.empty:
        return None
    opening = base.exact_row(
        frame, clock_stamp(day, "09:30", frame.index.tz)
    )
    terminal = base.exact_row(
        frame, clock_stamp(day, end_clock, frame.index.tz)
    )
    if opening is None or terminal is None:
        return None
    start = float(opening["open"])
    end = float(terminal["close"])
    if (
        not math.isfinite(start)
        or not math.isfinite(end)
        or start <= 0
        or end <= 0
    ):
        return None
    return sign(end - start)


def build_actions(
    expected: pd.DatetimeIndex,
    cot: dict[pd.Timestamp, dict[str, Any]],
    market: dict[pd.Timestamp, pd.DataFrame],
    end_clock: str,
) -> dict[pd.Timestamp, dict[str, Any]]:
    result: dict[pd.Timestamp, dict[str, Any]] = {}
    for raw_day in expected:
        day = pd.Timestamp(raw_day).normalize()
        if day not in cot:
            continue
        fast_direction = opening_direction(market.get(day), day, end_clock)
        if fast_direction is None:
            continue
        slow_direction = int(cot[day]["direction"])
        action = (
            "UPRO"
            if fast_direction == slow_direction == 1
            else "SPXU"
            if fast_direction == slow_direction == -1
            else "CASH"
        )
        result[day] = {
            **cot[day],
            "fast_direction": fast_direction,
            "action": action,
            "es_only_action": (
                "UPRO"
                if fast_direction > 0
                else "SPXU"
                if fast_direction < 0
                else "CASH"
            ),
            "cot_only_action": "UPRO" if slow_direction > 0 else "SPXU",
        }
    return result


def action_agreement(
    left: dict[pd.Timestamp, dict[str, Any]],
    right: dict[pd.Timestamp, dict[str, Any]] | dict[pd.Timestamp, str],
    *,
    right_field: str = "action",
) -> dict[str, Any]:
    overlap = sorted(set(left).intersection(right))
    matches = 0
    for day in overlap:
        right_value = right[day]
        action = (
            str(right_value[right_field])
            if isinstance(right_value, dict)
            else str(right_value)
        )
        matches += str(left[day]["action"]) == action
    return {
        "overlap": len(overlap),
        "identical_actions": matches,
        "identical_action_including_cash": matches / max(len(overlap), 1),
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
            frame, clock_stamp(day, ENTRY_CLOCK, frame.index.tz)
        )
        if base.valid_quote(quote):
            available += 1
    return {
        "signals": len(signals),
        "available": available,
        "coverage": available / max(len(signals), 1),
    }


def render(payload: dict[str, Any]) -> str:
    development = payload["development_2021_2023"]
    failures = [
        name for name, passed in payload["gates"].items() if not passed
    ]
    verdict = (
        "**All returns-blind gates passed. Formal preregistration and the "
        "single frozen 2021–2023 P&L test are allowed; recent years remain "
        "locked.**"
        if payload["gate_passed"]
        else "**Rejected returns-blind. No strategy P&L was opened.**"
    )
    lines = [
        "# CFTC Relative-Transfer / ES Opening Acceptance Audit v65",
        "",
        "## Verdict",
        "",
        verdict,
        "",
        "## Frozen state",
        "",
        "- Slow direction: sign of Asset Manager net-position change minus "
        "Leveraged Fund net-position change in the CFTC S&P 500 Consolidated "
        "futures-only report.",
        "- Availability: Tuesday report plus seven calendar days.",
        "- Fast confirmation: completed ES 09:30–09:34 move in the same "
        "direction.",
        "- Prospective entry: exact 09:36 UPRO/SPXU quote.",
        "",
        "## Reachability",
        "",
        f"- Expected cash sessions: {development['expected_sessions']}",
        f"- Eligible states: {development['eligible_sessions']} "
        f"({development['eligible_coverage']:.3%})",
        f"- Signals: {development['signals']} "
        f"({development['signals_per_week']:.3f}/week)",
        f"- UPRO / SPXU: {development['upro_signals']} / "
        f"{development['spxu_signals']}",
        "- Signals by year: "
        + ", ".join(
            f"{year}={count}"
            for year, count in development["signals_by_year"].items()
        ),
        "- CFTC direction switches by year: "
        + ", ".join(
            f"{year}={count}"
            for year, count in payload[
                "cftc_state_diagnostics"
            ]["direction_switches_by_year"].items()
        ),
        f"- Strict Asset Manager / Leveraged Fund collision reports: "
        f"{payload['cftc_state_diagnostics']['strict_collision_reports']} "
        f"({payload['cftc_state_diagnostics']['strict_collision_share']:.3%})",
        "",
        "## Robustness before returns",
        "",
    ]
    for name, item in payload["adjacent_opening_stability"].items():
        lines.append(
            f"- {name}: "
            f"{item['identical_action_including_cash']:.3%} action agreement"
        )
    lines.extend(
        [
            f"- Independent 2023 SPY proxy action agreement: "
            f"{payload['independent_spy_proxy_2023']['identical_action_including_cash']:.3%}",
            f"- Agreement with ES-only opening momentum: "
            f"{payload['distinctness']['es_only_opening_momentum']['identical_action_including_cash']:.3%}",
            f"- Agreement with COT-only direction: "
            f"{payload['distinctness']['cot_only_direction']['identical_action_including_cash']:.3%}",
            f"- Primary 09:36 quote coverage: "
            f"{payload['entry_quote_evidence']['primary']['coverage']:.3%}",
            f"- Independent quote coverage: "
            f"{payload['entry_quote_evidence']['independent']['coverage']:.3%}",
            "",
            "## Gates",
            "",
        ]
    )
    lines.extend(
        f"- {name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in payload["gates"].items()
    )
    lines.extend(
        [
            "",
            "Failed gates: " + (", ".join(failures) if failures else "none"),
            "",
            "No post-09:36 price, entry value, exit value, strategy return, "
            "or 2024–2025 outcome was read.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    expected = flowlib.load_spy_sessions()
    reports, integrity = load_cftc()
    cot = source_states(expected, reports)

    es_sessions = {
        pd.Timestamp(day).normalize(): frame
        for day, frame in eslib.load_development_sessions()
    }
    primary = build_actions(expected, cot, es_sessions, PRIMARY_END)
    adjacent = {
        name: build_actions(expected, cot, es_sessions, end_clock)
        for name, end_clock in ADJACENT_ENDS.items()
    }
    adjacent_stability = {
        name: action_agreement(primary, states)
        for name, states in adjacent.items()
    }

    spy_equs = v19.spy_sessions(v19.EQUS_SPY)
    spy_proxy = build_actions(expected, cot, spy_equs, PRIMARY_END)
    spy_proxy = {
        day: row for day, row in spy_proxy.items() if day.year == 2023
    }
    primary_2023 = {
        day: row for day, row in primary.items() if day.year == 2023
    }
    independent_spy = action_agreement(primary_2023, spy_proxy)

    es_only = {
        day: str(row["es_only_action"]) for day, row in primary.items()
    }
    cot_only = {
        day: str(row["cot_only_action"]) for day, row in primary.items()
    }
    distinctness = {
        "es_only_opening_momentum": action_agreement(primary, es_only),
        "cot_only_direction": action_agreement(primary, cot_only),
    }

    arca_pair = relay.sessions(relay.ARCA_PATH)
    equs_pair = relay.sessions(relay.EQUS_PATH)
    arca_excluded = relay.degraded(relay.ARCA_CONDITIONS)
    equs_excluded = relay.degraded(relay.EQUS_CONDITIONS)
    quote_evidence = {
        "primary": quote_coverage(primary, arca_pair, arca_excluded),
        "independent": quote_coverage(
            primary_2023, equs_pair, equs_excluded
        ),
    }

    signals = {
        day: row for day, row in primary.items() if row["action"] != "CASH"
    }
    counts = Counter(str(row["action"]) for row in signals.values())
    signals_by_year = {
        str(year): sum(day.year == year for day in signals) for year in YEARS
    }
    minority = (
        min(counts["UPRO"], counts["SPXU"]) / max(len(signals), 1)
    )
    development = {
        "expected_sessions": len(expected),
        "eligible_sessions": len(primary),
        "eligible_coverage": len(primary) / max(len(expected), 1),
        "signals": len(signals),
        "signals_per_week": len(signals) / (len(expected) / 5.0),
        "upro_signals": counts["UPRO"],
        "spxu_signals": counts["SPXU"],
        "minority_actuator_share": minority,
        "signals_by_year": signals_by_year,
    }

    switches: dict[str, int] = {}
    for year in YEARS:
        values = reports.loc[
            reports["report_date"].dt.year == year, "direction"
        ].astype(int)
        switches[str(year)] = int((values != values.shift(1)).iloc[1:].sum())
    cftc_diagnostics = {
        "direction_switches_by_year": switches,
        "strict_collision_reports": int(reports["strict_collision"].sum()),
        "strict_collision_share": float(reports["strict_collision"].mean()),
        "relative_transfer_zero_reports": int((reports["direction"] == 0).sum()),
    }

    gates = {
        "source_at_least_50_reports_each_year": all(
            integrity["records_by_year"][str(year)] >= 50 for year in YEARS
        ),
        "source_unique_and_complete_required_fields": (
            integrity["duplicate_report_date_rows"] == 0
            and integrity["rows_missing_required_changes"] == 0
        ),
        "eligible_coverage_at_least_90_percent": (
            development["eligible_coverage"] >= 0.90
        ),
        "at_least_two_signals_per_week": (
            development["signals_per_week"] >= 2.0
        ),
        "at_least_90_signals_each_year": all(
            signals_by_year[str(year)] >= 90 for year in YEARS
        ),
        "minority_actuator_share_at_least_30_percent": minority >= 0.30,
        "at_least_15_state_switches_each_year": all(
            switches[str(year)] >= 15 for year in YEARS
        ),
        "primary_entry_quote_coverage_at_least_90_percent": (
            quote_evidence["primary"]["coverage"] >= 0.90
        ),
        "four_minute_action_stability_at_least_75_percent": (
            adjacent_stability["four_minute"][
                "identical_action_including_cash"
            ]
            >= 0.75
        ),
        "six_minute_action_stability_at_least_75_percent": (
            adjacent_stability["six_minute"][
                "identical_action_including_cash"
            ]
            >= 0.75
        ),
        "independent_spy_proxy_agreement_at_least_85_percent": (
            independent_spy["identical_action_including_cash"] >= 0.85
        ),
        "es_only_control_agreement_below_80_percent": (
            distinctness["es_only_opening_momentum"][
                "identical_action_including_cash"
            ]
            < 0.80
        ),
        "cot_only_control_agreement_below_80_percent": (
            distinctness["cot_only_direction"][
                "identical_action_including_cash"
            ]
            < 0.80
        ),
    }

    payload = {
        "status": "returns_blind_no_post_entry_returns_read",
        "returns_read": False,
        "recent_years_read": False,
        "source_integrity": integrity,
        "availability_rule": "report_date_plus_7_calendar_days",
        "development_2021_2023": development,
        "cftc_state_diagnostics": cftc_diagnostics,
        "adjacent_opening_stability": adjacent_stability,
        "independent_spy_proxy_2023": independent_spy,
        "distinctness": distinctness,
        "entry_quote_evidence": quote_evidence,
        "gates": gates,
        "gate_passed": all(gates.values()),
    }
    OUTPUT.write_text(
        json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8"
    )
    REPORT.write_text(render(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
