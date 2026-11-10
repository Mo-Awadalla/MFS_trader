"""Frozen 2021-2023 P&L test for v67 inventory superposition.

The script does not load or evaluate a 2024-2025 signal partition. There is no
parameter search and no outcome-dependent branch.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import pandas as pd  # noqa: E402

from research_scout import (  # noqa: E402
    audit_leveraged_gamma_es_inventory_superposition_v67 as audit,
)
from research_scout import (  # noqa: E402
    audit_upro_spxu_cross_inverse_aggressor_relay as relay,
)
from research_scout import (  # noqa: E402
    test_spy_btc_perpetual_fresh_position_v44 as v44,
)
from research_scout import test_upro_spxu_creative_hypotheses as base  # noqa: E402
from research_scout import test_upro_spxu_variance_state as common  # noqa: E402

PREREG = (
    ROOT
    / "research_scout"
    / "leveraged_gamma_es_inventory_superposition_prereg_v67.json"
)
FEASIBILITY = (
    ROOT
    / "research_scout"
    / "leveraged_gamma_es_inventory_superposition_returns_blind_audit_v67.json"
)
OUTPUT = (
    ROOT
    / "research_scout"
    / "leveraged_gamma_es_inventory_superposition_results_v67.json"
)
REPORT = (
    ROOT
    / "research_scout"
    / "LEVERAGED_GAMMA_ES_INVENTORY_SUPERPOSITION_REPORT_V67.md"
)

START = pd.Timestamp("2021-01-01")
END = pd.Timestamp("2023-12-31")
ENTRY = "15:31"
EXIT = "15:59"
EXPECTED_SESSIONS = 753
EXPECTED_SIGNALS = 733
BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_BLOCK = 5
BOOTSTRAP_SEED = 20260730
PERMUTATION_SAMPLES = 5_000
PERMUTATION_SEED = 670067


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


def load_actions(
    payload: dict[str, Any],
) -> dict[str, dict[pd.Timestamp, str]]:
    actual: dict[pd.Timestamp, str] = {}
    fund_only: dict[pd.Timestamp, str] = {}
    es_only: dict[pd.Timestamp, str] = {}
    for row in payload["states"]:
        day = pd.Timestamp(row["session_date"]).normalize()
        actual[day] = str(row["action"])
        fund_only[day] = str(row["fund_only_action"])
        es_only[day] = str(row["es_only_action"])

    controls = payload["control_actions"]
    fixed = {
        pd.Timestamp(row["session_date"]).normalize(): str(row["action"])
        for row in controls["fixed_coefficient"]
    }
    shifted = {
        pd.Timestamp(row["session_date"]).normalize(): str(row["action"])
        for row in controls["shifted_es"]
    }
    return {
        "actual": actual,
        "fund_only": fund_only,
        "es_only": es_only,
        "fixed_aum_coefficient": fixed,
        "one_session_shifted_es": shifted,
    }


def make_rows(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    actions: dict[pd.Timestamp, str],
    *,
    adverse_cents: float = 0.0,
    delay_minutes: int = 0,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for day, symbol in sorted(actions.items()):
        if (
            symbol == "CASH"
            or day in excluded
            or not START <= day <= END
        ):
            continue
        quotes = sessions.get(day, {}).get(symbol)
        if quotes is None:
            continue
        entry_stamp = audit.clock_stamp(
            day, ENTRY, quotes.index.tz
        ) + timedelta(minutes=delay_minutes)
        exit_stamp = audit.clock_stamp(day, EXIT, quotes.index.tz)
        entry = base.quote_at(quotes, entry_stamp, 0)
        exit_quote = base.quote_at(quotes, exit_stamp, 0)
        if entry is None or exit_quote is None:
            continue
        entry_ask = float(entry.ask_px_00) + adverse_cents
        exit_bid = float(exit_quote.bid_px_00) - adverse_cents
        if min(entry_ask, exit_bid) <= 0:
            continue
        realized = exit_bid / entry_ask - 1.0
        midpoint = (
            float(entry.bid_px_00) + float(entry.ask_px_00)
        ) / 2.0
        rows.append(
            {
                "date": day,
                "symbol": symbol,
                "return": realized,
                "pnl_usd": 100.0 * realized,
                "entry_spread_bps": (
                    (float(entry.ask_px_00) - float(entry.bid_px_00))
                    / midpoint
                    * 10_000.0
                ),
            }
        )
    return rows


def session_vector(rows: list[dict[str, Any]]) -> np.ndarray:
    lookup = {
        pd.Timestamp(row["date"]).normalize(): float(row["return"])
        for row in rows
    }
    days = pd.bdate_range(START, END)
    return np.asarray([lookup.get(day.normalize(), 0.0) for day in days])


def bootstrap_lower(values: np.ndarray) -> float:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    starts = np.arange(len(values))
    offsets = np.arange(BOOTSTRAP_BLOCK)
    blocks = math.ceil(len(values) / BOOTSTRAP_BLOCK)
    means = np.empty(BOOTSTRAP_SAMPLES)
    for index in range(BOOTSTRAP_SAMPLES):
        selected = rng.choice(starts, blocks, replace=True)
        sample = np.concatenate(
            [values[(start + offsets) % len(values)] for start in selected]
        )[: len(values)]
        means[index] = sample.mean()
    return float(np.quantile(means, 0.025))


def summarize(
    rows: list[dict[str, Any]], *, robust: bool = False
) -> dict[str, Any]:
    result = common.summarize(rows, 0)
    result["trades_per_declared_week"] = len(rows) / (
        EXPECTED_SESSIONS / 5.0
    )
    result["median_entry_spread_bps"] = (
        float(np.median([row["entry_spread_bps"] for row in rows]))
        if rows
        else math.nan
    )
    if robust:
        ordered = np.sort(
            np.asarray([float(row["return"]) for row in rows])
        )
        result["pnl_without_best_10_sessions_usd"] = float(
            100.0 * ordered[:-10].sum()
        )
        result["moving_block_bootstrap_95pct_lower_mean_return"] = (
            bootstrap_lower(session_vector(rows))
        )
    return result


def return_panel(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    days: list[pd.Timestamp],
) -> dict[tuple[pd.Timestamp, str], float]:
    panel: dict[tuple[pd.Timestamp, str], float] = {}
    for day in days:
        if day in excluded:
            continue
        for symbol in ("UPRO", "SPXU"):
            quotes = sessions.get(day, {}).get(symbol)
            if quotes is None:
                continue
            entry = base.quote_at(
                quotes, audit.clock_stamp(day, ENTRY, quotes.index.tz), 0
            )
            exit_quote = base.quote_at(
                quotes, audit.clock_stamp(day, EXIT, quotes.index.tz), 0
            )
            if entry is None or exit_quote is None:
                continue
            entry_ask = float(entry.ask_px_00)
            exit_bid = float(exit_quote.bid_px_00)
            if min(entry_ask, exit_bid) > 0:
                panel[(day, symbol)] = exit_bid / entry_ask - 1.0
    return panel


def direction_permutation(
    actual_rows: list[dict[str, Any]],
    actions: dict[pd.Timestamp, str],
    panel: dict[tuple[pd.Timestamp, str], float],
) -> dict[str, Any]:
    days = sorted(actions)
    directions = np.asarray(
        [1 if actions[day] == "UPRO" else -1 for day in days],
        dtype=int,
    )
    actual = float(np.mean([row["return"] for row in actual_rows]))
    rng = np.random.default_rng(PERMUTATION_SEED)
    samples = np.empty(PERMUTATION_SAMPLES)
    for index in range(PERMUTATION_SAMPLES):
        shuffled = rng.permutation(directions)
        values = [
            panel[(day, "UPRO" if direction > 0 else "SPXU")]
            for day, direction in zip(days, shuffled, strict=True)
            if (day, "UPRO" if direction > 0 else "SPXU") in panel
        ]
        samples[index] = float(np.mean(values))
    return {
        "actual_mean_return": actual,
        "permuted_mean_return": float(samples.mean()),
        "permuted_95pct_quantile": float(np.quantile(samples, 0.95)),
        "one_sided_p_value": float(
            (1 + int((samples >= actual).sum()))
            / (1 + PERMUTATION_SAMPLES)
        ),
        "samples": PERMUTATION_SAMPLES,
    }


def development_gates(
    development: dict[str, Any],
    independent: dict[str, Any],
) -> dict[str, bool]:
    actual = development["observed_bbo"]
    years = actual.get("year_pnl_usd", {})
    sleeves = actual.get("instrument_pnl_usd", {})
    controls = development["controls"]
    return {
        "at_least_two_executed_trades_per_declared_week": actual[
            "trades_per_declared_week"
        ]
        >= 2.0,
        "execution_coverage_at_least_95_percent": development[
            "execution_coverage"
        ]
        >= 0.95,
        "profit_factor_at_least_1_10": actual["profit_factor"] >= 1.10,
        "positive_each_development_year": all(
            years.get(str(year), 0.0) > 0.0 for year in (2021, 2022, 2023)
        ),
        "both_upro_and_spxu_positive": all(
            sleeves.get(symbol, 0.0) > 0.0
            for symbol in ("UPRO", "SPXU")
        ),
        "compounded_ending_cash_above_adjusted_spy": actual[
            "ending_cash_usd"
        ]
        > development["spy_total_return_hurdle"]["ending_cash_usd"],
        "positive_after_one_extra_cent_each_fill": development[
            "extra_cent_each_fill"
        ]["fixed_notional_pnl_usd"]
        > 0.0,
        "positive_after_five_minute_entry_delay": development[
            "five_minute_entry_delay"
        ]["fixed_notional_pnl_usd"]
        > 0.0,
        "positive_after_deleting_ten_best_sessions": actual[
            "pnl_without_best_10_sessions_usd"
        ]
        > 0.0,
        "moving_block_bootstrap_lower_mean_above_zero": actual[
            "moving_block_bootstrap_95pct_lower_mean_return"
        ]
        > 0.0,
        "independent_2023_overlap_positive": (
            independent["fixed_notional_pnl_usd"] > 0.0
            and independent["profit_factor"] > 1.0
        ),
        "combined_mean_trade_above_all_controls": all(
            actual["mean_session_pnl_usd"]
            > item["mean_session_pnl_usd"]
            for item in controls.values()
        ),
    }


def render(payload: dict[str, Any]) -> str:
    development = payload["development"]
    actual = development["observed_bbo"]
    years = actual.get("year_pnl_usd", {})
    sleeves = actual.get("instrument_pnl_usd", {})
    independent = payload["independent_feed_overlap_2023"]
    failures = [
        name for name, passed in development["gates"].items() if not passed
    ]
    lines = [
        "# Leveraged-Fund Gamma / ES Inventory Superposition v67",
        "",
        "## Verdict",
        "",
        (
            "**Every 2021–2023 development gate passed; recent years are "
            "unlocked for one frozen evaluation.**"
            if development["gate_passed"]
            else "**Rejected in 2021–2023; recent years remain locked.**"
        ),
        "",
        "## Frozen result",
        "",
        f"- Trades: {actual['sessions']} "
        f"({actual['trades_per_declared_week']:.3f}/declared week)",
        f"- Fixed-$100 P&L: ${actual['fixed_notional_pnl_usd']:.2f}",
        f"- Ending compounded cash: ${actual['ending_cash_usd']:.2f}",
        f"- Adjusted SPY ending value: "
        f"${development['spy_total_return_hurdle']['ending_cash_usd']:.2f}",
        f"- Profit factor: {actual['profit_factor']:.3f}",
        "- Annual P&L: "
        + ", ".join(
            f"{year}=${years.get(str(year), 0.0):.2f}"
            for year in (2021, 2022, 2023)
        ),
        f"- UPRO / SPXU P&L: ${sleeves.get('UPRO', 0.0):.2f} / "
        f"${sleeves.get('SPXU', 0.0):.2f}",
        f"- Extra-cent stress: "
        f"${development['extra_cent_each_fill']['fixed_notional_pnl_usd']:.2f}",
        f"- Five-minute delay: "
        f"${development['five_minute_entry_delay']['fixed_notional_pnl_usd']:.2f}",
        f"- Delete ten best sessions: "
        f"${actual['pnl_without_best_10_sessions_usd']:.2f}",
        f"- Bootstrap lower mean: "
        f"{actual['moving_block_bootstrap_95pct_lower_mean_return']:.6f}",
        f"- Direction permutation p: "
        f"{development['direction_permutation']['one_sided_p_value']:.4f}",
        f"- Independent overlap: {independent['sessions']} trades, "
        f"${independent['fixed_notional_pnl_usd']:.2f}, "
        f"PF {independent['profit_factor']:.3f}",
        "",
        "## Controls",
        "",
    ]
    for name, item in development["controls"].items():
        lines.append(
            f"- {name}: {item['sessions']} trades, "
            f"${item['fixed_notional_pnl_usd']:.2f}, "
            f"mean ${item['mean_session_pnl_usd']:.4f}"
        )
    lines.extend(["", "## Gates", ""])
    lines.extend(
        f"- {name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in development["gates"].items()
    )
    lines.extend(
        [
            "",
            "Failed gates: " + (", ".join(failures) if failures else "none"),
            "",
            f"Recent-year status: {payload['recent_years_status']}.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    feasibility = json.loads(FEASIBILITY.read_text(encoding="utf-8"))
    if not feasibility.get("gate_passed"):
        raise RuntimeError("Returns-blind v67 audit did not pass")
    actions = load_actions(feasibility)
    feature_signals = sum(
        action != "CASH" for action in actions["actual"].values()
    )
    if feature_signals != EXPECTED_SIGNALS:
        raise RuntimeError(
            f"Feature signal count changed: {feature_signals} "
            f"!= {EXPECTED_SIGNALS}"
        )

    arca = relay.sessions(relay.ARCA_PATH)
    arca_excluded = relay.degraded(relay.ARCA_CONDITIONS)
    actual_rows = make_rows(arca, arca_excluded, actions["actual"])
    development = {
        "feature_signal_count": feature_signals,
        "execution_coverage": len(actual_rows) / feature_signals,
        "observed_bbo": summarize(actual_rows, robust=True),
        "extra_cent_each_fill": summarize(
            make_rows(
                arca,
                arca_excluded,
                actions["actual"],
                adverse_cents=0.01,
            )
        ),
        "five_minute_entry_delay": summarize(
            make_rows(
                arca,
                arca_excluded,
                actions["actual"],
                delay_minutes=5,
            )
        ),
        "controls": {
            name: summarize(make_rows(arca, arca_excluded, control))
            for name, control in actions.items()
            if name != "actual"
        },
        "spy_total_return_hurdle": v44.adjusted_spy_hurdle(START, END),
    }
    panel = return_panel(
        arca, arca_excluded, sorted(actions["actual"])
    )
    development["direction_permutation"] = direction_permutation(
        actual_rows, actions["actual"], panel
    )

    equs = relay.sessions(relay.EQUS_PATH)
    equs_excluded = relay.degraded(relay.EQUS_CONDITIONS)
    independent = summarize(
        make_rows(equs, equs_excluded, actions["actual"])
    )
    gates = development_gates(development, independent)
    development["gates"] = gates
    development["gate_passed"] = all(gates.values())

    payload = {
        "specification": str(PREREG.relative_to(ROOT)).replace("\\", "/"),
        "specification_sha256": hashlib.sha256(
            PREREG.read_bytes()
        ).hexdigest(),
        "specification_id": prereg["specification_id"],
        "status": (
            "development_survivor_recent_years_unlocked"
            if development["gate_passed"]
            else "rejected_in_development_recent_years_locked"
        ),
        "development": development,
        "independent_feed_overlap_2023": independent,
        "recent_years_status": (
            "unlocked_for_one_frozen_evaluation"
            if development["gate_passed"]
            else "locked_not_read"
        ),
        "new_databento_calls_or_purchases": False,
    }
    safe = json_safe(payload)
    OUTPUT.write_text(
        json.dumps(safe, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    REPORT.write_text(render(safe), encoding="utf-8")
    print(json.dumps(safe, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
