"""Frozen 2021-2023 test of Treasury dealer dollar-years overhang v66."""

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

from research_scout import audit_treasury_dealer_dollar_years_v66 as audit  # noqa: E402
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay  # noqa: E402
from research_scout import test_spy_btc_perpetual_fresh_position_v44 as v44  # noqa: E402
from research_scout import test_upro_spxu_creative_hypotheses as base  # noqa: E402
from research_scout import test_upro_spxu_variance_state as common  # noqa: E402

PREREG = ROOT / "research_scout" / "treasury_dealer_dollar_years_prereg_v66.json"
FEASIBILITY = (
    ROOT
    / "research_scout"
    / "treasury_dealer_dollar_years_returns_blind_audit_v66.json"
)
OUTPUT = (
    ROOT / "research_scout" / "treasury_dealer_dollar_years_results_v66.json"
)
REPORT = (
    ROOT / "research_scout" / "TREASURY_DEALER_DOLLAR_YEARS_REPORT_V66.md"
)

START = pd.Timestamp("2021-01-04")
END = pd.Timestamp("2023-12-29")
ENTRY = "09:33"
EXIT = "15:30"
EXPECTED_SESSIONS = 753
EXPECTED_SIGNALS = 572
BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_BLOCK = 5
BOOTSTRAP_SEED = 660066
PERMUTATION_SAMPLES = 5_000
PERMUTATION_SEED = 660166


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


def variants(
    states: dict[pd.Timestamp, dict[str, Any]],
    expected: pd.DatetimeIndex,
) -> dict[str, dict[pd.Timestamp, str]]:
    result = {
        "actual": {},
        "accepted_notional_only": {},
        "fixed_coupon_only": {},
        "extra_session_lag": {},
        "flipped_direction": {},
    }
    next_map = {
        pd.Timestamp(expected[index]).normalize(): pd.Timestamp(
            expected[index + 1]
        ).normalize()
        for index in range(len(expected) - 1)
    }
    for day, row in sorted(states.items()):
        actual = str(row["action"])
        result["actual"][day] = actual
        result["accepted_notional_only"][day] = str(row["notional_action"])
        result["fixed_coupon_only"][day] = str(row["coupon_action"])
        result["flipped_direction"][day] = (
            "SPXU"
            if actual == "UPRO"
            else "UPRO"
            if actual == "SPXU"
            else "CASH"
        )
        delayed = next_map.get(day)
        if delayed is not None:
            result["extra_session_lag"][delayed] = actual
    return result


