"""Returns-blind audit of constituent participation acceleration v75."""

from __future__ import annotations

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

from research.universes.residual_reversal_v1 import stock_symbols  # noqa: E402
from research_scout import audit_treasury_dealer_dollar_years_v66 as v66  # noqa: E402
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay  # noqa: E402
from research_scout import test_upro_spxu_creative_hypotheses as base  # noqa: E402

SOURCE_DIR = ROOT / "external_artifacts" / "alpaca_iex_breadth_v75"
BARS = SOURCE_DIR / "signal_bars_30min_2021_2023.parquet"
MANIFEST = SOURCE_DIR / "manifest.json"
OUTPUT = ROOT / "research_scout" / "constituent_participation_acceleration_returns_blind_audit_v75.json"
REPORT = ROOT / "research_scout" / "CONSTITUENT_PARTICIPATION_ACCELERATION_AUDIT_V75.md"
YEARS = (2021, 2022, 2023)
ENTRY = "10:31"
EXIT = "15:55"


def breadth_action(first: pd.Series, hour: pd.Series) -> tuple[str, int, int]:
    b30 = int((first > 0).sum() - (first < 0).sum())
    b60 = int((hour > 0).sum() - (hour < 0).sum())
    if b30 > 0 and b60 > 0 and abs(b60) > abs(b30):
        return "UPRO", b30, b60
    if b30 < 0 and b60 < 0 and abs(b60) > abs(b30):
        return "SPXU", b30, b60
    return "CASH", b30, b60


def load_states() -> tuple[dict[pd.Timestamp, dict[str, Any]], dict[str, Any]]:
    frame = pd.read_parquet(BARS)
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    frame["session_date"] = pd.to_datetime(frame["session_date"]).dt.normalize()
    symbols = sorted(stock_symbols())
    symbol_set = set(symbols)
    states = {}
    coverage = {}
    for day, group in frame.groupby("session_date", sort=True):
        indexed = group.set_index(["symbol", "local_clock"])
        complete = [
            symbol for symbol in symbols
            if (symbol, "09:30") in indexed.index
            and (symbol, "10:00") in indexed.index
        ]
        fraction = len(complete) / len(symbols)
        coverage[pd.Timestamp(day)] = fraction
        if fraction < 0.95 or ("SPY", "09:30") not in indexed.index or ("SPY", "10:00") not in indexed.index:
            continue
        first = pd.Series(
            {
                symbol: float(indexed.loc[(symbol, "09:30"), "close"])
                / float(indexed.loc[(symbol, "09:30"), "open"])
                - 1
                for symbol in complete
            }
        )
        hour = pd.Series(
            {
                symbol: float(indexed.loc[(symbol, "10:00"), "close"])
                / float(indexed.loc[(symbol, "09:30"), "open"])
                - 1
                for symbol in complete
            }
        )
        action, b30, b60 = breadth_action(first, hour)
        odd = [symbol for index, symbol in enumerate(symbols) if index % 2 and symbol in complete]
        even = [symbol for index, symbol in enumerate(symbols) if not index % 2 and symbol in complete]
        odd_action, _, _ = breadth_action(first[odd], hour[odd])
        even_action, _, _ = breadth_action(first[even], hour[even])
        spy_return = (
            float(indexed.loc[("SPY", "10:00"), "close"])
            / float(indexed.loc[("SPY", "09:30"), "open"])
            - 1
        )
        states[pd.Timestamp(day).normalize()] = {
            "session_date": pd.Timestamp(day).strftime("%Y-%m-%d"),
            "symbols": len(complete),
            "coverage": fraction,
            "breadth_30": b30,
            "breadth_60": b60,
            "action": action,
            "odd_action": odd_action,
            "even_action": even_action,
            "spy_action": "UPRO" if spy_return > 0 else "SPXU" if spy_return < 0 else "CASH",
            "final_breadth_action": "UPRO" if b60 > 0 else "SPXU" if b60 < 0 else "CASH",
        }
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    integrity = {
        "sha256": hashlib.sha256(BARS.read_bytes()).hexdigest().upper(),
        "manifest_sha256": manifest["sha256"],
        "sessions_requested": manifest["sessions_requested"],
        "sessions_at_least_95pct_complete": sum(value >= 0.95 for value in coverage.values()),
        "complete_session_fraction": sum(value >= 0.95 for value in coverage.values()) / manifest["sessions_requested"],
        "minimum_session_coverage": min(coverage.values()),
        "universe_symbols": len(symbol_set),
        "paid_data": manifest["paid_data"],
        "databento_call": manifest["databento_call"],
    }
    return states, integrity


def agreement(states: dict[pd.Timestamp, dict[str, Any]], field: str) -> dict[str, Any]:
    rows = [row for row in states.values() if row["action"] != "CASH" and row[field] != "CASH"]
    same = sum(row["action"] == row[field] for row in rows)
    return {"overlap": len(rows), "identical": same, "agreement": same / max(len(rows), 1)}


