"""Conditional full-allocation economics, before paying for queue evidence.

Official auction prices and observed after-hours quotes are references. Neither
proves our auction allocation or our actual routed exit. No strategy P&L claim.
"""

import json
import warnings
from datetime import UTC, datetime

import databento as db
import numpy as np
import pandas as pd

from research.auction_hft_event import costs
from research.crypto_symbol_cache import digest
from research_scout.correct_close_auction_clock_20260930 import DEST as INPUT
from research_scout.screen_close_auction_20260930 import BASE, BOUNDARY, OUT, PREFIX, ROOT, TAIL

DEST = OUT / "conditional_benchmark"
STATS = BASE / "ARCX.PILLAR/statistics/cash_etf_statistics_2021-01-01_2026-07-27.dbn.zst"
SCENARIOS = {"base": {"delay_s": 1, "fee_multiplier": 1., "adverse_bps": 1.},
             "double_fees": {"delay_s": 1, "fee_multiplier": 2., "adverse_bps": 1.},
             "latency_3s": {"delay_s": 3, "fee_multiplier": 1., "adverse_bps": 1.},
             "extra_slippage": {"delay_s": 1, "fee_multiplier": 1., "adverse_bps": 2.}}


def auction_references(signals):
    source = db.DBNStore.from_file(str(STATS)).to_df().reset_index()
    source = source.loc[source.symbol.astype(str).eq("SPY") & source.stat_type.eq(11)]
    source["date"] = source.ts_event.dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    rows = []
    for event in signals.to_dict("records"):
        group = source.loc[source.date.eq(event["date"])]
        row = {"date": event["date"], "official_rows": len(group), "valid": False}
        if len(group) == 1:
            r = group.iloc[0]
            receive, native = int(r.ts_recv.value), int(r.ts_event.value)
            row.update(price=float(r.price), quantity=int(r.quantity), event_ns=native, receive_ns=receive,
                       update_action=int(r.update_action), sequence=int(r.sequence), publisher_id=int(r.publisher_id))
            row["valid"] = bool(0 <= native - event["close_ns"] <= 10000000000 and native <= receive < native + 1000000000
                                 and r.price > 0 and r.quantity > 0 and int(r.update_action) == 1 and int(r.publisher_id) == 43)
        rows.append(row)
    frame = pd.DataFrame(rows)
    for field in ("event_ns", "receive_ns"):
        frame[field] = pd.array([r.get(field) for r in rows], dtype="Int64")
    frame.to_parquet(DEST / "auction_references.parquet", index=False)
    return frame


def targets(signals, auctions):
    records = []
    indexed = auctions.set_index("date").to_dict("index")
    for s in signals.to_dict("records"):
        a = indexed[s["date"]]
        if not a["valid"] or a["price"] > s["limit"] + 1e-9 or s["quantity"] > a["quantity"]:
            continue
        for delay in (1, 3):
            ack = max(int(a["receive_ns"]), int(a["event_ns"]) + delay * 1000000000)
            for hold in (15, 30):
                records.append({"date": s["date"], "delay_s": delay, "hold_s": hold, "ack_ns": ack,
                                "target_ns": ack + (hold + delay) * 1000000000 + 250000000})
    return pd.DataFrame(records)


def quote_references(requests):
    selected, counts = {}, {}
    for path in (PREFIX, TAIL):
        subset = requests.loc[requests.target_ns.lt(BOUNDARY) == (path == PREFIX)]
        if not len(subset):
            continue
        index = subset.to_dict("records")
        times = subset.target_ns.to_numpy(np.int64)
        end = int(times.max()) + 1000000000
        observed_rows = 0
        with warnings.catch_warnings(record=True) as notices:
            warnings.simplefilter("always")
            for chunk in db.DBNStore.from_file(str(path)).to_df(count=200000):
                frame = chunk.reset_index()
                all_receive = frame.ts_recv.dt.as_unit("ns").astype("int64").to_numpy()
                assert not (np.diff(all_receive) < 0).any()
                observed_rows += len(frame)
                filtered = frame.loc[frame.symbol.astype(str).eq("SPY") & ((frame["flags"].astype(int) & 128) != 0)]
                if len(filtered):
                    receive = filtered.ts_recv.dt.as_unit("ns").astype("int64").to_numpy()
                    pos = np.searchsorted(receive, times, side="left")
                    for j in np.flatnonzero(pos < len(receive)):
                        req = index[j]
                        key = (req["date"], req["delay_s"], req["hold_s"])
                        if key in selected:
                            continue
                        r = filtered.iloc[pos[j]]
                        selected[key] = {**req, "receive_ns": int(r.ts_recv.value), "event_ns": int(r.ts_event.value),
                                         "bid": float(r.bid_px_00), "ask": float(r.ask_px_00),
                                         "bid_qty": int(r.bid_sz_00), "ask_qty": int(r.ask_sz_00),
                                         "flags": int(r["flags"]), "source": str(path.relative_to(ROOT))}
                if all_receive[-1] >= end:
                    break
        counts[path.name] = {"rows_decoded": observed_rows, "warnings": sorted({str(w.message) for w in notices})}
        print(f"Exit reference extraction: {path.name}, {observed_rows:,} rows", flush=True)
    rows = [selected.get((r["date"], r["delay_s"], r["hold_s"]),
                         {**r, "receive_ns": -1, "event_ns": -1}) for r in requests.to_dict("records")]
    frame = pd.DataFrame(rows)
    for field in ("target_ns", "ack_ns", "receive_ns", "event_ns"):
        if field in frame:
            frame[field] = pd.array([r.get(field) for r in rows], dtype="Int64")
    frame.to_parquet(DEST / "exit_references.parquet", index=False)
    return frame, counts


