"""Frozen 2021-2023 P&L test of realized TGA reserve transfer v74."""

from __future__ import annotations

import bisect
import hashlib
import json
import math
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import pandas as pd  # noqa: E402

from research_scout import audit_tga_realized_reserve_transfer_v74 as audit  # noqa: E402
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay  # noqa: E402
from research_scout import test_spy_btc_perpetual_fresh_position_v44 as v44  # noqa: E402
from research_scout import test_upro_spxu_creative_hypotheses as base  # noqa: E402
from research_scout import test_upro_spxu_variance_state as common  # noqa: E402

PREREG = ROOT / "research_scout" / "tga_realized_reserve_transfer_prereg_v74.json"
FEASIBILITY = (
    ROOT / "research_scout" / "tga_realized_reserve_transfer_returns_blind_audit_v74.json"
)
OUTPUT = ROOT / "research_scout" / "tga_realized_reserve_transfer_results_v74.json"
REPORT = ROOT / "research_scout" / "TGA_REALIZED_RESERVE_TRANSFER_REPORT_V74.md"
SPY_DAILY = ROOT / "data" / "parquet" / "equity" / "alpaca_sip" / "SPY_1d.parquet"
START = pd.Timestamp("2021-01-04")
END = pd.Timestamp("2023-12-29")
ENTRY = "09:33"
EXIT = "15:30"
YEARS = (2021, 2022, 2023)
EXPECTED_SIGNALS = 745
EXPECTED_SESSIONS = 753
BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_BLOCK = 5
BOOTSTRAP_SEED = 740074
PERMUTATION_SAMPLES = 5_000
PERMUTATION_SEED = 740174


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def extra_session_lag(
    states: dict[pd.Timestamp, dict[str, Any]]
) -> dict[pd.Timestamp, str]:
    sessions = sorted(
        pd.Timestamp(day).normalize() for day in audit.v66.flowlib.load_spy_sessions()
    )
    result = {}
    for day, row in states.items():
        index = bisect.bisect_right(sessions, day)
        if index < len(sessions):
            result[sessions[index]] = str(row["action"])
    return result


