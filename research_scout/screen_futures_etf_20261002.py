"""Freeze and screen cached 2023 CME impulses; no futures positions or P&L."""

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import databento as db
import exchange_calendars as xcals
import numpy as np
import pandas as pd

from research.futures_etf_impulse import screen

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/"external_artifacts/databento_es_close/GLBX.MDP3"
OUT = ROOT/"research_scout/futures_etf_hft_20261002"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    assert not (OUT/"source_screen_results.json").exists()
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range("2023-01-01", "2023-12-31")
    jobs = []
    for session in sessions:
        day = session.date().isoformat()
        begin = pd.Timestamp(day+" 15:00:00", tz=ZoneInfo("America/New_York"))
        end = begin+pd.Timedelta(minutes=30)
        jobs.append({"date": day, "start_ns": begin.value, "end_ns": end.value,
                     "cash_market_open_through_window": calendar.session_close(session).value >= end.value,
                     "path": str((BASE/"sessions/2023"/day/"es_trades.dbn.zst").relative_to(ROOT))})
    spec = {"created_at_utc": datetime.now(UTC).isoformat(),
            "family": "CME impulse leading a delayed SPY response over 15 seconds",
            "scope": "Trade only SPY if subsequent execution is justified. Cached ES trades are a predictor, never a futures position. This is another dependent hypothesis in the global exposed search, not independent discovery.",
            "dates": "Every 2023 XNYS session; known early closes outside the 15:00-15:30 ET window are excluded by calendar, not returns. Missing/degraded/corrupt inputs remain unknown.",
            "signal": "250ms decisions from 15:00:02 inclusive to 15:29:00 exclusive. Strictly earlier Databento receive times than decision-100ms. Compare last ES trade prices at that cutoff and exactly one second earlier, each no older than 250ms. Same instrument only; no interpolation across a roll.",
            "gates": "Absolute one-second return >=4bp; at least 100 contracts in that second; signed aggressor volume aligns with price direction at >=75% of total. All records in the window and both endpoint trades must have positive price/size, side A/B, flags only 0 or F_LAST, and capture-event lag between -1ms and 100ms. Keep every decision and rejection. Earliest qualifying event wins a fixed 30-second cooldown.",
            "spy_supply_next": "Acquire bounded historical SIP windows for every selected event. Use strictly causal SPY standing quotes and their one-second change at the same cutoff. The signed ES-minus-SPY one-second return gap must exceed the full SPY round-trip spread/fee/adverse/borrow budget plus 3bp before any execution replay. This is a convergence opportunity screen, not a profit or guaranteed bound.",
            "spy_size": "One whole-share SPY position at a time, notional <=10000/1.01 and <=10% of directional displayed size; minimum 100 USDT-equivalent dollars. Fixed from the pre-decision quote. No leverage, future resizing or futures exposure.",
            "costs": {"commission_per_share": .0075, "minimum_per_order": 1.0, "sell_rate": .00003,
                      "sell_per_share": .0002, "adverse_per_execution": .0001, "short_annual_rate": .05, "minimum_borrow_days": 1},
            "if_supply": "Freeze economic implementation before reading future SPY returns. Conditional FOK entry collar 10bp from known quote; 50ms processing, 100ms outbound/ACK base, 250ms and 1s delays in stress. Exit decision 15 seconds after entry ACK, complete inventory horizon <=30s. Keep ambiguous fills/depth and carry unknown positions; charge both commissions, sell charges, adverse cost and one calendar-day short borrow. Test doubled fees/adverse and +/-100ms clock alignment. Actual historical SIP receipt/routing and stock-borrow eligibility remain conditional.",
            "feed_caution": "EQUS.MINI is a derived anonymized multi-venue BBO, not official SIP NBBO; do not treat its subset quotes as guaranteed market-wide executable prices. Cached ETF opening MBP-1 does not overlap this futures window, so the first screen uses only cached futures. SIP source quotes will be requested only for selected events.",
            "volume_roll": "ES.v.0 uses previous-day volume according to Databento. Read actual mapped instrument IDs and compare within the same contract. Do not splice unadjusted rollover price levels into returns.",
            "data_only": True, "strategy_pnl_tested": False, "selection_2024_2025_opened_by_this_family": False,
            "prior_exposure": "These historical periods and futures close studies were used in earlier research. A new family-specific holdout is not globally pristine forward evidence.",
            "sources": ["https://databento.com/docs/schemas-and-data-formats/trades", "https://databento.com/docs/standards-and-conventions/symbology", "https://databento.com/docs/venues-and-datasets"],
            "jobs": jobs, "code_sha256": {p: sha(ROOT/p) for p in ["research_scout/screen_futures_etf_20261002.py", "research/futures_etf_impulse.py", "tests/unit/test_futures_etf_impulse.py"]},
            "source_conditions_sha256": sha(BASE/"dataset_condition_2021_2025.json"), "download_ledger_sha256": sha(BASE/"download_ledger.jsonl")}
    spec_path = OUT/"specification.json"
    if spec_path.exists():
        prior = json.loads(spec_path.read_text())
        for key in ("code_sha256", "jobs", "source_conditions_sha256", "download_ledger_sha256"):
            assert prior[key] == spec[key]
    else:
        spec_path.write_text(json.dumps(spec, indent=2)+"\n")
    conditions = {r["date"]: r["condition"] for r in json.loads((BASE/"dataset_condition_2021_2025.json").read_text())["conditions"]}
    provenance = {}
    for line in (BASE/"download_ledger.jsonl").read_text().splitlines():
        row = json.loads(line)
        if row.get("component") == "es_trades" and row.get("sha256"):
            provenance.setdefault(row["date"], set()).add(row["sha256"])
    sources, frames = [], []
    (OUT/"decisions").mkdir(exist_ok=True)
    for job in jobs:
        row = {**job, "complete": False, "reason": "cash_market_closed", "selected_events": 0}
        if job["cash_market_open_through_window"]:
            try:
                path = ROOT/job["path"]
                assert conditions.get(job["date"]) == "available", "Dataset condition not available"
                row["sha256"] = sha(path)
                assert row["sha256"] in provenance.get(job["date"], set()), "Source hash does not match acquisition ledger"
                store = db.DBNStore.from_file(path)
                metadata = store.metadata
                assert metadata.dataset == "GLBX.MDP3" and metadata.symbols == ["ES.v.0"]
                assert metadata.start == job["start_ns"] and metadata.end == job["end_ns"]
                source = store.to_df()
                assert len(source) and source.action.eq("T").all() and source.instrument_id.nunique() == 1
                frame = pd.DataFrame({"capture_ns": source.index.asi8, "event_ns": source.ts_event.astype("int64").to_numpy(),
                                      "price": source.price.to_numpy(), "size": source["size"].to_numpy(), "side": source.side.to_numpy(),
                                      "flags_value": source["flags"].to_numpy(), "instrument_id": source.instrument_id.to_numpy()})
                decisions = np.arange(job["start_ns"]+2_000_000_000, job["end_ns"]-60_000_000_000, 250_000_000, dtype=np.int64)
                screened = screen(frame, decisions)
                screened.insert(0, "date", job["date"])
                output = OUT/"decisions"/f"{job['date']}.parquet"
                assert not output.exists()
                screened.to_parquet(output, index=False)
                selected = screened.loc[screened.selected].copy()
                frames.append(selected)
                row.update(complete=True, reason="source_screen_complete", native_trade_records=len(frame),
                           decision_slots=len(screened), valid_decisions=int(screened.valid.sum()),
                           selected_events=len(selected), instrument_id=int(source.instrument_id.iloc[0]),
                           decisions_path=str(output.relative_to(ROOT)), decisions_sha256=sha(output), outcomes=screened.reason.value_counts().to_dict())
            except Exception as error:
                row.update(reason="unknown_source", error_type=type(error).__name__, error=str(error))
        sources.append(row)
        if row["selected_events"] or row["reason"] != "source_screen_complete":
            print(json.dumps({k: row.get(k) for k in ("date", "reason", "native_trade_records", "selected_events", "error")}), flush=True)
        (OUT/"source_manifest.json").write_text(json.dumps({"files": sources, "expected_sessions": len(jobs), "finished": len(sources) == len(jobs)}, indent=2)+"\n")
    selected = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    selected.to_parquet(OUT/"es_impulses.parquet", index=False)
    result = {"calendar_sessions": len(jobs), "source_outcomes": dict(Counter(r["reason"] for r in sources)),
              "native_trade_records": sum(r.get("native_trade_records", 0) for r in sources),
              "decision_slots": sum(r.get("decision_slots", 0) for r in sources), "valid_decisions": sum(r.get("valid_decisions", 0) for r in sources),
              "selected_events": len(selected), "selected_dates": int(selected.date.nunique()) if len(selected) else 0,
              "impulses_sha256": sha(OUT/"es_impulses.parquet"), "manifest_sha256": sha(OUT/"source_manifest.json"),
              "specification_sha256": sha(spec_path), "etf_execution_tested": False, "strategy_pnl_tested": False,
              "futures_positions_assumed": False, "reliable_edge_established": False}
    (OUT/"source_screen_results.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
