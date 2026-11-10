"""Returns-blind audit of frozen HYG/IEF primary-flow transfer V79."""

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

from research_scout import audit_proshares_primary_market_flows_v60 as flowlib  # noqa: E402
from research_scout import audit_treasury_dealer_dollar_years_v66 as v66  # noqa: E402
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay  # noqa: E402
from research_scout import test_upro_spxu_creative_hypotheses as base  # noqa: E402

SOURCE_DIR = ROOT / "external_artifacts" / "ishares_cross_asset_flow_v79"
SOURCE = SOURCE_DIR / "historical_nav_shares_2020_2023.csv"
MANIFEST = SOURCE_DIR / "manifest.json"
OUTPUT = ROOT / "research_scout" / "cross_asset_primary_flow_returns_blind_audit_v79.json"
REPORT = ROOT / "research_scout" / "CROSS_ASSET_PRIMARY_FLOW_TRANSFER_AUDIT_V79.md"
YEARS = (2021, 2022, 2023)


def action(value: float) -> str:
    if not math.isfinite(value) or value == 0:
        return "CASH"
    return "UPRO" if value > 0 else "SPXU"


def load_spy_daily() -> pd.DataFrame:
    path = ROOT / "data" / "parquet" / "equity" / "alpaca_sip" / "SPY_1d.parquet"
    frame = pd.read_parquet(path)
    timestamps = pd.to_datetime(frame["timestamp"], utc=True).dt.tz_convert(
        "America/New_York"
    )
    frame = frame.copy()
    frame["session_date"] = timestamps.dt.tz_localize(None).dt.normalize()
    return frame.set_index("session_date").sort_index()


