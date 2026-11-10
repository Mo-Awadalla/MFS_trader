"""Returns-blind audit of settling-CUSIP collateral scarcity v72."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import pandas as pd  # noqa: E402

from research_scout import audit_treasury_dealer_dollar_years_v66 as v66  # noqa: E402
from research_scout import audit_treasury_settlement_rrp_liquidity_netting_v71 as v71  # noqa: E402
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay  # noqa: E402
from research_scout import test_upro_spxu_creative_hypotheses as base  # noqa: E402

LENDING = {
    year: ROOT
    / "external_artifacts"
    / "nyfed_securities_lending"
    / f"seclending_details_{year}.csv"
    for year in (2021, 2022, 2023)
}
OUTPUT = (
    ROOT
    / "research_scout"
    / "settling_cusip_collateral_scarcity_returns_blind_audit_v72.json"
)
REPORT = (
    ROOT
    / "research_scout"
    / "SETTLING_CUSIP_COLLATERAL_SCARCITY_AUDIT_V72.md"
)
START = pd.Timestamp("2021-01-01")
END = pd.Timestamp("2023-12-31")
YEARS = (2021, 2022, 2023)
ENTRY = "12:20"
EXIT = "15:30"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def clean_cusip(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.strip("'").str.upper()


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False).str.replace("$", "", regex=False),
        errors="coerce",
    )


def sign(value: float) -> int:
    return int(value > 0) - int(value < 0)


def action(value: float) -> str:
    return "SPXU" if value > 0 else "UPRO" if value < 0 else "CASH"


def load_lending() -> tuple[pd.DataFrame, dict[str, Any]]:
    parts = []
    hashes = {}
    for year, path in LENDING.items():
        frame = pd.read_csv(path, low_memory=False)
        frame["source_year"] = year
        parts.append(frame)
        hashes[str(year)] = sha256(path)
    frame = pd.concat(parts, ignore_index=True)
    frame["operation_date"] = pd.to_datetime(
        frame["Operation Date"], errors="coerce"
    ).dt.normalize()
    frame["settlement_date"] = pd.to_datetime(
        frame["Settlement Date"], errors="coerce"
    ).dt.normalize()
    frame["last_updated"] = pd.to_datetime(frame["Last Updated"], errors="coerce")
    frame["cusip"] = clean_cusip(frame["CUSIP"])
    for source, target in (
        ("Par Amt Submitted", "submitted"),
        ("Par Amt Accepted", "accepted"),
        ("Actual Available To Borrow", "actual_available"),
        ("Weighted Average Rate", "weighted_rate"),
    ):
        frame[target] = numeric(frame[source])
    required = (
        frame["operation_date"].notna()
        & frame["settlement_date"].notna()
        & frame["last_updated"].notna()
        & frame["cusip"].str.len().eq(9)
        & frame["submitted"].notna()
        & (frame["submitted"] >= 0)
        & frame["accepted"].notna()
        & (frame["accepted"] >= 0)
        & frame["actual_available"].notna()
        & (frame["actual_available"] > 0)
        & frame["weighted_rate"].notna()
    )
    valid_fraction = float(required.mean())
    frame = frame[required].copy()
    entry_cutoff = frame["operation_date"] + pd.Timedelta(hours=12, minutes=20)
    after_entry_rows = int((frame["last_updated"] >= entry_cutoff).sum())
    frame = frame[frame["last_updated"] < entry_cutoff].copy()
    duplicates = int(frame.duplicated(["operation_date", "cusip"], keep=False).sum())
    if duplicates:
        raise RuntimeError(f"Duplicate operation-date/CUSIP rows: {duplicates}")
    frame = frame.sort_values(["cusip", "operation_date"]).copy()
    frame["demand_pressure"] = frame["submitted"] / frame["actual_available"]
    frame["accepted_utilization"] = frame["accepted"] / frame["actual_available"]
    grouped = frame.groupby("cusip", sort=False)
    frame["prior_operation_date"] = grouped["operation_date"].shift(1)
    frame["prior_demand_pressure"] = grouped["demand_pressure"].shift(1)
    frame["prior2_demand_pressure"] = grouped["demand_pressure"].shift(2)
    frame["prior_accepted_utilization"] = grouped["accepted_utilization"].shift(1)
    frame["demand_change"] = frame["demand_pressure"] - frame["prior_demand_pressure"]
    frame["prior_demand_change"] = (
        frame["prior_demand_pressure"] - frame["prior2_demand_pressure"]
    )
    frame["accepted_change"] = (
        frame["accepted_utilization"] - frame["prior_accepted_utilization"]
    )
    frame["release_clock"] = pd.to_datetime(
        frame["Release Time"], format="%I:%M %p", errors="coerce"
    ).dt.strftime("%H:%M")
    frame["close_clock"] = pd.to_datetime(
        frame["Close Time"], format="%I:%M %p", errors="coerce"
    ).dt.strftime("%H:%M")
    integrity = {
        "sha256": hashes,
        "raw_rows": int(sum(len(part) for part in parts)),
        "valid_rows": int(len(frame)),
        "required_valid_fraction": valid_fraction,
        "rows_excluded_as_published_at_or_after_entry": after_entry_rows,
        "duplicate_operation_date_cusip_rows": duplicates,
        "operation_days": int(frame["operation_date"].nunique()),
    }
    return frame, integrity


def load_settling_auctions() -> tuple[pd.DataFrame, dict[str, Any]]:
    auctions, integrity = v66.load_auctions()
    auctions = auctions[auctions["issue_date"].between(START, END)].copy()
    auctions["cusip"] = clean_cusip(auctions["cusip"])
    auctions["security_bucket"] = auctions["security_type"].astype(str)
    return auctions, integrity


def build_states() -> tuple[dict[pd.Timestamp, dict[str, Any]], dict[str, Any]]:
    lending, lending_integrity = load_lending()
    auctions, auction_integrity = load_settling_auctions()
    event_keys = auctions[
        ["issue_date", "cusip", "security_bucket"]
    ].drop_duplicates()
    matched = event_keys.merge(
        lending,
        left_on=["issue_date", "cusip"],
        right_on=["operation_date", "cusip"],
        how="inner",
        validate="one_to_one",
    )
    matched = matched[
        matched["prior_operation_date"].notna()
        & (matched["prior_operation_date"] < matched["operation_date"])
        & matched["demand_change"].notna()
        & matched["accepted_change"].notna()
    ].copy()
    matched_keys = set(zip(matched["operation_date"], matched["cusip"]))
    nonsettling = lending[
        lending["demand_change"].notna()
        & ~pd.Series(
            list(zip(lending["operation_date"], lending["cusip"])),
            index=lending.index,
        ).isin(matched_keys)
    ].copy()
    common = nonsettling.groupby("operation_date", sort=False).agg(
        common_demand_change=("demand_change", "median"),
        common_accepted_change=("accepted_change", "median"),
        nonsettling_cusips=("cusip", "size"),
    )
    matched = matched.join(common, on="operation_date", how="inner")
    matched["residual_change"] = (
        matched["demand_change"] - matched["common_demand_change"]
    )
    matched["accepted_residual_change"] = (
        matched["accepted_change"] - matched["common_accepted_change"]
    )
    states: dict[pd.Timestamp, dict[str, Any]] = {}
    contributions: dict[str, defaultdict[str, float]] = {
        "bucket": defaultdict(float),
        "cusip": defaultdict(float),
    }
    for day, group in matched.groupby("operation_date", sort=True):
        score = float(group["residual_change"].sum())
        raw_score = float(group["demand_change"].sum())
        accepted_score = float(group["accepted_residual_change"].sum())
        for row in group.itertuples(index=False):
            magnitude = abs(float(row.residual_change))
            contributions["bucket"][str(row.security_bucket)] += magnitude
            contributions["cusip"][str(row.cusip)] += magnitude
        states[pd.Timestamp(day).normalize()] = {
            "session_date": pd.Timestamp(day).strftime("%Y-%m-%d"),
            "settling_cusips": int(len(group)),
            "cusips": sorted(group["cusip"].astype(str).tolist()),
            "security_buckets": sorted(group["security_bucket"].astype(str).unique().tolist()),
            "latest_prior_operation_date": group["prior_operation_date"].max().strftime("%Y-%m-%d"),
            "latest_result_update": group["last_updated"].max().strftime("%Y-%m-%d %H:%M:%S"),
            "minimum_nonsettling_cusips": int(group["nonsettling_cusips"].min()),
            "settlement_scarcity": score,
            "raw_matched_sum": raw_score,
            "accepted_scarcity": accepted_score,
            "median_abs_current_cusip_change": float(group["demand_change"].abs().median()),
            "median_abs_prior_cusip_change": float(group["prior_demand_change"].abs().median())
            if group["prior_demand_change"].notna().any()
            else None,
            "action": action(score),
            "raw_action": action(raw_score),
            "accepted_action": action(accepted_score),
        }
    source = {
        "lending": lending_integrity,
        "auction": auction_integrity,
        "auction_issue_dates": int(event_keys["issue_date"].nunique()),
        "matched_rows_with_strict_prior": int(len(matched)),
        "matched_issue_dates_with_strict_prior": int(len(states)),
        "release_clocks": sorted(lending["release_clock"].dropna().unique().tolist()),
        "close_clocks": sorted(lending["close_clock"].dropna().unique().tolist()),
        "maximum_last_updated_clock": lending["last_updated"].dt.strftime("%H:%M:%S").max(),
        "contributions": {
            kind: dict(values) for kind, values in contributions.items()
        },
    }
    return states, source


def agreement(
    states: dict[pd.Timestamp, dict[str, Any]], field: str
) -> dict[str, Any]:
    rows = [row for row in states.values() if row["action"] != "CASH"]
    same = sum(row["action"] == row[field] for row in rows)
    return {
        "overlap": len(rows),
        "identical": same,
        "agreement": same / max(len(rows), 1),
    }


def legacy_agreement(
    states: dict[pd.Timestamp, dict[str, Any]], legacy: dict[pd.Timestamp, str]
) -> dict[str, Any]:
    days = sorted(
        day for day in set(states).intersection(legacy)
        if states[day]["action"] != "CASH" and legacy[day] != "CASH"
    )
    same = sum(states[day]["action"] == legacy[day] for day in days)
    return {
        "overlap": len(days),
        "identical": same,
        "agreement": same / max(len(days), 1),
    }


def legacy_actions() -> tuple[dict[pd.Timestamp, str], dict[pd.Timestamp, str]]:
    auctions, _ = v66.load_auctions()
    v66_states = v66.build_states(
        v66.aggregate_auction_days(auctions), v66.flowlib.load_spy_sessions()
    )
    old66 = {day: row["action"] for day, row in v66_states.items()}
    v71_states, _ = v71.build_settlement_states()
    old71 = {day: row["action"] for day, row in v71_states.items()}
    return old66, old71


def quote_coverage(
    states: dict[pd.Timestamp, dict[str, Any]],
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
) -> dict[str, Any]:
    active = {
        day: row for day, row in states.items()
        if row["action"] != "CASH" and day not in excluded and day in sessions
    }
    valid = 0
    for day, row in active.items():
        frame = sessions.get(day, {}).get(row["action"])
        if frame is None:
            continue
        timezone = frame.index.tz
        entry = base.exact_row(frame, v66.v65.clock_stamp(day, ENTRY, timezone))
        exit_row = base.exact_row(frame, v66.v65.clock_stamp(day, EXIT, timezone))
        valid += int(base.valid_quote(entry) and base.valid_quote(exit_row))
    return {"active": len(active), "valid": valid, "coverage": valid / max(len(active), 1)}


def switches_by_year(states: dict[pd.Timestamp, dict[str, Any]]) -> dict[str, int]:
    result = {}
    for year in YEARS:
        actions = [
            states[day]["action"] for day in sorted(states)
            if day.year == year and states[day]["action"] != "CASH"
        ]
        result[str(year)] = sum(a != b for a, b in zip(actions, actions[1:]))
    return result


def maximum_share(values: dict[str, float]) -> tuple[float, str | None]:
    total = sum(values.values())
    if not values or total <= 0:
        return 0.0, None
    key = max(values, key=values.get)
    return values[key] / total, key


def render(payload: dict[str, Any]) -> str:
    dev = payload["development_2021_2023"]
    failures = [name for name, passed in payload["gates"].items() if not passed]
    verdict = (
        "**All returns-blind gates passed; frozen development P&L authorized.**"
        if payload["gate_passed"]
        else "**Rejected returns-blind before P&L.**"
    )
    return "\n".join(
        [
            "# Settling-CUSIP Collateral Scarcity Audit v72",
            "",
            verdict,
            "",
            f"- Signals: {dev['signals']} ({dev['signals_per_week']:.3f}/week)",
            f"- By year: {dev['by_year']}",
            f"- UPRO / SPXU: {dev['upro']} / {dev['spxu']}",
            f"- Event amplification: {payload['event_amplification_ratio']:.3f}x",
            f"- Accepted-utilization / raw-sum agreement: "
            f"{payload['agreement']['accepted']['agreement']:.3%} / "
            f"{payload['agreement']['raw']['agreement']:.3%}",
            f"- v66 / v71 agreement: {payload['agreement']['v66']['agreement']:.3%} / "
            f"{payload['agreement']['v71']['agreement']:.3%}",
            f"- Max bucket / CUSIP contribution: "
            f"{payload['concentration']['bucket']['share']:.3%} / "
            f"{payload['concentration']['cusip']['share']:.3%}",
            f"- Primary / independent quote coverage: "
            f"{payload['quotes']['primary']['coverage']:.3%} / "
            f"{payload['quotes']['independent']['coverage']:.3%}",
            "",
            "Failed gates: " + (", ".join(failures) if failures else "none"),
            "",
            "No post-entry return, P&L, or recent-year strategy outcome was calculated.",
            "",
        ]
    )


def main() -> None:
    states, source = build_states()
    counts = Counter(row["action"] for row in states.values())
    active_count = counts["UPRO"] + counts["SPXU"]
    by_year = {
        str(year): sum(
            day.year == year and row["action"] != "CASH"
            for day, row in states.items()
        )
        for year in YEARS
    }
    switches = switches_by_year(states)
    development = {
        "signals": active_count,
        "signals_per_week": active_count / (753 / 5),
        "by_year": by_year,
        "upro": counts["UPRO"],
        "spxu": counts["SPXU"],
        "cash": counts["CASH"],
        "minority_share": min(counts["UPRO"], counts["SPXU"]) / max(active_count, 1),
        "switches_by_year": switches,
    }
    old66, old71 = legacy_actions()
    agreements = {
        "accepted": agreement(states, "accepted_action"),
        "raw": agreement(states, "raw_action"),
        "v66": legacy_agreement(states, old66),
        "v71": legacy_agreement(states, old71),
    }
    current_abs = [
        row["median_abs_current_cusip_change"] for row in states.values()
        if row["median_abs_prior_cusip_change"] is not None
    ]
    prior_abs = [
        row["median_abs_prior_cusip_change"] for row in states.values()
        if row["median_abs_prior_cusip_change"] is not None
    ]
    event_amplification = (
        float(pd.Series(current_abs).median() / pd.Series(prior_abs).median())
        if prior_abs and pd.Series(prior_abs).median() > 0
        else 0.0
    )
    bucket_share, bucket_key = maximum_share(source["contributions"]["bucket"])
    cusip_share, cusip_key = maximum_share(source["contributions"]["cusip"])
    monthly = Counter(
        day.strftime("%Y-%m") for day, row in states.items() if row["action"] != "CASH"
    )
    max_month_share = max(monthly.values(), default=0) / max(active_count, 1)
    arca = relay.sessions(relay.ARCA_PATH)
    equs = relay.sessions(relay.EQUS_PATH)
    quotes = {
        "primary": quote_coverage(states, arca, relay.degraded(relay.ARCA_CONDITIONS)),
        "independent": quote_coverage(states, equs, relay.degraded(relay.EQUS_CONDITIONS)),
    }
    result_clocks_causal = (
        all(clock < "12:20" for clock in source["release_clocks"])
        and all(clock < "12:20" for clock in source["close_clocks"])
        and source["maximum_last_updated_clock"] < "12:20:00"
    )
    strict_prior = all(
        pd.Timestamp(row["latest_prior_operation_date"]) < day
        for day, row in states.items()
    )
    gates = {
        "source_required_fields_at_least_99_percent": source["lending"][
            "required_valid_fraction"
        ] >= 0.99,
        "unique_operation_date_cusip_rows": source["lending"][
            "duplicate_operation_date_cusip_rows"
        ] == 0,
        "at_least_2_signals_per_week": development["signals_per_week"] >= 2.0,
        "at_least_100_signals_each_year": min(by_year.values()) >= 100,
        "minority_action_at_least_30_percent": development["minority_share"] >= 0.30,
        "at_least_20_switches_each_year": min(switches.values()) >= 20,
        "strictly_prior_same_cusip_observation": strict_prior,
        "event_amplification_at_least_1_05": event_amplification >= 1.05,
        "accepted_utilization_agreement_at_least_70_percent": agreements[
            "accepted"
        ]["agreement"] >= 0.70,
        "raw_matched_sum_agreement_at_most_85_percent": agreements["raw"][
            "agreement"
        ] <= 0.85,
        "v66_agreement_at_most_80_percent": agreements["v66"]["agreement"] <= 0.80,
        "v71_agreement_at_most_80_percent": agreements["v71"]["agreement"] <= 0.80,
        "max_bucket_contribution_at_most_60_percent": bucket_share <= 0.60,
        "max_cusip_contribution_at_most_10_percent": cusip_share <= 0.10,
        "max_month_signal_share_at_most_6_percent": max_month_share <= 0.06,
        "operation_result_clocks_strictly_before_entry": result_clocks_causal,
        "primary_entry_exit_quotes_at_least_95_percent": quotes["primary"][
            "coverage"
        ] >= 0.95,
        "independent_entry_exit_quotes_at_least_90_percent": quotes["independent"][
            "coverage"
        ] >= 0.90,
        "no_post_entry_return_read": True,
    }
    source["contributions"].pop("bucket")
    source["contributions"].pop("cusip")
    payload = {
        "status": "returns_blind_v72_audit",
        "new_databento_calls_or_purchases": False,
        "free_external_source_added": "New York Fed securities-lending CUSIP-level results",
        "source_integrity": source,
        "development_2021_2023": development,
        "event_amplification_ratio": event_amplification,
        "agreement": agreements,
        "concentration": {
            "bucket": {"share": bucket_share, "largest": bucket_key},
            "cusip": {"share": cusip_share, "largest": cusip_key},
            "max_month_signal_share": max_month_share,
        },
        "quotes": quotes,
        "gates": gates,
        "gate_passed": all(gates.values()),
        "decision": (
            "authorize_frozen_development_pnl_only"
            if all(gates.values())
            else "reject_before_pnl"
        ),
        "states": [row for _, row in sorted(states.items())],
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(render(payload), encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items() if key != "states"}, indent=2))


if __name__ == "__main__":
    main()
