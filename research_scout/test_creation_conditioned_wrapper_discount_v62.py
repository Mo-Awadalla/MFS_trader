"""Test the preregistered creation-conditioned wrapper discount v62.

The 2024-2025 partition is not constructed or evaluated unless every frozen
2021-2023 development gate passes. No threshold or horizon search exists here.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import time, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

from research_scout import audit_proshares_primary_market_flows_v60 as flowlib  # noqa: E402
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay  # noqa: E402
from research_scout import test_spy_btc_perpetual_fresh_position_v44 as v44  # noqa: E402
from research_scout import test_upro_spxu_creative_hypotheses as base  # noqa: E402
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16  # noqa: E402
from research_scout import test_upro_spxu_variance_state as common  # noqa: E402

PREREG = (
    ROOT
    / "research_scout"
    / "creation_conditioned_wrapper_discount_prereg_v62.json"
)
FEASIBILITY = (
    ROOT
    / "research_scout"
    / "creation_conditioned_wrapper_discount_returns_blind_audit_v62.json"
)
OUTPUT = (
    ROOT
    / "research_scout"
    / "creation_conditioned_wrapper_discount_results_v62.json"
)
REPORT = (
    ROOT
    / "research_scout"
    / "CREATION_CONDITIONED_WRAPPER_DISCOUNT_REPORT_V62.md"
)

START = pd.Timestamp("2021-01-04")
DEVELOPMENT_END = pd.Timestamp("2023-12-29")
ENTRY = time(9, 33)
EXIT = time(10, 30)
BOOTSTRAP_RESAMPLES = 5000
BOOTSTRAP_BLOCK = 5
BOOTSTRAP_SEED = 620062
EXPECTED_FEATURE_SIGNALS = 315
EXPECTED_DEVELOPMENT_SESSIONS = 753


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


def load_states(
    payload: dict[str, Any], key: str
) -> dict[pd.Timestamp, dict[str, Any]]:
    return {
        pd.Timestamp(row["session_date"]).normalize(): row
        for row in payload[key]
    }


def choose(
    candidates: list[str],
    residuals: dict[str, float],
    *,
    richest: bool = False,
) -> str:
    if not candidates:
        return "CASH"
    if len(candidates) == 1:
        return candidates[0]
    values = [float(residuals[symbol]) for symbol in candidates]
    if values[0] == values[1]:
        return "CASH"
    function = max if richest else min
    target = function(values)
    return candidates[values.index(target)]


def build_variants(
    states: dict[pd.Timestamp, dict[str, Any]]
) -> dict[str, dict[pd.Timestamp, str]]:
    variants = {
        "actual": {},
        "discount_only": {},
        "creation_only": {},
        "redemption_conditioned_discount": {},
        "extra_lag_creation_discount": {},
        "creation_conditioned_premium_continuation": {},
    }
    expected = list(flowlib.load_spy_sessions())
    previous_session = {
        expected[index]: expected[index - 1]
        for index in range(1, len(expected))
    }
    for day, row in sorted(states.items()):
        residuals = {
            symbol: float(row["residuals_underlying_units"][symbol])
            for symbol in ("UPRO", "SPXU")
        }
        flows = {
            symbol: float(row["flows_dollars"][symbol])
            for symbol in ("UPRO", "SPXU")
        }
        variants["actual"][day] = str(row["action"])
        variants["discount_only"][day] = choose(
            [
                symbol
                for symbol in ("UPRO", "SPXU")
                if residuals[symbol] < 0.0
            ],
            residuals,
        )
        variants["creation_only"][day] = choose(
            [
                symbol
                for symbol in ("UPRO", "SPXU")
                if flows[symbol] > 0.01
            ],
            residuals,
        )
        variants["redemption_conditioned_discount"][day] = choose(
            [
                symbol
                for symbol in ("UPRO", "SPXU")
                if flows[symbol] < -0.01 and residuals[symbol] < 0.0
            ],
            residuals,
        )
        lagged_row = states.get(previous_session.get(day))
        lagged_flows = (
            {
                symbol: float(lagged_row["flows_dollars"][symbol])
                for symbol in ("UPRO", "SPXU")
            }
            if lagged_row is not None
            else {}
        )
        variants["extra_lag_creation_discount"][day] = choose(
            [
                symbol
                for symbol in ("UPRO", "SPXU")
                if lagged_flows.get(symbol, 0.0) > 0.01
                and residuals[symbol] < 0.0
            ],
            residuals,
        )
        variants["creation_conditioned_premium_continuation"][day] = choose(
            [
                symbol
                for symbol in ("UPRO", "SPXU")
                if flows[symbol] > 0.01 and residuals[symbol] > 0.0
            ],
            residuals,
            richest=True,
        )
    return variants


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
            or not START <= day <= DEVELOPMENT_END
        ):
            continue
        quotes = sessions.get(day, {}).get(symbol)
        if quotes is None:
            continue
        entry_stamp = v16.stamp(day, ENTRY, quotes.index.tz) + timedelta(
            minutes=delay_minutes
        )
        exit_stamp = v16.stamp(day, EXIT, quotes.index.tz)
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
                "entry_time": entry_stamp,
                "exit_time": exit_stamp,
                "entry_ask": entry_ask,
                "exit_bid": exit_bid,
                "entry_spread_bps": (
                    (float(entry.ask_px_00) - float(entry.bid_px_00))
                    / midpoint
                    * 10_000.0
                ),
                "return": realized,
                "pnl_usd": 100.0 * realized,
            }
        )
    return rows


def moving_block_bootstrap_lower(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return math.nan
    values = np.asarray([row["return"] for row in rows], dtype=float)
    size = len(values)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    starts = np.arange(size)
    means = np.empty(BOOTSTRAP_RESAMPLES, dtype=float)
    blocks_needed = math.ceil(size / BOOTSTRAP_BLOCK)
    for sample_index in range(BOOTSTRAP_RESAMPLES):
        chosen = rng.choice(starts, size=blocks_needed, replace=True)
        sample = np.concatenate(
            [
                values[(start + np.arange(BOOTSTRAP_BLOCK)) % size]
                for start in chosen
            ]
        )[:size]
        means[sample_index] = float(sample.mean())
    return float(np.quantile(means, 0.025))


def summarize(
    rows: list[dict[str, Any]], remove_best: int
) -> dict[str, Any]:
    result = common.summarize(rows, remove_best)
    result["moving_block_bootstrap_95pct_lower_mean_return"] = (
        moving_block_bootstrap_lower(rows)
    )
    result["median_entry_spread_bps"] = (
        float(np.median([row["entry_spread_bps"] for row in rows]))
        if rows
        else math.nan
    )
    result["trades_per_declared_week"] = (
        len(rows) / (EXPECTED_DEVELOPMENT_SESSIONS / 5.0)
    )
    return result


def evaluate_primary(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    variants: dict[str, dict[pd.Timestamp, str]],
) -> dict[str, Any]:
    actual = variants["actual"]
    actual_signal_count = sum(
        action != "CASH" for action in actual.values()
    )
    observed_rows = make_rows(sessions, excluded, actual)
    return {
        "feature_signal_count": actual_signal_count,
        "execution_coverage": len(observed_rows)
        / max(actual_signal_count, 1),
        "observed_bbo": summarize(observed_rows, 10),
        "extra_cent_each_fill": summarize(
            make_rows(
                sessions,
                excluded,
                actual,
                adverse_cents=0.01,
            ),
            10,
        ),
        "five_minute_entry_delay": summarize(
            make_rows(
                sessions,
                excluded,
                actual,
                delay_minutes=5,
            ),
            10,
        ),
        "controls": {
            name: summarize(
                make_rows(sessions, excluded, actions), 10
            )
            for name, actions in variants.items()
            if name != "actual"
        },
        "spy_total_return_hurdle": v44.adjusted_spy_hurdle(
            START, DEVELOPMENT_END
        ),
    }


def evaluate_independent(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    actual: dict[pd.Timestamp, str],
) -> dict[str, Any]:
    signal_count = sum(action != "CASH" for action in actual.values())
    rows = make_rows(sessions, excluded, actual)
    return {
        "feature_signal_count": signal_count,
        "execution_coverage": len(rows) / max(signal_count, 1),
        "observed_bbo": summarize(rows, 5),
    }


def development_gates(
    result: dict[str, Any], independent: dict[str, Any]
) -> dict[str, bool]:
    observed = result["observed_bbo"]
    years = observed.get("year_pnl_usd", {})
    sleeves = observed.get("instrument_pnl_usd", {})
    controls = result["controls"]
    mean_pnl = float(observed["mean_session_pnl_usd"])
    return {
        "minimum_two_executed_trades_per_declared_week": observed[
            "trades_per_declared_week"
        ]
        >= 2.0,
        "signal_execution_coverage_at_least_95_percent": result[
            "execution_coverage"
        ]
        >= 0.95,
        "profit_factor_strictly_above_1_10": observed["profit_factor"] > 1.10,
        "fixed_notional_pnl_positive_each_year": all(
            years.get(str(year), 0.0) > 0.0
            for year in (2021, 2022, 2023)
        ),
        "both_upro_and_spxu_fixed_notional_pnl_positive": all(
            sleeves.get(symbol, 0.0) > 0.0
            for symbol in ("UPRO", "SPXU")
        ),
        "compounded_ending_cash_above_adjusted_spy": observed[
            "ending_cash_usd"
        ]
        > result["spy_total_return_hurdle"]["ending_cash_usd"],
        "positive_after_one_extra_cent_each_fill": result[
            "extra_cent_each_fill"
        ]["fixed_notional_pnl_usd"]
        > 0.0,
        "positive_after_five_minute_entry_delay": result[
            "five_minute_entry_delay"
        ]["fixed_notional_pnl_usd"]
        > 0.0,
        "positive_after_deleting_ten_best_sessions": observed[
            "pnl_without_best_10_sessions_usd"
        ]
        > 0.0,
        "moving_block_bootstrap_lower_mean_above_zero": observed[
            "moving_block_bootstrap_95pct_lower_mean_return"
        ]
        > 0.0,
        "independent_feed_overlap_positive_and_pf_above_one": independent[
            "observed_bbo"
        ]["fixed_notional_pnl_usd"]
        > 0.0
        and independent["observed_bbo"]["profit_factor"] > 1.0,
        "mean_trade_return_above_every_control": all(
            mean_pnl > float(item["mean_session_pnl_usd"])
            for item in controls.values()
        ),
    }


def render(payload: dict[str, Any]) -> str:
    dev = payload["development"]
    observed = dev["observed_bbo"]
    independent = payload["independent_feed_overlap_2023"]["observed_bbo"]
    failures = [
        name for name, passed in dev["gates"].items() if not passed
    ]
    years = observed.get("year_pnl_usd", {})
    sleeves = observed.get("instrument_pnl_usd", {})
    lines = [
        "# Creation-Conditioned Wrapper Discount v62",
        "",
        "## Verdict",
        "",
        (
            "**Development survivor; recent-year feature audit is now allowed.**"
            if dev["gate_passed"]
            else "**Rejected in 2021-2023 development; 2024-2025 remains locked.**"
        ),
        "",
        "## Development result",
        "",
        f"- Executed trades: {observed['sessions']} "
        f"({observed['trades_per_declared_week']:.3f}/declared week)",
        f"- Fixed-$100 P&L: ${observed['fixed_notional_pnl_usd']:.2f}",
        f"- Ending compounded cash: ${observed['ending_cash_usd']:.2f}",
        f"- Adjusted SPY ending value: "
        f"${dev['spy_total_return_hurdle']['ending_cash_usd']:.2f}",
        f"- Profit factor: {observed['profit_factor']:.3f}",
        "- Annual P&L: "
        + ", ".join(
            f"{year}=${years.get(str(year), 0.0):.2f}"
            for year in (2021, 2022, 2023)
        ),
        f"- UPRO / SPXU P&L: ${sleeves.get('UPRO', 0.0):.2f} / "
        f"${sleeves.get('SPXU', 0.0):.2f}",
        f"- Extra-cent stress: "
        f"${dev['extra_cent_each_fill']['fixed_notional_pnl_usd']:.2f}",
        f"- Five-minute-delay stress: "
        f"${dev['five_minute_entry_delay']['fixed_notional_pnl_usd']:.2f}",
        f"- Delete ten best: "
        f"${observed['pnl_without_best_10_sessions_usd']:.2f}",
        f"- Block-bootstrap 95% lower mean return: "
        f"{observed['moving_block_bootstrap_95pct_lower_mean_return']:.6f}",
        f"- Independent 2023 overlap: {independent['sessions']} trades, "
        f"${independent['fixed_notional_pnl_usd']:.2f}, "
        f"PF {independent['profit_factor']:.3f}",
        "",
        "## Controls",
        "",
    ]
    for name, item in dev["controls"].items():
        lines.append(
            f"- {name}: ${item['fixed_notional_pnl_usd']:.2f}, "
            f"mean ${item['mean_session_pnl_usd']:.4f}"
        )
    lines.extend(["", "## Gates", ""])
    lines.extend(
        f"- {name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in dev["gates"].items()
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
    if not PREREG.exists():
        raise FileNotFoundError("Missing preregistration")
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    feasibility = json.loads(FEASIBILITY.read_text(encoding="utf-8"))
    if not feasibility.get("gate_passed"):
        raise RuntimeError("Returns-blind V62 construction did not pass")

    primary_states = load_states(feasibility, "states")
    independent_states = load_states(
        feasibility, "independent_states_2023"
    )
    variants = build_variants(primary_states)
    independent_variants = build_variants(independent_states)
    actual_count = sum(
        action != "CASH" for action in variants["actual"].values()
    )
    if actual_count != EXPECTED_FEATURE_SIGNALS:
        raise RuntimeError(
            f"Feature signal count changed: {actual_count} "
            f"!= {EXPECTED_FEATURE_SIGNALS}"
        )

    arca = relay.sessions(relay.ARCA_PATH)
    arca_excluded = relay.degraded(relay.ARCA_CONDITIONS)
    development = evaluate_primary(arca, arca_excluded, variants)

    equs = relay.sessions(relay.EQUS_PATH)
    equs_excluded = relay.degraded(relay.EQUS_CONDITIONS)
    independent = evaluate_independent(
        equs, equs_excluded, independent_variants["actual"]
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
            "development_survivor_recent_feature_audit_allowed"
            if development["gate_passed"]
            else "rejected_in_development_holdout_locked"
        ),
        "development": development,
        "independent_feed_overlap_2023": independent,
        "recent_years_status": (
            "unlocked_for_a_separate_point_in_time_feature_audit"
            if development["gate_passed"]
            else "locked_not_read"
        ),
        "new_databento_calls_or_purchases": False,
    }
    safe = json_safe(payload)
    OUTPUT.write_text(json.dumps(safe, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(render(safe), encoding="utf-8")
    print(json.dumps(safe, indent=2))


if __name__ == "__main__":
    main()
