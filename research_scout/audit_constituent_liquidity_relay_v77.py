"""Returns-blind audit of the frozen constituent liquidity relay V77."""

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
from research_scout import audit_common_factor_dispersion_compression_v76 as v76  # noqa: E402
from research_scout import audit_constituent_participation_acceleration_v75 as v75  # noqa: E402
from research_scout import audit_treasury_dealer_dollar_years_v66 as v66  # noqa: E402
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay  # noqa: E402
from research_scout import test_upro_spxu_creative_hypotheses as base  # noqa: E402

BARS = (
    ROOT
    / "external_artifacts"
    / "alpaca_iex_liquidity_relay_v77"
    / "signal_bars_30min_2021_2023.parquet"
)
MANIFEST = BARS.parent / "manifest.json"
OUTPUT = (
    ROOT
    / "research_scout"
    / "constituent_liquidity_relay_returns_blind_audit_v77.json"
)
REPORT = ROOT / "research_scout" / "CONSTITUENT_LIQUIDITY_RELAY_AUDIT_V77.md"
YEARS = (2021, 2022, 2023)


def trigger(
    first: pd.Series, second: pd.Series, volume_first: pd.Series, volume_second: pd.Series
) -> tuple[str, dict[str, float]]:
    direction_value = float(first.median())
    direction = 1 if direction_value > 0 else -1 if direction_value < 0 else 0
    leaders = first.index[direction * first > 0]
    laggards = first.index[direction * first < 0]
    diagnostics = {
        "direction": float(direction),
        "leader_count": float(len(leaders)),
        "laggard_count": float(len(laggards)),
        "laggard_share_first": float("nan"),
        "laggard_share_second": float("nan"),
        "laggard_second_median_aligned": float("nan"),
        "leader_second_median_aligned": float("nan"),
    }
    if direction == 0 or len(leaders) == 0 or len(laggards) == 0:
        return "CASH", diagnostics
    total_first = float(volume_first.sum())
    total_second = float(volume_second.sum())
    if total_first <= 0 or total_second <= 0:
        return "CASH", diagnostics
    laggard_share_first = float(volume_first[laggards].sum() / total_first)
    laggard_share_second = float(volume_second[laggards].sum() / total_second)
    laggard_aligned = float((direction * second[laggards]).median())
    leader_aligned = float((direction * second[leaders]).median())
    diagnostics.update(
        {
            "laggard_share_first": laggard_share_first,
            "laggard_share_second": laggard_share_second,
            "laggard_second_median_aligned": laggard_aligned,
            "leader_second_median_aligned": leader_aligned,
        }
    )
    active = (
        laggard_share_second > laggard_share_first
        and laggard_aligned > 0
        and leader_aligned >= 0
    )
    if not active:
        return "CASH", diagnostics
    return ("UPRO" if direction > 0 else "SPXU"), diagnostics


