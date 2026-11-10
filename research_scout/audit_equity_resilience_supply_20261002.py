"""Independent prefix-count audit of a zero-supply screen; no future prices used."""

import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

from research_scout.prepare_equity_resilience_20261002 import OUT, ROOT, SYMBOLS, sha

NS = 10**9


def difference_count(values, left, right):
    total = np.r_[0, np.cumsum(values, dtype=np.int64)]
    return total[right + 1] - total[left]


def inspect(source):
    assert sha(ROOT / source["path"]) == source["sha256"]
    store = db.read_dbn(ROOT / source["path"])
    all_records = store.to_ndarray()
    saved = json.loads((OUT / "sessions" / f"{source['date']}.json").read_text())
    assert len(all_records) == saved["source_rows"] and saved["raw_events"] == saved["selected_events"] == 0
    assert not saved["rows"] and sha(ROOT / saved["events_path"]) == saved["events_sha256"]
    assert pd.read_parquet(ROOT / saved["events_path"]).empty
    start = pd.Timestamp(source["date"] + " 09:30:00", tz="America/New_York").tz_convert("UTC").value
    decisions = np.arange(start + 5 * NS, start + 570 * NS + 1, 100_000_000, dtype=np.int64)
    cut = decisions - 250_000_000
    previous_cut = cut - 2 * NS
    counters, maxima, errors = Counter(), {"bid": D(0), "ask": D(0)}, []
    diagnostics = []
    for symbol in SYMBOLS:
        mapping = [m for m in store.metadata.mappings[symbol]
                   if str(m["start_date"]) <= source["date"] < str(m["end_date"])]
        assert len(mapping) == 1
        raw = all_records[all_records["instrument_id"] == int(mapping[0]["symbol"])]
        received = raw["ts_recv"].astype(np.int64)
        assert np.all(received >= 0) and np.all(received[1:] >= received[:-1])
        if np.any(raw["flags"] & 8):
            errors.append({"symbol": symbol, "reason": "BAD_TS_RECV record: no removal or timestamp repair"})
            counters["unassessable_symbol_sessions"] += 1
            continue
        counters["assessable_symbol_sessions"] += 1
        counters["decision_grids"] += len(decisions)
        complete = (raw["flags"] & 128) == 128
        q = raw[complete]
        qpos = np.flatnonzero(complete)
        t, e = q["ts_recv"].astype(np.int64), q["ts_event"].astype(np.int64)
        bid, ask, bq, aq = q["bid_px_00"], q["ask_px_00"], q["bid_sz_00"], q["ask_sz_00"]
        valid = ((bid > 0) & (ask > bid) & (ask < 10**16) & (bq > 0) & (aq > 0)
                 & (q["flags"] & 4 == 0) & (e <= t + 1_000_000) & (e >= t - NS))
        right = np.searchsorted(t, cut, side="left") - 1
        left = np.searchsorted(t, previous_cut, side="left") - 1
        exists = (left >= 0) & (right >= 0)
        li, ri = np.maximum(left, 0), np.maximum(right, 0)
        fresh = exists & valid[li] & valid[ri]
        for clocks in (t, e):
            fresh &= ((previous_cut - clocks[li] > 0) & (previous_cut - clocks[li] <= 250_000_000)
                      & (cut - clocks[ri] > 0) & (cut - clocks[ri] <= 250_000_000))
        counters["fresh_endpoint_grids"] += int(fresh.sum())
        spread = (ask[ri] - bid[ri]) / (ask[ri] + bid[ri]) * 20000
        fresh &= spread <= 5
        counters["fresh_tight_endpoint_grids"] += int(fresh.sum())
        no_invalid = difference_count(~valid, li, ri) == 0
        gaps = np.r_[False, np.diff(t) > 250_000_000]
        gap_prefix = np.r_[0, np.cumsum(gaps, dtype=np.int64)]
        no_gap = (gap_prefix[ri + 1] - gap_prefix[li + 1]) == 0
        clean = fresh & no_invalid & no_gap
        counters["continuous_clean_book_grids"] += int(clean.sum())
        bid_changes = np.r_[False, bid[1:] != bid[:-1]]
        ask_changes = np.r_[False, ask[1:] != ask[:-1]]
        bid_prefix = np.r_[0, np.cumsum(bid_changes, dtype=np.int64)]
        ask_prefix = np.r_[0, np.cumsum(ask_changes, dtype=np.int64)]
        held_bid = clean & ((bid_prefix[ri + 1] - bid_prefix[li + 1]) == 0)
        held_ask = clean & ((ask_prefix[ri + 1] - ask_prefix[li + 1]) == 0)
        counters["held_bid_grids"] += int(held_bid.sum())
        counters["held_ask_grids"] += int(held_ask.sum())
        is_trade = raw["action"] == b"T"
        trades, positions = raw[is_trade], np.flatnonzero(is_trade)
        tr, te = trades["ts_recv"].astype(np.int64), trades["ts_event"].astype(np.int64)
        tp, tq = trades["price"], trades["size"].astype(np.int64)
        valid_trade = ((tp > 0) & (tp < 10**16) & (tq > 0) & (trades["flags"] & 4 == 0)
                       & (te <= tr + 1_000_000) & (te >= tr - NS))
        for k in np.flatnonzero(held_bid | held_ask):
            lo, hi = np.searchsorted(tr, previous_cut[k], side="left"), np.searchsorted(tr, cut[k], side="left")
            idx = np.arange(lo, hi)
            idx = idx[positions[idx] <= qpos[ri[k]]]
            if (not np.all(valid_trade[idx]) or np.any(te[idx] < previous_cut[k]) or np.any(te[idx] >= cut[k])):
                counters["held_grids_with_invalid_trade_window"] += 1
                continue
            total = int(tq[idx].sum())
            if not total:
                counters["held_grids_with_no_completed_trades"] += 1
                continue
            counters["held_grids_with_valid_trade_volume"] += 1
            for name, held, price, depth, trade_side in (("bid", held_bid[k], bid[li[k]], bq[li[k]], b"A"),
                                                        ("ask", held_ask[k], ask[li[k]], aq[li[k]], b"B")):
                if not held:
                    continue
                at = idx[(trades["side"][idx] == trade_side) & (tp[idx] == price)]
                volume, clocks = int(tq[at].sum()), len(np.unique(tr[at]))
                multiple = D(volume) / D(int(depth))
                maxima[name] = max(maxima[name], multiple)
                if clocks < 5:
                    counters[name + "_fails_five_distinct_clocks"] += 1
                elif D(volume) * D(int(price)) / NS < 10000:
                    counters[name + "_fails_minimum_notional"] += 1
                elif 5 * volume < 4 * total:
                    counters[name + "_fails_directional_share"] += 1
                elif volume < 5 * int(depth):
                    counters[name + "_fails_five_times_displayed_size"] += 1
                else:
                    diagnostics.append({"symbol": symbol, "side": name, "decision_ns": int(decisions[k]),
                                        "volume": volume, "anchor_depth": int(depth), "distinct_clocks": clocks})
    assert errors == saved["source_errors"]
    # A zero seed count independently proves both the immediate rule and the
    # later-break rule had no possible event; no production detector is called.
    assert not diagnostics, (source["date"], diagnostics)
    return {"date": source["date"], "source_rows": len(all_records), "counters": dict(counters),
            "maximum_at_level_volume_multiple": {k: str(v) for k, v in maxima.items()},
            "unassessable": errors, "resilience_seeds": len(diagnostics)}


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    impl = json.loads((OUT / "implementation.json").read_text())
    result = json.loads((OUT / "results.json").read_text())
    assert sha(OUT / "specification.json") == impl["specification_sha256"]
    assert sha(OUT / "implementation.json") == result["implementation_sha256"]
    assert result["raw_events"] == result["selected_events"] == 0
    for p, digest in impl["code_sha256"].items():
        assert sha(ROOT / p) == digest
    for row in result["session_files"]:
        assert sha(OUT / "sessions" / f"{row['date']}.json") == row["sha256"]
    rows, counters = [], Counter()
    with ProcessPoolExecutor(max_workers=2) as pool:
        for n, future in enumerate(as_completed([pool.submit(inspect, s) for s in spec["sources"]]), 1):
            row = future.result()
            rows.append(row)
            counters.update(row["counters"])
            if n % 24 == 0 or n == len(spec["sources"]):
                print(json.dumps({"sessions_verified": n, "resilience_seeds": sum(r["resilience_seeds"] for r in rows)}), flush=True)
    assert sum(r["source_rows"] for r in rows) == result["source_rows"]
    for row in result["scenarios"]:
        assert row["optimistic_sum_usd"] is None and row["known_component_usd"] == "0"
        assert row["selected_events"] == row["priced_events"] == 0 and not row["outcomes"]
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(), "source_sessions_verified": len(rows),
             "source_rows_verified": result["source_rows"], "counters": dict(counters),
             "maximum_at_level_volume_multiple": {k: str(max(D(r["maximum_at_level_volume_multiple"][k]) for r in rows)) for k in ("bid", "ask")},
             "resilience_seeds": 0, "economic_replays_with_orders": 0,
             "scope": "Every source file and fixed-point book/trade window independently reconciled using prefix counts and direct trade aggregation, without importing the production detector or cash engine. Zero resilience seeds establish zero possible later-break entries. Two unassessable symbol-sessions remain unknown, never zero P&L.",
             "results_sha256": sha(OUT / "results.json"), "auditor_sha256": sha(Path(__file__)),
             "session_diagnostics": sorted(rows, key=lambda r: r["date"]),
             "actual_execution_verified": False, "reliable_edge_established": False}
    with (OUT / "independent_supply_verification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(audit, indent=2) + "\n")
    print(json.dumps({k: v for k, v in audit.items() if k != "session_diagnostics"}), flush=True)


if __name__ == "__main__":
    main()