def switches(states: dict[pd.Timestamp, dict[str, Any]]) -> dict[str, int]:
    result = {}
    for year in YEARS:
        actions = [states[day]["action"] for day in sorted(states) if day.year == year and states[day]["action"] != "CASH"]
        result[str(year)] = sum(a != b for a, b in zip(actions, actions[1:]))
    return result


def quote_coverage(states, sessions, excluded):
    active = {day: row for day, row in states.items() if row["action"] != "CASH" and day not in excluded and day in sessions}
    valid = 0
    for day, row in active.items():
        frame = sessions.get(day, {}).get(row["action"])
        if frame is None:
            continue
        zone = frame.index.tz
        entry = base.exact_row(frame, v66.v65.clock_stamp(day, ENTRY, zone))
        exit_row = base.exact_row(frame, v66.v65.clock_stamp(day, EXIT, zone))
        valid += int(base.valid_quote(entry) and base.valid_quote(exit_row))
    return {"active": len(active), "valid": valid, "coverage": valid / max(len(active), 1)}


def main() -> None:
    states, integrity = load_states()
    counts = Counter(row["action"] for row in states.values())
    active = counts["UPRO"] + counts["SPXU"]
    by_year = {str(year): sum(day.year == year and row["action"] != "CASH" for day, row in states.items()) for year in YEARS}
    turns = switches(states)
    dev = {
        "valid_sessions": len(states),
        "signals": active,
        "signals_per_week": active / (753 / 5),
        "selection_share": active / max(len(states), 1),
        "by_year": by_year,
        "upro": counts["UPRO"],
        "spxu": counts["SPXU"],
        "minority_share": min(counts["UPRO"], counts["SPXU"]) / max(active, 1),
        "switches_by_year": turns,
    }
    agreements = {
        "odd": agreement(states, "odd_action"),
        "even": agreement(states, "even_action"),
        "spy": agreement(states, "spy_action"),
    }
    monthly = Counter(day.strftime("%Y-%m") for day, row in states.items() if row["action"] != "CASH")
    max_month = max(monthly.values(), default=0) / max(active, 1)
    arca = relay.sessions(relay.ARCA_PATH)
    equs = relay.sessions(relay.EQUS_PATH)
    quotes = {
        "primary": quote_coverage(states, arca, relay.degraded(relay.ARCA_CONDITIONS)),
        "independent": quote_coverage(states, equs, relay.degraded(relay.EQUS_CONDITIONS)),
    }
    gates = {
        "source_hash_matches": integrity["sha256"] == integrity["manifest_sha256"],
        "no_paid_data_or_databento_call": not integrity["paid_data"] and not integrity["databento_call"],
        "complete_session_fraction_at_least_95_percent": integrity["complete_session_fraction"] >= 0.95,
        "at_least_2_signals_per_week": dev["signals_per_week"] >= 2,
        "at_least_100_signals_each_year": min(by_year.values()) >= 100,
        "minority_action_at_least_30_percent": dev["minority_share"] >= 0.30,
        "at_least_25_switches_each_year": min(turns.values()) >= 25,
        "selection_share_at_most_80_percent": dev["selection_share"] <= 0.80,
        "spy_action_agreement_at_most_85_percent": agreements["spy"]["agreement"] <= 0.85,
        "odd_action_agreement_at_least_70_percent": agreements["odd"]["agreement"] >= 0.70,
        "even_action_agreement_at_least_70_percent": agreements["even"]["agreement"] >= 0.70,
        "max_month_share_at_most_6_percent": max_month <= 0.06,
        "primary_quote_coverage_at_least_95_percent": quotes["primary"]["coverage"] >= 0.95,
        "independent_quote_coverage_at_least_90_percent": quotes["independent"]["coverage"] >= 0.90,
        "no_post_entry_return_read": True,
    }
    payload = {
        "status": "returns_blind_v75_audit",
        "source_integrity": integrity,
        "development_2021_2023": dev,
        "agreement": agreements,
        "max_month_signal_share": max_month,
        "quotes": quotes,
        "gates": gates,
        "gate_passed": all(gates.values()),
        "decision": "authorize_frozen_development_pnl_only" if all(gates.values()) else "reject_before_pnl",
        "new_databento_calls_or_purchases": False,
        "states": [row for _, row in sorted(states.items())],
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    failures = [name for name, passed in gates.items() if not passed]
    REPORT.write_text(
        "# Constituent Participation Acceleration Audit v75\n\n"
        + ("**All blind gates passed; P&L authorized.**" if payload["gate_passed"] else "**Rejected blind before P&L.**")
        + f"\n\n- Signals: {active} ({dev['signals_per_week']:.3f}/week)\n"
        + f"- By year: {by_year}\n- UPRO / SPXU: {counts['UPRO']} / {counts['SPXU']}\n"
        + f"- Selection share: {dev['selection_share']:.3%}\n"
        + f"- Odd / even / SPY agreement: {agreements['odd']['agreement']:.3%} / {agreements['even']['agreement']:.3%} / {agreements['spy']['agreement']:.3%}\n"
        + "Failed gates: " + (", ".join(failures) if failures else "none") + "\n\nNo post-entry return was read.\n",
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in payload.items() if key != "states"}, indent=2))


if __name__ == "__main__":
    main()
