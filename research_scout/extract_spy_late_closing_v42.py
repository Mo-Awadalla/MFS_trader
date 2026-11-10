"""Extract returns-blind late-closing snapshots and SPY/SH quote targets for v42."""

from __future__ import annotations

import json
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_cash_etf_new_data_v34 as technical

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_OUTPUT = ROOT / "research_scout" / "spy_late_closing_auction_snapshots_v42.json"
QUOTE_OUTPUT = ROOT / "research_scout" / "spy_sh_late_closing_target_quotes_v42.json"
CUTOFFS = {
    "15:49:50": 15 * 3600 + 49 * 60 + 50,
    "15:50:00": 15 * 3600 + 50 * 60,
    "15:50:10": 15 * 3600 + 50 * 60 + 10,
    "15:54:50": 15 * 3600 + 54 * 60 + 50,
    "15:55:00": 15 * 3600 + 55 * 60,
    "15:55:10": 15 * 3600 + 55 * 60 + 10,
}
TARGETS = {
    "15:50:00": 15 * 3600 + 50 * 60,
    "15:54:50": 15 * 3600 + 54 * 60 + 50,
    "15:55:01": 15 * 3600 + 55 * 60 + 1,
    "15:55:05": 15 * 3600 + 55 * 60 + 5,
    "15:56:00": 15 * 3600 + 56 * 60,
    "15:59:00": 15 * 3600 + 59 * 60,
}
SNAPSHOT_FIELDS = [
    "ref_price", "ind_match_price", "paired_qty", "total_imbalance_qty",
    "market_imbalance_qty", "unpaired_qty", "side", "auction_status",
    "freeze_status", "num_extensions", "significant_imbalance",
]


def scalar(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def extract_snapshots() -> dict[str, Any]:
    snapshots: dict[tuple[str, str], dict[str, Any]] = {}
    rows_seen = 0
    closing_rows_seen = 0
    for chunk_number, frame in enumerate(
        technical.db.read_dbn(technical.IMBALANCE).to_df(count=1_000_000, map_symbols=True, tz="UTC"), start=1
    ):
        frame = frame.reset_index()
        rows_seen += len(frame)
        event, days, seconds = technical.frame_times(frame)
        frame = frame.assign(event_ny=event, session_date=days, second=seconds)
        closing = frame.loc[
            frame["auction_type"].astype(str).eq("C")
            & frame["second"].ge(15 * 3600 + 45 * 60)
            & frame["second"].lt(15 * 3600 + 56 * 60)
        ]
        closing_rows_seen += len(closing)
        if closing.empty:
            continue
        for cutoff_name, cutoff in CUTOFFS.items():
            eligible = closing.loc[closing["second"].lt(cutoff)]
            if eligible.empty:
                continue
            latest = eligible.sort_values("ts_event").groupby("session_date", sort=False).tail(1)
            for _, row in latest.iterrows():
                key = (str(row["session_date"]), cutoff_name)
                candidate = {
                    "session_date": key[0],
                    "cutoff": cutoff_name,
                    "ts_event": pd.Timestamp(row["ts_event"]).isoformat(),
                    "ts_recv": pd.Timestamp(row["ts_recv"]).isoformat(),
                    "auction_time": pd.Timestamp(row["auction_time"]).isoformat(),
                    "auction_type": str(row["auction_type"]),
                }
                candidate.update({field: scalar(row[field]) for field in SNAPSHOT_FIELDS})
                old = snapshots.get(key)
                if old is None or candidate["ts_event"] > old["ts_event"]:
                    snapshots[key] = candidate
        if chunk_number % 5 == 0:
            print(json.dumps({"imbalance_chunk": chunk_number, "rows_seen": rows_seen, "late_closing_rows": closing_rows_seen}), flush=True)
    rows = [snapshots[key] for key in sorted(snapshots)]
    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "returns_read": False,
        "selection": "latest SPY auction_type C message strictly before each named cutoff",
        "source": str(technical.IMBALANCE.relative_to(ROOT)),
        "rows_seen": rows_seen,
        "late_closing_rows_seen": closing_rows_seen,
        "snapshot_counts": {cutoff: sum(row["cutoff"] == cutoff for row in rows) for cutoff in CUTOFFS},
        "snapshots": rows,
    }


