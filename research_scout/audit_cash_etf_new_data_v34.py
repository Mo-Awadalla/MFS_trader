"""Decode and audit the Databento cash-ETF package without calculating returns.

This script makes no network calls. It treats the truncated EQUS.MINI prefix as a
bounded stream and stops as soon as the first 2024-10-03 New York record is seen.
"""

from __future__ import annotations

import json
import math
import sys
import warnings
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import databento as db  # noqa: E402

PACKAGE = ROOT / "external_artifacts" / "databento_cash_etf_budget_v1"
INVENTORY = PACKAGE / "logical_inventory.json"
VALIDATION = PACKAGE / "validation_report.json"
ARCX_CONDITION = PACKAGE / "ARCX.PILLAR" / "dataset_condition.json"
EQUS_CONDITION = PACKAGE / "EQUS.MINI" / "dataset_condition.json"
IMBALANCE = PACKAGE / "ARCX.PILLAR" / "imbalance" / "spy_imbalance_2021-01-01_2026-07-27.dbn.zst"
STATISTICS = PACKAGE / "ARCX.PILLAR" / "statistics" / "cash_etf_statistics_2021-01-01_2026-07-27.dbn.zst"
STATUS = PACKAGE / "ARCX.PILLAR" / "status" / "cash_etf_status_2021-01-01_2026-07-27.dbn.zst"
ARCX_DEFINITION = PACKAGE / "ARCX.PILLAR" / "definition" / "cash_etf_arcx_definition_2021-01-01_2026-07-27.dbn.zst"
EQUS_DEFINITION = PACKAGE / "EQUS.MINI" / "definition" / "cash_etf_equs_definition_2023-03-28_2026-07-27.dbn.zst"
TBBO_PREFIX = PACKAGE / "EQUS.MINI" / "tbbo" / "cash_etf_tbbo_2023-03-28_2026-07-27.dbn.partial.dbn.zst"
TBBO_TAIL = PACKAGE / "EQUS.MINI" / "tbbo" / "cash_etf_tbbo_tail_2024-10-03_2026-07-27.dbn.zst"
OUTPUT = ROOT / "research_scout" / "new_data_technical_audit_v34.json"
SNAPSHOTS_OUTPUT = ROOT / "research_scout" / "spy_auction_snapshots_v34.json"
TARGET_QUOTES_OUTPUT = ROOT / "research_scout" / "cash_etf_tbbo_target_quotes_v34.json"
REPORT = ROOT / "research_scout" / "NEW_DATA_TECHNICAL_AUDIT_V34.md"

NY = "America/New_York"
SYMBOLS = ["SPY", "SSO", "UPRO", "SH", "SDS", "SPXU"]
OPEN_CUTOFFS = {
    "09:28:00": 9 * 3600 + 28 * 60,
    "09:29:00": 9 * 3600 + 29 * 60,
    "09:29:30": 9 * 3600 + 29 * 60 + 30,
    "09:29:50": 9 * 3600 + 29 * 60 + 50,
    "09:29:59": 9 * 3600 + 29 * 60 + 59,
}
FIXED_TARGETS = {
    "09:30:01": 9 * 3600 + 30 * 60 + 1,
    "09:30:05": 9 * 3600 + 30 * 60 + 5,
    "09:31:00": 9 * 3600 + 31 * 60,
    "09:31:01": 9 * 3600 + 31 * 60 + 1,
    "09:31:05": 9 * 3600 + 31 * 60 + 5,
    "09:32:00": 9 * 3600 + 32 * 60,
    "09:35:00": 9 * 3600 + 35 * 60,
    "09:45:00": 9 * 3600 + 45 * 60,
    "10:01:01": 10 * 3600 + 60 + 1,
    "10:01:05": 10 * 3600 + 60 + 5,
    "10:02:00": 10 * 3600 + 2 * 60,
    "15:30:01": 15 * 3600 + 30 * 60 + 1,
    "15:30:05": 15 * 3600 + 30 * 60 + 5,
    "15:31:00": 15 * 3600 + 31 * 60,
    "15:59:00": 15 * 3600 + 59 * 60,
}
WINDOWS = {
    "premarket_07_00_09_30": (7 * 3600, 9 * 3600 + 30 * 60),
    "open_09_30_10_30": (9 * 3600 + 30 * 60, 10 * 3600 + 30 * 60),
    "midday_10_30_15_00": (10 * 3600 + 30 * 60, 15 * 3600),
    "close_15_00_16_00": (15 * 3600, 16 * 3600),
}
LATENCY_BINS_NS = np.array([0, 1_000, 10_000, 100_000, 1_000_000, 10_000_000, 100_000_000, 1_000_000_000, np.iinfo(np.int64).max], dtype=np.int64)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def degraded_dates(path: Path) -> set[str]:
    return {
        row["date"]
        for row in load_json(path)["conditions"]
        if row["condition"] != "available"
    }


def clean_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not math.isfinite(float(value)) else float(value)
    if pd.isna(value):
        return None
    return value


