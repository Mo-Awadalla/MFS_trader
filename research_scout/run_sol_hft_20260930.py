"""Fixed cross-asset replication, with native SOL units and no outcome tuning."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from research.crypto_symbol_cache import digest
from research.liquidation_event_replay import events_for_day
from research.liquidation_passive import SCENARIOS, EventBook, load_event_tape, replay

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/sol_hft_replication_20260930"
CALIBRATION = [f"2024-{m:02d}-01" for m in range(1, 7)]
EVALUATION = [f"2024-{m:02d}-01" for m in range(7, 13)]


def checked_source(kind, day):
    path = OUT / "raw" / kind / day / "SOLUSDT.csv.gz"
    manifest = json.loads(path.with_suffix(path.suffix + ".json").read_text())
    if digest(path) != manifest["sha256"]:
        raise ValueError("Source hash mismatch")
    return path, manifest


def run_day(day, threshold):
    path, liquidations = checked_source("liquidations", day)
    events = events_for_day(pd.read_csv(path), day, threshold)
    events.to_parquet(OUT / "panels" / f"{day}_events.parquet", index=False)
    if events.empty:
        raise ValueError(f"No selected events; explicit empty-day support needed: {day}")
    frames, audits = {}, []
    for kind, source_kind in (("book", "book_snapshot_5"), ("trades", "trades")):
        path, manifest = checked_source(source_kind, day)
        frame, audit = load_event_tape(path, day, events, kind)
        cache = OUT / "panels" / f"{day}_{kind}.parquet"
        frame.to_parquet(cache, index=False)
        # Empirical consistency checks do not claim to replace historical
        # instrument-definition records or private order-acceptance evidence.
        if kind == "trades":
            price_error = np.abs(frame.price * 1000 - np.round(frame.price * 1000)).max()
            quantity_error = np.abs(frame.amount * 10 - np.round(frame.amount * 10)).max()
            if price_error > 1e-6 or quantity_error > 1e-6:
                raise ValueError("Observed prints conflict with the frozen SOL increments")
            audit.update(price_tick_consistency_error=float(price_error), quantity_grid_consistency_error=float(quantity_error))
        audit.update(source_sha256=manifest["sha256"], panel_sha256=digest(cache),
                     liquidation_source_sha256=liquidations["sha256"], events=len(events),
                     events_sha256=digest(OUT / "panels" / f"{day}_events.parquet"))
        audits.append(audit)
        frames[kind] = frame
    book = EventBook(frames["book"])
    frame = frames["trades"]
    trades = {key: frame[key].to_numpy() for key in ("exchange_us", "id", "price", "amount")}
    trades["sell"] = frame.side.eq("sell").to_numpy()
    records = {}
    for direction in ("follow", "reverse"):
        for offset in (8, 16):
            for hold in (30, 120):
                name = f"{direction}_{offset}bp_{hold}s"
                records[name] = {scenario: replay(day, book, trades, events, direction, offset, hold, settings,
                                                 tick_size=.001, quantity_step=.1)
                                 for scenario, settings in SCENARIOS.items()}
    return day, records, audits


def main():
    (OUT / "panels").mkdir(exist_ok=True)
    spec_path = OUT / "specification.json"
    if spec_path.exists():
        raise FileExistsError("SOL replication already started")
    calibration, calibration_audits = [], []
    for day in CALIBRATION:
        path, manifest = checked_source("liquidations", day)
        frame = pd.read_csv(path)
        calibration.append(frame)
        calibration_audits.append({"date": day, "rows": len(frame), "source_sha256": manifest["sha256"]})
    data = pd.concat(calibration, ignore_index=True)
    notional = data.price * data.amount
    if not np.isfinite(notional).all() or not (notional > 0).all():
        raise ValueError("Invalid calibration notional")
    threshold = float(notional.quantile(.99))
    code = [ROOT / p for p in ("research/liquidation_passive.py", "research/cross_venue_dual_clock.py",
                               "research/liquidation_event_replay.py", "research_scout/run_sol_hft_20260930.py")]
    btc_spec = ROOT / "research_scout/liquidation_passive_20260930/specification.json"
    spec = {"created_at_utc": datetime.now(UTC).isoformat(), "symbol": "SOLUSDT", "configs": 8,
            "calibration": CALIBRATION, "dates": EVALUATION, "threshold_reported_notional": threshold,
            "calibration_audits": calibration_audits, "btc_template_sha256": digest(btc_spec),
            "rules": "Same fixed follow/reverse, 8/16bp passive offsets and 30/120-second holds as BTC; five-second order lifetime, 250ms processing, one-second outbound baseline. SOL Jan-Jun 99th-percentile reported liquidation notional sets the trigger; first report after a five-minute refractory window.",
            "instrument_units": {"price_tick_usdt": .001, "quantity_step_sol": .1,
                                 "note": "Linear SOLUSDT prices in USDT, amounts in SOL; observed trade-grid consistency is checked. Historical exchange acceptance and private fills are not established by a quote replay."},
            "scenarios": SCENARIOS, "capital": "$10000 daily cash, max $1000 order, <=10% predecision visible size; exact partial inventory and independent exit depth retained.",
            "costs": "3bp maker entry and 6bp taker exit plus 1bp extra adverse exit cost. No rebate/VIP assumption. Existing doubled-fee, three-second delay and fill-model stresses are unchanged.",
            "clocks": "Capture-time signal information; physical exchange-time acceptance and exits. Cancel acknowledgement precedes hold/exit. Any unknown submitted path invalidates its entire day. No position over a UTC hour plus one-minute buffer.",
            "prior_exposure": "SOL is preselected before inspecting its price outcomes. Same calendar dates have prior BTC exposure, and the underlying rule family is already researched; this does not reset multiplicity or create forward evidence.",
            "progression": "Require complete positive outcomes under every scenario and positive baseline after deleting the best date before opening independent later dates. This is a screening condition, not an edge or win declaration.",
            "scope": "Strictly HFT, as explicitly confirmed by user; exclude slower intraday candidates.",
            "code_sha256": {str(p.relative_to(ROOT)): digest(p) for p in code}}
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"SOL threshold: ${threshold:,.4f} from {len(data):,} calibration reports", flush=True)
    records, audits = {}, []
    with ProcessPoolExecutor(max_workers=2) as pool:
        for job in as_completed([pool.submit(run_day, day, threshold) for day in EVALUATION]):
            day, daily_records, source_audits = job.result()
            records[day] = daily_records
            audits.extend(source_audits)
            print(f"{day}: {source_audits[0]['events']} SOL events", flush=True)
    results, further_evidence = {}, []
    for name in records[EVALUATION[0]]:
        scenarios = {}
        for scenario in SCENARIOS:
            days = [records[d][name][scenario] for d in EVALUATION]
            attempts = pd.DataFrame([attempt for day in days for attempt in day["attempts"]])
            priced = attempts.loc[attempts.status.eq("priced")]
            daily = pd.DataFrame([{k: v for k, v in day.items() if k != "attempts"} for day in days])
            attempts.to_parquet(OUT / f"{name}_{scenario}_attempts.parquet", index=False)
            daily.to_parquet(OUT / f"{name}_{scenario}_daily.parquet", index=False)
            complete = bool(daily.complete.all())
            pnl = daily.closed_subtotal.to_numpy(float)
            scenarios[scenario] = {"complete": complete, "net_dollars": float(pnl.sum()) if complete else None,
                "closed_subtotal": float(pnl.sum()), "gross_closed_subtotal": float(priced.gross.sum()) if len(priced) else 0.,
                "trades": len(priced), "mean_net_bps": float(priced.net_bps.mean()) if len(priced) else None,
                "positive_dates": int((pnl > 0).sum()) if complete else None,
                "net_without_best_date": float(pnl.sum() - pnl.max()) if complete else None,
                "outcomes": attempts.status.value_counts().to_dict(), "daily": daily.to_dict("records")}
        all_positive = all(s["complete"] and s["net_dollars"] > 0 for s in scenarios.values())
        proceed = all_positive and scenarios["base"]["net_without_best_date"] > 0
        results[name] = {"scenarios": scenarios, "needs_additional_evidence": proceed}
        if proceed:
            further_evidence.append(name)
        base = scenarios["base"]
        print(f"{name}: net={base['net_dollars']}, closed={base['closed_subtotal']:+.4f}, trades={base['trades']}, further={proceed}", flush=True)
    assert all(digest(ROOT / p) == expected for p, expected in spec["code_sha256"].items())
    (OUT / "results.json").write_text(json.dumps({"results": results, "source_audits": audits,
        "candidates_for_additional_evidence": further_evidence, "reliable_edge_established": False}, indent=2) + "\n")


if __name__ == "__main__":
    main()
