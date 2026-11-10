"""Returns-blind audit of common-factor dispersion compression v76."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import pandas as pd  # noqa: E402

from research.universes.residual_reversal_v1 import stock_symbols  # noqa: E402
from research_scout import audit_constituent_participation_acceleration_v75 as v75  # noqa: E402
from research_scout import audit_treasury_dealer_dollar_years_v66 as v66  # noqa: E402
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay  # noqa: E402
from research_scout import test_upro_spxu_creative_hypotheses as base  # noqa: E402

BARS = ROOT / "external_artifacts" / "alpaca_iex_breadth_v75" / "signal_bars_30min_2021_2023.parquet"
MANIFEST = BARS.parent / "manifest.json"
OUTPUT = ROOT / "research_scout" / "common_factor_dispersion_compression_returns_blind_audit_v76.json"
REPORT = ROOT / "research_scout" / "COMMON_FACTOR_DISPERSION_COMPRESSION_AUDIT_V76.md"
YEARS = (2021, 2022, 2023)


def mad(values: pd.Series) -> float:
    return float((values - values.median()).abs().median())


def trigger(r1: pd.Series, r2: pd.Series, spy1: float, spy2: float) -> str:
    same = (spy1 > 0 and spy2 > 0) or (spy1 < 0 and spy2 < 0)
    if not same or not mad(r2) < mad(r1):
        return "CASH"
    return "UPRO" if spy2 > 0 else "SPXU"


def load_states():
    frame = pd.read_parquet(BARS)
    frame["session_date"] = pd.to_datetime(frame["session_date"]).dt.normalize()
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    symbols = sorted(stock_symbols())
    states = {}
    valid_sessions = 0
    for day, group in frame.groupby("session_date", sort=True):
        idx = group.set_index(["symbol", "local_clock"])
        complete = [s for s in symbols if (s, "09:30") in idx.index and (s, "10:00") in idx.index]
        if len(complete) / len(symbols) < 0.95 or ("SPY", "09:30") not in idx.index or ("SPY", "10:00") not in idx.index:
            continue
        valid_sessions += 1
        opens = pd.Series({s: float(idx.loc[(s, "09:30"), "open"]) for s in complete})
        mid = pd.Series({s: float(idx.loc[(s, "09:30"), "close"]) for s in complete})
        end = pd.Series({s: float(idx.loc[(s, "10:00"), "close"]) for s in complete})
        r1, r2 = mid / opens - 1, end / mid - 1
        spy_open = float(idx.loc[("SPY", "09:30"), "open"])
        spy_mid = float(idx.loc[("SPY", "09:30"), "close"])
        spy_end = float(idx.loc[("SPY", "10:00"), "close"])
        spy1, spy2 = spy_mid / spy_open - 1, spy_end / spy_mid - 1
        odd = [s for i, s in enumerate(symbols) if i % 2 and s in complete]
        even = [s for i, s in enumerate(symbols) if not i % 2 and s in complete]
        states[pd.Timestamp(day)] = {
            "session_date": pd.Timestamp(day).strftime("%Y-%m-%d"),
            "action": trigger(r1, r2, spy1, spy2),
            "odd_action": trigger(r1[odd], r2[odd], spy1, spy2),
            "even_action": trigger(r1[even], r2[even], spy1, spy2),
            "spy_control_action": "UPRO" if spy1 > 0 and spy2 > 0 else "SPXU" if spy1 < 0 and spy2 < 0 else "CASH",
            "mad_first": mad(r1),
            "mad_second": mad(r2),
        }
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return states, {
        "sha256": hashlib.sha256(BARS.read_bytes()).hexdigest().upper(),
        "manifest_sha256": manifest["sha256"],
        "valid_sessions": valid_sessions,
        "session_fraction": valid_sessions / manifest["sessions_requested"],
        "paid_data": manifest["paid_data"],
    }


def agreement(states, field):
    rows = [r for r in states.values() if r["action"] != "CASH" and r[field] != "CASH"]
    same = sum(r["action"] == r[field] for r in rows)
    return {"overlap": len(rows), "agreement": same / max(len(rows), 1)}


def quote_coverage(states, sessions, excluded):
    active = {d: r for d, r in states.items() if r["action"] != "CASH" and d not in excluded and d in sessions}
    valid = 0
    for day, row in active.items():
        frame = sessions.get(day, {}).get(row["action"])
        if frame is None:
            continue
        zone = frame.index.tz
        entry = base.exact_row(frame, v66.v65.clock_stamp(day, "10:31", zone))
        exit_row = base.exact_row(frame, v66.v65.clock_stamp(day, "15:55", zone))
        valid += int(base.valid_quote(entry) and base.valid_quote(exit_row))
    return {"active": len(active), "valid": valid, "coverage": valid / max(len(active), 1)}


def main():
    states, integrity = load_states()
    counts = Counter(r["action"] for r in states.values())
    active = counts["UPRO"] + counts["SPXU"]
    by_year = {str(y): sum(d.year == y and r["action"] != "CASH" for d, r in states.items()) for y in YEARS}
    minority = min(counts["UPRO"], counts["SPXU"]) / max(active, 1)
    turns = {}
    for y in YEARS:
        acts = [states[d]["action"] for d in sorted(states) if d.year == y and states[d]["action"] != "CASH"]
        turns[str(y)] = sum(a != b for a, b in zip(acts, acts[1:]))
    old_states, _ = v75.load_states()
    old_days = {d for d, r in old_states.items() if r["action"] != "CASH"}
    new_days = {d for d, r in states.items() if r["action"] != "CASH"}
    overlap = len(old_days & new_days) / max(len(new_days), 1)
    agreements = {"odd": agreement(states, "odd_action"), "even": agreement(states, "even_action")}
    monthly = Counter(d.strftime("%Y-%m") for d in new_days)
    max_month = max(monthly.values(), default=0) / max(active, 1)
    arca, equs = relay.sessions(relay.ARCA_PATH), relay.sessions(relay.EQUS_PATH)
    quotes = {
        "primary": quote_coverage(states, arca, relay.degraded(relay.ARCA_CONDITIONS)),
        "independent": quote_coverage(states, equs, relay.degraded(relay.EQUS_CONDITIONS)),
    }
    dev = {
        "valid_sessions": len(states), "signals": active, "signals_per_week": active / (753 / 5),
        "selection_share": active / max(len(states), 1), "by_year": by_year,
        "upro": counts["UPRO"], "spxu": counts["SPXU"], "minority_share": minority,
        "switches_by_year": turns, "v75_signal_date_overlap": overlap,
    }
    gates = {
        "source_hash_matches": integrity["sha256"] == integrity["manifest_sha256"],
        "no_paid_data": not integrity["paid_data"],
        "complete_sessions_at_least_95_percent": integrity["session_fraction"] >= 0.95,
        "at_least_2_signals_per_week": dev["signals_per_week"] >= 2,
        "at_least_100_signals_each_year": min(by_year.values()) >= 100,
        "minority_action_at_least_30_percent": minority >= 0.30,
        "at_least_25_switches_each_year": min(turns.values()) >= 25,
        "selection_share_between_20_and_80_percent": 0.20 <= dev["selection_share"] <= 0.80,
        "odd_action_agreement_at_least_70_percent": agreements["odd"]["agreement"] >= 0.70,
        "even_action_agreement_at_least_70_percent": agreements["even"]["agreement"] >= 0.70,
        "v75_signal_date_overlap_at_most_80_percent": overlap <= 0.80,
        "max_month_share_at_most_6_percent": max_month <= 0.06,
        "primary_quote_coverage_at_least_95_percent": quotes["primary"]["coverage"] >= 0.95,
        "independent_quote_coverage_at_least_90_percent": quotes["independent"]["coverage"] >= 0.90,
        "no_post_entry_return_read": True,
    }
    payload = {
        "status": "returns_blind_v76_audit", "source_integrity": integrity,
        "development_2021_2023": dev, "agreement": agreements,
        "max_month_signal_share": max_month, "quotes": quotes, "gates": gates,
        "gate_passed": all(gates.values()),
        "decision": "authorize_frozen_development_pnl_only" if all(gates.values()) else "reject_before_pnl",
        "new_databento_calls_or_purchases": False,
        "states": [r for _, r in sorted(states.items())],
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    failed = [k for k, v in gates.items() if not v]
    REPORT.write_text(
        f"# Common-Factor Dispersion Compression Audit v76\n\n"
        f"{'**All blind gates passed; P&L authorized.**' if payload['gate_passed'] else '**Rejected blind before P&L.**'}\n\n"
        f"- Signals: {active} ({dev['signals_per_week']:.3f}/week)\n- By year: {by_year}\n"
        f"- UPRO / SPXU: {counts['UPRO']} / {counts['SPXU']}\n- V75 overlap: {overlap:.3%}\n"
        f"- Odd / even agreement: {agreements['odd']['agreement']:.3%} / {agreements['even']['agreement']:.3%}\n"
        f"- Failed gates: {', '.join(failed) if failed else 'none'}\n\nNo post-entry return was read.\n",
        encoding="utf-8",
    )
    print(json.dumps({k: v for k, v in payload.items() if k != "states"}, indent=2))


if __name__ == "__main__":
    main()
