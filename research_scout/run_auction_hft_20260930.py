"""New seconds-only auction test using the full quote updates already on disk."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

from research.auction_hft_event import RULES, SCENARIOS, extract_quotes, replay_day
from research.crypto_symbol_cache import digest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/auction_hft_20260930"
MANIFEST = ROOT / "external_artifacts/databento_cash_etf_mbp1_open_v55/manifest.json"
AUCTION = ROOT / "external_artifacts/databento_cash_etf_budget_v1/ARCX.PILLAR/imbalance/spy_imbalance_2021-01-01_2026-07-27.dbn.zst"
QUALITY = ROOT / "research_scout/new_data_technical_audit_v34.json"
AUCTION_FIELDS = ["ref_price", "ind_match_price", "paired_qty", "total_imbalance_qty",
                  "market_imbalance_qty", "auction_type", "side", "auction_status", "freeze_status"]


def auction_inputs(days):
    targets = pd.DataFrame([{"date": day, "label": label,
                             "target_ns": pd.Timestamp(day + " " + clock, tz="America/New_York").value}
                            for day in days for label, clock in (("early", "09:28:00"), ("late", "09:29:50"))])
    times = targets.target_ns.to_numpy(np.int64)
    values = np.full((len(targets), len(AUCTION_FIELDS)), None, object)
    receive = np.full(len(targets), -1, np.int64)
    event = receive.copy()
    previous, raw_rows = -1, 0
    for chunk in db.DBNStore.from_file(str(AUCTION)).to_df(count=200000):
        frame = chunk.reset_index()
        local = frame.ts_recv.dt.as_unit("ns").astype("int64").to_numpy()
        if not len(local):
            continue
        if (np.diff(local) < 0).any() or local[0] < previous:
            raise ValueError("Unordered native auction capture stream")
        previous = local[-1]
        raw_rows += len(frame)
        index = np.searchsorted(local, times, side="left") - 1
        keep = index >= 0
        values[keep] = frame[AUCTION_FIELDS].to_numpy()[index[keep]]
        receive[keep] = local[index[keep]]
        event[keep] = frame.ts_event.dt.as_unit("ns").astype("int64").to_numpy()[index[keep]]
    targets[AUCTION_FIELDS] = values
    targets["receive_ns"], targets["event_ns"] = receive, event
    targets.to_parquet(OUT / "auction_inputs.parquet", index=False)
    return targets, {"raw_auction_rows": raw_rows, "source_sha256": digest(AUCTION),
                     "panel_sha256": digest(OUT / "auction_inputs.parquet")}


def process_day(source):
    day, path = source["date"], ROOT / source["path"]
    assert digest(path) == source["sha256"]
    frame = db.DBNStore.from_file(str(path)).to_df().reset_index()
    quotes, audits = extract_quotes(frame, day)
    cache = OUT / "panels" / f"{day}.parquet"
    quotes.to_parquet(cache, index=False)
    return {"date": day, "source_path": source["path"], "source_sha256": source["sha256"],
            "panel_sha256": digest(cache), "raw_rows": len(frame), "symbols": audits}


def summarize(frame):
    priced = frame.loc[frame.status.eq("priced")]
    complete = bool(frame.complete.all())
    pnl = frame.pnl.fillna(0).to_numpy(float)
    return {"complete": complete, "net_dollars": float(pnl.sum()) if complete else None,
            "closed_subtotal": float(pnl.sum()), "gross_closed_subtotal": float(priced.gross.sum()) if len(priced) else 0.,
            "trades": len(priced), "dates": len(frame), "positive_dates": int((pnl > 0).sum()) if complete else None,
            "net_without_best_five_dates": float(pnl.sum() - np.sort(pnl)[-5:].sum()) if complete else None,
            "outcomes": frame.status.value_counts().to_dict(),
            "unresolved_dates": frame.loc[~frame.complete, "date"].tolist()}


def main():
    (OUT / "panels").mkdir(parents=True, exist_ok=True)
    spec_path = OUT / "specification.json"
    if spec_path.exists():
        raise FileExistsError("Seconds-only auction batch already frozen")
    manifest, quality = json.loads(MANIFEST.read_text()), json.loads(QUALITY.read_text())
    excluded = sorted(set(quality["degraded_dates"]["ARCX.PILLAR"]) | set(quality["degraded_dates"]["EQUS.MINI"]))
    sources = [row for row in manifest["results"] if row["date"] < "2026-01-01" and row["date"] not in excluded]
    days = sorted(row["date"] for row in sources)
    code = ["research/auction_hft_event.py", "research_scout/run_auction_hft_20260930.py"]
    spec = {"created_at_utc": datetime.now(UTC).isoformat(), "configs": 8, "rules": RULES,
        "holds_seconds": [15, 30], "dates": days, "scenarios": SCENARIOS,
        "source_manifest_sha256": digest(MANIFEST), "quality_source_sha256": digest(QUALITY),
        "auction_source_sha256": digest(AUCTION), "excluded_degraded_dates": excluded,
        "scope": "Strict HFT: decision at 09:29:50 ET, hold 15/30s after entry acknowledgment, then delayed exit. Long cash ETFs only. No multi-minute historical auction rule is run or declared revived.",
        "forecast": "Frozen, unfitted mechanisms: SPY indicative match price / contemporaneous SPY midpoint minus 1; indicative-versus-reference return leadership from 09:28 to 09:29:50; prior-30s SPY midpoint momentum control. Direction maps to SPY/SH at 1x or UPRO/SPXU at 3x. Hypothetical return magnitude scales by stated ETF leverage; this is a tested hypothesis, not a fundamental fair-value guarantee.",
        "gate": "Projected exit is current instrument bid times one plus projected return. Predicted cash gain must exceed frozen base costs plus 1bp of entry notional. Reuse the same decision under all stresses.",
        "sizing": "$10000 independently reset daily; integer shares, <=10% predecision displayed ask size, 1% cash reserve. Actual size never resized using a later quote. Single position per date/rule.",
        "execution": "250ms decision processing then 1s outbound; 3s delay stress. Entry FOK with 5bp causal collar rounded down to one cent. Holding starts only after return acknowledgment, then exit is sent with outbound delay. Source-event-clock displayed touch must be <=250ms old. Insufficient known top size or unknown submitted entry/exit invalidates the date, preserving any known inventory. No passive or auction fill is assumed.",
        "costs": "$0.0075/share per side with $1 minimum per side; additional sell levy 0.30bp plus $0.0002/share. 1bp adverse allowance per side, separate from actual limit-constrained prices. Double all fees and sell levies; separately double adverse allowance. Conservative assumptions, not verified competition fee terms.",
        "information": "Strictly prior capture timestamps for all features; late auction state <=2s old and source event not in future. Last invalid complete book state remains invalid, never resurrect an earlier valid quote. Backward source event time marks nearby execution targets ambiguous.",
        "limitations": "EQUS.MINI is anonymized aggregated BBO, not SIP NBBO or a identified routable exchange book. Source-event-clock execution is a historical proxy, not proof of matching-engine fills. Historical quote-quality exclusions create conditional samples. Auction indicative/reference fields do not establish latent or institutional inventory.",
        "validation": "2023-24 and 2025 are all historically exposed discovery. Separately report each year, but do not call 2025 untouched. Progress requires complete positive 2025 net in every scenario, >=50 completed trades and positive after removing best five dates; positive 2023-24 aggregate as well. Only then inspect later dates, still requiring new forward/live evidence.",
        "multiplicity": "8 more configurations; session totals become 108 configurations / 132 implementations. Prior 100/124 plus repository-wide historical selection remain. No reliability claim from naive confidence intervals.",
        "code_sha256": {p: digest(ROOT / p) for p in code}}
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"Frozen {len(days)} quote sessions, 8 seconds-only rules; extracting native auction states", flush=True)
    auction, auction_audit = auction_inputs(days)
    print(f"Read {auction_audit['raw_auction_rows']:,} native auction messages", flush=True)
    audits = []
    with ProcessPoolExecutor(max_workers=2) as pool:
        for job in as_completed([pool.submit(process_day, source) for source in sources]):
            audits.append(job.result())
            if len(audits) % 50 == 0 or len(audits) == len(sources):
                print(f"Quote extraction {len(audits)}/{len(sources)} sessions", flush=True)
    state = {(row["date"], row["label"]): row for row in auction.to_dict("records")}
    records = {f"{rule}_{hold}s": {scenario: [] for scenario in SCENARIOS} for rule in RULES for hold in (15, 30)}
    for day in days:
        quotes = pd.read_parquet(OUT / "panels" / f"{day}.parquet")
        for rule in RULES:
            for hold in (15, 30):
                for name, scenario in SCENARIOS.items():
                    records[f"{rule}_{hold}s"][name].append(replay_day(day, quotes, state[day, "early"], state[day, "late"], rule, hold, scenario))
    results, advance = {}, []
    for name, scenarios in records.items():
        reports = {}
        for scenario, rows in scenarios.items():
            frame = pd.DataFrame(rows)
            frame.to_parquet(OUT / f"{name}_{scenario}_attempts.parquet", index=False)
            reports[scenario] = {"all": summarize(frame), "development_2023_2024": summarize(frame.loc[frame.date.lt("2025-01-01")]),
                                 "selection_2025": summarize(frame.loc[frame.date.ge("2025-01-01")]),
                                 "by_year": {year: summarize(group) for year, group in frame.groupby(frame.date.str[:4])}}
        base = reports["base"]["selection_2025"]
        passed = (all(s["selection_2025"]["complete"] and s["selection_2025"]["net_dollars"] > 0 for s in reports.values())
                  and reports["base"]["development_2023_2024"]["complete"]
                  and reports["base"]["development_2023_2024"]["net_dollars"] > 0
                  and base["trades"] >= 50 and base["net_without_best_five_dates"] > 0)
        results[name] = {"scenarios": reports, "needs_additional_evidence": passed}
        if passed:
            advance.append(name)
        print(f"{name}: 2025 net={base['net_dollars']}, closed={base['closed_subtotal']:+.4f}, trades={base['trades']}, advance={passed}", flush=True)
    assert all(digest(ROOT / p) == sha for p, sha in spec["code_sha256"].items())
    (OUT / "results.json").write_text(json.dumps({"results": results, "candidates_for_additional_evidence": advance,
        "source_audits": audits, "auction_audit": auction_audit, "reliable_edge_established": False}, indent=2) + "\n")


if __name__ == "__main__":
    main()