def enum_name(enum_cls: Any, value: Any) -> str:
    text = str(value)
    if not text.lstrip("-").isdigit():
        return text
    try:
        resolved = enum_cls.from_int(int(value))
        return getattr(resolved, "name", str(resolved))
    except Exception:
        return text


def frame_times(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    event = pd.to_datetime(frame["ts_event"], utc=True).dt.tz_convert(NY)
    days = event.dt.strftime("%Y-%m-%d")
    seconds = (
        event.dt.hour * 3600
        + event.dt.minute * 60
        + event.dt.second
        + event.dt.microsecond / 1_000_000.0
        + event.dt.nanosecond / 1_000_000_000.0
    )
    return event, days, seconds


def audit_definitions(path: Path) -> dict[str, Any]:
    frame = db.read_dbn(path).to_df(map_symbols=True, tz="UTC").reset_index()
    event, days, _ = frame_times(frame)
    by_symbol: dict[str, Any] = {}
    for symbol, group in frame.groupby("symbol", sort=True):
        by_symbol[str(symbol)] = {
            "rows": int(len(group)),
            "instrument_ids": sorted(int(v) for v in group["instrument_id"].unique()),
            "raw_symbols": sorted(str(v) for v in group["raw_symbol"].dropna().unique()),
            "update_actions": dict(Counter(group["security_update_action"].astype(str))),
            "min_price_increments": sorted(float(v) for v in group["min_price_increment"].dropna().unique() if float(v) > 0),
            "activation_min": clean_value(group["activation"].dropna().min()) if group["activation"].notna().any() else None,
            "activation_max": clean_value(group["activation"].dropna().max()) if group["activation"].notna().any() else None,
            "first_event_utc": event.loc[group.index].min().isoformat(),
            "last_event_utc": event.loc[group.index].max().isoformat(),
            "session_dates": int(days.loc[group.index].nunique()),
        }
    return {
        "rows": int(len(frame)),
        "symbols": by_symbol,
        "instrument_id_to_symbol": {
            str(int(instrument_id)): str(group["symbol"].iloc[-1])
            for instrument_id, group in frame.sort_values("ts_event").groupby("instrument_id")
        },
    }


def audit_status() -> dict[str, Any]:
    frame = db.read_dbn(STATUS).to_df(map_symbols=True, tz="UTC").reset_index()
    event, days, seconds = frame_times(frame)
    frame = frame.assign(event_ny=event, session_date=days, second=seconds)
    action_names = frame["action"].map(lambda v: enum_name(db.StatusAction, v))
    reason_names = frame["reason"].map(lambda v: enum_name(db.StatusReason, v))
    event_names = frame["trading_event"].map(lambda v: enum_name(db.TradingEvent, v))
    frame = frame.assign(action_name=action_names, reason_name=reason_names, trading_event_name=event_names)
    rth = frame["second"].ge(9 * 3600 + 30 * 60) & frame["second"].lt(16 * 3600)
    action_abnormal = frame["action_name"].str.upper().isin({"HALT", "PAUSE", "SUSPEND"})
    reason_abnormal = ~frame["reason_name"].str.upper().isin({"NONE", "SCHEDULED", "0"})
    quote_off = frame["is_quoting"].astype(str).str.upper().isin({"N", "NO", "FALSE", "0"})
    abnormal_mask = rth & (action_abnormal | reason_abnormal | quote_off)
    abnormal = frame.loc[abnormal_mask]
    by_symbol: dict[str, Any] = {}
    for symbol, group in frame.groupby("symbol", sort=True):
        bad = abnormal.loc[abnormal["symbol"].eq(symbol)]
        by_symbol[str(symbol)] = {
            "rows": int(len(group)),
            "session_dates": int(group["session_date"].nunique()),
            "actions": dict(Counter(group["action_name"])),
            "reasons": dict(Counter(group["reason_name"])),
            "trading_events": dict(Counter(group["trading_event_name"])),
            "is_trading": dict(Counter(group["is_trading"].astype(str))),
            "is_quoting": dict(Counter(group["is_quoting"].astype(str))),
            "is_short_sell_restricted": dict(Counter(group["is_short_sell_restricted"].astype(str))),
            "flagged_dates": sorted(bad["session_date"].unique().tolist()),
            "flagged_rows": int(len(bad)),
            "ssr_dates": sorted(
                group.loc[
                    group["is_short_sell_restricted"].astype(str).str.upper().isin({"Y", "YES", "TRUE", "1"}),
                    "session_date",
                ].unique().tolist()
            ),
        }
    return {
        "rows": int(len(frame)),
        "action_encoding_note": "Names are resolved with databento_dbn enum metadata when integer-coded.",
        "by_symbol": by_symbol,
    }


def audit_statistics() -> dict[str, Any]:
    frame = db.read_dbn(STATISTICS).to_df(map_symbols=True, tz="UTC").reset_index()
    event, days, _ = frame_times(frame)
    frame = frame.assign(event_ny=event, session_date=days)
    frame["stat_name"] = frame["stat_type"].map(lambda v: enum_name(db.StatType, v))
    by_type: dict[str, Any] = {}
    for stat_name, group in frame.groupby("stat_name", sort=True):
        by_type[str(stat_name)] = {
            "rows": int(len(group)),
            "symbols": dict(Counter(group["symbol"].astype(str))),
            "session_dates": int(group["session_date"].nunique()),
            "positive_price_rows": int(pd.to_numeric(group["price"], errors="coerce").gt(0).sum()),
            "positive_quantity_rows": int(pd.to_numeric(group["quantity"], errors="coerce").gt(0).sum()),
            "first_event_ny": group["event_ny"].min().isoformat(),
            "last_event_ny": group["event_ny"].max().isoformat(),
        }
    relevant = [
        name
        for name in by_type
        if any(token in name.upper() for token in ("OPEN", "CLOSE", "UNCROSS", "AUCTION_COLLAR", "VWAP"))
    ]
    return {
        "rows": int(len(frame)),
        "types": by_type,
        "potentially_relevant_types": relevant,
        "usage_decision": "Use only types with explicit opening/closing/uncrossing/collar semantics and adequate session coverage; venue-specific types remain excluded without venue documentation.",
    }


def audit_imbalance(arcx_degraded: set[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    total_rows = 0
    type_counts: Counter[str] = Counter()
    type_days: defaultdict[str, set[str]] = defaultdict(set)
    auction_time_clocks: defaultdict[str, Counter[str]] = defaultdict(Counter)
    hour_counts: Counter[str] = Counter()
    degraded_rows = 0
    field_nonzero: defaultdict[str, Counter[str]] = defaultdict(Counter)
    value_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    receive_latency_bins = np.zeros(len(LATENCY_BINS_NS) - 1, dtype=np.int64)
    receive_latency_negative = 0
    snapshots: dict[tuple[str, str], dict[str, Any]] = {}
    columns = [
        "ref_price", "cont_book_clr_price", "auct_interest_clr_price", "ssr_filling_price",
        "ind_match_price", "upper_collar", "lower_collar", "paired_qty",
        "total_imbalance_qty", "market_imbalance_qty", "unpaired_qty",
    ]
    categorical = ["side", "auction_status", "freeze_status", "num_extensions", "unpaired_side", "significant_imbalance"]
    for chunk_number, frame in enumerate(db.read_dbn(IMBALANCE).to_df(count=1_000_000, map_symbols=True, tz="UTC"), start=1):
        frame = frame.reset_index()
        total_rows += len(frame)
        event, days, seconds = frame_times(frame)
        frame = frame.assign(event_ny=event, session_date=days, second=seconds)
        types = frame["auction_type"].astype(str)
        type_counts.update(types)
        hour_counts.update(event.dt.strftime("%H"))
        degraded_rows += int(days.isin(arcx_degraded).sum())
        for auction_type, group in frame.groupby(types, sort=False):
            auction_type = str(auction_type)
            type_days[auction_type].update(group["session_date"].unique())
            # ARCX AuctionTime is an exchange-local wall-clock field. The DBN
            # pretty representation carries a +00:00 label, but timezone
            # conversion would incorrectly turn 09:30 into 04:30/05:30.
            projected = pd.to_datetime(group["auction_time"], utc=True, errors="coerce")
            auction_time_clocks[auction_type].update(projected.dropna().dt.strftime("%H:%M:%S"))
            for column in columns:
                field_nonzero[auction_type][column] += int(pd.to_numeric(group[column], errors="coerce").gt(0).sum())
            for column in categorical:
                value_counts[f"{auction_type}:{column}"].update(group[column].astype(str))
        recv = pd.to_datetime(frame["ts_recv"], utc=True) if "ts_recv" in frame else pd.to_datetime(frame.index, utc=True)
        event_utc = pd.to_datetime(frame["ts_event"], utc=True)
        latency = (recv.astype("int64") - event_utc.astype("int64")).to_numpy(dtype=np.int64)
        receive_latency_negative += int((latency < 0).sum())
        hist, _ = np.histogram(np.maximum(latency, 0), bins=LATENCY_BINS_NS)
        receive_latency_bins += hist
        opening = frame.loc[types.eq("M") & seconds.ge(9 * 3600 + 27 * 60) & seconds.lt(9 * 3600 + 30 * 60)]
        if not opening.empty:
            for cutoff_name, cutoff in OPEN_CUTOFFS.items():
                eligible = opening.loc[opening["second"].lt(cutoff)]
                if eligible.empty:
                    continue
                latest = eligible.sort_values("ts_event").groupby("session_date", sort=False).tail(1)
                for row in latest.itertuples(index=False):
                    key = (str(row.session_date), cutoff_name)
                    prior = snapshots.get(key)
                    payload = {
                        "session_date": str(row.session_date),
                        "cutoff": cutoff_name,
                        "ts_event": pd.Timestamp(row.ts_event).isoformat(),
                        "ts_recv": pd.Timestamp(row.ts_recv).isoformat() if hasattr(row, "ts_recv") else None,
                        "auction_time": clean_value(row.auction_time),
                        "auction_type": str(row.auction_type),
                        "ref_price": clean_value(row.ref_price),
                        "cont_book_clr_price": clean_value(row.cont_book_clr_price),
                        "auct_interest_clr_price": clean_value(row.auct_interest_clr_price),
                        "ssr_filling_price": clean_value(row.ssr_filling_price),
                        "ind_match_price": clean_value(row.ind_match_price),
                        "upper_collar": clean_value(row.upper_collar),
                        "lower_collar": clean_value(row.lower_collar),
                        "paired_qty": clean_value(row.paired_qty),
                        "total_imbalance_qty": clean_value(row.total_imbalance_qty),
                        "market_imbalance_qty": clean_value(row.market_imbalance_qty),
                        "unpaired_qty": clean_value(row.unpaired_qty),
                        "side": str(row.side),
                        "auction_status": clean_value(row.auction_status),
                        "freeze_status": clean_value(row.freeze_status),
                        "num_extensions": clean_value(row.num_extensions),
                        "unpaired_side": str(row.unpaired_side),
                        "significant_imbalance": str(row.significant_imbalance),
                        "arcx_degraded": str(row.session_date) in arcx_degraded,
                    }
                    if prior is None or payload["ts_event"] > prior["ts_event"]:
                        snapshots[key] = payload
        if chunk_number % 10 == 0:
            print(f"imbalance chunks={chunk_number} rows={total_rows}", flush=True)
    by_cutoff: dict[str, Any] = {}
    for cutoff in OPEN_CUTOFFS:
        rows = [row for (day, name), row in snapshots.items() if name == cutoff and not row["arcx_degraded"]]
        by_cutoff[cutoff] = {
            "nondegraded_sessions": len(rows),
            "first_session": min((row["session_date"] for row in rows), default=None),
            "last_session": max((row["session_date"] for row in rows), default=None),
            "side_counts": dict(Counter(row["side"] for row in rows)),
            "positive_ref_price": sum((row["ref_price"] or 0) > 0 for row in rows),
            "positive_ind_match_price": sum((row["ind_match_price"] or 0) > 0 for row in rows),
            "positive_paired_qty": sum((row["paired_qty"] or 0) > 0 for row in rows),
            "positive_total_imbalance_qty": sum((row["total_imbalance_qty"] or 0) > 0 for row in rows),
        }
    audit = {
        "rows": total_rows,
        "degraded_rows": degraded_rows,
        "auction_type_counts": dict(type_counts),
        "auction_type_session_counts": {key: len(value) for key, value in type_days.items()},
        "event_hour_counts_ny": dict(hour_counts),
        "projected_auction_time_clock_counts_ny": {key: dict(value) for key, value in auction_time_clocks.items()},
        "field_positive_counts_by_auction_type": {key: dict(value) for key, value in field_nonzero.items()},
        "categorical_counts": {key: dict(value) for key, value in value_counts.items()},
        "receive_minus_event_latency_histogram_ns": {
            f"[{int(LATENCY_BINS_NS[index])},{int(LATENCY_BINS_NS[index + 1])})": int(value)
            for index, value in enumerate(receive_latency_bins)
        },
        "negative_receive_latency_rows": receive_latency_negative,
        "opening_snapshot_coverage": by_cutoff,
        "timestamp_interpretation": {
            "ts_event": "Matching-engine-received timestamp; used for feature observability and ordering.",
            "ts_recv": "Capture-server-received timestamp (DataFrame index before reset); audited but not used to make a signal earlier.",
            "auction_time": "Projected auction timestamp, not publication timestamp or realized print.",
        },
    }
    snapshot_payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "returns_read": False,
        "selection": "latest auction_type M message strictly before each named cutoff",
        "degraded_dates_flagged_not_dropped": sorted(arcx_degraded),
        "snapshots": sorted(snapshots.values(), key=lambda row: (row["session_date"], row["cutoff"])),
    }
    return audit, snapshot_payload


def window_name(seconds: pd.Series) -> pd.Series:
    result = pd.Series("outside", index=seconds.index, dtype="object")
    for name, (start, end) in WINDOWS.items():
        result.loc[seconds.ge(start) & seconds.lt(end)] = name
    return result


def audit_tbbo(equs_degraded: set[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    segment_rows: Counter[str] = Counter()
    segment_first: dict[str, str] = {}
    segment_last: dict[str, str] = {}
    symbol_rows: Counter[str] = Counter()
    valid_rows: Counter[str] = Counter()
    crossed_rows: Counter[str] = Counter()
    nonpositive_rows: Counter[str] = Counter()
    degraded_rows: Counter[str] = Counter()
    symbol_days: defaultdict[str, set[str]] = defaultdict(set)
    window_days: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    window_rows: Counter[tuple[str, str]] = Counter()
    latency_hist: defaultdict[str, np.ndarray] = defaultdict(lambda: np.zeros(len(LATENCY_BINS_NS) - 1, dtype=np.int64))
    target_quotes: dict[tuple[str, str, str], dict[str, Any]] = {}
    prefix_boundary_seen = False
    prefix_terminal_warning_observed = False
    sources = [
        ("prefix_through_2024-10-02", TBBO_PREFIX, "2024-10-02", True),
        ("tail_from_2024-10-03", TBBO_TAIL, None, False),
    ]
    for segment, path, cutoff, must_break in sources:
        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            iterator = db.read_dbn(path).to_df(count=100_000, map_symbols=True, tz="UTC")
            for chunk_number, frame in enumerate(iterator, start=1):
                frame = frame.reset_index()
                event, days, seconds = frame_times(frame)
                frame = frame.assign(event_ny=event, session_date=days, second=seconds)
                if cutoff is not None and days.gt(cutoff).any():
                    prefix_boundary_seen = True
                    frame = frame.loc[days.le(cutoff)].copy()
                    if not frame.empty:
                        event, days, seconds = frame_times(frame)
                        frame = frame.assign(event_ny=event, session_date=days, second=seconds)
                    stop_after_chunk = True
                else:
                    stop_after_chunk = False
                if not frame.empty:
                    segment_rows[segment] += len(frame)
                    segment_first.setdefault(segment, frame["event_ny"].min().isoformat())
                    segment_last[segment] = frame["event_ny"].max().isoformat()
                    symbols = frame["symbol"].astype(str)
                    symbol_rows.update(symbols)
                    bids = pd.to_numeric(frame["bid_px_00"], errors="coerce")
                    asks = pd.to_numeric(frame["ask_px_00"], errors="coerce")
                    nonpositive = bids.le(0) | asks.le(0) | bids.isna() | asks.isna()
                    crossed = asks.lt(bids) & ~nonpositive
                    valid = ~nonpositive & ~crossed
                    for symbol in SYMBOLS:
                        mask = symbols.eq(symbol)
                        valid_mask = mask & valid
                        valid_rows[symbol] += int(valid_mask.sum())
                        crossed_rows[symbol] += int((mask & crossed).sum())
                        nonpositive_rows[symbol] += int((mask & nonpositive).sum())
                        degraded_rows[symbol] += int((valid_mask & days.isin(equs_degraded)).sum())
                        if valid_mask.any():
                            symbol_days[symbol].update(days.loc[valid_mask].unique())
                    valid_frame = frame.loc[valid].copy()
                    if not valid_frame.empty:
                        valid_frame["window"] = window_name(valid_frame["second"])
                        for (symbol, window), group in valid_frame.groupby(["symbol", "window"], sort=False):
                            if window == "outside":
                                continue
                            key = (str(symbol), str(window))
                            window_rows[key] += len(group)
                            window_days[key].update(group["session_date"].unique())
                        recv = pd.to_datetime(valid_frame["ts_recv"], utc=True)
                        event_utc = pd.to_datetime(valid_frame["ts_event"], utc=True)
                        latencies = (recv.astype("int64") - event_utc.astype("int64")).to_numpy(dtype=np.int64)
                        for symbol, group_index in valid_frame.groupby("symbol").groups.items():
                            positions = valid_frame.index.get_indexer(group_index)
                            hist, _ = np.histogram(np.maximum(latencies[positions], 0), bins=LATENCY_BINS_NS)
                            latency_hist[str(symbol)] += hist
                        for target_name, target_second in FIXED_TARGETS.items():
                            eligible = valid_frame.loc[
                                valid_frame["second"].ge(target_second)
                                & valid_frame["second"].le(target_second + 60.0)
                            ]
                            if eligible.empty:
                                continue
                            first = eligible.sort_values("ts_event").groupby(["session_date", "symbol"], sort=False).head(1)
                            for row in first.itertuples(index=False):
                                key = (str(row.session_date), str(row.symbol), target_name)
                                wait_seconds = float(row.second) - target_second
                                candidate = {
                                    "session_date": str(row.session_date),
                                    "symbol": str(row.symbol),
                                    "target": target_name,
                                    "target_second_ny": target_second,
                                    "ts_event": pd.Timestamp(row.ts_event).isoformat(),
                                    "ts_recv": pd.Timestamp(row.ts_recv).isoformat(),
                                    "event_wait_seconds": wait_seconds,
                                    "bid": float(row.bid_px_00),
                                    "ask": float(row.ask_px_00),
                                    "bid_size": int(row.bid_sz_00),
                                    "ask_size": int(row.ask_sz_00),
                                    "trade_price": float(row.price),
                                    "trade_size": int(row.size),
                                    "segment": segment,
                                    "equs_degraded": str(row.session_date) in equs_degraded,
                                }
                                old = target_quotes.get(key)
                                if old is None or candidate["ts_event"] < old["ts_event"]:
                                    target_quotes[key] = candidate
                if chunk_number % 20 == 0:
                    print(f"tbbo segment={segment} chunks={chunk_number} rows={segment_rows[segment]}", flush=True)
                if stop_after_chunk:
                    break
            if must_break:
                prefix_terminal_warning_observed = any(
                    "truncated" in str(item.message).lower()
                    or "incomplete record" in str(item.message).lower()
                    for item in caught_warnings
                )
        if must_break and not prefix_boundary_seen:
            raise RuntimeError("Prefix cutoff boundary was not observed before EOF; refusing blind truncated decode")
    spy_rth_days = window_days[("SPY", "open_09_30_10_30")] | window_days[("SPY", "midday_10_30_15_00")] | window_days[("SPY", "close_15_00_16_00")]
    coverage: dict[str, Any] = {}
    for symbol in SYMBOLS:
        coverage[symbol] = {
            "rows_total": int(symbol_rows[symbol]),
            "rows_valid": int(valid_rows[symbol]),
            "crossed_rows_rejected": int(crossed_rows[symbol]),
            "nonpositive_rows_rejected": int(nonpositive_rows[symbol]),
            "valid_rows_on_degraded_dates": int(degraded_rows[symbol]),
            "valid_session_dates": len(symbol_days[symbol]),
            "missing_rth_sessions_vs_spy": sorted(spy_rth_days - symbol_days[symbol]),
            "rth_session_coverage_vs_spy_pct": 100.0 * len(symbol_days[symbol] & spy_rth_days) / max(len(spy_rth_days), 1),
            "windows": {
                name: {
                    "valid_rows": int(window_rows[(symbol, name)]),
                    "session_dates": len(window_days[(symbol, name)]),
                    "coverage_vs_spy_same_window_pct": 100.0 * len(window_days[(symbol, name)] & window_days[("SPY", name)]) / max(len(window_days[("SPY", name)]), 1),
                }
                for name in WINDOWS
            },
            "receive_minus_event_latency_histogram_ns": {
                f"[{int(LATENCY_BINS_NS[index])},{int(LATENCY_BINS_NS[index + 1])})": int(value)
                for index, value in enumerate(latency_hist[symbol])
            },
        }
    target_coverage: dict[str, Any] = {}
    target_rows = list(target_quotes.values())
    for target_name in FIXED_TARGETS:
        target_coverage[target_name] = {}
        for symbol in SYMBOLS:
            rows = [row for row in target_rows if row["target"] == target_name and row["symbol"] == symbol and not row["equs_degraded"]]
            waits = [row["event_wait_seconds"] for row in rows]
            target_coverage[target_name][symbol] = {
                "nondegraded_sessions_with_event_within_60s": len(rows),
                "median_event_wait_seconds": float(np.median(waits)) if waits else None,
                "p95_event_wait_seconds": float(np.quantile(waits, 0.95)) if waits else None,
                "max_event_wait_seconds": max(waits) if waits else None,
            }
    audit = {
        "segments": {
            key: {"rows_consumed": int(value), "first_event_ny": segment_first.get(key), "last_event_ny": segment_last.get(key)}
            for key, value in segment_rows.items()
        },
        "prefix_boundary_seen_and_stopped": prefix_boundary_seen,
        "prefix_terminal_warning_observed": prefix_terminal_warning_observed,
        "deduplication_rule_applied": "prefix New York dates <= 2024-10-02; tail dates >= 2024-10-03",
        "symbols": coverage,
        "fixed_target_coverage": target_coverage,
        "feed_semantics": {
            "official_sip_nbbo": False,
            "description": "Derived anonymized multi-venue EQUS.MINI TBBO; each record is a trade event with BBO immediately before the trade's effect.",
            "standing_quote_age_observable": False,
            "quote_age_policy": "The schema has no timestamp for when each standing bid/ask was established. Report event wait from order target and capture latency; do not claim true quote age. Reject simulations when no valid pre-trade BBO event appears within the preregistered maximum wait.",
        },
    }
    targets_payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "returns_read": False,
        "deduplication_rule": audit["deduplication_rule_applied"],
        "quote_filter": "bid > 0, ask > 0, ask >= bid",
        "event_wait_limit_seconds": 60,
        "quotes": sorted(target_rows, key=lambda row: (row["session_date"], row["symbol"], row["target"])),
    }
    return audit, targets_payload


def render_markdown(payload: dict[str, Any]) -> str:
    imbalance = payload["imbalance"]
    tbbo = payload["tbbo"]
    lines = [
        "# New Cash-ETF Data Technical Audit v34",
        "",
        "## Scope and evidence boundary",
        "",
        "This is a returns-blind decode and capability audit. It makes no paid API calls and calculates no post-signal strategy return. The package inventory and validation report are authoritative for file identity, hashes, row counts, and clean/partial EOF status.",
        "",
        "Historical fields are new, historical price outcomes are not. Auction measurement in 2021–2023 is development/measurement evidence; 2024–2025 is historically contaminated validation; 2026 is a temporal extension, not automatically pristine.",
        "",
        "## File integrity and bounded decoding",
        "",
        f"- Files inventoried: {payload['validation_report']['files_found']}.",
        f"- Clean EOF overall: {payload['validation_report']['all_clean_eof']} because the prefix is intentionally partial.",
        f"- Prefix boundary observed and logical consumption stopped at 2024-10-02: {tbbo['prefix_boundary_seen_and_stopped']}.",
        f"- The SDK explicitly reported and trimmed the incomplete terminal record while yielding preceding complete records: {tbbo['prefix_terminal_warning_observed']}.",
        f"- Prefix records consumed through 2024-10-02: {tbbo['segments']['prefix_through_2024-10-02']['rows_consumed']:,}.",
        f"- Clean-tail records consumed from 2024-10-03: {tbbo['segments']['tail_from_2024-10-03']['rows_consumed']:,}.",
        "- No segment concatenation was performed without the mandatory New York date partition.",
        "",
        "## Timestamp semantics",
        "",
        "- `ts_event` is the matching-engine-received timestamp and is the causal ordering clock.",
        "- The DataFrame index is `ts_recv`, the capture-server-received timestamp. It is audited only; it never makes a signal earlier.",
        "- `auction_time` is a projected auction timestamp, not the message-publication time and not a realized auction print.",
        "- All session boundaries and cutoffs are converted from UTC to `America/New_York`, including DST.",
        "",
        "## SPY ARCX.PILLAR imbalance",
        "",
        f"- Decoded records: {imbalance['rows']:,}.",
        f"- Auction-type counts: {json.dumps(imbalance['auction_type_counts'], sort_keys=True)}.",
        f"- Session counts by auction type: {json.dumps(imbalance['auction_type_session_counts'], sort_keys=True)}.",
        "- Databento's ARCX.PILLAR venue documentation defines `O` as Early Opening, `M` as Core Opening, `H` as Halt Resume, and `C` as Closing. This SPY file contains O/M/C and no H messages.",
        "- `auction_time` is an exchange-local wall-clock field. The DBN pretty representation's `+00:00` label must not be timezone-converted; doing so would create false 04:30/05:30 clocks from a 09:30 Core Open.",
        "- Snapshot artifacts select the latest `M` message strictly before each cutoff. No final match or post-auction state is used to initiate a pre-auction order.",
        "",
        "Field interpretation follows Databento's ARCX.PILLAR venue documentation: `ref_price` is the imbalance calculation price; `cont_book_clr_price` includes cross and continuous orders; `auct_interest_clr_price` uses eligible auction-only interest; and `ind_match_price` maximizes matched shares subject to collars and includes reserve quantity. **There is a documented semantic break on 2025-11-13:** `paired_qty`, `total_imbalance_qty`, and `market_imbalance_qty` are measured at `ref_price` from that date onward, but were measured at `ind_match_price` before it. Cross-regime level comparisons require an explicit break control.",
        "",
        "ARCX documentation also defines auction status 0/1/2/3, freeze status 0/1, extension count, and the significant-imbalance flag. Opening/closing statistics are final auction outcomes published after the cross and cannot be used for a pre-auction order.",
        "",
        "## EQUS.MINI TBBO semantics and quality",
        "",
        "EQUS.MINI is not described here as official SIP NBBO. It is a derived, anonymized multi-venue product. TBBO records occur on trades and carry the BBO immediately before each trade's effect; they do not contain every quote update.",
        "",
        "True standing-quote age cannot be reconstructed because the record does not timestamp when each bid or ask was established. The executable policy therefore records the wait from simulated order target to the first valid trade-event BBO and rejects waits beyond a frozen limit. Capture latency (`ts_recv - ts_event`) is reported separately.",
        "",
        "| Symbol | Valid rows | Crossed rejected | Nonpositive rejected | RTH session coverage vs SPY |",
        "|---|---:|---:|---:|---:|",
    ]
    for symbol in SYMBOLS:
        row = tbbo["symbols"][symbol]
        lines.append(f"| {symbol} | {row['rows_valid']:,} | {row['crossed_rows_rejected']:,} | {row['nonpositive_rows_rejected']:,} | {row['rth_session_coverage_vs_spy_pct']:.2f}% |")
    lines.extend([
        "",
        "Missing-session lists and coverage by premarket/open/midday/close window are machine-readable in `research_scout/new_data_technical_audit_v34.json`.",
        "",
        "## Definitions, status, and statistics",
        "",
        "Definitions verify the requested symbol/instrument mappings and expose definition updates, minimum ticks, and activation metadata. Status records are decoded into trading, quoting, halt/pause/suspend, and SSR states; flagged dates are exclusions or explicit diagnostics, never silent inclusions.",
        "",
        "Statistics are not used merely because they exist. ARCX venue documentation maps `OPENING_PRICE` to the Core Opening auction, `CLOSE_PRICE` to the Closing auction, and `UNCROSSING_PRICE` to Early Opening and halt/re-opening auctions. These are final outcomes: useful for integrity and post-event measurement, prohibited as pre-auction predictors.",
        "",
        "Venue source: https://databento.com/docs/venues-and-datasets/arcx-pillar (accessed 2026-07-28).",
        "",
        "## Degraded dates",
        "",
        f"- ARCX.PILLAR degraded dates ({len(payload['degraded_dates']['ARCX.PILLAR'])}): {', '.join(payload['degraded_dates']['ARCX.PILLAR'])}.",
        f"- EQUS.MINI degraded dates ({len(payload['degraded_dates']['EQUS.MINI'])}): {', '.join(payload['degraded_dates']['EQUS.MINI'])}.",
        "- Primary results must exclude the union applicable to signal and execution. Sensitivity results may report degraded sessions separately but may not choose inclusion based on P&L.",
        "",
        "## What the package resolves",
        "",
        "The package resolves V33's factual absence of official primary-listing SPY auction-imbalance messages and materially improves synchronized event-time cash-ETF execution measurement across SPY/SSO/UPRO/SH/SDS/SPXU. It also supplies status and definition integrity records.",
        "",
        "## What remains unresolved",
        "",
        "- EQUS.MINI is not official SIP NBBO and has no venue identifiers in the supplied logical TBBO view.",
        "- TBBO is trade-event-conditioned, not a complete quote-update history; standing quote age and quote-only lead/lag are unobservable.",
        "- No queue position, passive-fill probability, order-book depth, dealer/AP identity, iNAV/NAV, shares outstanding, AUM, creation/redemption basket, or primary-market hedge flow is present.",
        "- Auction type/status/freeze/significance codes are venue-specific where the installed generic schema does not define their ARCX meaning.",
        "- The package begins TBBO on 2023-03-28, so 2021–2022 auction signals cannot receive event-level ETF execution reconstruction from this feed.",
        "- Historical outcomes remain multiply exposed; any survivor requires prospective forward paper trading.",
        "",
        "## Generated machine-readable evidence",
        "",
        "- `research_scout/new_data_technical_audit_v34.json`",
        "- `research_scout/spy_auction_snapshots_v34.json`",
        "- `research_scout/cash_etf_tbbo_target_quotes_v34.json`",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--refresh-status":
        payload = load_json(OUTPUT)
        payload["status"] = audit_status()
        OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        REPORT.write_text(render_markdown(payload) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(OUTPUT.relative_to(ROOT)), "status_rows": payload["status"]["rows"]}, indent=2))
        return 0
    if len(sys.argv) == 2 and sys.argv[1] == "--refresh-imbalance":
        payload = load_json(OUTPUT)
        arcx_degraded = degraded_dates(ARCX_CONDITION)
        payload["imbalance"], snapshots = audit_imbalance(arcx_degraded)
        OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        SNAPSHOTS_OUTPUT.write_text(json.dumps(snapshots, indent=2) + "\n", encoding="utf-8")
        REPORT.write_text(render_markdown(payload) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(OUTPUT.relative_to(ROOT)), "imbalance_rows": payload["imbalance"]["rows"]}, indent=2))
        return 0
    inventory = load_json(INVENTORY)
    validation = load_json(VALIDATION)
    arcx_degraded = degraded_dates(ARCX_CONDITION)
    equs_degraded = degraded_dates(EQUS_CONDITION)
    arcx_definition = audit_definitions(ARCX_DEFINITION)
    equs_definition = audit_definitions(EQUS_DEFINITION)
    status = audit_status()
    statistics = audit_statistics()
    imbalance, snapshots = audit_imbalance(arcx_degraded)
    tbbo, target_quotes = audit_tbbo(equs_degraded)
    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "returns_read": False,
        "paid_api_calls_made": False,
        "inventory": inventory,
        "validation_report": validation,
        "degraded_dates": {
            "ARCX.PILLAR": sorted(arcx_degraded),
            "EQUS.MINI": sorted(equs_degraded),
        },
        "definitions": {"ARCX.PILLAR": arcx_definition, "EQUS.MINI": equs_definition},
        "status": status,
        "statistics": statistics,
        "imbalance": imbalance,
        "tbbo": tbbo,
    }
    SNAPSHOTS_OUTPUT.write_text(json.dumps(snapshots, indent=2) + "\n", encoding="utf-8")
    TARGET_QUOTES_OUTPUT.write_text(json.dumps(target_quotes, indent=2) + "\n", encoding="utf-8")
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(render_markdown(payload) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(OUTPUT.relative_to(ROOT)),
        "report": str(REPORT.relative_to(ROOT)),
        "imbalance_rows": imbalance["rows"],
        "tbbo_segments": tbbo["segments"],
        "prefix_boundary_seen_and_stopped": tbbo["prefix_boundary_seen_and_stopped"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
