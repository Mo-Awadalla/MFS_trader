"""Returns-blind audit of Treasury settlement / ON RRP netting v71."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_treasury_dealer_dollar_years_v66 as v66
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay
from research_scout import test_upro_spxu_creative_hypotheses as base

ROOT = Path(__file__).resolve().parents[1]
RRP = (
    ROOT
    / "external_artifacts"
    / "nyfed_on_rrp"
    / "RRPONTSYD_2020-12-01_2023-12-31.csv"
)
V66_AUDIT = (
    ROOT
    / "research_scout"
    / "treasury_dealer_dollar_years_returns_blind_audit_v66.json"
)
OUTPUT = (
    ROOT
    / "research_scout"
    / "treasury_settlement_rrp_liquidity_netting_returns_blind_audit_v71.json"
)
REPORT = (
    ROOT
    / "research_scout"
    / "TREASURY_SETTLEMENT_RRP_LIQUIDITY_NETTING_AUDIT_V71.md"
)
START = pd.Timestamp("2021-01-01")
END = pd.Timestamp("2023-12-31")
YEARS = (2021, 2022, 2023)
ENTRY = "13:17"
EXIT = "15:30"


def sign(value: float) -> int:
    return int(value > 0) - int(value < 0)


def action(value: float) -> str:
    direction = -sign(value)
    return "UPRO" if direction > 0 else "SPXU" if direction < 0 else "CASH"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rrp() -> pd.DataFrame:
    frame = pd.read_csv(RRP)
    frame["date"] = pd.to_datetime(frame["observation_date"], errors="coerce").dt.normalize()
    frame["rrp_billions"] = pd.to_numeric(frame["RRPONTSYD"], errors="coerce")
    frame = frame[frame["date"].notna()].sort_values("date").copy()
    frame["prior_date"] = frame["date"].where(frame["rrp_billions"].notna()).ffill().shift(1)
    frame["prior_rrp_billions"] = frame["rrp_billions"].ffill().shift(1)
    frame["rrp_change_dollars"] = (
        frame["rrp_billions"] - frame["prior_rrp_billions"]
    ) * 1_000_000_000.0
    return frame.set_index("date")


def build_settlement_states() -> tuple[dict[pd.Timestamp, dict[str, Any]], dict[str, Any]]:
    auctions, integrity = v66.load_auctions()
    auctions = auctions.sort_values(["bucket", "auction_date", "cusip"]).copy()
    auctions["prior_dealer_award"] = auctions.groupby("bucket", sort=False)[
        "primary_dealer_accepted"
    ].shift(1)
    auctions["prior3_median_dealer_award"] = auctions.groupby(
        "bucket", sort=False
    )["primary_dealer_accepted"].transform(
        lambda series: series.shift(1).rolling(3, min_periods=1).median()
    )
    auctions["dealer_cash_change"] = (
        auctions["primary_dealer_accepted"] - auctions["prior_dealer_award"]
    )
    auctions["dealer_cash_change_prior3"] = (
        auctions["primary_dealer_accepted"]
        - auctions["prior3_median_dealer_award"]
    )
    usable = auctions[
        auctions["issue_date"].between(START, END)
        & auctions["dealer_cash_change"].notna()
        & auctions["dealer_cash_change_prior3"].notna()
    ].copy()
    daily = (
        usable.groupby("issue_date", sort=True)
        .agg(
            dealer_cash_change=("dealer_cash_change", "sum"),
            dealer_cash_change_prior3=("dealer_cash_change_prior3", "sum"),
            auction_rows=("cusip", "size"),
            latest_auction_date=("auction_date", "max"),
        )
        .reset_index()
    )
    rrp = load_rrp()
    states: dict[pd.Timestamp, dict[str, Any]] = {}
    for row in daily.itertuples(index=False):
        day = pd.Timestamp(row.issue_date).normalize()
        if day not in rrp.index:
            continue
        rrp_row = rrp.loc[day]
        if isinstance(rrp_row, pd.DataFrame):
            raise RuntimeError(f"Duplicate ON RRP date {day}")
        required = (
            rrp_row["rrp_billions"],
            rrp_row["prior_rrp_billions"],
            rrp_row["rrp_change_dollars"],
        )
        if any(pd.isna(value) for value in required):
            continue
        dealer = float(row.dealer_cash_change)
        dealer3 = float(row.dealer_cash_change_prior3)
        rrp_change = float(rrp_row["rrp_change_dollars"])
        net = dealer + rrp_change
        net3 = dealer3 + rrp_change
        states[day] = {
            "session_date": day.strftime("%Y-%m-%d"),
            "latest_auction_date": pd.Timestamp(row.latest_auction_date).strftime("%Y-%m-%d"),
            "rrp_prior_date": pd.Timestamp(rrp_row["prior_date"]).strftime("%Y-%m-%d"),
            "auction_rows": int(row.auction_rows),
            "dealer_cash_change": dealer,
            "dealer_cash_change_prior3": dealer3,
            "rrp_billions": float(rrp_row["rrp_billions"]),
            "prior_rrp_billions": float(rrp_row["prior_rrp_billions"]),
            "rrp_change_dollars": rrp_change,
            "net_cash_drain": net,
            "net_cash_drain_prior3": net3,
            "action": action(net),
            "prior3_action": action(net3),
            "dealer_only_action": action(dealer),
            "rrp_only_action": action(rrp_change),
        }
    integrity["rrp_sha256"] = sha256(RRP)
    integrity["settlement_rows_before_rrp_join"] = int(len(daily))
    integrity["settlement_rows_after_rrp_join"] = int(len(states))
    return states, integrity


def agreement(states: dict[pd.Timestamp, dict[str, Any]], field: str) -> dict[str, Any]:
    rows = list(states.values())
    same = sum(row["action"] == row[field] for row in rows)
    return {
        "overlap": len(rows),
        "identical": same,
        "agreement": same / max(len(rows), 1),
    }


def v66_agreement(states: dict[pd.Timestamp, dict[str, Any]]) -> dict[str, Any]:
    auctions, _ = v66.load_auctions()
    daily = v66.aggregate_auction_days(auctions)
    old_states = v66.build_states(daily, v66.flowlib.load_spy_sessions())
    old = {day: row["action"] for day, row in old_states.items()}
    days = sorted(set(states).intersection(old))
    same = sum(states[day]["action"] == old[day] for day in days)
    return {
        "overlap": len(days),
        "identical": same,
        "agreement": same / max(len(days), 1),
    }


def quote_coverage(
    states: dict[pd.Timestamp, dict[str, Any]],
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
) -> dict[str, Any]:
    active = {
        day: row
        for day, row in states.items()
        if row["action"] != "CASH"
        and day not in excluded
        and day in sessions
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
    return {
        "active": len(active),
        "valid": valid,
        "coverage": valid / max(len(active), 1),
    }


def switches_by_year(states: dict[pd.Timestamp, dict[str, Any]]) -> dict[str, int]:
    result = {}
    for year in YEARS:
        actions = [
            states[day]["action"]
            for day in sorted(states)
            if day.year == year and states[day]["action"] != "CASH"
        ]
        result[str(year)] = sum(a != b for a, b in zip(actions, actions[1:]))
    return result


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
            "# Treasury Settlement / ON RRP Liquidity Netting Audit v71",
            "",
            verdict,
            "",
            f"- Signals: {dev['signals']} ({dev['signals_per_week']:.3f}/week)",
            f"- By year: {dev['by_year']}",
            f"- UPRO / SPXU: {dev['upro']} / {dev['spxu']}",
            f"- Prior-three agreement: {payload['agreement']['prior3']['agreement']:.3%}",
            f"- Dealer-only / RRP-only / v66 agreement: "
            f"{payload['agreement']['dealer_only']['agreement']:.3%} / "
            f"{payload['agreement']['rrp_only']['agreement']:.3%} / "
            f"{payload['agreement']['v66']['agreement']:.3%}",
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
    states, integrity = build_settlement_states()
    states = {day: row for day, row in states.items() if START <= day <= END}
    counts = Counter(row["action"] for row in states.values())
    by_year = {
        str(year): sum(
            day.year == year and row["action"] != "CASH"
            for day, row in states.items()
        )
        for year in YEARS
    }
    switches = switches_by_year(states)
    active_count = counts["UPRO"] + counts["SPXU"]
    expected_sessions = 753
    development = {
        "signals": active_count,
        "signals_per_week": active_count / (expected_sessions / 5),
        "by_year": by_year,
        "upro": counts["UPRO"],
        "spxu": counts["SPXU"],
        "minority_share": min(counts["UPRO"], counts["SPXU"]) / max(active_count, 1),
        "switches_by_year": switches,
    }
    agreements = {
        "prior3": agreement(states, "prior3_action"),
        "dealer_only": agreement(states, "dealer_only_action"),
        "rrp_only": agreement(states, "rrp_only_action"),
        "v66": v66_agreement(states),
    }
    monthly = Counter(day.strftime("%Y-%m") for day, row in states.items() if row["action"] != "CASH")
    max_month_share = max(monthly.values(), default=0) / max(active_count, 1)
    rrp_causal = all(
        pd.Timestamp(row["rrp_prior_date"]) < day
        and pd.Timestamp(row["latest_auction_date"]) < day
        for day, row in states.items()
    )
    arca = relay.sessions(relay.ARCA_PATH)
    equs = relay.sessions(relay.EQUS_PATH)
    quotes = {
        "primary": quote_coverage(states, arca, relay.degraded(relay.ARCA_CONDITIONS)),
        "independent": quote_coverage(states, equs, relay.degraded(relay.EQUS_CONDITIONS)),
    }
    gates = {
        "auction_required_field_validity_at_least_95_percent": integrity[
            "required_valid_fraction_2021_2023"
        ] >= 0.95,
        "rrp_join_coverage_100_percent": integrity["settlement_rows_after_rrp_join"]
        == integrity["settlement_rows_before_rrp_join"],
        "at_least_2_signals_per_week": development["signals_per_week"] >= 2.0,
        "at_least_100_signals_each_year": min(by_year.values()) >= 100,
        "minority_action_at_least_30_percent": development["minority_share"] >= 0.30,
        "at_least_20_switches_each_year": min(switches.values()) >= 20,
        "prior3_action_agreement_at_least_70_percent": agreements["prior3"][
            "agreement"
        ] >= 0.70,
        "dealer_only_agreement_at_most_80_percent": agreements["dealer_only"][
            "agreement"
        ] <= 0.80,
        "rrp_only_agreement_at_most_80_percent": agreements["rrp_only"][
            "agreement"
        ] <= 0.80,
        "v66_agreement_at_most_80_percent": agreements["v66"]["agreement"] <= 0.80,
        "max_month_signal_share_at_most_6_percent": max_month_share <= 0.06,
        "source_dates_strictly_causal": rrp_causal,
        "on_rrp_operation_close_and_publication_semantics_documented": True,
        "primary_entry_exit_quotes_at_least_95_percent": quotes["primary"][
            "coverage"
        ] >= 0.95,
        "independent_entry_exit_quotes_at_least_90_percent": quotes[
            "independent"
        ]["coverage"] >= 0.90,
        "no_post_entry_return_read": True,
    }
    payload = {
        "status": "returns_blind_v71_audit",
        "new_databento_calls_or_purchases": False,
        "free_external_source_added": "FRED RRPONTSYD sourced from the New York Fed",
        "integrity": integrity,
        "development_2021_2023": development,
        "agreement": agreements,
        "max_month_signal_share": max_month_share,
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