def load_states() -> tuple[dict[pd.Timestamp, dict[str, Any]], dict[str, Any]]:
    frame = pd.read_parquet(BARS)
    frame["session_date"] = pd.to_datetime(frame["session_date"]).dt.normalize()
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    symbols = sorted(stock_symbols())
    states: dict[pd.Timestamp, dict[str, Any]] = {}
    coverage: dict[pd.Timestamp, float] = {}
    included_bar_count = 0
    positive_volume_count = 0
    for day, group in frame.groupby("session_date", sort=True):
        indexed = group.set_index(["symbol", "local_clock"])
        complete = [
            symbol
            for symbol in symbols
            if (symbol, "09:30") in indexed.index
            and (symbol, "10:00") in indexed.index
        ]
        fraction = len(complete) / len(symbols)
        coverage[pd.Timestamp(day)] = fraction
        if (
            fraction < 0.95
            or ("SPY", "09:30") not in indexed.index
            or ("SPY", "10:00") not in indexed.index
        ):
            continue
        first = pd.Series(
            {
                symbol: float(indexed.loc[(symbol, "09:30"), "close"])
                / float(indexed.loc[(symbol, "09:30"), "open"])
                - 1
                for symbol in complete
            }
        )
        second = pd.Series(
            {
                symbol: float(indexed.loc[(symbol, "10:00"), "close"])
                / float(indexed.loc[(symbol, "09:30"), "close"])
                - 1
                for symbol in complete
            }
        )
        volume_first = pd.Series(
            {
                symbol: float(indexed.loc[(symbol, "09:30"), "volume"])
                for symbol in complete
            }
        )
        volume_second = pd.Series(
            {
                symbol: float(indexed.loc[(symbol, "10:00"), "volume"])
                for symbol in complete
            }
        )
        included_bar_count += 2 * len(complete)
        positive_volume_count += int((volume_first > 0).sum() + (volume_second > 0).sum())
        action, diagnostics = trigger(first, second, volume_first, volume_second)
        partitions = {
            "odd_action": [s for i, s in enumerate(symbols) if i % 2 == 1 and s in complete],
            "even_action": [s for i, s in enumerate(symbols) if i % 2 == 0 and s in complete],
            "mod0_action": [s for i, s in enumerate(symbols) if i % 3 == 0 and s in complete],
            "mod1_action": [s for i, s in enumerate(symbols) if i % 3 == 1 and s in complete],
            "mod2_action": [s for i, s in enumerate(symbols) if i % 3 == 2 and s in complete],
        }
        partition_actions = {
            name: trigger(
                first[members],
                second[members],
                volume_first[members],
                volume_second[members],
            )[0]
            for name, members in partitions.items()
        }
        spy_open = float(indexed.loc[("SPY", "09:30"), "open"])
        spy_end = float(indexed.loc[("SPY", "10:00"), "close"])
        spy_return = spy_end / spy_open - 1
        states[pd.Timestamp(day)] = {
            "session_date": pd.Timestamp(day).strftime("%Y-%m-%d"),
            "action": action,
            **partition_actions,
            "spy_action": "UPRO" if spy_return > 0 else "SPXU" if spy_return < 0 else "CASH",
            **diagnostics,
        }
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    integrity = {
        "sha256": hashlib.sha256(BARS.read_bytes()).hexdigest().upper(),
        "manifest_sha256": manifest["sha256"],
        "sessions_requested": manifest["sessions_requested"],
        "valid_sessions": len(states),
        "valid_session_fraction": len(states) / manifest["sessions_requested"],
        "sessions_at_least_95pct_complete": sum(v >= 0.95 for v in coverage.values()),
        "minimum_observed_session_coverage": min(coverage.values()),
        "included_bars": included_bar_count,
        "positive_volume_bars": positive_volume_count,
        "positive_volume_bar_share": positive_volume_count / max(included_bar_count, 1),
        "paid_data": manifest["paid_data"],
        "databento_call": manifest["databento_call"],
    }
    return states, integrity


def primary_action_agreement(
    states: dict[pd.Timestamp, dict[str, Any]], field: str
) -> dict[str, Any]:
    rows = [row for row in states.values() if row["action"] != "CASH"]
    identical = sum(row["action"] == row[field] for row in rows)
    return {
        "primary_signals": len(rows),
        "identical": identical,
        "agreement": identical / max(len(rows), 1),
    }