def make_rows(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    actions: dict[pd.Timestamp, str],
    cluster_lookup: dict[pd.Timestamp, pd.Timestamp],
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
        entry_stamp = audit.v65.clock_stamp(
            day, ENTRY, quotes.index.tz
        ) + timedelta(minutes=delay_minutes)
        exit_stamp = audit.v65.clock_stamp(day, EXIT, quotes.index.tz)
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
                "cluster": cluster_lookup.get(day, day),
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


def cluster_vector(
    rows: list[dict[str, Any]], cluster_days: list[pd.Timestamp]
) -> np.ndarray:
    totals = {day: 0.0 for day in cluster_days}
    for row in rows:
        cluster = pd.Timestamp(row["cluster"]).normalize()
        if cluster in totals:
            totals[cluster] += float(row["return"])
    return np.asarray([totals[day] for day in cluster_days], dtype=float)


def bootstrap_lower(values: np.ndarray) -> float:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    starts = np.arange(len(values))
    blocks = math.ceil(len(values) / BOOTSTRAP_BLOCK)
    offsets = np.arange(BOOTSTRAP_BLOCK)
    means = np.empty(BOOTSTRAP_SAMPLES)
    for index in range(BOOTSTRAP_SAMPLES):
        chosen = rng.choice(starts, blocks, replace=True)
        sample = np.concatenate(
            [values[(start + offsets) % len(values)] for start in chosen]
        )[: len(values)]
        means[index] = sample.mean()
    return float(np.quantile(means, 0.025))


def summarize(
    rows: list[dict[str, Any]],
    cluster_days: list[pd.Timestamp],
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
        values = cluster_vector(rows, cluster_days)
        result.update(
            {
                "mapped_auction_clusters": len(values),
                "clusters_with_executed_trades": int((values != 0).sum()),
                "pnl_without_best_5_clusters_usd": float(
                    100.0 * np.sort(values)[:-5].sum()
                ),
                "cluster_block_bootstrap_95pct_lower_mean_return": (
                    bootstrap_lower(values)
                ),
                "best_cluster": cluster_days[
                    int(np.argmax(values))
                ].date().isoformat(),
                "best_cluster_pnl_usd": float(100.0 * values.max()),
            }
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
                quotes,
                audit.v65.clock_stamp(day, ENTRY, quotes.index.tz),
                0,
            )
            exit_quote = base.quote_at(
                quotes,
                audit.v65.clock_stamp(day, EXIT, quotes.index.tz),
                0,
            )
            if entry is not None and exit_quote is not None:
                panel[(day, symbol)] = (
                    float(exit_quote.bid_px_00) / float(entry.ask_px_00) - 1.0
                )
    return panel


def permutation_test(
    actual_rows: list[dict[str, Any]],
    states: dict[pd.Timestamp, dict[str, Any]],
    panel: dict[tuple[pd.Timestamp, str], float],
) -> dict[str, Any]:
    days = sorted(states)
    directions = np.asarray(
        [
            1 if states[day]["action"] == "UPRO" else -1
            for day in days
        ],
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
    p_value = (1 + int((samples >= actual).sum())) / (
        1 + PERMUTATION_SAMPLES
    )
    return {
        "actual_mean_return": actual,
        "permuted_mean_return": float(samples.mean()),
        "permuted_95pct_quantile": float(np.quantile(samples, 0.95)),
        "one_sided_p_value": float(p_value),
        "samples": PERMUTATION_SAMPLES,
    }


def gates(
    dev: dict[str, Any],
    independent: dict[str, Any],
    permutation: dict[str, Any],
) -> dict[str, bool]:
    actual = dev["observed_bbo"]
    years = actual.get("year_pnl_usd", {})
    sleeves = actual.get("instrument_pnl_usd", {})
    independent_sleeves = independent.get("instrument_pnl_usd", {})
    controls = dev["controls"]
    return {
        "more_than_two_executed_trades_per_declared_week": actual[
            "trades_per_declared_week"
        ]
        > 2.0,
        "execution_coverage_at_least_95_percent": dev[
            "execution_coverage"
        ]
        >= 0.95,
        "profit_factor_strictly_above_1_10": actual["profit_factor"] > 1.10,
        "positive_each_development_year": all(
            years.get(str(year), 0.0) > 0.0 for year in (2021, 2022, 2023)
        ),
        "both_upro_and_spxu_positive": all(
            sleeves.get(symbol, 0.0) > 0.0 for symbol in ("UPRO", "SPXU")
        ),
        "compounded_ending_cash_above_adjusted_spy": actual[
            "ending_cash_usd"
        ]
        > dev["spy_total_return_hurdle"]["ending_cash_usd"],
        "positive_after_one_extra_cent_each_fill": dev[
            "extra_cent_each_fill"
        ]["fixed_notional_pnl_usd"]
        > 0.0,
        "positive_after_five_minute_entry_delay": dev[
            "five_minute_entry_delay"
        ]["fixed_notional_pnl_usd"]
        > 0.0,
        "positive_after_deleting_best_five_clusters": actual[
            "pnl_without_best_5_clusters_usd"
        ]
        > 0.0,
        "cluster_bootstrap_lower_above_zero": actual[
            "cluster_block_bootstrap_95pct_lower_mean_return"
        ]
        > 0.0,
        "event_direction_permutation_p_below_0_05": permutation[
            "one_sided_p_value"
        ]
        < 0.05,
        "independent_positive_pf_above_one_both_sleeves": (
            independent["fixed_notional_pnl_usd"] > 0.0
            and independent["profit_factor"] > 1.0
            and all(
                independent_sleeves.get(symbol, 0.0) != 0.0
                for symbol in ("UPRO", "SPXU")
            )
        ),
        "actual_mean_above_frozen_controls": all(
            actual["mean_session_pnl_usd"]
            > controls[name]["mean_session_pnl_usd"]
            for name in (
                "accepted_notional_only",
                "fixed_coupon_only",
                "extra_session_lag",
            )
        ),
    }


def render(payload: dict[str, Any]) -> str:
    dev = payload["development"]
    actual = dev["observed_bbo"]
    years = actual.get("year_pnl_usd", {})
    sleeves = actual.get("instrument_pnl_usd", {})
    independent = payload["independent_feed_overlap_2023"]
    failures = [name for name, passed in dev["gates"].items() if not passed]
    lines = [
        "# Treasury Dealer Dollar-Years Overhang v66",
        "",
        "## Verdict",
        "",
        (
            "**Development survivor; recent-year source acquisition is "
            "allowed.**"
            if dev["gate_passed"]
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
        f"${dev['spy_total_return_hurdle']['ending_cash_usd']:.2f}",
        f"- Profit factor: {actual['profit_factor']:.3f}",
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
        f"- Delete five event clusters: "
        f"${actual['pnl_without_best_5_clusters_usd']:.2f}",
        f"- Cluster bootstrap lower mean: "
        f"{actual['cluster_block_bootstrap_95pct_lower_mean_return']:.6f}",
        f"- Direction permutation p: "
        f"{dev['event_direction_permutation']['one_sided_p_value']:.4f}",
        f"- Independent overlap: {independent['sessions']} trades, "
        f"${independent['fixed_notional_pnl_usd']:.2f}, "
        f"PF {independent['profit_factor']:.3f}",
        "",
        "## Controls",
        "",
    ]
    for name, item in dev["controls"].items():
        lines.append(
            f"- {name}: {item['sessions']} trades, "
            f"${item['fixed_notional_pnl_usd']:.2f}, "
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
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    feasibility = json.loads(FEASIBILITY.read_text(encoding="utf-8"))
    if not feasibility.get("gate_passed"):
        raise RuntimeError("Returns-blind v66 construction did not pass")
    auctions, _ = audit.load_auctions()
    expected = audit.flowlib.load_spy_sessions()
    states = audit.build_states(audit.aggregate_auction_days(auctions), expected)
    action_variants = variants(states, expected)
    signal_count = sum(
        action != "CASH" for action in action_variants["actual"].values()
    )
    if signal_count != EXPECTED_SIGNALS:
        raise RuntimeError(
            f"Feature signals changed: {signal_count} != {EXPECTED_SIGNALS}"
        )
    cluster_days = sorted(states)
    cluster_lookup = {day: day for day in cluster_days}

    arca = relay.sessions(relay.ARCA_PATH)
    arca_excluded = relay.degraded(relay.ARCA_CONDITIONS)
    actual_rows = make_rows(
        arca,
        arca_excluded,
        action_variants["actual"],
        cluster_lookup,
    )
    dev = {
        "feature_signal_count": signal_count,
        "execution_coverage": len(actual_rows) / signal_count,
        "observed_bbo": summarize(
            actual_rows, cluster_days, cluster_metrics=True
        ),
        "extra_cent_each_fill": summarize(
            make_rows(
                arca,
                arca_excluded,
                action_variants["actual"],
                cluster_lookup,
                adverse_cents=0.01,
            ),
            cluster_days,
        ),
        "five_minute_entry_delay": summarize(
            make_rows(
                arca,
                arca_excluded,
                action_variants["actual"],
                cluster_lookup,
                delay_minutes=5,
            ),
            cluster_days,
        ),
        "controls": {
            name: summarize(
                make_rows(
                    arca,
                    arca_excluded,
                    actions,
                    cluster_lookup,
                ),
                cluster_days,
            )
            for name, actions in action_variants.items()
            if name != "actual"
        },
        "spy_total_return_hurdle": v44.adjusted_spy_hurdle(START, END),
    }
    panel = return_panel(arca, arca_excluded, cluster_days)
    permutation = permutation_test(actual_rows, states, panel)
    dev["event_direction_permutation"] = permutation

    equs = relay.sessions(relay.EQUS_PATH)
    equs_excluded = relay.degraded(relay.EQUS_CONDITIONS)
    independent = summarize(
        make_rows(
            equs,
            equs_excluded,
            action_variants["actual"],
            cluster_lookup,
        ),
        cluster_days,
    )
    frozen_gates = gates(dev, independent, permutation)
    dev["gates"] = frozen_gates
    dev["gate_passed"] = all(frozen_gates.values())
    payload = {
        "specification": str(PREREG.relative_to(ROOT)).replace("\\", "/"),
        "specification_sha256": hashlib.sha256(
            PREREG.read_bytes()
        ).hexdigest(),
        "specification_id": prereg["specification_id"],
        "status": (
            "development_survivor_recent_source_acquisition_allowed"
            if dev["gate_passed"]
            else "rejected_in_development_recent_years_locked"
        ),
        "development": dev,
        "independent_feed_overlap_2023": independent,
        "recent_years_status": (
            "unlocked_for_separate_source_acquisition_and_feature_audit"
            if dev["gate_passed"]
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
