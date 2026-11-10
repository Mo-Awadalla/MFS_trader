"""Event-level EQUS.MINI TBBO execution-fidelity audit of unchanged V20.

V20 remains rejected because its original development concentration gate failed.
This audit does not alter its signal, stop, actuator, or liquidation rule and is
not a new pristine validation.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import warnings
from collections import defaultdict
from datetime import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_scout import test_es_scar_to_leveraged_etf as v20

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import databento as db  # noqa: E402

PACKAGE = ROOT / "external_artifacts" / "databento_cash_etf_budget_v1"
PREFIX = PACKAGE / "EQUS.MINI" / "tbbo" / "cash_etf_tbbo_2023-03-28_2026-07-27.dbn.partial.dbn.zst"
TAIL = PACKAGE / "EQUS.MINI" / "tbbo" / "cash_etf_tbbo_tail_2024-10-03_2026-07-27.dbn.zst"
ARCX_CONDITION = PACKAGE / "ARCX.PILLAR" / "dataset_condition.json"
EQUS_CONDITION = PACKAGE / "EQUS.MINI" / "dataset_condition.json"
OUTPUT = ROOT / "research_scout" / "v20_tbbo_execution_fidelity_audit_v34.json"
REPORT = ROOT / "research_scout" / "V20_TBBO_EXECUTION_FIDELITY_AUDIT_V34.md"
NY = "America/New_York"
MAX_EVENT_WAIT_SECONDS = 60.0
DELAYS = [1, 5, 60]
PARTITIONS = {
    "development_overlap_2023": (pd.Timestamp("2023-03-28"), pd.Timestamp("2023-12-29")),
    "historical_validation_2024_2025": (pd.Timestamp("2024-01-02"), pd.Timestamp("2025-12-31")),
    "temporal_extension_2026": (pd.Timestamp("2026-01-02"), pd.Timestamp("2026-07-24")),
}


def degraded(path: Path) -> set[pd.Timestamp]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        pd.Timestamp(row["date"])
        for row in payload["conditions"]
        if row["condition"] != "available"
    }


def seconds_from_midnight(timestamp: pd.Timestamp) -> float:
    return (
        timestamp.hour * 3600
        + timestamp.minute * 60
        + timestamp.second
        + timestamp.microsecond / 1_000_000.0
        + timestamp.nanosecond / 1_000_000_000.0
    )


def build_orders(signal_states: dict[pd.Timestamp, dict[str, Any]], excluded: set[pd.Timestamp]) -> list[dict[str, Any]]:
    orders: list[dict[str, Any]] = []
    for day, state in sorted(signal_states.items()):
        day = pd.Timestamp(day)
        if day < pd.Timestamp("2023-03-28") or day > pd.Timestamp("2026-07-24") or day in excluded:
            continue
        side = int(state["side"])
        symbol = "UPRO" if side > 0 else "SPXU"
        stop = float(state["center"]) - side * v20.scar.TICK_SIZE
        es = state["bars"]
        for delay in DELAYS:
            entry_index = 31 if delay < 60 else 32
            preentry = es.iloc[30:entry_index]
            touched = bool((preentry.low <= stop).any()) if side > 0 else bool((preentry.high >= stop).any())
            if touched:
                continue
            scan = es.iloc[entry_index:360]
            hits = scan.index[scan.low <= stop] if side > 0 else scan.index[scan.high >= stop]
            exit_target = pd.Timestamp.combine(day.date(), time(15, 30)).tz_localize(NY)
            exit_reason = "scheduled_15_30"
            if len(hits):
                hit = pd.Timestamp(hits[0])
                if hit.tzinfo is None:
                    hit = hit.tz_localize(NY)
                else:
                    hit = hit.tz_convert(NY)
                exit_target = hit + pd.Timedelta(minutes=1)
                exit_reason = "es_structural_invalidation_next_minute"
            entry_target = pd.Timestamp.combine(day.date(), time(10, 1)).tz_localize(NY) + pd.Timedelta(seconds=delay)
            if exit_target <= entry_target:
                continue
            orders.append({
                "date": day.strftime("%Y-%m-%d"),
                "symbol": symbol,
                "side": side,
                "delay_seconds": delay,
                "entry_target": entry_target.isoformat(),
                "exit_target": exit_target.isoformat(),
                "exit_reason": exit_reason,
                "center": float(state["center"]),
                "anchor": float(state["anchor"]),
                "stop": stop,
            })
    return orders


def scan_quotes(orders: list[dict[str, Any]]) -> tuple[dict[tuple[str, str, int, str], dict[str, Any]], dict[str, Any]]:
    targets: defaultdict[tuple[str, str], list[tuple[int, str, float]]] = defaultdict(list)
    for order in orders:
        day_symbol = (order["date"], order["symbol"])
        for kind in ("entry", "exit"):
            target = pd.Timestamp(order[f"{kind}_target"]).tz_convert(NY)
            targets[day_symbol].append((order["delay_seconds"], kind, seconds_from_midnight(target)))
    found: dict[tuple[str, str, int, str], dict[str, Any]] = {}
    prefix_boundary_seen = False
    prefix_warning_seen = False
    segment_rows: dict[str, int] = {}
    sources = [
        ("prefix", PREFIX, "2024-10-02"),
        ("tail", TAIL, None),
    ]
    for segment, path, cutoff in sources:
        consumed = 0
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            iterator = db.read_dbn(path).to_df(count=1_000_000, map_symbols=True, tz="UTC")
            for frame in iterator:
                frame = frame.reset_index()
                event = pd.to_datetime(frame["ts_event"], utc=True).dt.tz_convert(NY)
                days = event.dt.strftime("%Y-%m-%d")
                if cutoff is not None and days.gt(cutoff).any():
                    prefix_boundary_seen = True
                    frame = frame.loc[days.le(cutoff)].copy()
                    event = pd.to_datetime(frame["ts_event"], utc=True).dt.tz_convert(NY)
                    days = event.dt.strftime("%Y-%m-%d")
                    stop = True
                else:
                    stop = False
                consumed += len(frame)
                if not frame.empty:
                    seconds = (
                        event.dt.hour * 3600 + event.dt.minute * 60 + event.dt.second
                        + event.dt.microsecond / 1_000_000.0 + event.dt.nanosecond / 1_000_000_000.0
                    )
                    frame = frame.assign(event_ny=event, session_date=days, second=seconds)
                    frame = frame.loc[frame["symbol"].isin(["UPRO", "SPXU"])]
                    frame = frame.loc[
                        frame["bid_px_00"].gt(0)
                        & frame["ask_px_00"].gt(0)
                        & frame["ask_px_00"].ge(frame["bid_px_00"])
                    ]
                    if not frame.empty:
                        frame = frame.loc[
                            [
                                (day, symbol) in targets
                                for day, symbol in zip(frame["session_date"], frame["symbol"], strict=True)
                            ]
                        ]
                    for (day, symbol), group in frame.groupby(["session_date", "symbol"], sort=False):
                        for delay, kind, target_second in targets[(str(day), str(symbol))]:
                            key = (str(day), str(symbol), int(delay), kind)
                            if key in found:
                                continue
                            eligible = group.loc[
                                group["second"].ge(target_second)
                                & group["second"].le(target_second + MAX_EVENT_WAIT_SECONDS)
                            ]
                            if eligible.empty:
                                continue
                            row = eligible.sort_values("ts_event").iloc[0]
                            found[key] = {
                                "ts_event": pd.Timestamp(row["ts_event"]).isoformat(),
                                "ts_recv": pd.Timestamp(row["ts_recv"]).isoformat(),
                                "event_wait_seconds": float(row["second"] - target_second),
                                "bid": float(row["bid_px_00"]),
                                "ask": float(row["ask_px_00"]),
                                "bid_size": int(row["bid_sz_00"]),
                                "ask_size": int(row["ask_sz_00"]),
                                "segment": segment,
                            }
                if stop:
                    break
            if segment == "prefix":
                prefix_warning_seen = any(
                    "truncated" in str(item.message).lower() or "incomplete record" in str(item.message).lower()
                    for item in caught
                )
        segment_rows[segment] = consumed
    if not prefix_boundary_seen:
        raise RuntimeError("Mandatory prefix date boundary was not observed")
    return found, {
        "prefix_boundary_seen": prefix_boundary_seen,
        "prefix_terminal_warning_seen": prefix_warning_seen,
        "segment_rows_logically_consumed": segment_rows,
    }


def make_trades(orders: list[dict[str, Any]], quotes: dict[tuple[str, str, int, str], dict[str, Any]]) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    for order in orders:
        base = (order["date"], order["symbol"], order["delay_seconds"])
        entry = quotes.get((*base, "entry"))
        exit_quote = quotes.get((*base, "exit"))
        if entry is None or exit_quote is None:
            continue
        entry_mid = (entry["bid"] + entry["ask"]) / 2.0
        exit_mid = (exit_quote["bid"] + exit_quote["ask"]) / 2.0
        executable_return = exit_quote["bid"] / entry["ask"] - 1.0
        midpoint_return = exit_mid / entry_mid - 1.0
        adverse_return = (exit_quote["bid"] - 0.01) / (entry["ask"] + 0.01) - 1.0
        trades.append({
            **order,
            "entry": entry,
            "exit": exit_quote,
            "executable_return": executable_return,
            "midpoint_return": midpoint_return,
            "spread_drag_usd": 100.0 * (midpoint_return - executable_return),
            "fixed_100_pnl_usd": 100.0 * executable_return,
            "adverse_cent_pnl_usd": 100.0 * adverse_return,
        })
    return trades


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"trades": 0}
    pnl = np.array([row["fixed_100_pnl_usd"] for row in rows], dtype=float)
    gross_profit = float(pnl[pnl > 0].sum())
    gross_loss = float(-pnl[pnl < 0].sum())
    dates = pd.to_datetime([row["date"] for row in rows])
    return {
        "trades": len(rows),
        "trades_per_calendar_week": len(rows) / max((dates.max() - dates.min()).days / 7.0, 1.0),
        "fixed_100_pnl_usd": float(pnl.sum()),
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else math.inf,
        "win_rate": float((pnl > 0).mean()),
        "midpoint_pnl_usd": float(100.0 * sum(row["midpoint_return"] for row in rows)),
        "spread_drag_usd": float(sum(row["spread_drag_usd"] for row in rows)),
        "adverse_cent_pnl_usd": float(sum(row["adverse_cent_pnl_usd"] for row in rows)),
        "median_entry_event_wait_seconds": float(np.median([row["entry"]["event_wait_seconds"] for row in rows])),
        "p95_entry_event_wait_seconds": float(np.quantile([row["entry"]["event_wait_seconds"] for row in rows], 0.95)),
        "median_exit_event_wait_seconds": float(np.median([row["exit"]["event_wait_seconds"] for row in rows])),
        "by_symbol_pnl_usd": {
            symbol: float(sum(row["fixed_100_pnl_usd"] for row in rows if row["symbol"] == symbol))
            for symbol in ("UPRO", "SPXU")
        },
        "by_year_pnl_usd": {
            str(year): float(sum(row["fixed_100_pnl_usd"] for row in rows if row["date"].startswith(str(year))))
            for year in sorted({int(row["date"][:4]) for row in rows})
        },
    }


def render(payload: dict[str, Any]) -> str:
    lines = [
        "# V20 Event-Level TBBO Execution-Fidelity Audit v34",
        "",
        "## Status",
        "",
        "V20 remains rejected because its unchanged original development test failed winner-concentration. This audit is execution reconstruction, not a new strategy, a repair, or pristine validation.",
        "",
        "The frozen V20 economic rule remains: prior ES volume scar; current 09:30–09:59 ES center/terminal confirmation; long UPRO for positive state or long SPXU for negative state; enter after the causal 10:01 boundary; liquidate on the minute after structural ES invalidation or at 15:30.",
        "",
        "## Event-level execution model",
        "",
        "- Entry: first valid EQUS.MINI trade-event pre-trade ask after 10:01 plus 1, 5, or 60 seconds.",
        "- Exit: first valid trade-event pre-trade bid after the unchanged V20 target.",
        "- Quotes with nonpositive prices or ask below bid are rejected.",
        "- If no valid event appears within 60 seconds, the order is unfilled and excluded; no forward fill is allowed.",
        "- EQUS.MINI is derived and anonymized, not official SIP NBBO.",
        "- True standing quote age is not present in TBBO; event wait and capture latency are the measurable substitutes.",
        "- Spread drag is midpoint-return P&L minus executable ask-to-bid P&L. One-cent-per-share adverse execution is reported separately.",
        "",
        "## Results",
        "",
        "| Partition | Delay | Trades | Fixed-$100 P&L | PF | Spread drag | +1 cent/share P&L | UPRO | SPXU |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for partition, delays in payload["partitions"].items():
        for delay, result in delays.items():
            if not result.get("trades"):
                lines.append(f"| {partition} | {delay}s | 0 | n/a | n/a | n/a | n/a | n/a | n/a |")
                continue
            lines.append(
                f"| {partition} | {delay}s | {result['trades']} | ${result['fixed_100_pnl_usd']:.2f} | {result['profit_factor']:.3f} | ${result['spread_drag_usd']:.2f} | ${result['adverse_cent_pnl_usd']:.2f} | ${result['by_symbol_pnl_usd']['UPRO']:.2f} | ${result['by_symbol_pnl_usd']['SPXU']:.2f} |"
            )
    lines.extend([
        "",
        "## Interpretation boundary",
        "",
        "The overlap begins on 2023-03-28, so this feed cannot reconstruct V20's 2021–2022 executions. Results after 2023 are historically contaminated because the rule and much of the price history were previously examined. Any improved fill fidelity cannot undo V20's failed original concentration gate, and no rule component may be modified from these outcomes.",
        "",
        "The frozen V20 ES source ends at 2025-12-31. The zero-trade 2026 rows therefore mean no V20 states were available, not that a 2026 execution sample failed.",
        "",
        "Machine-readable evidence: `research_scout/v20_tbbo_execution_fidelity_audit_v34.json`.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--render-only":
        payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
        REPORT.write_text(render(payload) + "\n", encoding="utf-8")
        print(json.dumps({"report": str(REPORT.relative_to(ROOT))}, indent=2))
        return 0
    excluded = degraded(ARCX_CONDITION) | degraded(EQUS_CONDITION)
    signal_states = v20.states()
    orders = build_orders(signal_states, excluded)
    quotes, decode = scan_quotes(orders)
    trades = make_trades(orders, quotes)
    partitions: dict[str, Any] = {}
    for name, (start, end) in PARTITIONS.items():
        partitions[name] = {}
        for delay in DELAYS:
            rows = [
                row for row in trades
                if row["delay_seconds"] == delay and start <= pd.Timestamp(row["date"]) <= end
            ]
            partitions[name][str(delay)] = summarize(rows)
    source_hash = hashlib.sha256((ROOT / "research_scout" / "es_scar_to_leveraged_etf_prereg_v20.json").read_bytes()).hexdigest()
    payload = {
        "status": "execution_fidelity_audit_only_v20_remains_rejected",
        "source_v20_prereg_sha256": source_hash,
        "rule_modified": False,
        "feed": "EQUS.MINI derived anonymized multi-venue TBBO, not official SIP NBBO",
        "logical_coverage": "2023-03-28 through 2026-07-24",
        "degraded_dates_excluded_union": sorted(day.strftime("%Y-%m-%d") for day in excluded),
        "quote_filter": "bid > 0, ask > 0, ask >= bid",
        "maximum_event_wait_seconds": MAX_EVENT_WAIT_SECONDS,
        "standing_quote_age_observable": False,
        "orders_constructed": len(orders),
        "orders_with_both_fills": len(trades),
        "decode": decode,
        "partitions": partitions,
        "trades": trades,
        "contamination_warning": "Execution audit after the V20 result; not a new pristine validation and cannot rescue the failed concentration gate.",
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(render(payload) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT.relative_to(ROOT)), "orders": len(orders), "filled": len(trades)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
