"""Extract returns-blind SPY Closing-auction snapshots for v41."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_cash_etf_new_data_v34 as technical

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "spy_closing_auction_snapshots_v41.json"
CUTOFFS = {
    "15:20:00": 15 * 3600 + 20 * 60,
    "15:29:30": 15 * 3600 + 29 * 60 + 30,
    "15:29:50": 15 * 3600 + 29 * 60 + 50,
    "15:29:59": 15 * 3600 + 29 * 60 + 59,
}
FIELDS = [
    "ref_price",
    "cont_book_clr_price",
    "auct_interest_clr_price",
    "ssr_filling_price",
    "ind_match_price",
    "upper_collar",
    "lower_collar",
    "paired_qty",
    "total_imbalance_qty",
    "market_imbalance_qty",
    "unpaired_qty",
    "side",
    "auction_status",
    "freeze_status",
    "num_extensions",
    "unpaired_side",
    "significant_imbalance",
]


def scalar(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def main() -> int:
    snapshots: dict[tuple[str, str], dict[str, Any]] = {}
    rows_seen = 0
    closing_rows_seen = 0
    for chunk_number, frame in enumerate(
        technical.db.read_dbn(technical.IMBALANCE).to_df(count=1_000_000, map_symbols=True, tz="UTC"),
        start=1,
    ):
        frame = frame.reset_index()
        rows_seen += len(frame)
        event = pd.to_datetime(frame["ts_event"], utc=True).dt.tz_convert("America/New_York")
        seconds = event.dt.hour * 3600 + event.dt.minute * 60 + event.dt.second + event.dt.microsecond / 1_000_000.0
        frame = frame.assign(
            event_ny=event,
            session_date=event.dt.strftime("%Y-%m-%d"),
            second=seconds,
        )
        closing = frame.loc[
            frame["auction_type"].astype(str).eq("C")
            & frame["second"].ge(15 * 3600)
            & frame["second"].lt(15 * 3600 + 30 * 60)
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
                prior = snapshots.get(key)
                ts_event = pd.Timestamp(row["ts_event"])
                if prior is not None and pd.Timestamp(prior["ts_event"]) >= ts_event:
                    continue
                payload = {
                    "session_date": key[0],
                    "cutoff": cutoff_name,
                    "ts_event": ts_event.isoformat(),
                    "ts_recv": pd.Timestamp(row["ts_recv"]).isoformat(),
                    "auction_time": pd.Timestamp(row["auction_time"]).isoformat(),
                    "auction_type": str(row["auction_type"]),
                }
                payload.update({field: scalar(row[field]) for field in FIELDS})
                snapshots[key] = payload
        if chunk_number % 5 == 0:
            print(json.dumps({"chunk": chunk_number, "rows_seen": rows_seen, "closing_rows_seen": closing_rows_seen}))

    rows = [snapshots[key] for key in sorted(snapshots)]
    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "returns_read": False,
        "selection": "latest SPY auction_type C message strictly before each named cutoff",
        "source": str(technical.IMBALANCE.relative_to(ROOT)),
        "rows_seen": rows_seen,
        "closing_rows_seen_15_00_to_15_30": closing_rows_seen,
        "snapshot_counts": {
            cutoff: sum(row["cutoff"] == cutoff for row in rows)
            for cutoff in CUTOFFS
        },
        "snapshots": rows,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT.relative_to(ROOT)), "snapshots": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
