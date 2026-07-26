"""Frozen UPRO-sensor / SH-actuator expanding-memory test."""

from __future__ import annotations

import json
import math
from datetime import time, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_density_invariant_sync_2026 as forward
from research_scout import test_upro_spxu_expanding_analog_memory as v7

ROOT = Path(__file__).resolve().parents[1]
SH_ARCA = (
    ROOT
    / "external_artifacts"
    / "databento_sh_bbo"
    / "ARCX.PILLAR"
    / "bbo"
    / "sh_bbo_1m_2021-01-01_2026-07-25.dbn.zst"
)
SH_EQUS = (
    ROOT
    / "external_artifacts"
    / "databento_sh_bbo"
    / "EQUS.MINI"
    / "bbo"
    / "sh_bbo_1m_2023-03-28_2026-07-25.dbn.zst"
)
PAIR_EQUS = (
    ROOT
    / "external_artifacts"
    / "databento_leveraged_etf"
    / "EQUS.MINI"
    / "bbo"
    / "upro_spxu_bbo_1m_2023-03-28_2026-01-01.dbn.zst"
)
OUTPUT = ROOT / "research_scout" / "upro_sh_sensor_actuator_result_v8.json"
REPORT = ROOT / "research_scout" / "UPRO_SH_SENSOR_ACTUATOR_REPORT_V8.md"
V7_RESULT = ROOT / "research_scout" / "upro_spxu_expanding_analog_memory_result_v7.json"


def sh_sessions(path: Path) -> dict[pd.Timestamp, pd.DataFrame]:
    frame = base.load_dbn(path)
    frame = frame[frame.symbol == "SH"]
    return base.split_sessions(frame)


def pair_sessions(path: Path) -> dict[pd.Timestamp, dict[str, pd.DataFrame]]:
    frame = base.load_dbn(path)
    output: dict[pd.Timestamp, dict[str, pd.DataFrame]] = {}
    for symbol in ["UPRO", "SPXU"]:
        selected = frame[frame.symbol == symbol]
        for day, session in base.split_sessions(selected).items():
            output.setdefault(day, {})[symbol] = session
    return output


def sh_potential_trade(
    day: pd.Timestamp,
    spy: pd.DataFrame,
    quotes: pd.DataFrame,
    delay_minutes: int = 0,
) -> dict[str, Any] | None:
    tz = spy.index.tz
    anchor_stamp = base.clock_timestamp(day, time(11, 1), tz)
    entry_stamp = anchor_stamp + timedelta(minutes=delay_minutes)
    exit_stamp = base.clock_timestamp(day, time(15, 30), tz)
    anchor_bar = base.exact_row(spy, anchor_stamp)
    entry_quote = base.quote_at(quotes, entry_stamp)
    if anchor_bar is None or entry_quote is None:
        return None
    anchor = float(anchor_bar.open)
    stop = anchor * 1.10
    if delay_minutes and base.stop_touched(
        spy,
        anchor_stamp,
        entry_stamp,
        -1,
        stop,
    ):
        return None
    scan = spy[(spy.index >= entry_stamp) & (spy.index < exit_stamp)]
    trigger_stamp = None
    for stamp, row in scan.iterrows():
        if float(row.high) >= stop:
            trigger_stamp = stamp + timedelta(minutes=1)
            break
    desired_exit = trigger_stamp if trigger_stamp is not None else exit_stamp
    exit_quote = base.quote_at(quotes, desired_exit, max_lag_minutes=2)
    if exit_quote is None:
        return None
    return {
        "hypothesis": "expanding_analog_memory_sensor_actuator",
        "date": day,
        "direction": "bearish",
        "symbol": "SH",
        "score": 0.0,
        "planned_notional": 100.0,
        "signal_entry": anchor,
        "stop": stop,
        "entry_time": entry_stamp,
        "exit_time": exit_quote.name,
        "entry_ask": float(entry_quote.ask_px_00),
        "entry_bid": float(entry_quote.bid_px_00),
        "exit_bid": float(exit_quote.bid_px_00),
        "exit_ask": float(exit_quote.ask_px_00),
        "reason": "stop" if trigger_stamp is not None else "time",
        "additional_delay_minutes": delay_minutes,
    }