def benchmark(signal, auction, quote, hold, scenario):
    record = {"date": signal["date"], "hold_s": hold, "quantity": int(signal["quantity"]),
              "limit": signal["limit"], "strategy_execution_verified": False}
    if not auction["valid"]:
        return {**record, "status": "unknown_official_auction", "conditional_complete": False}
    price, qty = auction["price"], record["quantity"]
    record.update(auction_price=price, auction_quantity=auction["quantity"], at_limit=abs(price - signal["limit"]) <= 1e-9)
    if price > signal["limit"] + 1e-9:
        return {**record, "status": "outside_limit_no_reference_fill", "conditional_complete": True, "conditional_pnl": 0.}
    if qty > auction["quantity"]:
        return {**record, "status": "unknown_auction_capacity", "conditional_complete": False, "possible_open_quantity": qty}
    if quote is None or not 0 <= quote["receive_ns"] - quote["target_ns"] <= 1000000000:
        return {**record, "status": "unknown_exit_observation", "conditional_complete": False, "possible_open_quantity": qty}
    values = [quote[k] for k in ("bid", "ask", "bid_qty", "ask_qty")]
    if (not np.isfinite(values).all() or min(values) <= 0 or quote["bid"] >= quote["ask"] or quote["ask"] >= 1e7
            or quote["bid_qty"] < qty or int(quote["flags"]) & (4 | 8)
            or quote["event_ns"] > quote["receive_ns"] + 1000000):
        return {**record, "status": "unknown_exit_depth_or_state", "conditional_complete": False, "possible_open_quantity": qty}
    fee, levy, adverse = costs(qty, price, quote["bid"], scenario["fee_multiplier"], scenario["adverse_bps"])
    gross = qty * (quote["bid"] - price)
    return {**record, "status": "conditional_full_allocation", "conditional_complete": True,
            "entry_notional": qty * price, "exit_notional": qty * quote["bid"], "exit_bid": quote["bid"],
            "exit_receive_ns": int(quote["receive_ns"]), "exit_target_ns": int(quote["target_ns"]),
            "gross": gross, "commission": fee, "sell_levies": levy, "adverse": adverse,
            "conditional_pnl": gross - fee - levy - adverse}


def summary(frame):
    complete = bool(frame.conditional_complete.all())
    pnl = frame.conditional_pnl.fillna(0)
    return {"conditional_complete": complete, "conditional_net": float(pnl.sum()) if complete else None,
            "conditional_closed_subtotal": float(pnl.sum()), "conditional_full_allocations": int(frame.status.eq("conditional_full_allocation").sum()),
            "without_best_three": float(pnl.sum() - pnl.nlargest(3).sum()) if complete else None,
            "positive_dates": int((pnl > 0).sum()), "outcomes": frame.status.value_counts().to_dict(),
            "strategy_execution_verified": False}


