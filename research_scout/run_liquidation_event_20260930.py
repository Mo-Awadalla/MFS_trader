"""Fixed liquidation-event screen on first-of-month public samples."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from research.crypto_symbol_cache import digest
from research.liquidation_event_replay import (
    events_for_day,
    extract_quotes,
    quote_targets,
    simulate,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout/liquidation_event_20260930"
CALIBRATION = [f"2024-{month:02d}-01" for month in range(1, 7)]
EVALUATION = [f"2024-{month:02d}-01" for month in range(7, 13)]


def extract_day(day, threshold):
    path = OUTPUT / "raw/liquidations" / day / "BTCUSDT.csv.gz"
    book = OUTPUT / "raw/book_snapshot_5" / day / "BTCUSDT.csv.gz"
    for source in (path, book):
        manifest = json.loads(source.with_suffix(source.suffix + ".json").read_text())
        if digest(source) != manifest["sha256"]:
            raise ValueError(f"Downloaded source checksum changed: {source}")
    events = events_for_day(pd.read_csv(path), day, threshold)
    events.to_parquet(OUTPUT / "panels" / f"{day}_events.parquet", index=False)
    if events.empty:
        return day, {"date": day, "events": 0, "requested_snapshots": 0}
    quotes, audit = extract_quotes(book, day, quote_targets(events))
    quotes.to_parquet(OUTPUT / "panels" / f"{day}_quotes.parquet", index=False)
    audit.update(events=len(events), quiet_events=int(events.quiet_2s.sum()),
                 fresh_snapshot_fraction=float(quotes.quote_age_us.between(0, 1_000_000).mean()))
    return day, audit


def summary(trades, daily):
    pnl = daily.closed_trade_subtotal.to_numpy()
    complete = bool(daily.complete.all())
    priced = trades.loc[trades.status.eq("priced")] if len(trades) else trades
    rng = np.random.default_rng(93026)
    boot = pnl[rng.integers(0, len(pnl), (30000, len(pnl)))].mean(axis=1)
    return {"complete": complete, "closed_trade_subtotal": float(pnl.sum()),
            "net_dollars": float(pnl.sum()) if complete else None, "trades": len(priced),
            "gross_dollars": float(priced.gross_dollars.sum()) if len(priced) else 0,
            "mean_gross_bps": float(priced.gross_bps.mean()) if len(priced) else None,
            "mean_net_bps": float(priced.net_bps.mean()) if len(priced) else None,
            "positive_days": int((pnl > 0).sum()) if complete else None,
            "mean_daily_ci95": np.quantile(boot, [.025, .975]).tolist() if complete else None,
            "sixty_four_version_adjusted_mean_lower": float(np.quantile(boot, .05 / 64)) if complete else None,
            "net_without_best_day": float(pnl.sum() - pnl.max()) if complete else None,
            "daily": daily.to_dict("records")}


def main():
    (OUTPUT / "panels").mkdir(parents=True, exist_ok=True)
    spec_path = OUTPUT / "strategy_specification.json"
    if spec_path.exists():
        raise FileExistsError("Frozen liquidation screen already started")
    calibration = pd.concat([pd.read_csv(OUTPUT / "raw/liquidations" / day / "BTCUSDT.csv.gz") for day in CALIBRATION])
    threshold = float((calibration.price * calibration.amount).quantile(.99))
    source_paths = [ROOT / name for name in ("research/liquidation_event_replay.py", "research_scout/run_liquidation_event_20260930.py")]
    spec = {"created_at_utc": datetime.now(UTC).isoformat(), "calibration": CALIBRATION, "evaluation": EVALUATION,
            "threshold_reported_notional": threshold, "threshold_definition": "99th percentile of individual reported order notional in Jan-Jun samples; no future-return fitting",
            "events": "First above-threshold report after a five-minute refractory period; never retrospectively choose burst maximum or end. Quiet mode additionally requires no further report in the next two seconds, known before its delayed decision.",
            "directions": ["follow", "reverse", "price_follow", "price_reverse"], "modes": ["immediate", "quiet"], "horizons_seconds": [30, 120],
            "controls": "Price directions use the prior 30-second midpoint move at the SAME liquidation event clocks; they do not establish an independent event-timing control.",
            "configs": 16, "primary_event_configs": 8, "price_controls": 8, "session_version_correction": 64,
            "clocks": "Native microsecond capture order and exact strictly-prior book lookup. Decision 250ms after receipt, or after a two-second quiet wait. One-second order latency; three-second stress. Quote age<=1s; receive-exchange delay between -1ms and 2s.",
            "execution": "FOK entry with a causal 5bp tick-rounded collar; known five-level volume-weighted fills. Insufficient unknown deeper liquidity or missing submitted-order state invalidates day. Forced market exit at fixed horizon. No funding-boundary position, overlapping position or free inventory deletion.",
            "capital": "$10000 each isolated date, max $1000 ticket, <=10% pre-decision top quantity, 0.001 BTC increments; summed daily P&L, not continuous-calendar compounded wealth",
            "costs": "5bp taker fee plus 1bp adverse execution-cost allowance on EACH side, plus observed spread and depth crossing. Double-fee stress uses 10bp each side.",
            "gate": "Every scenario complete and profitable; >=50 baseline trades, >=5/6 positive dates, 64-version-adjusted date bootstrap lower>0, positive after deleting best day. Any survivor needs further independent dates and execution validation.",
            "limitations": "Public liquidation snapshots are throttled, not complete forced volume. Calendar-selected monthly first days are not ordinary continuous coverage. Reconstructed books remove crossed levels and CSV lacks disconnect events. Receive-clock historical replay does not measure actual order fills or impact. Freshly downloaded does not mean genuinely forward evidence.",
            "sources": ["https://docs.tardis.dev/downloadable-csv-files/data-types", "https://docs.tardis.dev/faq/data", "https://developers.binance.com/zh-CN/docs/products/derivatives-trading-usds-futures/common-definition"],
            "code_sha256": {str(path.relative_to(ROOT)): digest(path) for path in source_paths}}
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    audits = []
    with ProcessPoolExecutor(max_workers=2) as pool:
        for job in as_completed([pool.submit(extract_day, day, threshold) for day in EVALUATION]):
            day, audit = job.result()
            audits.append(audit)
            print(f"{day}: {audit['events']} events, {audit['requested_snapshots']} exact as-of book states", flush=True)
    (OUTPUT / "book_data_audit.json").write_text(json.dumps(audits, indent=2) + "\n")
    panels = [pd.read_parquet(OUTPUT / "panels" / f"{day}_quotes.parquet") for day in EVALUATION if (OUTPUT / "panels" / f"{day}_quotes.parquet").exists()]
    if not panels:
        (OUTPUT / "results.json").write_text(json.dumps({"verdict": "NO_LIQUIDATION_EVENTS", "survivors": [], "results": {}}, indent=2) + "\n")
        return
    quotes = pd.concat(panels, ignore_index=True)
    results, survivors = {}, []
    for direction in spec["directions"]:
        for mode in spec["modes"]:
            for horizon in spec["horizons_seconds"]:
                name = f"{direction}_{mode}_{horizon}s"
                scenarios = {}
                for scenario, kwargs in {"base": {}, "double_fees": {"fee_bps": 10}, "latency_3s": {"delay_ms": 3000}}.items():
                    trades, daily = simulate(quotes, direction, mode, horizon, **kwargs)
                    # Explicit zero-position days count; missing execution days never become zeros.
                    absent = [day for day in EVALUATION if day not in set(daily.date)]
                    if absent:
                        daily = pd.concat([daily, pd.DataFrame([{"date": day, "closed_trade_subtotal": 0., "complete": True, "unresolved": 0, "rejected_or_ineligible": 0} for day in absent])], ignore_index=True).sort_values("date")
                    trades.to_parquet(OUTPUT / f"{name}_{scenario}_trades.parquet", index=False)
                    daily.to_parquet(OUTPUT / f"{name}_{scenario}_daily.parquet", index=False)
                    scenarios[scenario] = summary(trades, daily)
                base = scenarios["base"]
                passed = (all(s["complete"] and s["net_dollars"] > 0 for s in scenarios.values())
                          and base["trades"] >= 50 and base["positive_days"] >= 5
                          and base["sixty_four_version_adjusted_mean_lower"] > 0 and base["net_without_best_day"] > 0)
                results[name] = {"scenarios": scenarios, "passed_gate": bool(passed), "is_price_control": direction.startswith("price_")}
                if passed:
                    survivors.append(name)
                print(f"{name}: net={base['net_dollars']}, gross={base['gross_dollars']:.2f}, trades={base['trades']}, pass={passed}", flush=True)
    assert all(digest(path) == spec["code_sha256"][str(path.relative_to(ROOT))] for path in source_paths)
    result = {"verdict": "SURVIVORS_REQUIRE_FURTHER_EVIDENCE" if survivors else "NO_LIQUIDATION_SURVIVOR", "survivors": survivors, "results": results}
    (OUTPUT / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result["verdict"], flush=True)


if __name__ == "__main__":
    main()