def build_rows(
    spy: dict[pd.Timestamp, pd.DataFrame],
    pair_bars: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    pair_bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    upro_execution_bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    sh: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for day in sorted(spy):
        if day in excluded:
            continue
        bars = pair_bars.get(day)
        sensors = pair_bbo.get(day)
        execution = upro_execution_bbo.get(day)
        sh_quotes = sh.get(day)
        if (
            bars is None
            or sensors is None
            or execution is None
            or sh_quotes is None
        ):
            continue
        if not {"UPRO", "SPXU"}.issubset(bars) or not {
            "UPRO",
            "SPXU",
        }.issubset(sensors):
            continue
        if "UPRO" not in execution:
            continue
        feature = v7.morning_feature(day, spy[day], bars, sensors)
        if feature is None:
            continue
        upro = v7.potential_trade(day, 1, spy[day], execution["UPRO"])
        bearish = sh_potential_trade(day, spy[day], sh_quotes)
        if upro is None or bearish is None:
            continue
        upro_return = float(base.trade_pnl(pd.DataFrame([upro])).iloc[0] / 100.0)
        sh_return = float(base.trade_pnl(pd.DataFrame([bearish])).iloc[0] / 100.0)
        rows.append(
            {
                "date": day,
                "feature": feature,
                "UPRO": upro,
                "SH": bearish,
                "UPRO_return": upro_return,
                "SH_return": sh_return,
            }
        )
    return rows


def choose(
    rows: list[dict[str, Any]],
) -> tuple[pd.DataFrame, list[dict[str, Any]], list[pd.Timestamp]]:
    selected: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    evaluation_days = [row["date"] for row in rows[v7.MINIMUM_MEMORY :]]
    matrix = np.stack([row["feature"] for row in rows])
    returns = {
        symbol: np.array([row[f"{symbol}_return"] for row in rows])
        for symbol in ["UPRO", "SH"]
    }
    for idx in range(v7.MINIMUM_MEMORY, len(rows)):
        prior = matrix[:idx]
        median = np.median(prior, axis=0)
        scale = np.quantile(prior, 0.75, axis=0) - np.quantile(
            prior,
            0.25,
            axis=0,
        )
        scale[scale == 0] = 1.0
        distances = np.sqrt(
            np.square(
                (prior - median) / scale - (matrix[idx] - median) / scale
            ).sum(axis=1)
        ) / math.sqrt(len(v7.FEATURE_NAMES))
        k = int(math.ceil(math.sqrt(idx)))
        neighbors = np.argsort(distances, kind="stable")[:k]
        forecasts = {
            symbol: float(values[neighbors].mean())
            for symbol, values in returns.items()
        }
        votes = {
            symbol: float((values[neighbors] > 0).mean())
            for symbol, values in returns.items()
        }
        if forecasts["UPRO"] == forecasts["SH"]:
            continue
        symbol = max(["UPRO", "SH"], key=lambda item: forecasts[item])
        traded = forecasts[symbol] > 0 and votes[symbol] > 0.5
        decision = {
            "date": rows[idx]["date"],
            "symbol": symbol,
            "forecast_return": forecasts[symbol],
            "positive_neighbor_fraction": votes[symbol],
            "neighbor_count": k,
            "traded": traded,
        }
        decisions.append(decision)
        if traded:
            trade = dict(rows[idx][symbol])
            trade.update(
                {
                    "forecast_return": forecasts[symbol],
                    "positive_neighbor_fraction": votes[symbol],
                    "neighbor_count": k,
                }
            )
            selected.append(trade)
    return pd.DataFrame(selected), decisions, evaluation_days


def delayed(
    decisions: list[dict[str, Any]],
    spy: dict[pd.Timestamp, pd.DataFrame],
    upro_execution_bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    sh: dict[pd.Timestamp, pd.DataFrame],
    minutes: int,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for decision in decisions:
        if not decision["traded"]:
            continue
        day = decision["date"]
        if decision["symbol"] == "UPRO":
            trade = v7.potential_trade(
                day,
                1,
                spy[day],
                upro_execution_bbo[day]["UPRO"],
                minutes,
            )
        else:
            trade = sh_potential_trade(day, spy[day], sh[day], minutes)
        if trade is not None:
            records.append(trade)
    return pd.DataFrame(records)


def render_report(result: dict[str, Any]) -> str:
    observed = result["observed_bbo"]
    spy = result["spy_price_only_hurdle"]
    v7_observed = result["v7_spxu_actuator_reference"]["observed_bbo"]
    criteria = result["acceptance_criteria"]
    years = observed.get("year_pnl_usd", {})
    directions = observed.get("direction_pnl_usd", {})
    audit = result["consolidated_overlap_audit"]["observed_bbo"]
    verdict = "PASS" if result["all_acceptance_criteria_passed"] else "REJECT"
    criterion_lines = "\n".join(
        f"- {'PASS' if passed else 'FAIL'} — {name.replace('_', ' ')}"
        for name, passed in criteria.items()
    )
    year_lines = "\n".join(f"- {year}: ${pnl:.4f}" for year, pnl in years.items())
    return f"""# UPRO/SH Sensor–Actuator Separation v8

## Verdict

**{verdict}.** This is the untouched result of the frozen substitution test. SH
was used only as the bearish execution instrument; all 12 state features still
came from SPY, UPRO, and SPXU.

## Before and after

| Metric | UPRO/SPXU v7 | UPRO/SH v8 | SPY price-only |
|---|---:|---:|---:|
| Ending $100 cash | ${v7_observed['cash_account']['ending_equity_usd']:.4f} | ${observed['cash_account']['ending_equity_usd']:.4f} | ${spy['ending_value_usd']:.4f} |
| Fixed-$100 P&L | ${v7_observed['net_pnl_usd']:.4f} | ${observed['net_pnl_usd']:.4f} | — |
| Profit factor | {v7_observed['profit_factor']:.4f} | {observed['profit_factor']:.4f} | — |
| Trades/week | {v7_observed['trades_per_week']:.3f} | {observed['trades_per_week']:.3f} | — |
| Worst trade | ${v7_observed['worst_trade_usd']:.4f} | ${observed['worst_trade_usd']:.4f} | — |
| P&L without best five | ${v7_observed['net_without_five_best_usd']:.4f} | ${observed['net_without_five_best_usd']:.4f} | — |

## Actuator attribution

- UPRO bullish P&L: ${directions.get('bullish', 0.0):.4f}
- SH bearish P&L: ${directions.get('bearish', 0.0):.4f}

## Calendar-year P&L

{year_lines}

## Consolidated-feed audit

The complete UPRO/SH consolidated overlap supports a separate expanding-memory
run from {result['consolidated_overlap_audit']['evaluation_period']['first']} to
{result['consolidated_overlap_audit']['evaluation_period']['last']}. It produced
{audit['trades']} trades, ${audit['net_pnl_usd']:.4f} fixed-notional P&L, a
{audit['profit_factor']:.4f} profit factor, and
${audit['cash_account']['ending_equity_usd']:.4f} ending cash. This is reported
as an execution-feed audit, not substituted for the full-period primary result.

## Frozen acceptance gates

{criterion_lines}

## Interpretation

The correct comparison is not whether SH looks better in isolation. It is
whether replacing only the bearish actuator repairs the recurring SPXU drag
while preserving frequency, robustness, and the passive-SPY hurdle. No
thresholds or features were repaired after observing SH outcomes.
"""


def main() -> int:
    spy, pair_bars, pair_bbo = v7.combined_sessions()
    excluded = v7.excluded_dates()
    sh = sh_sessions(SH_ARCA)
    rows = build_rows(spy, pair_bars, pair_bbo, pair_bbo, sh, excluded)
    trades, decisions, evaluation_days = choose(rows)
    delay_five = delayed(decisions, spy, pair_bbo, sh, 5)
    observed = forward.summarize(trades, evaluation_days)
    one_cent = forward.summarize(trades, evaluation_days, 0.01)
    five_delay = forward.summarize(delay_five, evaluation_days)
    spy_hurdle = v7.benchmark_between(
        spy,
        evaluation_days[0],
        evaluation_days[-1],
    )
    v7_result = json.loads(V7_RESULT.read_text(encoding="utf-8"))
    v7_observed = v7_result["observed_bbo"]
    eq_pair = pair_sessions(PAIR_EQUS)
    eq_sh = sh_sessions(SH_EQUS)
    audit_rows = build_rows(
        spy,
        pair_bars,
        pair_bbo,
        eq_pair,
        eq_sh,
        excluded,
    )
    audit_trades, audit_decisions, audit_days = choose(audit_rows)
    audit_observed = forward.summarize(audit_trades, audit_days)
    years = observed.get("year_pnl_usd", {})
    directions = observed.get("direction_pnl_usd", {})
    criteria = {
        "minimum_two_trades_per_week": observed["trades_per_week"] >= 2.0,
        "profit_factor_at_least_1_15": observed.get("profit_factor", 0.0) >= 1.15,
        "each_2022_through_2026_ytd_positive": (
            set(years) >= {"2022", "2023", "2024", "2025", "2026"}
            and all(years[year] > 0 for year in ["2022", "2023", "2024", "2025", "2026"])
        ),
        "both_instruments_positive": (
            set(directions) == {"bearish", "bullish"}
            and all(value > 0 for value in directions.values())
        ),
        "positive_after_one_extra_cent_each_fill": one_cent["net_pnl_usd"] > 0,
        "positive_after_five_minute_delay": five_delay["net_pnl_usd"] > 0,
        "positive_after_removing_five_best": (
            observed.get("net_without_five_best_usd", 0.0) > 0
        ),
        "beats_same_period_spy_price_only": (
            observed.get("cash_account", {}).get("ending_equity_usd", 0.0)
            > spy_hurdle["ending_value_usd"]
        ),
        "improves_v7_ending_cash_and_profit_factor": (
            observed.get("cash_account", {}).get("ending_equity_usd", 0.0)
            > 125.2279
            and observed.get("profit_factor", 0.0) > 1.0548
        ),
    }
    result = {
        "status": "walk_forward_substitution_test_complete_no_repairs",
        "specification": "research_scout/upro_sh_sensor_actuator_prereg_v8.json",
        "data_validation": (
            "external_artifacts/databento_sh_bbo/validation_report.json"
        ),
        "evidence_warning": (
            "The substitution follows observed SPXU weakness and is not an "
            "independent discovery; future paper validation remains necessary."
        ),
        "feature_names_unchanged_from_v7": v7.FEATURE_NAMES,
        "valid_memory_sessions": len(rows),
        "evaluation_period": {
            "first": str(evaluation_days[0].date()),
            "last": str(evaluation_days[-1].date()),
            "eligible_sessions": len(evaluation_days),
        },
        "observed_bbo": observed,
        "midpoint_diagnostic": forward.summarize(
            trades,
            evaluation_days,
            midpoint_execution=True,
        ),
        "one_extra_cent_each_fill": one_cent,
        "two_extra_cents_each_fill": forward.summarize(
            trades,
            evaluation_days,
            0.02,
        ),
        "five_additional_minutes_delay": five_delay,
        "spy_price_only_hurdle": spy_hurdle,
        "v7_spxu_actuator_reference": {
            "specification": v7_result["specification"],
            "observed_bbo": v7_observed,
        },
        "consolidated_overlap_audit": {
            "feed": "EQUS.MINI for UPRO and SH executable outcomes",
            "sensor_feed": "ARCX.PILLAR unchanged",
            "valid_memory_sessions": len(audit_rows),
            "evaluation_period": {
                "first": str(audit_days[0].date()),
                "last": str(audit_days[-1].date()),
                "eligible_sessions": len(audit_days),
            },
            "observed_bbo": audit_observed,
            "decision_counts": {
                "evaluated": len(audit_decisions),
                "traded": int(
                    sum(bool(row["traded"]) for row in audit_decisions)
                ),
                "skipped": int(
                    sum(not bool(row["traded"]) for row in audit_decisions)
                ),
            },
        },
        "acceptance_criteria": criteria,
        "all_acceptance_criteria_passed": all(criteria.values()),
        "decision_counts": {
            "evaluated": len(decisions),
            "traded": int(sum(bool(row["traded"]) for row in decisions)),
            "skipped": int(sum(not bool(row["traded"]) for row in decisions)),
        },
    }
    OUTPUT.write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    REPORT.write_text(render_report(result), encoding="utf-8")
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