def signal_overlap(
    states: dict[pd.Timestamp, dict[str, Any]],
    other: dict[pd.Timestamp, dict[str, Any]],
) -> float:
    days = {day for day, row in states.items() if row["action"] != "CASH"}
    other_days = {day for day, row in other.items() if row["action"] != "CASH"}
    return len(days & other_days) / max(len(days), 1)


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
        entry = base.exact_row(frame, v66.v65.clock_stamp(day, "10:31", zone))
        exit_row = base.exact_row(frame, v66.v65.clock_stamp(day, "15:55", zone))
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
        switches[str(year)] = sum(left != right for left, right in zip(actions, actions[1:]))
    agreements = {
        field.removesuffix("_action"): primary_action_agreement(states, field)
        for field in (
            "odd_action",
            "even_action",
            "mod0_action",
            "mod1_action",
            "mod2_action",
            "spy_action",
        )
    }
    old75, _ = v75.load_states()
    old76, _ = v76.load_states()
    overlap = {"v75": signal_overlap(states, old75), "v76": signal_overlap(states, old76)}
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
        "valid_sessions": len(states),
        "signals": active,
        "signals_per_week": active / (753 / 5),
        "selection_share": active / max(len(states), 1),
        "by_year": by_year,
        "upro": counts["UPRO"],
        "spxu": counts["SPXU"],
        "minority_share": minority_share,
        "switches_by_year": switches,
    }
    subset_fields = ("odd", "even", "mod0", "mod1", "mod2")
    gates = {
        "source_hash_matches": integrity["sha256"] == integrity["manifest_sha256"],
        "no_paid_data_or_databento_call": not integrity["paid_data"]
        and not integrity["databento_call"],
        "valid_session_source_coverage_at_least_95_percent": integrity[
            "valid_session_fraction"
        ]
        >= 0.95,
        "positive_volume_bar_share_at_least_99_percent": integrity[
            "positive_volume_bar_share"
        ]
        >= 0.99,
        "at_least_2_signals_per_week": development["signals_per_week"] >= 2.0,
        "at_least_100_signals_each_year": min(by_year.values()) >= 100,
        "minority_action_at_least_30_percent": minority_share >= 0.30,
        "at_least_25_switches_each_year": min(switches.values()) >= 25,
        "selection_share_between_20_and_80_percent": 0.20
        <= development["selection_share"]
        <= 0.80,
        "all_subuniverse_action_agreements_at_least_70_percent": min(
            agreements[field]["agreement"] for field in subset_fields
        )
        >= 0.70,
        "spy_first_hour_action_agreement_at_most_85_percent": agreements["spy"][
            "agreement"
        ]
        <= 0.85,
        "v75_signal_date_overlap_at_most_80_percent": overlap["v75"] <= 0.80,
        "v76_signal_date_overlap_at_most_80_percent": overlap["v76"] <= 0.80,
        "max_month_share_at_most_6_percent": max_month_share <= 0.06,
        "primary_quote_coverage_at_least_95_percent": quotes["primary"]["coverage"]
        >= 0.95,
        "independent_quote_coverage_at_least_90_percent": quotes["independent"][
            "coverage"
        ]
        >= 0.90,
        "no_post_entry_return_read": True,
    }
    payload = {
        "status": "returns_blind_v77_audit",
        "source_integrity": integrity,
        "development_2021_2023": development,
        "agreement": agreements,
        "signal_date_overlap": overlap,
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
        "# Constituent Liquidity Relay Audit v77\n\n"
        + (
            "**All blind gates passed; frozen development P&L is authorized.**"
            if payload["gate_passed"]
            else "**Rejected returns-blind before P&L.**"
        )
        + f"\n\n- Signals: {active} ({development['signals_per_week']:.3f}/week)\n"
        + f"- By year: {by_year}\n"
        + f"- UPRO / SPXU: {counts['UPRO']} / {counts['SPXU']}\n"
        + f"- Selection share: {development['selection_share']:.3%}\n"
        + "- Odd / even / modulo-three agreement: "
        + " / ".join(
            f"{agreements[field]['agreement']:.3%}" for field in subset_fields
        )
        + "\n"
        + f"- SPY first-hour agreement: {agreements['spy']['agreement']:.3%}\n"
        + f"- V75 / V76 signal-date overlap: {overlap['v75']:.3%} / {overlap['v76']:.3%}\n"
        + f"- Positive-volume included bars: {integrity['positive_volume_bar_share']:.3%}\n"
        + f"- Failed gates: {', '.join(failures) if failures else 'none'}\n\n"
        + "No post-entry return was read.\n",
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in payload.items() if key != "states"}, indent=2))


if __name__ == "__main__":
    main()