def load_states() -> tuple[dict[pd.Timestamp, dict[str, Any]], dict[str, Any]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    frame = pd.read_csv(SOURCE)
    frame["as_of"] = pd.to_datetime(frame["as_of"]).dt.normalize()
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    expected_all = flowlib.load_spy_sessions()
    expected = pd.DatetimeIndex(
        day for day in expected_all if pd.Timestamp("2020-01-01") <= day <= pd.Timestamp("2023-12-31")
    )
    next_map = flowlib.next_session_map(expected_all)
    shares = frame.pivot(index="as_of", columns="ticker", values="shares_outstanding")
    nav = frame.pivot(index="as_of", columns="ticker", values="nav_per_share")
    common = shares.dropna(subset=["HYG", "IEF"]).index.intersection(
        nav.dropna(subset=["HYG", "IEF"]).index
    )
    shares = shares.loc[common].sort_index()
    nav = nav.loc[common].sort_index()
    share_change = shares.pct_change(fill_method=None)
    delta_shares = shares.diff()
    nav_return = nav.pct_change(fill_method=None)
    spy = load_spy_daily()
    states: dict[pd.Timestamp, dict[str, Any]] = {}
    source_rows = 0
    consecutive_rows = 0
    previous_expected = {expected[i]: expected[i - 1] for i in range(1, len(expected))}
    for source_day in common:
        source_day = pd.Timestamp(source_day).normalize()
        if source_day < pd.Timestamp("2020-01-02") or source_day > pd.Timestamp("2023-12-29"):
            continue
        source_rows += 1
        position = shares.index.get_loc(source_day)
        if not isinstance(position, int) or position == 0:
            continue
        prior_day = pd.Timestamp(shares.index[position - 1]).normalize()
        if previous_expected.get(source_day) != prior_day:
            continue
        consecutive_rows += 1
        target = next_map.get(source_day)
        if target is None or target.year not in YEARS:
            continue
        hyg_fraction = float(share_change.loc[source_day, "HYG"])
        ief_fraction = float(share_change.loc[source_day, "IEF"])
        relative_fraction = hyg_fraction - ief_fraction
        hyg_dollars = float(
            delta_shares.loc[source_day, "HYG"] * nav.loc[source_day, "HYG"]
        )
        ief_dollars = float(
            delta_shares.loc[source_day, "IEF"] * nav.loc[source_day, "IEF"]
        )
        prior_assets = float(
            (shares.loc[prior_day, ["HYG", "IEF"]] * nav.loc[prior_day, ["HYG", "IEF"]]).sum()
        )
        normalized_dollar = (
            (hyg_dollars - ief_dollars) / prior_assets
            if prior_assets > 0
            else float("nan")
        )
        price_relative = float(
            nav_return.loc[source_day, "HYG"] - nav_return.loc[source_day, "IEF"]
        )
        spy_return = float("nan")
        if source_day in spy.index:
            spy_position = spy.index.get_loc(source_day)
            if isinstance(spy_position, int) and spy_position > 0:
                spy_return = (
                    float(spy.iloc[spy_position]["close"])
                    / float(spy.iloc[spy_position - 1]["close"])
                    - 1
                )
        states[pd.Timestamp(target).normalize()] = {
            "session_date": pd.Timestamp(target).strftime("%Y-%m-%d"),
            "source_date": source_day.strftime("%Y-%m-%d"),
            "prior_source_date": prior_day.strftime("%Y-%m-%d"),
            "hyg_fractional_flow": hyg_fraction,
            "ief_fractional_flow": ief_fraction,
            "relative_fractional_flow": relative_fraction,
            "normalized_dollar_flow": normalized_dollar,
            "hyg_creation_dollars": hyg_dollars,
            "ief_creation_dollars": ief_dollars,
            "price_relative_return": price_relative,
            "prior_spy_return": spy_return,
            "action": action(relative_fraction),
            "dollar_action": action(normalized_dollar),
            "hyg_only_action": action(hyg_fraction),
            "ief_only_action": action(-ief_fraction),
            "price_action": action(price_relative),
            "prior_spy_action": action(spy_return),
        }
    source_dates = set(common)
    coverage = {
        ticker: len(set(frame.loc[frame["ticker"] == ticker, "as_of"]) & set(expected))
        / len(expected)
        for ticker in ("HYG", "IEF")
    }
    integrity = {
        "output_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest().upper(),
        "manifest_output_sha256": manifest["output_sha256"],
        "raw_hashes": {
            ticker: hashlib.sha256(
                (SOURCE_DIR / "raw" / f"{ticker}_fundDownload.xml").read_bytes()
            )
            .hexdigest()
            .upper()
            for ticker in ("HYG", "IEF")
        },
        "manifest_raw_hashes": {
            ticker: manifest["downloaded"][ticker]["sha256"]
            for ticker in ("HYG", "IEF")
        },
        "source_date_min": min(source_dates).strftime("%Y-%m-%d"),
        "source_date_max": max(source_dates).strftime("%Y-%m-%d"),
        "post_2023_rows": int((frame["as_of"] > pd.Timestamp("2023-12-31")).sum()),
        "duplicate_fund_dates": int(frame.duplicated(["as_of", "ticker"]).sum()),
        "nonpositive_nav_or_shares": int(
            ((frame["nav_per_share"] <= 0) | (frame["shares_outstanding"] <= 0)).sum()
        ),
        "expected_sessions_2020_2023": len(expected),
        "coverage_by_fund": coverage,
        "candidate_source_rows": source_rows,
        "consecutive_source_rows": consecutive_rows,
        "paid_data": manifest["paid_data"],
        "databento_call": manifest["databento_call"],
    }
    return states, integrity


def agreement(
    states: dict[pd.Timestamp, dict[str, Any]], field: str
) -> dict[str, Any]:
    rows = [row for row in states.values() if row["action"] != "CASH"]
    same = sum(row["action"] == row[field] for row in rows)
    return {
        "primary_signals": len(rows),
        "identical": same,
        "agreement": same / max(len(rows), 1),
    }


def quote_coverage(states, sessions, excluded):
    active = {
        day: row
        for day, row in states.items()
        if row["action"] != "CASH" and day not in excluded and day in sessions
    }
    valid = 0
    for day, row in active.items():
        frame = sessions.get(day, {}).get(row["action"])
        if frame is None:
            continue
        zone = frame.index.tz
        entry = base.exact_row(frame, v66.v65.clock_stamp(day, "09:31", zone))
        exit_row = base.exact_row(frame, v66.v65.clock_stamp(day, "15:30", zone))
        valid += int(base.valid_quote(entry) and base.valid_quote(exit_row))
    return {"active": len(active), "valid": valid, "coverage": valid / max(len(active), 1)}


def main() -> None:
    states, integrity = load_states()
    counts = Counter(row["action"] for row in states.values())
    active = counts["UPRO"] + counts["SPXU"]
    by_year = {
        str(year): sum(
            day.year == year and row["action"] != "CASH"
            for day, row in states.items()
        )
        for year in YEARS
    }
    switches: dict[str, int] = {}
    for year in YEARS:
        actions = [
            states[day]["action"]
            for day in sorted(states)
            if day.year == year and states[day]["action"] != "CASH"
        ]
        switches[str(year)] = sum(a != b for a, b in zip(actions, actions[1:]))
    agreements = {
        name: agreement(states, field)
        for name, field in {
            "normalized_dollar": "dollar_action",
            "hyg_only": "hyg_only_action",
            "ief_only": "ief_only_action",
            "price_only": "price_action",
            "prior_spy": "prior_spy_action",
        }.items()
    }
    signal_days = [day for day, row in states.items() if row["action"] != "CASH"]
    monthly = Counter(day.strftime("%Y-%m") for day in signal_days)
    max_month_share = max(monthly.values(), default=0) / max(active, 1)
    arca = relay.sessions(relay.ARCA_PATH)
    equs = relay.sessions(relay.EQUS_PATH)
    quotes = {
        "primary": quote_coverage(states, arca, relay.degraded(relay.ARCA_CONDITIONS)),
        "independent": quote_coverage(states, equs, relay.degraded(relay.EQUS_CONDITIONS)),
    }
    minority_share = min(counts["UPRO"], counts["SPXU"]) / max(active, 1)
    development = {
        "mapped_sessions": len(states),
        "signals": active,
        "signals_per_week": active / (753 / 5),
        "by_year": by_year,
        "upro": counts["UPRO"],
        "spxu": counts["SPXU"],
        "cash": counts["CASH"],
        "minority_share": minority_share,
        "switches_by_year": switches,
    }
    gates = {
        "output_source_hash_matches": integrity["output_sha256"]
        == integrity["manifest_output_sha256"],
        "raw_source_hashes_match": integrity["raw_hashes"]
        == integrity["manifest_raw_hashes"],
        "no_paid_data_or_databento_call": not integrity["paid_data"]
        and not integrity["databento_call"],
        "source_coverage_each_fund_at_least_98_percent": min(
            integrity["coverage_by_fund"].values()
        )
        >= 0.98,
        "unique_positive_source_values": integrity["duplicate_fund_dates"] == 0
        and integrity["nonpositive_nav_or_shares"] == 0,
        "no_post_2023_rows_in_signal_source": integrity["post_2023_rows"] == 0,
        "one_session_delay_and_consecutive_source_observations": all(
            pd.Timestamp(row["session_date"]) > pd.Timestamp(row["source_date"])
            for row in states.values()
        ),
        "at_least_2_signals_per_week": development["signals_per_week"] >= 2.0,
        "at_least_100_signals_each_year": min(by_year.values()) >= 100,
        "minority_action_at_least_30_percent": minority_share >= 0.30,
        "at_least_25_switches_each_year": min(switches.values()) >= 25,
        "max_month_share_at_most_6_percent": max_month_share <= 0.06,
        "normalized_dollar_action_agreement_at_least_70_percent": agreements[
            "normalized_dollar"
        ]["agreement"]
        >= 0.70,
        "hyg_only_action_agreement_below_80_percent": agreements["hyg_only"][
            "agreement"
        ]
        < 0.80,
        "ief_only_action_agreement_below_80_percent": agreements["ief_only"][
            "agreement"
        ]
        < 0.80,
        "prior_spy_action_agreement_below_80_percent": agreements["prior_spy"][
            "agreement"
        ]
        < 0.80,
        "primary_quote_coverage_at_least_95_percent": quotes["primary"]["coverage"]
        >= 0.95,
        "independent_quote_coverage_at_least_90_percent": quotes["independent"][
            "coverage"
        ]
        >= 0.90,
        "no_post_entry_return_or_recent_outcome_read": True,
    }
    payload = {
        "status": "returns_blind_v79_audit",
        "source_integrity": integrity,
        "development_2021_2023": development,
        "agreements": agreements,
        "max_month_signal_share": max_month_share,
        "quotes": quotes,
        "gates": gates,
        "gate_passed": all(gates.values()),
        "decision": (
            "authorize_frozen_development_pnl_only"
            if all(gates.values())
            else "reject_before_pnl"
        ),
        "new_databento_calls_or_purchases": False,
        "states": [row for _, row in sorted(states.items())],
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    failures = [name for name, passed in gates.items() if not passed]
    REPORT.write_text(
        "# Cross-Asset Primary-Flow Transfer Audit v79\n\n"
        + (
            "**All returns-blind gates passed; frozen development P&L is authorized.**"
            if payload["gate_passed"]
            else "**Rejected returns-blind before P&L.**"
        )
        + f"\n\n- Signals: {active} ({development['signals_per_week']:.3f}/week)\n"
        + f"- By year: {by_year}\n"
        + f"- UPRO / SPXU / cash: {counts['UPRO']} / {counts['SPXU']} / {counts['CASH']}\n"
        + f"- Minority share: {minority_share:.3%}\n"
        + f"- Source coverage HYG / IEF: {integrity['coverage_by_fund']['HYG']:.3%} / {integrity['coverage_by_fund']['IEF']:.3%}\n"
        + "- Dollar / HYG-only / IEF-only / prior-SPY agreement: "
        + " / ".join(
            f"{agreements[name]['agreement']:.3%}"
            for name in ("normalized_dollar", "hyg_only", "ief_only", "prior_spy")
        )
        + "\n"
        + f"- Primary / independent quote coverage: {quotes['primary']['coverage']:.3%} / {quotes['independent']['coverage']:.3%}\n"
        + f"- Failed gates: {', '.join(failures) if failures else 'none'}\n\n"
        + "No post-entry return or recent-year outcome was read.\n",
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in payload.items() if key != "states"}, indent=2))


if __name__ == "__main__":
    main()
