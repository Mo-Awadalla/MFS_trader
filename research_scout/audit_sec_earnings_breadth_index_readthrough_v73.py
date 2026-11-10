"""Returns-blind audit of SEC earnings-breadth index read-through v73."""

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
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay  # noqa: E402
from research_scout import download_sec_earnings_breadth_signal_bars_v73 as source  # noqa: E402
from research_scout import test_upro_spxu_creative_hypotheses as base  # noqa: E402

BARS = (
    ROOT
    / "external_artifacts"
    / "alpaca_iex_sec_earnings_v73"
    / "signal_bars_30min_2021_2023.parquet"
)
MANIFEST = BARS.parent / "manifest.json"
OUTPUT = (
    ROOT
    / "research_scout"
    / "sec_earnings_breadth_index_readthrough_returns_blind_audit_v73.json"
)
REPORT = (
    ROOT
    / "research_scout"
    / "SEC_EARNINGS_BREADTH_INDEX_READTHROUGH_AUDIT_V73.md"
)
YEARS = (2021, 2022, 2023)
ENTRY = "10:31"
EXIT = "15:55"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def action(value: float) -> str:
    return "UPRO" if value > 0 else "SPXU" if value < 0 else "CASH"


def load_signal_rows() -> tuple[pd.DataFrame, dict[str, Any]]:
    events, _ = source.event_map()
    bars = pd.read_parquet(BARS)
    bars["symbol"] = bars["symbol"].astype(str).str.upper()
    bars["session_date"] = bars["session_date"].astype(str)
    bars["local_clock"] = bars["local_clock"].astype(str)
    if bars.duplicated(["session_date", "symbol", "local_clock"]).any():
        raise RuntimeError("Duplicate signal bars")
    indexed = bars.set_index(["session_date", "symbol", "local_clock"])
    spy_rows: dict[str, dict[str, float]] = {}
    for day in sorted(events["session_date"].unique()):
        keys = [(str(day), "SPY", "09:30"), (str(day), "SPY", "10:00")]
        if not all(key in indexed.index for key in keys):
            continue
        first = indexed.loc[keys[0]]
        second = indexed.loc[keys[1]]
        spy_rows[str(day)] = {
            "spy_open": float(first["open"]),
            "spy_first30_close": float(first["close"]),
            "spy_hour_close": float(second["close"]),
        }
    rows = []
    for event in events.itertuples(index=False):
        day = str(event.session_date)
        symbol = str(event.symbol).upper()
        keys = [(day, symbol, "09:30"), (day, symbol, "10:00")]
        if day not in spy_rows or not all(key in indexed.index for key in keys):
            continue
        first = indexed.loc[keys[0]]
        second = indexed.loc[keys[1]]
        issuer_open = float(first["open"])
        issuer_first30_close = float(first["close"])
        issuer_hour_close = float(second["close"])
        spy = spy_rows[day]
        valid = all(
            pd.notna(value) and float(value) > 0
            for value in (
                issuer_open,
                issuer_first30_close,
                issuer_hour_close,
                spy["spy_open"],
                spy["spy_first30_close"],
                spy["spy_hour_close"],
            )
        )
        if not valid:
            continue
        issuer_hour = issuer_hour_close / issuer_open - 1
        issuer_first30 = issuer_first30_close / issuer_open - 1
        spy_hour = spy["spy_hour_close"] / spy["spy_open"] - 1
        spy_first30 = spy["spy_first30_close"] / spy["spy_open"] - 1
        rows.append(
            {
                "session_date": day,
                "symbol": symbol,
                "acceptance_datetime": pd.Timestamp(event.acceptance_datetime),
                "hour_residual": issuer_hour - spy_hour,
                "first30_residual": issuer_first30 - spy_first30,
                "spy_hour": spy_hour,
            }
        )
    frame = pd.DataFrame(rows)
    expected = events.groupby("session_date")["symbol"].nunique()
    observed = frame.groupby("session_date")["symbol"].nunique()
    complete_days = sorted(
        day for day, count in expected.items()
        if int(observed.get(day, 0)) == int(count)
    )
    frame = frame[frame["session_date"].isin(complete_days)].copy()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    integrity = {
        "events_sha256": sha256(source.EVENTS),
        "calendar_sha256": sha256(source.CALENDAR),
        "bars_sha256": sha256(BARS),
        "manifest_output_sha256": manifest["output_sha256"],
        "expected_events": int(len(events)),
        "expected_sessions": int(events["session_date"].nunique()),
        "observed_valid_event_rows": int(len(rows)),
        "complete_sessions": int(len(complete_days)),
        "complete_session_fraction": len(complete_days)
        / max(events["session_date"].nunique(), 1),
        "stored_bar_rows": int(len(bars)),
        "bar_clocks": sorted(bars["local_clock"].unique().tolist()),
        "paid_data": bool(manifest["paid_data"]),
        "databento_call": bool(manifest["databento_call"]),
    }
    return frame, integrity


def build_states(
    frame: pd.DataFrame,
) -> tuple[dict[pd.Timestamp, dict[str, Any]], dict[str, float]]:
    states: dict[pd.Timestamp, dict[str, Any]] = {}
    contribution: defaultdict[str, float] = defaultdict(float)
    for day, group in frame.groupby("session_date", sort=True):
        score = float(group["hour_residual"].median())
        first30 = float(group["first30_residual"].median())
        spy_hour = float(group["spy_hour"].iloc[0])
        for row in group.itertuples(index=False):
            contribution[str(row.symbol)] += abs(float(row.hour_residual))
        states[pd.Timestamp(day).normalize()] = {
            "session_date": str(day),
            "filers": int(len(group)),
            "symbols": sorted(group["symbol"].tolist()),
            "latest_acceptance": group["acceptance_datetime"].max().isoformat(),
            "earnings_breadth_shock": score,
            "first30_breadth_shock": first30,
            "spy_first_hour_return": spy_hour,
            "action": action(score),
            "first30_action": action(first30),
            "spy_momentum_action": action(spy_hour),
        }
    return states, dict(contribution)


