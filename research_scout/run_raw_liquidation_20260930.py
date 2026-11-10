"""Fixed HFT screening using native executed liquidation size, not CSV proxies."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime

import pandas as pd

from research.crypto_symbol_cache import digest
from research.liquidation_event_replay import events_for_day
from research.liquidation_passive import SCENARIOS, EventBook, load_event_tape, replay
from research.raw_liquidation_replay import TAKER_SCENARIOS, taker_replay
from research_scout.audit_force_order_full_20260930 import ASSETS, DATES, OUT, ROOT

CALIBRATION, EVALUATION = DATES[:6], DATES[6:]


def available_reports(data, recoveries):
    """Known startup/recovery cooldown, never veto an earlier submitted trade."""
    midnight = pd.to_datetime(data.date, utc=True).dt.as_unit("us").astype("int64")
    keep = data.local_timestamp.ge(midnight + 300_000_000)
    for recovery in recoveries:
        keep &= ~data.local_timestamp.between(recovery["recovery_local_timestamp"],
                                              recovery["warmup_end_local_timestamp"], inclusive="left")
    return data.loc[keep].copy()


def native_events(data, day, threshold):
    # Input is the completed visible order, preserving its raw capture clock.
    completed = data.loc[data.status.eq("FILLED") & data.date.eq(day)].copy().reset_index(drop=True)
    completed["price"], completed["amount"] = completed.average_price, completed.filled_quantity
    events = events_for_day(completed, day, threshold)
    for name in ("local_timestamp", "timestamp", "filled_quantity", "last_fill_quantity", "average_price", "limit_price"):
        events[name] = completed.loc[events.event_id.to_numpy(), name].to_numpy()
    return events


def run_day(symbol, day, threshold):
    settings = ASSETS[symbol]
    output = OUT / symbol
    raw = pd.read_parquet(OUT / "orders.parquet")
    field_audit = json.loads((OUT / "field_audit.json").read_text())
    raw = available_reports(raw, field_audit["recovery_warmups"])
    events = native_events(raw.loc[raw.symbol.eq(symbol)], day, threshold)
    events_path = output / "panels" / f"{day}_events.parquet"
    events.to_parquet(events_path, index=False)
    frames, audits = {}, []
    for kind, folder, data_type in (("book", settings["source"], "book_snapshot_5"),
                                    ("trades", settings["trades"], "trades")):
        path = ROOT / "research_scout" / folder / "raw" / data_type / day / f"{symbol}.csv.gz"
        manifest = json.loads(path.with_suffix(path.suffix + ".json").read_text())
        assert digest(path) == manifest["sha256"]
        frame, audit = load_event_tape(path, day, events, kind)
        panel = output / "panels" / f"{day}_{kind}.parquet"
        frame.to_parquet(panel, index=False)
        audit.update(symbol=symbol, source_path=str(path.relative_to(ROOT)), source_sha256=manifest["sha256"],
                     panel_sha256=digest(panel), events=len(events), events_sha256=digest(events_path))
        audits.append(audit)
        frames[kind] = frame
    book = EventBook(frames["book"])
    frame = frames["trades"]
    tape = {key: frame[key].to_numpy() for key in ("exchange_us", "id", "price", "amount")}
    tape["sell"] = frame.side.eq("sell").to_numpy()
    units = {key: settings[key] for key in ("tick_size", "quantity_step")}
    records = {}
    for direction in ("follow", "reverse"):
        for hold in (30, 120):
            name = f"taker_{direction}_{hold}s"
            records[name] = {scenario: taker_replay(day, book, events, direction, hold, params, **units)
                             for scenario, params in TAKER_SCENARIOS.items()}
            for offset in (8, 16):
                name = f"passive_{direction}_{offset}bp_{hold}s"
                records[name] = {scenario: replay(day, book, tape, events, direction, offset, hold, params, **units)
                                 for scenario, params in SCENARIOS.items()}
    return symbol, day, records, audits


def main():
    spec_path = OUT / "strategy_specification.json"
    if spec_path.exists():
        raise FileExistsError("Native-size strategy batch already frozen")
    audit = json.loads((OUT / "field_audit.json").read_text())
    assert audit["verified"] and digest(OUT / "orders.parquet") == audit["orders_sha256"]
    raw = pd.read_parquet(OUT / "orders.parquet")
    raw = available_reports(raw, audit["recovery_warmups"])
    thresholds, sample_counts = {}, {}
    for symbol in ASSETS:
        sample = raw.loc[raw.symbol.eq(symbol) & raw.date.isin(CALIBRATION) & raw.status.eq("FILLED")]
        thresholds[symbol] = float(sample.executed_notional.quantile(.99))
        sample_counts[symbol] = len(sample)
        (OUT / symbol / "panels").mkdir(parents=True, exist_ok=True)
    code = ["research/raw_liquidation_replay.py", "research/liquidation_passive.py",
            "research/liquidation_event_replay.py", "research/cross_venue_dual_clock.py",
            "research_scout/run_raw_liquidation_20260930.py", "research_scout/audit_force_order_full_20260930.py"]
    spec = {"created_at_utc": datetime.now(UTC).isoformat(), "configs": 24,
        "calibration_dates": CALIBRATION, "evaluation_dates": EVALUATION,
        "threshold_quantile": .99, "threshold_executed_order_notional": thresholds,
        "calibration_counts": sample_counts, "field_audit_sha256": digest(OUT / "field_audit.json"),
        "orders_sha256": digest(OUT / "orders.parquet"), "assets": ASSETS,
        "rules": "First reported completed order with cumulative z times average ap at or above the Jan-Jun 99th percentile, five-minute refractory period. No threshold optimization. Follow/reverse with 30/120-second holds; taker entry and passive 8/16bp offsets. Same calendar dates and all prior exposure remain.",
        "capital": "$10000 reset daily per isolated strategy, max $1000 order, <=10% predecision top-level quantity; independent asset results are not an allocated portfolio.",
        "taker_execution": "5bp causal FOK collar, physical five-level weighted fills; 250ms processing + 1s outbound + 1s return acknowledgment. Hold begins only after entry acknowledgment. 6bp fees plus 1bp adverse cost EACH side. Doubled fees and three-second outbound/return stress.",
        "passive_execution": "Unchanged counterfactual strict-through partial fills, five-second resting time, wait for cancellation acknowledgment then hold and market exit. 3bp maker, 6bp taker plus 1bp exit allowance. Doubled fees, three-second delay, full-first-through and touch-price sensitivities.",
        "clocks": "Signals strictly prior capture time; submitted fills strictly prior exchange-time state <=250ms old. Unknown submitted outcomes invalidate day and retain unresolved inventory. No position within one minute of a UTC hour.",
        "availability": "Five-minute startup warmup on each day and five minutes after the first captured report following a raw disconnect marker. This is a causal recovery cooldown, applied equally to calibration and event selection. Previously submitted positions keep their scheduled exits; a subsequent liquidation-feed disconnect never deletes a trade or loss. Book/trade availability is independently enforced at execution.",
        "recovery_warmups": audit["recovery_warmups"],
        "taker_scenarios": TAKER_SCENARIOS, "passive_scenarios": SCENARIOS,
        "progression": "Every scenario complete and net positive; base remains positive after deleting the best date. Passing is only permission to test further independent dates, never a declaration of reliable alpha. No latency or fee assumptions may be relaxed to rescue a failure.",
        "exposure": "24 additional configurations, session totals 100 configurations / 124 implementation versions, dependent rather than independent trials. Historical raw-field correction does not erase previous selection. No corrected statistical significance claim from six dates.",
        "limitations": "Throttled observed reports omit forced orders. FILLED quantity is completed order volume, not future residual demand. Counterfactual queue/fill/impact and real execution remain unverified. Monthly samples are not continuous competition returns.",
        "code_sha256": {name: digest(ROOT / name) for name in code}}
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"Frozen native executed-notional thresholds: {thresholds}", flush=True)
    records, audits = {}, []
    with ProcessPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(run_day, symbol, day, thresholds[symbol]) for symbol in ASSETS for day in EVALUATION]
        for job in as_completed(jobs):
            symbol, day, daily_records, source_audits = job.result()
            records[symbol, day] = daily_records
            audits.extend(source_audits)
            print(f"{symbol} {day}: {source_audits[0]['events']} native-size events", flush=True)
    results, advance = {}, []
    for symbol in ASSETS:
        output = OUT / symbol
        for name in records[symbol, EVALUATION[0]]:
            scenarios = {}
            for scenario in records[symbol, EVALUATION[0]][name]:
                days = [records[symbol, day][name][scenario] for day in EVALUATION]
                attempts = pd.DataFrame([row for day in days for row in day["attempts"]])
                daily = pd.DataFrame([{key: value for key, value in day.items() if key != "attempts"} for day in days])
                attempts.to_parquet(output / f"{name}_{scenario}_attempts.parquet", index=False)
                daily.to_parquet(output / f"{name}_{scenario}_daily.parquet", index=False)
                priced = attempts.loc[attempts.status.eq("priced")] if len(attempts) else attempts
                pnl = daily.closed_subtotal.to_numpy(float)
                complete = bool(daily.complete.all())
                scenarios[scenario] = {"complete": complete, "net_dollars": float(pnl.sum()) if complete else None,
                    "closed_subtotal": float(pnl.sum()), "gross_closed_subtotal": float(priced.gross.sum()) if len(priced) else 0.,
                    "trades": len(priced), "mean_net_bps": float(priced.net_bps.mean()) if len(priced) else None,
                    "positive_dates": int((pnl > 0).sum()) if complete else None,
                    "net_without_best_date": float(pnl.sum() - pnl.max()) if complete else None,
                    "outcomes": attempts.status.value_counts().to_dict() if len(attempts) else {},
                    "daily": daily.to_dict("records")}
            passed = all(s["complete"] and s["net_dollars"] > 0 for s in scenarios.values()) and scenarios["base"]["net_without_best_date"] > 0
            key = f"{symbol}/{name}"
            results[key] = {"symbol": symbol, "name": name, "scenarios": scenarios, "needs_additional_evidence": passed}
            if passed:
                advance.append(key)
            base = scenarios["base"]
            print(f"{key}: net={base['net_dollars']}, gross={base['gross_closed_subtotal']:+.4f}, trades={base['trades']}, advance={passed}", flush=True)
    assert all(digest(ROOT / name) == sha for name, sha in spec["code_sha256"].items())
    (OUT / "results.json").write_text(json.dumps({"results": results, "source_audits": audits,
        "candidates_for_additional_evidence": advance, "reliable_edge_established": False}, indent=2) + "\n")


if __name__ == "__main__":
    main()