def prior_spy_actions(
    states: dict[pd.Timestamp, dict[str, Any]]
) -> dict[pd.Timestamp, str]:
    frame = pd.read_parquet(SPY_DAILY).copy()
    frame["session_date"] = (
        pd.to_datetime(frame["timestamp"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
        .dt.normalize()
    )
    frame = frame.sort_values("session_date")
    frame["action"] = [
        "UPRO" if close > opening else "SPXU" if close < opening else "CASH"
        for opening, close in zip(frame["open"], frame["close"], strict=True)
    ]
    prior = {
        pd.Timestamp(current.session_date).normalize(): str(previous.action)
        for previous, current in zip(
            frame.iloc[:-1].itertuples(index=False),
            frame.iloc[1:].itertuples(index=False),
            strict=True,
        )
    }
    return {day: prior.get(day, "CASH") for day in states}


def action_variants(
    states: dict[pd.Timestamp, dict[str, Any]]
) -> dict[str, dict[pd.Timestamp, str]]:
    return {
        "actual": {day: row["action"] for day, row in states.items()},
        "extra_publication_session_lag": extra_session_lag(states),
        "prior_spy_direction": prior_spy_actions(states),
    }


def make_rows(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    actions: dict[pd.Timestamp, str],
    *,
    adverse_cents: float = 0.0,
    delay_minutes: int = 0,
) -> list[dict[str, Any]]:
    rows = []
    for day, symbol in sorted(actions.items()):
        if symbol == "CASH" or day in excluded or not START <= day <= END:
            continue
        quotes = sessions.get(day, {}).get(symbol)
        if quotes is None:
            continue
        entry_stamp = audit.v66.v65.clock_stamp(
            day, ENTRY, quotes.index.tz
        ) + timedelta(minutes=delay_minutes)
        exit_stamp = audit.v66.v65.clock_stamp(day, EXIT, quotes.index.tz)
        entry = base.quote_at(quotes, entry_stamp, 0)
        exit_quote = base.quote_at(quotes, exit_stamp, 0)
        if entry is None or exit_quote is None:
            continue
        entry_ask = float(entry.ask_px_00) + adverse_cents
        exit_bid = float(exit_quote.bid_px_00) - adverse_cents
        if min(entry_ask, exit_bid) <= 0:
            continue
        realized = exit_bid / entry_ask - 1
        rows.append(
            {
                "date": day,
                "symbol": symbol,
                "return": realized,
                "pnl_usd": 100.0 * realized,
            }
        )
    return rows


def summarize(rows: list[dict[str, Any]], remove_best: int = 0) -> dict[str, Any]:
    result = common.summarize(rows, remove_best)
    result["trades_per_declared_week"] = len(rows) / (EXPECTED_SESSIONS / 5)
    return result


def bootstrap_lower(rows: list[dict[str, Any]]) -> float:
    values = np.asarray([row["return"] for row in rows], dtype=float)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    starts = np.arange(len(values))
    offsets = np.arange(BOOTSTRAP_BLOCK)
    blocks = math.ceil(len(values) / BOOTSTRAP_BLOCK)
    means = np.empty(BOOTSTRAP_SAMPLES)
    for index in range(BOOTSTRAP_SAMPLES):
        chosen = rng.choice(starts, blocks, replace=True)
        sample = np.concatenate(
            [values[(start + offsets) % len(values)] for start in chosen]
        )[: len(values)]
        means[index] = sample.mean()
    return float(np.quantile(means, 0.025))


def return_panel(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    days: list[pd.Timestamp],
) -> dict[tuple[pd.Timestamp, str], float]:
    result = {}
    for day in days:
        if day in excluded:
            continue
        for symbol in ("UPRO", "SPXU"):
            quotes = sessions.get(day, {}).get(symbol)
            if quotes is None:
                continue
            entry = base.quote_at(
                quotes,
                audit.v66.v65.clock_stamp(day, ENTRY, quotes.index.tz),
                0,
            )
            exit_quote = base.quote_at(
                quotes,
                audit.v66.v65.clock_stamp(day, EXIT, quotes.index.tz),
                0,
            )
            if entry is not None and exit_quote is not None:
                result[(day, symbol)] = (
                    float(exit_quote.bid_px_00) / float(entry.ask_px_00) - 1
                )
    return result


def month_permutation(
    rows: list[dict[str, Any]],
    states: dict[pd.Timestamp, dict[str, Any]],
    panel: dict[tuple[pd.Timestamp, str], float],
) -> dict[str, Any]:
    days = sorted(
        row["date"] for row in rows
        if (row["date"], "UPRO") in panel and (row["date"], "SPXU") in panel
    )
    directions = {
        day: 1 if states[day]["action"] == "UPRO" else -1 for day in days
    }
    grouped: defaultdict[str, list[pd.Timestamp]] = defaultdict(list)
    for day in days:
        grouped[day.strftime("%Y-%m")].append(day)
    actual = float(np.mean([row["return"] for row in rows]))
    rng = np.random.default_rng(PERMUTATION_SEED)
    samples = np.empty(PERMUTATION_SAMPLES)
    for index in range(PERMUTATION_SAMPLES):
        assigned = {}
        for month_days in grouped.values():
            shuffled = rng.permutation([directions[day] for day in month_days])
            assigned.update(zip(month_days, shuffled, strict=True))
        samples[index] = float(
            np.mean(
                [
                    panel[(day, "UPRO" if assigned[day] > 0 else "SPXU")]
                    for day in days
                ]
            )
        )
    p_value = (1 + int((samples >= actual).sum())) / (1 + PERMUTATION_SAMPLES)
    return {
        "actual_mean_return": actual,
        "permuted_mean_return": float(samples.mean()),
        "permuted_95pct_quantile": float(np.quantile(samples, 0.95)),
        "one_sided_p_value": float(p_value),
        "samples": PERMUTATION_SAMPLES,
        "stratification": "calendar month",
    }


def gates(dev: dict[str, Any], independent: dict[str, Any]) -> dict[str, bool]:
    actual = dev["observed_bbo"]
    years = actual.get("year_pnl_usd", {})
    sleeves = actual.get("instrument_pnl_usd", {})
    return {
        "at_least_2_executed_trades_per_declared_week": actual[
            "trades_per_declared_week"
        ] >= 2,
        "execution_coverage_at_least_95_percent": dev["execution_coverage"] >= 0.95,
        "profit_factor_at_least_1_10": actual["profit_factor"] >= 1.10,
        "positive_each_development_year": all(
            years.get(str(year), 0.0) > 0 for year in YEARS
        ),
        "both_upro_and_spxu_positive": all(
            sleeves.get(symbol, 0.0) > 0 for symbol in ("UPRO", "SPXU")
        ),
        "ending_cash_above_adjusted_spy": actual["ending_cash_usd"]
        > dev["spy_total_return_hurdle"]["ending_cash_usd"],
        "positive_after_one_extra_cent_each_fill": dev["extra_cent_each_fill"][
            "fixed_notional_pnl_usd"
        ] > 0,
        "positive_after_09_38_entry_delay": dev["five_minute_entry_delay"][
            "fixed_notional_pnl_usd"
        ] > 0,
        "positive_after_deleting_best_10_sessions": actual[
            "pnl_without_best_10_sessions_usd"
        ] > 0,
        "block_bootstrap_lower_mean_above_zero": dev[
            "block_bootstrap_95pct_lower_mean_return"
        ] > 0,
        "month_stratified_permutation_p_below_0_05": dev[
            "month_stratified_direction_permutation"
        ]["one_sided_p_value"] < 0.05,
        "independent_overlap_positive_pf_above_one": (
            independent["fixed_notional_pnl_usd"] > 0
            and independent["profit_factor"] > 1
        ),
        "mean_above_extra_publication_session_lag": actual[
            "mean_session_pnl_usd"
        ] > dev["controls"]["extra_publication_session_lag"]["mean_session_pnl_usd"],
        "mean_above_prior_spy_direction_control": actual["mean_session_pnl_usd"]
        > dev["controls"]["prior_spy_direction"]["mean_session_pnl_usd"],
    }


def render(payload: dict[str, Any]) -> str:
    dev = payload["development"]
    actual = dev["observed_bbo"]
    years = actual.get("year_pnl_usd", {})
    sleeves = actual.get("instrument_pnl_usd", {})
    independent = payload["independent_feed_overlap"]
    failures = [name for name, passed in dev["gates"].items() if not passed]
    return "\n".join(
        [
            "# TGA Realized Reserve Transfer v74",
            "",
            "## Verdict",
            "",
            (
                "**Development survivor; recent-year testing is authorized.**"
                if dev["gate_passed"]
                else "**Rejected in 2021–2023; recent years remain locked.**"
            ),
            "",
            f"- Trades: {actual['sessions']} "
            f"({actual['trades_per_declared_week']:.3f}/declared week)",
            f"- Fixed-$100 P&L: ${actual['fixed_notional_pnl_usd']:.2f}",
            f"- Ending cash / adjusted SPY: ${actual['ending_cash_usd']:.2f} / "
            f"${dev['spy_total_return_hurdle']['ending_cash_usd']:.2f}",
            f"- Profit factor: {actual['profit_factor']:.3f}",
            "- Annual P&L: "
            + ", ".join(
                f"{year}=${years.get(str(year), 0.0):.2f}" for year in YEARS
            ),
            f"- UPRO / SPXU: ${sleeves.get('UPRO', 0.0):.2f} / "
            f"${sleeves.get('SPXU', 0.0):.2f}",
            f"- Extra-cent / 09:38 delay: "
            f"${dev['extra_cent_each_fill']['fixed_notional_pnl_usd']:.2f} / "
            f"${dev['five_minute_entry_delay']['fixed_notional_pnl_usd']:.2f}",
            f"- Delete ten: ${actual['pnl_without_best_10_sessions_usd']:.2f}",
            f"- Bootstrap lower mean: "
            f"{dev['block_bootstrap_95pct_lower_mean_return']:.6f}",
            f"- Month-stratified permutation p: "
            f"{dev['month_stratified_direction_permutation']['one_sided_p_value']:.4f}",
            f"- Independent overlap: {independent['sessions']} trades, "
            f"${independent['fixed_notional_pnl_usd']:.2f}, "
            f"PF {independent['profit_factor']:.3f}",
            f"- Extra-lag / prior-SPY control means: "
            f"${dev['controls']['extra_publication_session_lag']['mean_session_pnl_usd']:.4f} / "
            f"${dev['controls']['prior_spy_direction']['mean_session_pnl_usd']:.4f}",
            "",
            "Failed gates: " + (", ".join(failures) if failures else "none"),
            "",
            f"Recent-year status: {payload['recent_years_status']}.",
            "",
        ]
    )


def main() -> None:
    feasibility = json.loads(FEASIBILITY.read_text(encoding="utf-8"))
    if not feasibility.get("gate_passed"):
        raise RuntimeError("Returns-blind v74 construction did not pass")
    records, integrity = audit.load_records()
    states = audit.build_states(records)
    variants = action_variants(states)
    signal_count = sum(action != "CASH" for action in variants["actual"].values())
    if signal_count != EXPECTED_SIGNALS:
        raise RuntimeError(f"Feature signals changed: {signal_count} != {EXPECTED_SIGNALS}")
    arca = relay.sessions(relay.ARCA_PATH)
    arca_excluded = relay.degraded(relay.ARCA_CONDITIONS)
    actual_rows = make_rows(arca, arca_excluded, variants["actual"])
    dev = {
        "source_integrity": integrity,
        "feature_signal_count": signal_count,
        "execution_coverage": len(actual_rows) / signal_count,
        "observed_bbo": summarize(actual_rows, 10),
        "extra_cent_each_fill": summarize(
            make_rows(
                arca,
                arca_excluded,
                variants["actual"],
                adverse_cents=0.01,
            )
        ),
        "five_minute_entry_delay": summarize(
            make_rows(
                arca,
                arca_excluded,
                variants["actual"],
                delay_minutes=5,
            )
        ),
        "controls": {
            name: summarize(make_rows(arca, arca_excluded, actions))
            for name, actions in variants.items()
            if name != "actual"
        },
        "spy_total_return_hurdle": v44.adjusted_spy_hurdle(START, END),
        "block_bootstrap_95pct_lower_mean_return": bootstrap_lower(actual_rows),
    }
    panel = return_panel(arca, arca_excluded, sorted(states))
    dev["month_stratified_direction_permutation"] = month_permutation(
        actual_rows, states, panel
    )
    equs = relay.sessions(relay.EQUS_PATH)
    equs_excluded = relay.degraded(relay.EQUS_CONDITIONS)
    independent = summarize(
        make_rows(equs, equs_excluded, variants["actual"])
    )
    frozen = gates(dev, independent)
    dev["gates"] = frozen
    dev["gate_passed"] = all(frozen.values())
    payload = {
        "candidate": "v74",
        "specification": str(PREREG.relative_to(ROOT)).replace("\\", "/"),
        "specification_sha256": hashlib.sha256(PREREG.read_bytes()).hexdigest(),
        "status": (
            "development_survivor_recent_year_testing_authorized"
            if dev["gate_passed"]
            else "rejected_in_development_recent_years_locked"
        ),
        "development": dev,
        "independent_feed_overlap": independent,
        "recent_years_status": (
            "unlocked_for_unchanged_feature_acquisition_and_test"
            if dev["gate_passed"]
            else "locked_not_read"
        ),
        "new_databento_calls_or_purchases": False,
    }
    safe = json_safe(payload)
    OUTPUT.write_text(
        json.dumps(safe, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    REPORT.write_text(render(safe), encoding="utf-8")
    print(json.dumps(safe, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
