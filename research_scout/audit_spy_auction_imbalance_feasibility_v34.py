"""Returns-blind feasibility summary for the SPY Arca imbalance feed."""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import databento as db  # noqa: E402

SOURCE = (
    ROOT
    / "external_artifacts"
    / "databento_cash_etf_budget_v1"
    / "ARCX.PILLAR"
    / "imbalance"
    / "spy_imbalance_2021-01-01_2026-07-27.dbn.zst"
)
CONDITIONS = (
    ROOT
    / "external_artifacts"
    / "databento_cash_etf_budget_v1"
    / "ARCX.PILLAR"
    / "dataset_condition.json"
)
OUTPUT = ROOT / "research_scout" / "spy_auction_imbalance_feasibility_v34.json"
STATES_OUTPUT = ROOT / "research_scout" / "spy_auction_imbalance_states_v34.json"
NY = "America/New_York"
PRICE_COLUMNS = ["ref_price", "ind_match_price"]


def main() -> int:
    degraded = {
        item["date"]
        for item in json.loads(CONDITIONS.read_text(encoding="utf-8"))["conditions"]
        if item["condition"] != "available"
    }
    store = db.read_dbn(SOURCE)
    auction_types: Counter[str] = Counter()
    hour_counts: Counter[str] = Counter()
    open_candidates: list[pd.DataFrame] = []
    close_candidates: list[pd.DataFrame] = []
    total_rows = 0

    for chunk_number, frame in enumerate(
        store.to_df(count=1_000_000, map_symbols=True), start=1
    ):
        total_rows += len(frame)
        event = pd.to_datetime(frame["ts_event"], utc=True).dt.tz_convert(NY)
        frame = frame.assign(
            event_ny=event,
            session_date=event.dt.strftime("%Y-%m-%d"),
            event_clock=event.dt.strftime("%H:%M:%S.%f"),
        )
        frame = frame.loc[~frame["session_date"].isin(degraded)]
        auction_types.update(frame["auction_type"].astype(str).tolist())
        hour_counts.update(event.loc[frame.index].dt.strftime("%H").tolist())
        clock_seconds = (
            frame["event_ny"].dt.hour * 3600
            + frame["event_ny"].dt.minute * 60
            + frame["event_ny"].dt.second
        )
        opening = frame.loc[
            (clock_seconds >= 4 * 3600)
            & (clock_seconds < (9 * 3600 + 29 * 60))
        ]
        closing = frame.loc[(clock_seconds >= 15 * 3600) & (clock_seconds < 16 * 3600)]
        if not opening.empty:
            open_candidates.append(opening)
        if not closing.empty:
            close_candidates.append(closing)
        print(f"chunk={chunk_number} rows={total_rows}", flush=True)

    opening = pd.concat(open_candidates, ignore_index=True)
    closing = pd.concat(close_candidates, ignore_index=True)

    open_type_counts = Counter(opening["auction_type"].astype(str).tolist())
    close_type_counts = Counter(closing["auction_type"].astype(str).tolist())
    chosen_open_type = open_type_counts.most_common(1)[0][0]
    open_type = opening.loc[opening["auction_type"].astype(str).eq(chosen_open_type)]
    final_open = (
        open_type.sort_values("event_ny")
        .groupby("session_date", sort=True, as_index=False)
        .tail(1)
        .copy()
    )

    valid_prices = pd.Series(True, index=final_open.index)
    for column in PRICE_COLUMNS:
        valid_prices &= final_open[column].notna() & final_open[column].gt(0)
    valid_prices &= final_open["paired_qty"].gt(0)
    valid_prices &= final_open["total_imbalance_qty"].gt(0)
    valid = final_open.loc[valid_prices].copy()
    buy = valid["side"].astype(str).eq("B")
    sell = valid["side"].astype(str).eq("A")
    buy_acceptance = buy & valid["ind_match_price"].gt(valid["ref_price"])
    sell_acceptance = sell & valid["ind_match_price"].lt(valid["ref_price"])

    by_year: dict[str, dict[str, int]] = {}
    for year, group in valid.groupby(valid["session_date"].str[:4]):
        group_buy = group["side"].astype(str).eq("B")
        group_sell = group["side"].astype(str).eq("A")
        group_buy_acceptance = group_buy & group["ind_match_price"].gt(
            group["ref_price"]
        )
        group_sell_acceptance = group_sell & group["ind_match_price"].lt(
            group["ref_price"]
        )
        by_year[str(year)] = {
            "valid_sessions": int(len(group)),
            "buy_side_sessions": int(group_buy.sum()),
            "sell_side_sessions": int(group_sell.sum()),
            "buy_price_acceptance_sessions": int(group_buy_acceptance.sum()),
            "sell_price_acceptance_sessions": int(group_sell_acceptance.sum()),
        }

    span_weeks = (
        pd.Timestamp(valid["session_date"].max())
        - pd.Timestamp(valid["session_date"].min())
    ).days / 7.0
    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "returns_read": False,
        "source": SOURCE.relative_to(ROOT).as_posix(),
        "total_rows": total_rows,
        "degraded_dates_excluded": sorted(degraded),
        "auction_type_counts_all": dict(sorted(auction_types.items())),
        "hour_counts_all": dict(sorted(hour_counts.items())),
        "opening_window_auction_type_counts": dict(sorted(open_type_counts.items())),
        "closing_window_auction_type_counts": dict(sorted(close_type_counts.items())),
        "selected_opening_auction_type_for_reachability": chosen_open_type,
        "decision_cutoff": "09:29:00 America/New_York; event timestamp strictly before cutoff",
        "final_opening_sessions": int(len(final_open)),
        "valid_reference_and_match_price_sessions": int(len(valid)),
        "first_valid_session": valid["session_date"].min(),
        "last_valid_session": valid["session_date"].max(),
        "buy_side_sessions": int(buy.sum()),
        "sell_side_sessions": int(sell.sum()),
        "buy_price_acceptance_sessions": int(buy_acceptance.sum()),
        "sell_price_acceptance_sessions": int(sell_acceptance.sum()),
        "buy_acceptance_trades_per_calendar_week": float(
            buy_acceptance.sum() / span_weeks
        ),
        "sell_acceptance_trades_per_calendar_week": float(
            sell_acceptance.sum() / span_weeks
        ),
        "by_year": by_year,
        "warning": "This is signal reachability only. No post-signal price or return was opened.",
    }
    states = []
    for row in valid.sort_values("session_date").itertuples(index=False):
        states.append(
            {
                "session_date": str(row.session_date),
                "ts_event": str(row.event_ny),
                "side": str(row.side),
                "ref_price": float(row.ref_price),
                "ind_match_price": float(row.ind_match_price),
                "paired_qty": int(row.paired_qty),
                "total_imbalance_qty": int(row.total_imbalance_qty),
            }
        )
    STATES_OUTPUT.write_text(
        json.dumps(
            {
                "returns_read": False,
                "decision_cutoff": payload["decision_cutoff"],
                "states": states,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    payload["states_file"] = STATES_OUTPUT.relative_to(ROOT).as_posix()
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
