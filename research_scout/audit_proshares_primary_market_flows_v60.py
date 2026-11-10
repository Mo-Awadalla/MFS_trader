"""Returns-blind audit of split-adjusted UPRO/SPXU shares-outstanding changes.

The audit reads the already-downloaded free official ProShares NAV and split
files. It does not read target returns, strategy P&L, or recent-year outcomes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "proshares_inventory_v59"
NAV_PATH = RAW / "historical_nav.csv"
SPLIT_PATH = RAW / "split_history.csv"
SOURCE_AUDIT = ROOT / "research_scout" / "proshares_inventory_history_audit_v59.json"
OUTPUT = ROOT / "research_scout" / "proshares_primary_market_flow_audit_v60.json"
REPORT = ROOT / "research_scout" / "PROSHARES_PRIMARY_MARKET_FLOW_AUDIT_V60.md"

START = pd.Timestamp("2021-01-01")
END = pd.Timestamp("2023-12-31")
SYMBOLS = ("UPRO", "SPXU")


def load_spy_sessions() -> pd.DatetimeIndex:
    path = ROOT / "data" / "parquet" / "equity" / "yahoo_chart" / "SPY_1d.parquet"
    frame = pd.read_parquet(path)
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    days = (
        timestamps.dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
        .dt.normalize()
    )
    return pd.DatetimeIndex(sorted({day for day in days if START <= day <= END}))


def next_session_map(sessions: pd.DatetimeIndex) -> dict[pd.Timestamp, pd.Timestamp]:
    extended = pd.DatetimeIndex(
        sorted(
            set(sessions)
            | {
                day
                for day in load_all_spy_sessions()
                if START <= day <= END + pd.Timedelta(days=10)
            }
        )
    )
    return {
        extended[index]: extended[index + 1]
        for index in range(len(extended) - 1)
    }


def load_all_spy_sessions() -> pd.DatetimeIndex:
    path = ROOT / "data" / "parquet" / "equity" / "yahoo_chart" / "SPY_1d.parquet"
    frame = pd.read_parquet(path)
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    days = (
        timestamps.dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
        .dt.normalize()
    )
    return pd.DatetimeIndex(sorted(set(days)))


def split_expected_shares(
    prior_shares: float,
    split_type: str | None,
    ratio: float | None,
) -> float:
    if not split_type or not ratio or not np.isfinite(ratio):
        return prior_shares
    if split_type.casefold() == "forward":
        return prior_shares * ratio
    if split_type.casefold() == "reverse":
        return prior_shares / ratio
    raise ValueError(f"Unsupported split type: {split_type}")


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def summarize_symbol(frame: pd.DataFrame, expected_sessions: int) -> dict[str, Any]:
    active = frame[frame["flow_dollars"].abs() > 0.01]
    absolute_flow = active["flow_dollars"].abs().sort_values(ascending=False)
    total_absolute_flow = absolute_flow.sum()
    top_ten_share = (
        float(absolute_flow.head(10).sum() / total_absolute_flow)
        if total_absolute_flow > 0
        else None
    )
    return {
        "sessions": len(frame),
        "coverage": len(frame) / expected_sessions,
        "active_creation_or_redemption_sessions": len(active),
        "active_sessions_per_week": len(active) / (expected_sessions / 5.0),
        "creation_sessions": int((frame["flow_dollars"] > 0.01).sum()),
        "redemption_sessions": int((frame["flow_dollars"] < -0.01).sum()),
        "zero_change_sessions": int((frame["flow_dollars"].abs() <= 0.01).sum()),
        "median_absolute_flow_dollars_on_active_sessions": float(
            active["flow_dollars"].abs().median()
        ),
        "median_absolute_share_change_fraction_on_active_sessions": float(
            active["share_change_fraction"].abs().median()
        ),
        "top_ten_absolute_flow_share": top_ten_share,
        "split_dates": frame.loc[
            frame["split_type"].notna(), "date"
        ].dt.strftime("%Y-%m-%d").tolist(),
    }


def render(payload: dict[str, Any]) -> str:
    pair = payload["paired_directional_flow"]
    failures = [
        name for name, passed in payload["admission_gates"].items() if not passed
    ]
    lines = [
        "# ProShares Primary-Market Flow Audit v60",
        "",
        "## Verdict",
        "",
        (
            "**Data and cadence gates passed for preimplementation critique. "
            "No return has been opened.**"
            if payload["admission_passed"]
            else "**Rejected returns-blind before strategy implementation.**"
        ),
        "",
        "The source is the free official ProShares historical NAV/shares file. "
        "Every observation is delayed by one U.S. trading session.",
        "",
        "## Coverage and activity",
        "",
        f"- Expected 2021-2023 SPY sessions: {payload['expected_sessions']}",
    ]
    for symbol in SYMBOLS:
        item = payload["symbols"][symbol]
        lines.extend(
            [
                f"- {symbol}: {item['coverage']:.3%} coverage",
                (
                    f"- {symbol}: {item['active_creation_or_redemption_sessions']} "
                    f"active sessions ({item['active_sessions_per_week']:.3f}/week)"
                ),
            ]
        )
    lines.extend(
        [
            "",
            "## Paired directional exposure-flow state",
            "",
            (
                f"- Nonzero next-session states: {pair['nonzero_states']} "
                f"({pair['states_per_week']:.3f}/week)"
            ),
            f"- Bullish / bearish: {pair['positive_states']} / {pair['negative_states']}",
            (
                "- Top-ten absolute-flow concentration: "
                f"{pair['top_ten_absolute_flow_share']:.3%}"
            ),
            "",
            "## Admission gates",
            "",
        ]
    )
    for name, passed in payload["admission_gates"].items():
        lines.append(f"- {name}: {'PASS' if passed else 'FAIL'}")
    lines.extend(
        [
            "",
            "Failed gates: " + (", ".join(failures) if failures else "none"),
            "",
            "## Boundary",
            "",
            "This audit establishes availability and cadence only. Share changes "
            "estimate creations/redemptions; they do not identify end investors, "
            "AP inventory, or the timing of the fund's hedge. A strategy may not "
            "be tested until a separate institutional critique and preregistration "
            "freeze the direction, timing, controls, and execution gates.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    source_audit = json.loads(SOURCE_AUDIT.read_text(encoding="utf-8"))
    expected = load_spy_sessions()
    next_sessions = next_session_map(expected)

    nav = pd.read_csv(NAV_PATH)
    nav["date"] = pd.to_datetime(nav["Date"], errors="coerce")
    nav = nav[nav["Ticker"].isin(SYMBOLS)].copy()
    nav["shares_000"] = pd.to_numeric(
        nav["Shares Outstanding (000)"], errors="coerce"
    )
    nav["nav"] = pd.to_numeric(nav["NAV"], errors="coerce")
    nav["aum"] = pd.to_numeric(nav["Assets Under Management"], errors="coerce")

    splits = pd.read_csv(SPLIT_PATH)
    splits["date"] = pd.to_datetime(splits["Date of Split"], errors="coerce")
    splits = splits[splits["Symbol"].isin(SYMBOLS)].copy()
    splits["split_ratio"] = pd.to_numeric(splits["Ratio"], errors="coerce")
    split_lookup = {
        (record["Symbol"], record["date"]): (
            record["Split Type"],
            record["split_ratio"],
        )
        for record in splits.to_dict(orient="records")
    }

    symbol_frames: dict[str, pd.DataFrame] = {}
    summaries: dict[str, Any] = {}
    for symbol in SYMBOLS:
        selected = nav[nav["Ticker"] == symbol].sort_values("date").copy()
        selected["prior_shares_000"] = selected["shares_000"].shift(1)
        selected["split_type"] = None
        selected["split_ratio"] = np.nan
        expected_prior: list[float] = []
        for row in selected.itertuples(index=False):
            split_type, ratio = split_lookup.get((symbol, row.date), (None, None))
            prior = row.prior_shares_000
            expected_prior.append(
                split_expected_shares(prior, split_type, ratio)
                if pd.notna(prior)
                else np.nan
            )
            if split_type is not None:
                selected.loc[selected["date"] == row.date, "split_type"] = split_type
                selected.loc[selected["date"] == row.date, "split_ratio"] = ratio
        selected["expected_prior_shares_000"] = expected_prior
        selected["delta_shares_000"] = (
            selected["shares_000"] - selected["expected_prior_shares_000"]
        )
        selected["share_change_fraction"] = (
            selected["delta_shares_000"] / selected["expected_prior_shares_000"]
        )
        selected["flow_dollars"] = (
            selected["delta_shares_000"] * 1000.0 * selected["nav"]
        )
        selected = selected[selected["date"].between(START, END)].copy()
        selected["available_session"] = selected["date"].map(next_sessions)
        symbol_frames[symbol] = selected
        summaries[symbol] = summarize_symbol(selected, len(expected))

    paired = symbol_frames["UPRO"][
        ["date", "available_session", "flow_dollars", "aum"]
    ].rename(
        columns={
            "flow_dollars": "upro_flow_dollars",
            "aum": "upro_aum",
        }
    )
    paired = paired.merge(
        symbol_frames["SPXU"][["date", "flow_dollars", "aum"]].rename(
            columns={
                "flow_dollars": "spxu_flow_dollars",
                "aum": "spxu_aum",
            }
        ),
        on="date",
        how="inner",
        validate="one_to_one",
    )
    paired["directional_flow_dollars"] = (
        paired["upro_flow_dollars"] - paired["spxu_flow_dollars"]
    )
    paired["directional_flow_fraction"] = paired["directional_flow_dollars"] / (
        paired["upro_aum"] + paired["spxu_aum"]
    )
    nonzero = paired[paired["directional_flow_dollars"].abs() > 0.01].copy()
    absolute_pair_flow = nonzero["directional_flow_dollars"].abs().sort_values(
        ascending=False
    )
    pair_total = absolute_pair_flow.sum()
    pair_summary = {
        "paired_sessions": len(paired),
        "nonzero_states": len(nonzero),
        "states_per_week": len(nonzero) / (len(expected) / 5.0),
        "positive_states": int((nonzero["directional_flow_dollars"] > 0).sum()),
        "negative_states": int((nonzero["directional_flow_dollars"] < 0).sum()),
        "median_absolute_directional_flow_dollars": float(
            nonzero["directional_flow_dollars"].abs().median()
        ),
        "median_absolute_directional_flow_fraction": float(
            nonzero["directional_flow_fraction"].abs().median()
        ),
        "top_ten_absolute_flow_share": float(
            absolute_pair_flow.head(10).sum() / pair_total
        ),
        "states_by_source_year": {
            str(year): int((nonzero["date"].dt.year == year).sum())
            for year in (2021, 2022, 2023)
        },
        "available_session_missing": int(nonzero["available_session"].isna().sum()),
        "states": [
            {
                "source_date": row.date,
                "available_session": row.available_session,
                "direction": (
                    "B" if row.directional_flow_dollars > 0 else "A"
                ),
                "upro_flow_dollars": row.upro_flow_dollars,
                "spxu_flow_dollars": row.spxu_flow_dollars,
                "directional_flow_dollars": row.directional_flow_dollars,
                "directional_flow_fraction": row.directional_flow_fraction,
            }
            for row in nonzero.itertuples(index=False)
        ],
    }

    gates = {
        "official_source_audit_rejects_no_nav_or_split_field": bool(
            source_audit["admission_gates"][
                "daily_nav_aum_coverage_at_least_98_percent"
            ]
            and source_audit["admission_gates"]["split_history_available"]
        ),
        "both_symbols_at_least_98_percent_coverage": all(
            summaries[symbol]["coverage"] >= 0.98 for symbol in SYMBOLS
        ),
        "split_dates_explicitly_normalized": all(
            summaries[symbol]["split_dates"] for symbol in SYMBOLS
        ),
        "one_session_publication_delay_enforced": bool(
            pair_summary["available_session_missing"] == 0
        ),
        "paired_state_cadence_at_least_2_per_week": bool(
            pair_summary["states_per_week"] >= 2.0
        ),
        "both_directions_at_least_15_percent_of_states": bool(
            min(pair_summary["positive_states"], pair_summary["negative_states"])
            / pair_summary["nonzero_states"]
            >= 0.15
        ),
        "no_target_return_or_strategy_pnl_read": True,
    }
    payload = {
        "status": "returns_blind_primary_market_flow_audit",
        "source": {
            "historical_nav_path": str(NAV_PATH.relative_to(ROOT)),
            "historical_nav_sha256": source_audit["source_metadata"][
                "historical_nav"
            ]["sha256"],
            "split_history_path": str(SPLIT_PATH.relative_to(ROOT)),
            "split_history_sha256": source_audit["source_metadata"]["split_history"][
                "sha256"
            ],
            "databento_calls_or_purchases": False,
        },
        "expected_sessions": len(expected),
        "symbols": summaries,
        "paired_directional_flow": pair_summary,
        "admission_gates": gates,
        "admission_passed": all(gates.values()),
        "decision": (
            "allow_preimplementation_critique_only"
            if all(gates.values())
            else "reject_before_strategy_implementation"
        ),
    }
    safe = json_safe(payload)
    OUTPUT.write_text(json.dumps(safe, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(render(safe), encoding="utf-8")
    print(json.dumps(safe, indent=2))


if __name__ == "__main__":
    main()