def extract_quotes() -> dict[str, Any]:
    quotes: dict[tuple[str, str, str], dict[str, Any]] = {}
    prefix_boundary_seen = False
    sources = [
        ("prefix_through_2024-10-02", technical.TBBO_PREFIX, "2024-10-02", True),
        ("tail_from_2024-10-03", technical.TBBO_TAIL, None, False),
    ]
    rows_seen: dict[str, int] = {}
    for segment, path, cutoff, must_break in sources:
        rows_seen[segment] = 0
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            iterator = technical.db.read_dbn(path).to_df(count=1_000_000, map_symbols=True, tz="UTC")
            for chunk_number, frame in enumerate(iterator, start=1):
                frame = frame.reset_index()
                event, days, seconds = technical.frame_times(frame)
                frame = frame.assign(event_ny=event, session_date=days, second=seconds)
                stop_after_chunk = False
                if cutoff is not None and days.gt(cutoff).any():
                    prefix_boundary_seen = True
                    frame = frame.loc[days.le(cutoff)].copy()
                    stop_after_chunk = True
                rows_seen[segment] += len(frame)
                if not frame.empty:
                    symbols = frame["symbol"].astype(str)
                    bids = pd.to_numeric(frame["bid_px_00"], errors="coerce")
                    asks = pd.to_numeric(frame["ask_px_00"], errors="coerce")
                    valid = symbols.isin(["SPY", "SH"]) & bids.gt(0) & asks.gt(0) & asks.ge(bids)
                    valid_frame = frame.loc[valid].copy()
                    for target_name, target_second in TARGETS.items():
                        eligible = valid_frame.loc[
                            valid_frame["second"].ge(target_second)
                            & valid_frame["second"].le(target_second + 60.0)
                        ]
                        if eligible.empty:
                            continue
                        first = eligible.sort_values("ts_event").groupby(["session_date", "symbol"], sort=False).head(1)
                        for row in first.itertuples(index=False):
                            key = (str(row.session_date), str(row.symbol), target_name)
                            candidate = {
                                "session_date": key[0],
                                "symbol": key[1],
                                "target": target_name,
                                "target_second_ny": target_second,
                                "ts_event": pd.Timestamp(row.ts_event).isoformat(),
                                "ts_recv": pd.Timestamp(row.ts_recv).isoformat(),
                                "event_wait_seconds": float(row.second) - target_second,
                                "bid": float(row.bid_px_00),
                                "ask": float(row.ask_px_00),
                                "bid_size": int(row.bid_sz_00),
                                "ask_size": int(row.ask_sz_00),
                                "trade_price": float(row.price),
                                "trade_size": int(row.size),
                                "segment": segment,
                            }
                            old = quotes.get(key)
                            if old is None or candidate["ts_event"] < old["ts_event"]:
                                quotes[key] = candidate
                if chunk_number % 10 == 0:
                    print(json.dumps({"tbbo_segment": segment, "chunk": chunk_number, "rows_seen": rows_seen[segment]}), flush=True)
                if stop_after_chunk:
                    break
        if must_break and not prefix_boundary_seen:
            raise RuntimeError("Prefix cutoff boundary not observed; refusing unsafe partial decode")
    rows = [quotes[key] for key in sorted(quotes)]
    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "returns_read": False,
        "deduplication_rule": "prefix New York dates <= 2024-10-02; tail dates >= 2024-10-03",
        "prefix_boundary_seen_and_stopped": prefix_boundary_seen,
        "symbols": ["SPY", "SH"],
        "quote_filter": "bid > 0, ask > 0, ask >= bid",
        "event_wait_limit_seconds": 60,
        "rows_seen": rows_seen,
        "target_counts": {
            target: {symbol: sum(row["target"] == target and row["symbol"] == symbol for row in rows) for symbol in ["SPY", "SH"]}
            for target in TARGETS
        },
        "quotes": rows,
    }


def main() -> int:
    snapshots = extract_snapshots()
    SNAPSHOT_OUTPUT.write_text(json.dumps(snapshots, indent=2) + "\n", encoding="utf-8")
    quotes = extract_quotes()
    QUOTE_OUTPUT.write_text(json.dumps(quotes, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "snapshot_output": str(SNAPSHOT_OUTPUT.relative_to(ROOT)),
        "snapshot_rows": len(snapshots["snapshots"]),
        "quote_output": str(QUOTE_OUTPUT.relative_to(ROOT)),
        "quote_rows": len(quotes["quotes"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