def agreement(
    states: dict[pd.Timestamp, dict[str, Any]], field: str
) -> dict[str, Any]:
    rows = [
        row for row in states.values()
        if row["action"] != "CASH" and row[field] != "CASH"
    ]
    same = sum(row["action"] == row[field] for row in rows)
    return {
        "overlap": len(rows),
        "identical": same,
        "agreement": same / max(len(rows), 1),
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
            "# SEC Earnings-Breadth Index Read-Through Audit v73",
            "",
            verdict,
            "",
            f"- Signals: {dev['signals']} ({dev['signals_per_week']:.3f}/week)",
            f"- By year: {dev['by_year']}",
            f"- UPRO / SPXU: {dev['upro']} / {dev['spxu']}",
            f"- Complete event sessions: "
            f"{payload['source_integrity']['complete_session_fraction']:.3%}",
            f"- First-30 / SPY-momentum agreement: "
            f"{payload['agreement']['first30']['agreement']:.3%} / "
            f"{payload['agreement']['spy_momentum']['agreement']:.3%}",
            f"- Single-issuer session share: {dev['single_issuer_session_share']:.3%}",
            f"- Largest issuer contribution: "
            f"{payload['concentration']['issuer_share']:.3%} "
            f"({payload['concentration']['largest_issuer']})",
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
    frame, integrity = load_signal_rows()
    states, contribution = build_states(frame)
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
    single_count = sum(
        row["filers"] == 1 and row["action"] != "CASH"
        for row in states.values()
    )
    development = {
        "signals": active_count,
        "signals_per_week": active_count / (753 / 5),
        "by_year": by_year,
        "upro": counts["UPRO"],
        "spxu": counts["SPXU"],
        "cash": counts["CASH"],
        "minority_share": min(counts["UPRO"], counts["SPXU"]) / max(active_count, 1),
        "switches_by_year": switches,
        "single_issuer_sessions": single_count,
        "single_issuer_session_share": single_count / max(active_count, 1),
    }
    agreements = {
        "first30": agreement(states, "first30_action"),
        "spy_momentum": agreement(states, "spy_momentum_action"),
    }
    total_contribution = sum(contribution.values())
    largest_issuer = max(contribution, key=contribution.get) if contribution else None
    issuer_share = (
        contribution[largest_issuer] / total_contribution
        if largest_issuer and total_contribution > 0
        else 0.0
    )
    monthly = Counter(
        day.strftime("%Y-%m") for day, row in states.items() if row["action"] != "CASH"
    )
    max_month_share = max(monthly.values(), default=0) / max(active_count, 1)
    all_events_causal = all(
        pd.Timestamp(row["latest_acceptance"]).tz_convert("America/New_York")
        <= pd.Timestamp(f"{day.strftime('%Y-%m-%d')} 09:25", tz="America/New_York")
        for day, row in states.items()
    )
    arca = relay.sessions(relay.ARCA_PATH)
    equs = relay.sessions(relay.EQUS_PATH)
    quotes = {
        "primary": quote_coverage(states, arca, relay.degraded(relay.ARCA_CONDITIONS)),
        "independent": quote_coverage(states, equs, relay.degraded(relay.EQUS_CONDITIONS)),
    }
    gates = {
        "expected_event_count_matches_preregistration": integrity["expected_events"] == 1654,
        "expected_session_count_matches_preregistration": integrity[
            "expected_sessions"
        ] == 447,
        "signal_bar_clocks_are_exact": integrity["bar_clocks"] == ["09:30", "10:00"],
        "no_paid_data_or_databento_call": not integrity["paid_data"]
        and not integrity["databento_call"],
        "complete_session_fraction_at_least_95_percent": integrity[
            "complete_session_fraction"
        ] >= 0.95,
        "at_least_2_signals_per_week": development["signals_per_week"] >= 2.0,
        "at_least_100_signals_each_year": min(by_year.values()) >= 100,
        "minority_action_at_least_30_percent": development["minority_share"] >= 0.30,
        "at_least_25_switches_each_year": min(switches.values()) >= 25,
        "single_issuer_session_share_at_most_45_percent": development[
            "single_issuer_session_share"
        ] <= 0.45,
        "first30_action_agreement_at_least_70_percent": agreements["first30"][
            "agreement"
        ] >= 0.70,
        "spy_momentum_action_agreement_at_most_80_percent": agreements[
            "spy_momentum"
        ]["agreement"] <= 0.80,
        "max_issuer_contribution_at_most_10_percent": issuer_share <= 0.10,
        "max_month_signal_share_at_most_8_percent": max_month_share <= 0.08,
        "all_events_known_by_09_25": all_events_causal,
        "primary_entry_exit_quotes_at_least_95_percent": quotes["primary"][
            "coverage"
        ] >= 0.95,
        "independent_entry_exit_quotes_at_least_90_percent": quotes["independent"][
            "coverage"
        ] >= 0.90,
        "no_post_entry_return_read": True,
    }
    payload = {
        "status": "returns_blind_v73_audit",
        "new_databento_calls_or_purchases": False,
        "free_external_source_added": "Alpaca IEX 30-minute signal-window bars",
        "source_integrity": integrity,
        "development_2021_2023": development,
        "agreement": agreements,
        "concentration": {
            "issuer_share": issuer_share,
            "largest_issuer": largest_issuer,
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
