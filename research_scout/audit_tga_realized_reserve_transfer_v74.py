"""Returns-blind audit of realized TGA reserve transfer v74."""

from __future__ import annotations

import bisect
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import pandas as pd  # noqa: E402
from pandas.tseries.holiday import USFederalHolidayCalendar  # noqa: E402
from pandas.tseries.offsets import CustomBusinessDay  # noqa: E402

from research_scout import audit_treasury_dealer_dollar_years_v66 as v66  # noqa: E402
from research_scout import audit_treasury_settlement_rrp_liquidity_netting_v71 as v71  # noqa: E402
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay  # noqa: E402
from research_scout import test_upro_spxu_creative_hypotheses as base  # noqa: E402

SOURCE_DIR = ROOT / "external_artifacts" / "fiscaldata_tga_v74"
BALANCE = SOURCE_DIR / "operating_cash_balance_2020_2023.csv"
FLOW = SOURCE_DIR / "deposits_withdrawals_2020_2023.csv"
MANIFEST = SOURCE_DIR / "manifest.json"
OUTPUT = (
    ROOT
    / "research_scout"
    / "tga_realized_reserve_transfer_returns_blind_audit_v74.json"
)
REPORT = ROOT / "research_scout" / "TGA_REALIZED_RESERVE_TRANSFER_AUDIT_V74.md"
START = pd.Timestamp("2021-01-01")
END = pd.Timestamp("2023-12-31")
YEARS = (2021, 2022, 2023)
ENTRY = "09:33"
EXIT = "15:30"
FEDERAL_DAY = CustomBusinessDay(calendar=USFederalHolidayCalendar())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.replace({"null": None}), errors="coerce")


def action(value: float) -> str:
    return "SPXU" if value > 0 else "UPRO" if value < 0 else "CASH"


