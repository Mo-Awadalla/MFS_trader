"""Fixed eight-rule passive-liquidation screen and complete failed-path records."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from research.crypto_symbol_cache import digest
from research.liquidation_passive import SCENARIOS, EventBook, load_event_tape, replay

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research_scout/liquidation_event_20260930"
OUT = ROOT / "research_scout/liquidation_passive_20260930"
DATES = [f"2024-{month:02d}-01" for month in range(7, 13)]


def run_day(day):
    events_path = BASE / "panels" / f"{day}_events.parquet"
    events = pd.read_parquet(events_path)
    frames, audits = {}, []
    for kind, base, source_kind in (("book", BASE, "book_snapshot_5"), ("trades", OUT, "trades")):
        path = base / "raw" / source_kind / day / "BTCUSDT.csv.gz"
        manifest = json.loads(path.with_suffix(path.suffix + ".json").read_text())
        if digest(path) != manifest["sha256"]:
            raise ValueError("Raw source hash mismatch")
        cache, audit_path = OUT / "panels" / f"{day}_{kind}.parquet", OUT / "panels" / f"{day}_{kind}.json"
        if cache.exists() and audit_path.exists():
            audit = json.loads(audit_path.read_text())
            assert digest(cache) == audit["panel_sha256"] and audit["source_sha256"] == manifest["sha256"]
            assert audit["events_sha256"] == digest(events_path)
            frame = pd.read_parquet(cache)
        else:
            frame, audit = load_event_tape(path, day, events, kind)
            frame.to_parquet(cache, index=False)
            audit.update(source_sha256=manifest["sha256"], panel_sha256=digest(cache), events_sha256=digest(events_path))
            audit_path.write_text(json.dumps(audit, indent=2) + "\n")
        audits.append(audit)
        frames[kind] = frame
    book = EventBook(frames["book"])
    trade_frame = frames["trades"]
    trades = {key: trade_frame[key].to_numpy() for key in ("exchange_us", "id", "price", "amount")}
    trades["sell"] = trade_frame.side.eq("sell").to_numpy()
    records = {}
    for direction in ("follow", "reverse"):
        for offset in (8, 16):
            for hold in (30, 120):
                name = f"{direction}_{offset}bp_{hold}s"
                records[name] = {scenario: replay(day, book, trades, events, direction, offset, hold, settings)
                                 for scenario, settings in SCENARIOS.items()}
    return day, records, audits


def main():
    (OUT / "panels").mkdir(exist_ok=True)
    spec_path = OUT / "specification.json"
    if spec_path.exists():
        raise FileExistsError("Passive event batch already started")
    code = [ROOT / p for p in ("research/liquidation_passive.py", "research/cross_venue_dual_clock.py",
                               "research/liquidation_event_replay.py", "research_scout/run_liquidation_passive_20260930.py")]
    spec = {"created_at_utc": datetime.now(UTC).isoformat(), "dates": DATES, "configs": 8,
            "event_source": str(BASE / "strategy_specification.json"), "event_selection_unchanged": True,
            "prior_exposure": "All six dates and original 124 events have prior taker and cross-venue research exposure. Trade-through outcomes are new; this is development, not clean holdout evidence.",
            "rules": "Follow or oppose forced direction, 8/16bp passive offset from the capture-visible midpoint, 30/120-second holding time after entry cancellation acknowledgement. No quiet filter or event reselection.",
            "clocks": "Signal at recorded event capture, extra 250ms processing then 1s outbound (3s stress). Physical exchange book determines post-only acceptance and exits. Five-second venue resting window; cancel then wait one return trip before holding; market exit incurs outbound and acknowledgement latency.",
            "fills": "Baseline uses only correctly signed prints strictly through the resting limit and strictly inside activation/cancellation times, accumulating every partial up to intended quantity. Alternatives fill all on first-through, or accumulate touch-price volume. These are counterfactual sensitivities, not bounds or proven queue fills.",
            "costs": "3bp maker entry; 6bp taker exit plus 1bp adverse allowance. Double fees 6/12bp; observed depth-weighted exit spread retained. No rebates or VIP discounts.",
            "capital": "$10000 per isolated date, max $1000 intended notional, <=10% cash and predecision passive-side touch quantity, 0.001BTC step, 0.1USDT tick, $100 minimum initial order. Every partial retained. No position crossing any UTC hour plus one-minute buffer.",
            "data_quality": "Raw capture and exchange clocks ordered; trade IDs strictly increasing. Fixed -35/+170-second event windows. Signal age <=1s, physical book age <=250ms. Invalid submitted-order states or unavailable exit depth stop the day; subtotals never become complete P&L.",
            "scenarios": SCENARIOS,
            "progression": "Only complete positive results in every cost/latency/fill scenario and positive baseline after deleting the best date justify additional untouched dates. Sparse positive candidates are unresolved until more evidence. No frequency target is used as proof of negative economics.",
            "limits": "Six calendar-selected historical dates. Throttled liquidation reports are not full forced flow. Hidden queue, self-impact, actual fills, price bands, rejects, disconnects and continuously funded portfolio returns remain unobserved.",
            "sources": ["https://docs.tardis.dev/downloadable-csv-files/data-types", "https://www.binance.com/en-BH/fee/futureFee"],
            "code_sha256": {str(p.relative_to(ROOT)): digest(p) for p in code},
            "event_sha256": {d: digest(BASE / "panels" / f"{d}_events.parquet") for d in DATES}}
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    records, audits = {}, []
    with ProcessPoolExecutor(max_workers=2) as pool:
        for job in as_completed([pool.submit(run_day, day) for day in DATES]):
            day, result, source_audits = job.result()
            records[day] = result
            audits.extend(source_audits)
            print(f"Completed {day}: {len(result)} frozen variants", flush=True)
    results, further_evidence = {}, []
    for name in records[DATES[0]]:
        scenarios = {}
        for scenario in SCENARIOS:
            days = [records[d][name][scenario] for d in DATES]
            attempts = pd.DataFrame([attempt for day in days for attempt in day["attempts"]])
            priced = attempts.loc[attempts.status.eq("priced")]
            daily = pd.DataFrame([{k: v for k, v in day.items() if k != "attempts"} for day in days])
            attempts.to_parquet(OUT / f"{name}_{scenario}_attempts.parquet", index=False)
            daily.to_parquet(OUT / f"{name}_{scenario}_daily.parquet", index=False)
            complete = bool(daily.complete.all())
            pnl = daily.closed_subtotal.to_numpy(float)
            rng = np.random.default_rng(93026)
            boot = pnl[rng.integers(0, len(pnl), (30000, len(pnl)))].mean(axis=1)
            scenarios[scenario] = {"complete": complete, "net_dollars": float(pnl.sum()) if complete else None,
                "closed_subtotal": float(pnl.sum()), "gross_closed_subtotal": float(priced.gross.sum()) if len(priced) else 0.,
                "trades": len(priced), "mean_net_bps": float(priced.net_bps.mean()) if len(priced) else None,
                "partial_entries": int(priced.partial_entry.sum()) if len(priced) else 0,
                "positive_dates": int((pnl > 0).sum()) if complete else None,
                "net_without_best_date": float(pnl.sum() - pnl.max()) if complete else None,
                "date_bootstrap_mean_ci95": np.quantile(boot, [.025, .975]).tolist() if complete else None,
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
