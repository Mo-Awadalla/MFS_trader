"""Extract returns-blind SPY Early Opening states and V43 ETF quote targets."""

from __future__ import annotations

import json
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_cash_etf_new_data_v34 as technical

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_OUTPUT = ROOT / "research_scout" / "spy_early_opening_snapshots_v43.json"
QUOTE_OUTPUT = ROOT / "research_scout" / "upro_spxu_premarket_target_quotes_v43.json"

CUTOFFS = {
    "03:59:30": 3 * 3600 + 59 * 60 + 30,
    "03:59:50": 3 * 3600 + 59 * 60 + 50,
    "03:59:59": 3 * 3600 + 59 * 60 + 59,
}
TARGETS = {
    "07:00:01": 7 * 3600 + 1,
    "07:01:00": 7 * 3600 + 60,
    "07:05:00": 7 * 3600 + 5 * 60,
    "09:20:00": 9 * 3600 + 20 * 60,
}
SYMBOLS = {"UPRO", "SPXU"}


def projected_clock(value: Any) -> str | None:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    return timestamp.strftime("%H:%M:%S")


def extract_snapshots(arcx_degraded: set[str]) -> dict[str, Any]:
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    rows_seen = 0
    for chunk in technical.db.read_dbn(technical.IMBALANCE).to_df(count=1_000_000, map_symbols=True, tz="UTC"):
        frame = chunk.reset_index()
        event, days, seconds = technical.frame_times(frame)
        frame = frame.assign(event_ny=event, session_date=days, second=seconds)
        frame = frame.loc[
            frame["symbol"].astype(str).eq("SPY")
            & frame["auction_type"].astype(str).eq("O")
            & frame["second"].between(3 * 3600 + 50 * 60, 4 * 3600, inclusive="left")
        ].copy()
        if frame.empty:
            continue
        frame["projected_clock"] = frame["auction_time"].map(projected_clock)
        frame = frame.loc[frame["projected_clock"].eq("04:00:00")]
        rows_seen += len(frame)
        for cutoff, cutoff_second in CUTOFFS.items():
            eligible = frame.loc[frame["second"].lt(cutoff_second)]
            if eligible.empty:
                continue
            latest = eligible.sort_values("ts_event").groupby("session_date", sort=False).tail(1)
            for row in latest.itertuples(index=False):
                key = (str(row.session_date), cutoff)
                candidate = {
                    "session_date": str(row.session_date),
                    "cutoff": cutoff,
                    "ts_event": pd.Timestamp(row.ts_event).isoformat(),
                    "ts_recv": pd.Timestamp(row.ts_recv).isoformat(),
                    "seconds_ny": float(row.second),
                    "auction_type": str(row.auction_type),
                    "projected_auction_clock": str(row.projected_clock),
                    "side": str(row.side),
                    "ref_price": float(row.ref_price),
                    "ind_match_price": float(row.ind_match_price),
                    "paired_qty": int(row.paired_qty),
                    "total_imbalance_qty": int(row.total_imbalance_qty),
                    "freeze_status": str(row.freeze_status),
                    "arcx_degraded": str(row.session_date) in arcx_degraded,
                }
                old = selected.get(key)
                if old is None or candidate["ts_event"] > old["ts_event"]:
                    selected[key] = candidate
    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "returns_read": False,
        "semantics": "Latest SPY O message strictly before each cutoff, only projected exchange-local 04:00:00 auctions; publication ordered by ts_event.",
        "rows_seen_in_window": rows_seen,
        "snapshots": sorted(selected.values(), key=lambda row: (row["session_date"], row["cutoff"])),
    }
    SNAPSHOT_OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def extract_quotes(equs_degraded: set[str]) -> dict[str, Any]:
    quotes: dict[tuple[str, str, str], dict[str, Any]] = {}
    sources = [
        ("prefix_through_2024-10-02", technical.TBBO_PREFIX, "2024-10-02", True),
        ("tail_from_2024-10-03", technical.TBBO_TAIL, None, False),
    ]
    segment_rows: dict[str, int] = {}
    prefix_boundary_seen = False
    terminal_warning_seen = False
    for segment, path, cutoff, must_break in sources:
        consumed = 0
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            iterator = technical.db.read_dbn(path).to_df(count=1_000_000, map_symbols=True, tz="UTC")
            for chunk_number, chunk in enumerate(iterator, start=1):
                frame = chunk.reset_index()
                event, days, seconds = technical.frame_times(frame)
                frame = frame.assign(event_ny=event, session_date=days, second=seconds)
                stop = False
                if cutoff is not None and days.gt(cutoff).any():
                    prefix_boundary_seen = True
                    frame = frame.loc[days.le(cutoff)].copy()
                    stop = True
                consumed += len(frame)
                if not frame.empty:
                    symbols = frame["symbol"].astype(str)
                    bids = pd.to_numeric(frame["bid_px_00"], errors="coerce")
                    asks = pd.to_numeric(frame["ask_px_00"], errors="coerce")
                    valid = symbols.isin(SYMBOLS) & bids.gt(0) & asks.gt(0) & asks.ge(bids)
                    valid_frame = frame.loc[valid].copy()
                    for target, target_second in TARGETS.items():
                        eligible = valid_frame.loc[
                            valid_frame["second"].ge(target_second)
                            & valid_frame["second"].le(target_second + 60)
                        ]
                        if eligible.empty:
                            continue
                        first = eligible.sort_values("ts_event").groupby(["session_date", "symbol"], sort=False).head(1)
                        for row in first.itertuples(index=False):
                            key = (str(row.session_date), str(row.symbol), target)
                            candidate = {
                                "session_date": str(row.session_date),
                                "symbol": str(row.symbol),
                                "target": target,
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
                                "equs_degraded": str(row.session_date) in equs_degraded,
                            }
                            old = quotes.get(key)
                            if old is None or candidate["ts_event"] < old["ts_event"]:
                                quotes[key] = candidate
                if chunk_number % 10 == 0:
                    print(f"tbbo segment={segment} chunks={chunk_number} rows={consumed}", flush=True)
                if stop:
                    break
            if must_break:
                terminal_warning_seen = any(
                    "truncated" in str(item.message).lower() or "incomplete record" in str(item.message).lower()
                    for item in caught
                )
        segment_rows[segment] = consumed
    if not prefix_boundary_seen:
        raise RuntimeError("Mandatory 2024-10-02 prefix boundary was not observed")
    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "returns_read": False,
        "deduplication_rule": "prefix New York dates <= 2024-10-02; tail dates >= 2024-10-03",
        "quote_filter": "bid > 0, ask > 0, ask >= bid",
        "event_wait_limit_seconds": 60,
        "prefix_boundary_seen_and_stopped": prefix_boundary_seen,
        "prefix_terminal_warning_observed": terminal_warning_seen,
        "segment_rows_consumed": segment_rows,
        "quotes": sorted(quotes.values(), key=lambda row: (row["session_date"], row["symbol"], row["target"])),
    }
    QUOTE_OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    arcx_degraded = technical.degraded_dates(technical.ARCX_CONDITION)
    equs_degraded = technical.degraded_dates(technical.EQUS_CONDITION)
    snapshots = extract_snapshots(arcx_degraded)
    quotes = extract_quotes(equs_degraded)
    print(json.dumps({"snapshots": len(snapshots["snapshots"]), "quotes": len(quotes["quotes"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