def main():
    DEST.mkdir(exist_ok=True)
    path = DEST / "specification.json"
    if path.exists():
        raise FileExistsError("Conditional auction benchmark already frozen")
    inputs = pd.read_parquet(INPUT / "screen.parquet")
    signals = inputs.loc[inputs.eligible]
    old = json.loads((OUT / "screen_specification.json").read_text())
    validation = json.loads((BASE / "validation_report.json").read_text())
    sha = next(f["sha256"] for f in validation["files"] if f["path"].replace("\\", "/") == STATS.relative_to(ROOT).as_posix())
    assert digest(STATS) == sha
    for p, source_sha in old["source_sha256"].items():
        assert digest(ROOT / p) == source_sha
    code = ["research_scout/benchmark_close_auction_20260930.py", "research/auction_hft_event.py"]
    spec = {"created_at_utc": datetime.now(UTC).isoformat(), "stage": "conditional allocation/observed-quote economics only",
            "new_configurations": 2, "holds_seconds": [15, 30], "scenarios": SCENARIOS, "dates": signals.date.tolist(),
            "input_sha256": digest(INPUT / "screen.parquet"), "statistics_sha256": sha,
            "source_sha256": old["source_sha256"], "code_sha256": {p: digest(ROOT / p) for p in code},
            "entry": "Frozen predecision integer size and LOC limit. Send at15:58:55.25;1s/3s outbound arrives before15:59 freeze. No cancellation. Use unique native ARCX.PILLAR SPY ClosingPrice statistic, sourced from CrossTrade, timestamp within10s of16:00. If official price is above limit, no reference fill. If at/below limit and quantity<=reported auction quantity, conditionally assume full allocation for this economic diagnostic ONLY. Actual priority/rationing, auction impact and individual order acceptance are unverified; even strictly better-priced limits do not by themselves prove allocation.",
            "exit": "ACK reference=max(auction capture,auction event+return delay). Hold15/30s after this reference, then250ms processing plus1s/3s outbound. Select first complete SPY TBBO event at/after that target; require wait<=1s, positive noncrossed book and displayed bid size>=fixed quantity. Retain invalid first states and insufficient depth as unknown. Use its bid as a conditional observed-price reference, not a guaranteed live after-hours fill. No fractional resizing, no carrying a missing exit at zero loss.",
            "fees": "Original conservative$.0075/share minimum$1/side; sale.30bp +$.0002/share;1bp adverse each side. Stress doubled fees, doubled adverse allowance,3s network delay. Decisions fixed across stresses.",
            "scope": "Do not call conditional P&L actual strategy profitability. Auction allocation and routable after-hours execution require separate evidence if economics pass. This stage avoids spending on those prerequisites for unprofitable reference economics. All dates are previously exposed discovery, not a holdout. No live orders or paid API.",
            "advance": "Only if conditional totals are complete and positive in every scenario for BOTH2023-24 and2025, baselinepositive>=3 dates in each period and positive after removing its best3 dates; passing justifies allocation/venue evidence, never an edge claim. Otherwise retire this rule without changing clocks, caps or fees.",
            "sources": ["https://databento.com/docs/venues-and-datasets", "https://databento.com/docs/schemas-and-data-formats/statistics", "https://databento.com/docs/schemas-and-data-formats/tbbo"]}
    path.write_text(json.dumps(spec, indent=2) + "\n")
    auctions = auction_references(signals)
    requests = targets(signals, auctions)
    print(f"Frozen two holds: {len(signals)} predecision dates, {len(requests)} conditional exit targets", flush=True)
    if len(requests):
        quotes, extraction = quote_references(requests)
        lookup = {(r["date"], r["delay_s"], r["hold_s"]): r for r in quotes.to_dict("records")}
    else:
        extraction, lookup = {}, {}
    au = auctions.set_index("date").to_dict("index")
    results, advance = {}, []
    for hold in (15, 30):
        scenarios = {}
        for name, scenario in SCENARIOS.items():
            rows = [benchmark(s, au[s["date"]], lookup.get((s["date"], scenario["delay_s"], hold)), hold, scenario)
                    for s in signals.to_dict("records")]
            frame = pd.DataFrame(rows)
            for field in ("exit_receive_ns", "exit_target_ns"):
                if field in frame:
                    frame[field] = pd.array([r.get(field) for r in rows], dtype="Int64")
            frame.to_parquet(DEST / f"{hold}s_{name}_ledger.parquet", index=False)
            scenarios[name] = {"all": summary(frame), "development_2023_2024": summary(frame.loc[frame.date.lt("2025-01-01")]),
                               "selection_2025": summary(frame.loc[frame.date.ge("2025-01-01")])}
        passed = True
        for period in ("development_2023_2024", "selection_2025"):
            base = scenarios["base"][period]
            passed &= (all(s[period]["conditional_complete"] and s[period]["conditional_net"] > 0 for s in scenarios.values())
                       and base["positive_dates"] >= 3 and base["without_best_three"] > 0)
        if passed:
            advance.append(f"{hold}s")
        results[f"{hold}s"] = {"scenarios": scenarios, "advance_to_allocation_evidence": bool(passed)}
        print(f"{hold}s: {json.dumps(scenarios['base'])}; advance={passed}", flush=True)
    assert all(digest(ROOT / p) == h for p, h in spec["code_sha256"].items())
    report = {"results": results, "advance_to_allocation_evidence": advance, "extraction": extraction,
              "evidence_sha256": {p.name: digest(p) for p in DEST.glob("*.parquet")},
              "strategy_execution_verified": False, "reliable_edge_established": False}
    (DEST / "results.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
