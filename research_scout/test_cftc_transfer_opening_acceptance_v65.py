"""Frozen 2021-2023 test of CFTC transfer / ES opening acceptance v65.

Recent years are neither loaded nor evaluated unless every development gate
passes. The script contains no parameter search.
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

from research_scout import audit_cftc_transfer_opening_acceptance_v65 as audit  # noqa: E402
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay  # noqa: E402
from research_scout import test_es_auction_polarity_transfer as eslib  # noqa: E402
from research_scout import test_spy_btc_perpetual_fresh_position_v44 as v44  # noqa: E402
from research_scout import test_upro_spxu_creative_hypotheses as base  # noqa: E402
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16  # noqa: E402
from research_scout import test_upro_spxu_variance_state as common  # noqa: E402

PREREG = (
    ROOT
    / "research_scout"
    / "cftc_transfer_opening_acceptance_prereg_v65.json"
)
FEASIBILITY = (
    ROOT
    / "research_scout"
    / "cftc_transfer_opening_acceptance_returns_blind_audit_v65.json"
)
OUTPUT = (
    ROOT
    / "research_scout"
    / "cftc_transfer_opening_acceptance_results_v65.json"
)
REPORT = (
    ROOT
    / "research_scout"
    / "CFTC_TRANSFER_OPENING_ACCEPTANCE_REPORT_V65.md"
)

START = pd.Timestamp("2021-01-04")
END = pd.Timestamp("2023-12-29")
ENTRY_CLOCK = "09:36"
EXIT_CLOCK = "15:30"
EXPECTED_SESSIONS = 753
EXPECTED_FEATURE_SIGNALS = 381
BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_BLOCK_REPORTS = 4
BOOTSTRAP_SEED = 650065
PERMUTATION_SAMPLES = 5_000
PERMUTATION_SEED = 650165


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


def shifted_direction_lookup(reports: pd.DataFrame) -> dict[pd.Timestamp, int]:
    ordered = reports.sort_values("report_date").reset_index(drop=True)
    result: dict[pd.Timestamp, int] = {}
    for index in range(1, len(ordered)):
        result[pd.Timestamp(ordered.iloc[index]["report_date"]).normalize()] = (
            int(ordered.iloc[index - 1]["direction"])
        )
    return result


def actions_for_controls(
    primary: dict[pd.Timestamp, dict[str, Any]],
    reports: pd.DataFrame,
) -> dict[str, dict[pd.Timestamp, str]]:
    shifted = shifted_direction_lookup(reports)
    result = {
        "actual": {},
        "es_only_opening_direction": {},
        "cot_only_relative_transfer": {},
        "one_report_shifted_transfer": {},
        "asset_manager_only_confirmation": {},
        "leveraged_fund_rejection": {},
    }
    for day, row in sorted(primary.items()):
        fast = int(row["fast_direction"])
        report_date = pd.Timestamp(row["report_date"]).normalize()
        asset_manager = audit.sign(float(row["asset_manager_net_change"]))
        leveraged_fund = audit.sign(float(row["leveraged_fund_net_change"]))
        shifted_direction = shifted.get(report_date, 0)
        result["actual"][day] = str(row["action"])
        result["es_only_opening_direction"][day] = str(
            row["es_only_action"]
        )
        result["cot_only_relative_transfer"][day] = str(
            row["cot_only_action"]
        )
        result["one_report_shifted_transfer"][day] = (
            "UPRO"
            if fast == shifted_direction == 1
            else "SPXU"
            if fast == shifted_direction == -1
            else "CASH"
        )
        result["asset_manager_only_confirmation"][day] = (
            "UPRO"
            if fast == asset_manager == 1
            else "SPXU"
            if fast == asset_manager == -1
            else "CASH"
        )
        result["leveraged_fund_rejection"][day] = (
            "UPRO"
            if fast == -leveraged_fund == 1
            else "SPXU"
            if fast == -leveraged_fund == -1
            else "CASH"
        )
    return result


def make_rows(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    actions: dict[pd.Timestamp, str],
    primary: dict[pd.Timestamp, dict[str, Any]],
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
            or day not in primary
        ):
            continue
        quotes = sessions.get(day, {}).get(symbol)
        if quotes is None:
            continue
        entry_stamp = audit.clock_stamp(
            day, ENTRY_CLOCK, quotes.index.tz
        ) + timedelta(minutes=delay_minutes)
        exit_stamp = audit.clock_stamp(day, EXIT_CLOCK, quotes.index.tz)
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
                "report_date": pd.Timestamp(
                    primary[day]["report_date"]
                ).normalize(),
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


def cluster_vector(
    rows: list[dict[str, Any]], reports: pd.DataFrame
) -> tuple[np.ndarray, list[pd.Timestamp]]:
    report_dates = [
        pd.Timestamp(value).normalize()
        for value in reports["report_date"].sort_values()
        if START.year <= pd.Timestamp(value).year <= END.year
    ]
    totals = {
        report_date: 0.0 for report_date in report_dates
    }
    for row in rows:
        totals[pd.Timestamp(row["report_date"]).normalize()] += float(
            row["return"]
        )
    return (
        np.asarray([totals[day] for day in report_dates], dtype=float),
        report_dates,
    )


def cluster_bootstrap_lower(values: np.ndarray) -> float:
    if not len(values):
        return math.nan
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    starts = np.arange(len(values))
    blocks = math.ceil(len(values) / BOOTSTRAP_BLOCK_REPORTS)
    means = np.empty(BOOTSTRAP_SAMPLES, dtype=float)
    offsets = np.arange(BOOTSTRAP_BLOCK_REPORTS)
    for index in range(BOOTSTRAP_SAMPLES):
        chosen = rng.choice(starts, size=blocks, replace=True)
        sample = np.concatenate(
            [values[(start + offsets) % len(values)] for start in chosen]
        )[: len(values)]
        means[index] = float(sample.mean())
    return float(np.quantile(means, 0.025))


def summarize(
    rows: list[dict[str, Any]],
    reports: pd.DataFrame,
    *,
    cluster_metrics: bool = False,
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
    if cluster_metrics:
        values, report_dates = cluster_vector(rows, reports)
        ordered = np.sort(values)
        without_best = (
            ordered[:-5] if len(ordered) > 5 else np.asarray([], dtype=float)
        )
        result.update(
            {
                "source_report_clusters": len(values),
                "source_report_clusters_with_trades": int(
                    sum(value != 0.0 for value in values)
                ),
                "pnl_without_best_5_source_reports_usd": float(
                    100.0 * without_best.sum()
                ),
                "source_report_block_bootstrap_95pct_lower_mean_return": (
                    cluster_bootstrap_lower(values)
                ),
                "best_source_report": (
                    report_dates[int(np.argmax(values))].date().isoformat()
                    if len(values)
                    else None
                ),
                "best_source_report_pnl_usd": (
                    float(100.0 * values.max()) if len(values) else math.nan
                ),
            }
        )
    return result


def return_panel(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    primary: dict[pd.Timestamp, dict[str, Any]],
) -> dict[tuple[pd.Timestamp, str], float]:
    panel: dict[tuple[pd.Timestamp, str], float] = {}
    for day in sorted(primary):
        if day in excluded or not START <= day <= END:
            continue
        for symbol in ("UPRO", "SPXU"):
            quotes = sessions.get(day, {}).get(symbol)
            if quotes is None:
                continue
            entry = base.quote_at(
                quotes,
                audit.clock_stamp(day, ENTRY_CLOCK, quotes.index.tz),
                0,
            )
            exit_quote = base.quote_at(
                quotes,
                audit.clock_stamp(day, EXIT_CLOCK, quotes.index.tz),
                0,
            )
            if entry is None or exit_quote is None:
                continue
            entry_ask = float(entry.ask_px_00)
            exit_bid = float(exit_quote.bid_px_00)
            if min(entry_ask, exit_bid) > 0:
                panel[(day, symbol)] = exit_bid / entry_ask - 1.0
    return panel


def report_direction_permutation(
    actual_rows: list[dict[str, Any]],
    primary: dict[pd.Timestamp, dict[str, Any]],
    reports: pd.DataFrame,
    panel: dict[tuple[pd.Timestamp, str], float],
) -> dict[str, Any]:
    actual = float(np.mean([row["return"] for row in actual_rows]))
    report_dates = [
        pd.Timestamp(value).normalize()
        for value in reports["report_date"].sort_values()
    ]
    directions = np.asarray(
        [
            int(
                reports.loc[
                    reports["report_date"] == report_date, "direction"
                ].iloc[0]
            )
            for report_date in report_dates
        ],
        dtype=int,
    )
    rng = np.random.default_rng(PERMUTATION_SEED)
    permuted = np.empty(PERMUTATION_SAMPLES, dtype=float)
    for sample in range(PERMUTATION_SAMPLES):
        shuffled = rng.permutation(directions)
        lookup = dict(zip(report_dates, shuffled, strict=True))
        values: list[float] = []
        for day, row in primary.items():
            direction = int(
                lookup[pd.Timestamp(row["report_date"]).normalize()]
            )
            if int(row["fast_direction"]) != direction:
                continue
            symbol = "UPRO" if direction > 0 else "SPXU"
            value = panel.get((day, symbol))
            if value is not None:
                values.append(value)
        permuted[sample] = float(np.mean(values)) if values else math.nan
    finite = permuted[np.isfinite(permuted)]
    p_value = (1 + int((finite >= actual).sum())) / (1 + len(finite))
    return {
        "actual_mean_return": actual,
        "samples": int(len(finite)),
        "permuted_mean_return_mean": float(finite.mean()),
        "permuted_95pct_quantile": float(np.quantile(finite, 0.95)),
        "one_sided_p_value": float(p_value),
    }


def development_gates(
    development: dict[str, Any],
    independent: dict[str, Any],
    permutation: dict[str, Any],
) -> dict[str, bool]:
    actual = development["observed_bbo"]
    years = actual.get("year_pnl_usd", {})
    sleeves = actual.get("instrument_pnl_usd", {})
    independent_sleeves = independent.get("instrument_pnl_usd", {})
    controls = development["controls"]
    return {
        "more_than_two_executed_trades_per_declared_week": actual[
            "trades_per_declared_week"
        ]
        > 2.0,
        "execution_coverage_at_least_95_percent": development[
            "execution_coverage"
        ]
        >= 0.95,
        "profit_factor_strictly_above_1_10": actual["profit_factor"] > 1.10,
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
        "positive_after_deleting_best_five_source_reports": actual[
            "pnl_without_best_5_source_reports_usd"
        ]
        > 0.0,
        "source_report_block_bootstrap_lower_above_zero": actual[
            "source_report_block_bootstrap_95pct_lower_mean_return"
        ]
        > 0.0,
        "source_report_direction_permutation_p_below_0_05": permutation[
            "one_sided_p_value"
        ]
        < 0.05,
        "independent_overlap_positive_pf_above_one_both_sleeves": (
            independent["fixed_notional_pnl_usd"] > 0.0
            and independent["profit_factor"] > 1.0
            and all(
                independent_sleeves.get(symbol, 0.0) != 0.0
                for symbol in ("UPRO", "SPXU")
            )
        ),
        "actual_mean_trade_above_shifted_and_cot_only_controls": all(
            actual["mean_session_pnl_usd"]
            > controls[name]["mean_session_pnl_usd"]
            for name in (
                "one_report_shifted_transfer",
                "cot_only_relative_transfer",
            )
        ),
    }


def render(payload: dict[str, Any]) -> str:
    development = payload["development"]
    actual = development["observed_bbo"]
    independent = payload["independent_feed_overlap_2023"]
    years = actual.get("year_pnl_usd", {})
    sleeves = actual.get("instrument_pnl_usd", {})
    failures = [
        name for name, passed in development["gates"].items() if not passed
    ]
    lines = [
        "# CFTC Relative-Transfer / ES Opening Acceptance v65",
        "",
        "## Verdict",
        "",
        (
            "**Development survivor; recent-year source acquisition is "
            "allowed.**"
            if development["gate_passed"]
            else "**Rejected in 2021–2023; recent years remain locked.**"
        ),
        "",
        "## Frozen development result",
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
        f"- Five-minute-delay stress: "
        f"${development['five_minute_entry_delay']['fixed_notional_pnl_usd']:.2f}",
        f"- Delete best five source reports: "
        f"${actual['pnl_without_best_5_source_reports_usd']:.2f}",
        f"- Source-report bootstrap lower mean: "
        f"{actual['source_report_block_bootstrap_95pct_lower_mean_return']:.6f}",
        f"- Source-report permutation p: "
        f"{development['source_report_direction_permutation']['one_sided_p_value']:.4f}",
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
    if not PREREG.exists():
        raise FileNotFoundError("Missing frozen preregistration")
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    feasibility = json.loads(FEASIBILITY.read_text(encoding="utf-8"))
    if not feasibility.get("gate_passed"):
        raise RuntimeError("Returns-blind v65 construction did not pass")

    expected = audit.flowlib.load_spy_sessions()
    reports, _ = audit.load_cftc()
    cot = audit.source_states(expected, reports)
    es_sessions = {
        pd.Timestamp(day).normalize(): frame
        for day, frame in eslib.load_development_sessions()
    }
    primary = audit.build_actions(
        expected, cot, es_sessions, audit.PRIMARY_END
    )
    variants = actions_for_controls(primary, reports)
    signal_count = sum(
        action != "CASH" for action in variants["actual"].values()
    )
    if signal_count != EXPECTED_FEATURE_SIGNALS:
        raise RuntimeError(
            f"Feature signal count changed: {signal_count} "
            f"!= {EXPECTED_FEATURE_SIGNALS}"
        )

    arca = relay.sessions(relay.ARCA_PATH)
    arca_excluded = relay.degraded(relay.ARCA_CONDITIONS)
    actual_rows = make_rows(
        arca, arca_excluded, variants["actual"], primary
    )
    development = {
        "feature_signal_count": signal_count,
        "execution_coverage": len(actual_rows) / signal_count,
        "observed_bbo": summarize(
            actual_rows, reports, cluster_metrics=True
        ),
        "extra_cent_each_fill": summarize(
            make_rows(
                arca,
                arca_excluded,
                variants["actual"],
                primary,
                adverse_cents=0.01,
            ),
            reports,
        ),
        "five_minute_entry_delay": summarize(
            make_rows(
                arca,
                arca_excluded,
                variants["actual"],
                primary,
                delay_minutes=5,
            ),
            reports,
        ),
        "controls": {
            name: summarize(
                make_rows(arca, arca_excluded, actions, primary),
                reports,
            )
            for name, actions in variants.items()
            if name != "actual"
        },
        "spy_total_return_hurdle": v44.adjusted_spy_hurdle(START, END),
    }

    panel = return_panel(arca, arca_excluded, primary)
    permutation = report_direction_permutation(
        actual_rows, primary, reports, panel
    )
    development["source_report_direction_permutation"] = permutation

    equs = relay.sessions(relay.EQUS_PATH)
    equs_excluded = relay.degraded(relay.EQUS_CONDITIONS)
    independent_rows = make_rows(
        equs, equs_excluded, variants["actual"], primary
    )
    independent = summarize(independent_rows, reports)

    gates = development_gates(development, independent, permutation)
    development["gates"] = gates
    development["gate_passed"] = all(gates.values())

    payload = {
        "specification": str(PREREG.relative_to(ROOT)).replace("\\", "/"),
        "specification_sha256": hashlib.sha256(
            PREREG.read_bytes()
        ).hexdigest(),
        "specification_id": prereg["specification_id"],
        "status": (
            "development_survivor_recent_source_acquisition_allowed"
            if development["gate_passed"]
            else "rejected_in_development_recent_years_locked"
        ),
        "development": development,
        "independent_feed_overlap_2023": independent,
        "recent_years_status": (
            "unlocked_for_separate_source_acquisition_and_feature_audit"
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