def balance_rows(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for day, group in frame.groupby("record_date", sort=True):
        by_type = {str(row.account_type): row for row in group.itertuples(index=False)}
        if (
            "Treasury General Account (TGA) Opening Balance" in by_type
            and "Treasury General Account (TGA) Closing Balance" in by_type
        ):
            opening = float(
                by_type["Treasury General Account (TGA) Opening Balance"].open_today_bal
            )
            closing = float(
                by_type["Treasury General Account (TGA) Closing Balance"].open_today_bal
            )
            main_account = "Treasury General Account (TGA)"
        else:
            main_account = (
                "Treasury General Account (TGA)"
                if "Treasury General Account (TGA)" in by_type
                else "Federal Reserve Account"
            )
            if main_account not in by_type:
                continue
            row = by_type[main_account]
            opening = float(row.open_today_bal)
            closing = float(row.close_today_bal)
        rows.append(
            {
                "record_date": pd.Timestamp(day).normalize(),
                "opening": opening,
                "closing": closing,
                "balance_change": closing - opening,
                "main_account": main_account,
            }
        )
    return pd.DataFrame(rows)


def flow_rows(frame: pd.DataFrame, balances: pd.DataFrame) -> pd.DataFrame:
    accounts = balances.set_index("record_date")["main_account"].to_dict()
    rows = []
    for day, group in frame.groupby("record_date", sort=True):
        day = pd.Timestamp(day).normalize()
        if day not in accounts:
            continue
        deposit_total = group[
            group["account_type"].eq("Treasury General Account Total Deposits")
            & group["transaction_type"].eq("Deposits")
        ]
        withdrawal_total = group[
            group["account_type"].eq("Treasury General Account Total Withdrawals")
            & group["transaction_type"].eq("Withdrawals")
        ]
        if len(deposit_total) == 1 and len(withdrawal_total) == 1:
            selected = pd.concat([deposit_total, withdrawal_total])
            deposits = float(deposit_total["transaction_today_amt"].iloc[0])
            withdrawals = float(withdrawal_total["transaction_today_amt"].iloc[0])
            source_kind = "official_total_rows"
        else:
            selected = group[group["account_type"].eq(accounts[day])]
            deposits = float(
                selected.loc[
                    selected["transaction_type"].eq("Deposits"),
                    "transaction_today_amt",
                ].sum()
            )
            withdrawals = float(
                selected.loc[
                    selected["transaction_type"].eq("Withdrawals"),
                    "transaction_today_amt",
                ].sum()
            )
            source_kind = "sum_rounded_detail_rows"
        rows.append(
            {
                "record_date": day,
                "deposits": deposits,
                "withdrawals": withdrawals,
                "net_tga_drain": deposits - withdrawals,
                "included_flow_rows": int(len(selected)),
                "rounding_tolerance": 0.5 * len(selected) + 1.5,
                "flow_source_kind": source_kind,
            }
        )
    return pd.DataFrame(rows)


def load_records() -> tuple[pd.DataFrame, dict[str, Any]]:
    balance = pd.read_csv(BALANCE, low_memory=False)
    flow = pd.read_csv(FLOW, low_memory=False)
    for frame in (balance, flow):
        frame["record_date"] = pd.to_datetime(
            frame["record_date"], errors="coerce"
        ).dt.normalize()
    for column in ("close_today_bal", "open_today_bal"):
        balance[column] = numeric(balance[column])
    flow["transaction_today_amt"] = numeric(flow["transaction_today_amt"])
    required_balance = (
        balance["record_date"].notna()
        & balance["account_type"].notna()
    )
    required_flow = (
        flow["record_date"].notna()
        & flow["account_type"].notna()
        & flow["transaction_type"].notna()
        & flow["transaction_today_amt"].notna()
    )
    required_fraction = float(
        (required_balance.sum() + required_flow.sum())
        / (len(balance) + len(flow))
    )
    balances = balance_rows(balance[required_balance].copy())
    flows = flow_rows(flow[required_flow].copy(), balances)
    records = balances.merge(flows, on="record_date", how="inner", validate="one_to_one")
    records["reconciliation_error"] = (
        records["net_tga_drain"] - records["balance_change"]
    ).abs()
    records["reconciles"] = (
        records["reconciliation_error"] <= records["rounding_tolerance"]
    )
    records["accounting_action"] = records["balance_change"].map(action)
    records["flow_action"] = records["net_tga_drain"].map(action)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    integrity = {
        "balance_sha256": sha256(BALANCE),
        "flow_sha256": sha256(FLOW),
        "manifest_balance_sha256": manifest["output_sha256"],
        "manifest_flow_sha256": manifest["flow_output_sha256"],
        "required_field_fraction": required_fraction,
        "balance_record_dates": int(balances["record_date"].nunique()),
        "flow_record_dates": int(flows["record_date"].nunique()),
        "joined_record_dates": int(records["record_date"].nunique()),
        "reconciliation_fraction": float(records["reconciles"].mean()),
        "maximum_reconciliation_error_millions": float(
            records["reconciliation_error"].max()
        ),
        "maximum_rounding_tolerance_millions": float(
            records["rounding_tolerance"].max()
        ),
        "flow_source_kinds": records["flow_source_kind"].value_counts().to_dict(),
        "paid_data": bool(manifest["paid_data"]),
        "databento_call": bool(manifest["databento_call"]),
    }
    return records, integrity


def build_states(
    records: pd.DataFrame,
) -> dict[pd.Timestamp, dict[str, Any]]:
    sessions = sorted(
        pd.Timestamp(day).normalize() for day in v66.flowlib.load_spy_sessions()
    )
    mapped: dict[pd.Timestamp, dict[str, Any]] = {}
    for row in records.itertuples(index=False):
        record_date = pd.Timestamp(row.record_date).normalize()
        publication_date = (record_date + FEDERAL_DAY).normalize()
        index = bisect.bisect_right(sessions, publication_date)
        if index >= len(sessions):
            continue
        trade_date = sessions[index]
        if not START <= trade_date <= END:
            continue
        state = mapped.setdefault(
            trade_date,
            {
                "record_dates": [],
                "publication_dates": [],
                "net_tga_drain": 0.0,
                "balance_change": 0.0,
                "record_rows": 0,
            },
        )
        state["record_dates"].append(record_date.strftime("%Y-%m-%d"))
        state["publication_dates"].append(publication_date.strftime("%Y-%m-%d"))
        state["net_tga_drain"] += float(row.net_tga_drain)
        state["balance_change"] += float(row.balance_change)
        state["record_rows"] += 1
    for day, state in mapped.items():
        state["session_date"] = day.strftime("%Y-%m-%d")
        state["action"] = action(float(state["net_tga_drain"]))
        state["accounting_action"] = action(float(state["balance_change"]))
    return mapped


def agreement_field(
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
    states: dict[pd.Timestamp, dict[str, Any]],
    legacy: dict[pd.Timestamp, str],
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


def legacy_actions() -> dict[str, dict[pd.Timestamp, str]]:
    auctions, _ = v66.load_auctions()
    old66_states = v66.build_states(
        v66.aggregate_auction_days(auctions), v66.flowlib.load_spy_sessions()
    )
    old71_states, _ = v71.build_settlement_states()
    return {
        "v66": {day: row["action"] for day, row in old66_states.items()},
        "v71": {day: row["action"] for day, row in old71_states.items()},
        "rrp_only": {
            day: row["rrp_only_action"] for day, row in old71_states.items()
        },
    }


def switches_by_year(states: dict[pd.Timestamp, dict[str, Any]]) -> dict[str, int]:
    result = {}
    for year in YEARS:
        actions = [
            states[day]["action"] for day in sorted(states)
            if day.year == year and states[day]["action"] != "CASH"
        ]
        result[str(year)] = sum(a != b for a, b in zip(actions, actions[1:]))
    return result


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
            "# TGA Realized Reserve Transfer Audit v74",
            "",
            verdict,
            "",
            f"- Signals: {dev['signals']} ({dev['signals_per_week']:.3f}/week)",
            f"- By year: {dev['by_year']}",
            f"- UPRO / SPXU: {dev['upro']} / {dev['spxu']}",
            f"- Accounting action agreement: "
            f"{payload['agreement']['accounting']['agreement']:.3%}",
            f"- v66 / v71 / RRP agreement: "
            f"{payload['agreement']['v66']['agreement']:.3%} / "
            f"{payload['agreement']['v71']['agreement']:.3%} / "
            f"{payload['agreement']['rrp_only']['agreement']:.3%}",
            f"- Reconciliation fraction: "
            f"{payload['source_integrity']['reconciliation_fraction']:.3%}",
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
    records, integrity = load_records()
    states = build_states(records)
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
    legacy = legacy_actions()
    agreements = {
        "accounting": agreement_field(states, "accounting_action"),
        **{
            name: legacy_agreement(states, actions)
            for name, actions in legacy.items()
        },
    }
    monthly = Counter(
        day.strftime("%Y-%m") for day, row in states.items() if row["action"] != "CASH"
    )
    max_month_share = max(monthly.values(), default=0) / max(active_count, 1)
    causal = all(
        all(pd.Timestamp(pub) < day for pub in row["publication_dates"])
        for day, row in states.items()
    )
    arca = relay.sessions(relay.ARCA_PATH)
    equs = relay.sessions(relay.EQUS_PATH)
    quotes = {
        "primary": quote_coverage(states, arca, relay.degraded(relay.ARCA_CONDITIONS)),
        "independent": quote_coverage(states, equs, relay.degraded(relay.EQUS_CONDITIONS)),
    }
    gates = {
        "source_hashes_match_manifest": (
            integrity["balance_sha256"] == integrity["manifest_balance_sha256"]
            and integrity["flow_sha256"] == integrity["manifest_flow_sha256"]
        ),
        "no_paid_data_or_databento_call": not integrity["paid_data"]
        and not integrity["databento_call"],
        "required_field_fraction_at_least_99_percent": integrity[
            "required_field_fraction"
        ] >= 0.99,
        "accounting_reconciliation_at_least_99_percent": integrity[
            "reconciliation_fraction"
        ] >= 0.99,
        "trade_dates_strictly_after_publication_dates": causal,
        "at_least_2_signals_per_week": development["signals_per_week"] >= 2.0,
        "at_least_100_signals_each_year": min(by_year.values()) >= 100,
        "minority_action_at_least_30_percent": development["minority_share"] >= 0.30,
        "at_least_20_switches_each_year": min(switches.values()) >= 20,
        "accounting_action_agreement_at_least_99_percent": agreements[
            "accounting"
        ]["agreement"] >= 0.99,
        "v66_agreement_at_most_80_percent": agreements["v66"]["agreement"] <= 0.80,
        "v71_agreement_at_most_80_percent": agreements["v71"]["agreement"] <= 0.80,
        "rrp_agreement_at_most_80_percent": agreements["rrp_only"]["agreement"] <= 0.80,
        "max_month_signal_share_at_most_6_percent": max_month_share <= 0.06,
        "primary_entry_exit_quotes_at_least_95_percent": quotes["primary"][
            "coverage"
        ] >= 0.95,
        "independent_entry_exit_quotes_at_least_90_percent": quotes["independent"][
            "coverage"
        ] >= 0.90,
        "no_post_entry_return_read": True,
    }
    payload = {
        "status": "returns_blind_v74_audit",
        "new_databento_calls_or_purchases": False,
        "free_external_source_added": "U.S. Treasury Daily Treasury Statement",
        "source_integrity": integrity,
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
