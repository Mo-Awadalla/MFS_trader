"""Independent raw-event grouping and all reported burst-survival predicates."""

import json
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

from research_scout.prepare_equity_burst_20261002 import OUT, ROOT, SYMBOLS, sha

NS = 10**9


def book_valid(row):
    b, a, bq, aq = (int(row[k]) for k in ("bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00"))
    r, e = int(row["ts_recv"]), int(row["ts_event"])
    return 0 < b < a < 10**16 and min(bq, aq) > 0 and not int(row["flags"]) & 4 and r - NS <= e <= r + 1_000_000


def group_source(raw, ends):
    assignment, counts, accepted = defaultdict(list), Counter(), []
    for position in np.flatnonzero(raw["action"] == b"T"):
        # Locate the source event that closes after this trade.
        closing = int(np.searchsorted(ends, position, side="left"))
        assignment[closing].append(int(position))
    for closing, trade_indices in sorted(assignment.items()):
        counts["trade_bearing_source_groups"] += 1
        if closing == len(ends):
            counts["unterminated_source_group"] += 1
            continue
        last = int(ends[closing])
        first = int(ends[closing - 1]) + 1 if closing else 0
        records = raw[first:last + 1]
        identities = {(int(r["ts_recv"]), int(r["ts_event"])) for r in records}
        if len(identities) != 1 or any(int(r["flags"]) & 12 for r in records):
            counts["mixed_clocks_or_bad_group"] += 1
            continue
        received, event_time = identities.pop()
        sides = {bytes(raw[i]["side"]) for i in trade_indices}
        prices = {int(raw[i]["price"]) for i in trade_indices}
        sizes = [int(raw[i]["size"]) for i in trade_indices]
        if (len(sides) != 1 or not sides <= {b"A", b"B"} or len(prices) != 1
                or not all(0 < p < 10**16 for p in prices) or min(sizes) <= 0):
            counts["unknown_or_mixed_trade_side_price"] += 1
            continue
        if closing == 0 or not book_valid(raw[int(ends[closing - 1])]) or not book_valid(raw[last]):
            counts["invalid_pre_or_completion_book"] += 1
            continue
        pre = raw[int(ends[closing - 1])]
        dr, de = received - int(pre["ts_recv"]), event_time - int(pre["ts_event"])
        if not (0 < dr <= 250_000_000 and 0 <= de <= 250_000_000 and -1_000_000 <= received - event_time <= NS):
            counts["ambiguous_stale_or_inconsistent_prestate"] += 1
            continue
        side, price, quantity = next(iter(sides)), next(iter(prices)), sum(sizes)
        prefix = "bid" if side == b"A" else "ask"
        pre_price, pre_size = int(pre[prefix + "_px_00"]), int(pre[prefix + "_sz_00"])
        if price != pre_price:
            counts["trade_price_not_preburst_touch"] += 1
            continue
        if quantity < pre_size * 5 or price * quantity < 10000 * NS:
            counts["burst_below_size_or_notional"] += 1
            continue
        accepted.append({"burst_first_source": first, "burst_last_source": last, "burst_quote_index": closing,
                         "burst_receive_ns": received, "burst_event_ns": event_time,
                         "burst_pre_quote_index": closing - 1, "burst_pre_quantity": pre_size,
                         "burst_quantity": quantity, "burst_trade_records": len(trade_indices),
                         "defended_price_int": price, "kind": 0 if side == b"A" else 1})
    counts["prestate_qualified_bursts"] = len(accepted)
    return accepted, dict(counts)


def reject_reason(raw, ends, burst, decision):
    cutoff, start = decision - 250_000_000, decision - 2_250_000_000
    qr = raw["ts_recv"][ends].astype(np.int64)
    first = int(np.searchsorted(qr, start, side="left")) - 1
    last = int(np.searchsorted(qr, cutoff, side="left")) - 1
    if first < 0 or last < 0:
        return "missing_endpoint"
    for index, boundary in ((first, start), (last, cutoff)):
        q = raw[int(ends[index])]
        if not book_valid(q) or any(not 0 < boundary - int(q[k]) <= 250_000_000 for k in ("ts_recv", "ts_event")):
            return "invalid_or_stale_endpoint"
    current = raw[int(ends[last])]
    if (int(current["ts_recv"]) - burst["burst_receive_ns"] < 250_000_000
            or int(current["ts_event"]) - burst["burst_event_ns"] < 250_000_000):
        return "missing_quarter_second_postburst_proof"
    if burst["burst_last_source"] > int(ends[last]):
        return "burst_not_yet_complete"
    previous_clock = None
    for index in range(first, last + 1):
        q = raw[int(ends[index])]
        r = int(q["ts_recv"])
        if not book_valid(q) or (previous_clock is not None and r - previous_clock > 250_000_000):
            return "intervening_invalid_or_stale_book"
        previous_clock = r
    bid, ask = int(current["bid_px_00"]), int(current["ask_px_00"])
    if 20000 * (ask - bid) > 5 * (ask + bid):
        return "current_spread"
    prefix = "bid" if burst["kind"] == 0 else "ask"
    if any(int(raw[int(ends[index])][prefix + "_px_00"]) != burst["defended_price_int"] for index in range(first, last + 1)):
        return "defended_price_did_not_hold"
    anchor_size = int(raw[int(ends[first])][prefix + "_sz_00"])
    if burst["burst_quantity"] < 5 * anchor_size:
        return "insufficient_volume_vs_anchor"
    lo = int(np.searchsorted(raw["ts_recv"], start, side="left"))
    stop = min(int(np.searchsorted(raw["ts_recv"], cutoff, side="left")), int(ends[last]) + 1)
    total = 0
    for row in raw[lo:stop]:
        if row["action"] != b"T":
            continue
        r, e, p, q = (int(row[k]) for k in ("ts_recv", "ts_event", "price", "size"))
        if not (0 < p < 10**16 and q > 0 and not int(row["flags"]) & 4
                and r - NS <= e <= r + 1_000_000 and start <= e < cutoff):
            return "invalid_or_delayed_window_trade"
        total += q
    if burst["burst_quantity"] * 5 < total * 4:
        return "burst_not_dominant_in_full_window"
    return None


def inspect(source):
    assert sha(ROOT / source["path"]) == source["sha256"]
    store = db.read_dbn(ROOT / source["path"])
    raw = store.to_ndarray()
    saved = json.loads((OUT / "sessions" / f"{source['date']}.json").read_text())
    assert saved["source_rows"] == len(raw) and saved["source_sha256"] == source["sha256"]
    assert not saved["events"] and not saved["selected_events"]
    opening = pd.Timestamp(source["date"] + " 09:30:00", tz="America/New_York").tz_convert("UTC").value
    grid = range(opening + 5 * NS, opening + 570 * NS + 1, 100_000_000)
    errors, counters, rejections = [], Counter(), Counter()
    candidate_windows = 0
    for symbol in SYMBOLS:
        ids = [int(m["symbol"]) for m in store.metadata.mappings[symbol] if str(m["start_date"]) <= source["date"] < str(m["end_date"])]
        assert len(ids) == 1
        records = raw[raw["instrument_id"] == ids[0]]
        captures = records["ts_recv"].astype(np.int64)
        assert np.all(captures >= 0) and np.all(captures[1:] >= captures[:-1])
        if np.any(records["flags"] & 8):
            errors.append({"symbol": symbol, "reason": "BAD_TS_RECV record: no removal or timestamp repair"})
            continue
        ends = np.flatnonzero(records["flags"] & 128)
        groups, counts = group_source(records, ends)
        observed = next(s for s in saved["symbol_diagnostics"] if s["symbol"] == symbol)
        assert counts == observed["counts"] and groups == observed["groups"]
        local_reasons = Counter()
        for burst in groups:
            for decision in grid:
                if not burst["burst_receive_ns"] + 500_000_000 < decision <= burst["burst_receive_ns"] + 2_250_000_000:
                    continue
                candidate_windows += 1
                reason = reject_reason(records, ends, burst, decision)
                assert reason is not None, (source["date"], symbol, decision, "Unexpected valid seed")
                local_reasons[reason] += 1
        assert dict(local_reasons) == observed["seed_failures"] and not observed["seeds"]
        counters.update(counts)
        rejections.update(local_reasons)
    assert errors == saved["source_errors"] and dict(counters) == saved["group_counters"]
    assert dict(rejections) == saved["seed_failures"]
    return {"source_rows": len(raw), "counts": dict(counters), "rejections": dict(rejections),
            "candidate_windows": candidate_windows, "errors": [{"date": source["date"], **e} for e in errors]}


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    result = json.loads((OUT / "screen_results.json").read_text())
    impl = json.loads((OUT / "implementation.json").read_text())
    assert sha(OUT / "specification.json") == impl["specification_sha256"]
    assert sha(OUT / "implementation.json") == result["implementation_sha256"]
    for path, digest in impl["code_sha256"].items():
        assert sha(ROOT / path) == digest
    for row in result["session_files"]:
        assert sha(OUT / "sessions" / f"{row['date']}.json") == row["sha256"]
    assert sha(OUT / "selected.parquet") == result["selected_sha256"]
    assert pd.read_parquet(OUT / "selected.parquet").empty and result["selected_events"] == result["raw_events"] == 0
    rows, counts, rejections = [], Counter(), Counter()
    with ProcessPoolExecutor(max_workers=2) as pool:
        for n, future in enumerate(as_completed([pool.submit(inspect, s) for s in spec["sources"]]), 1):
            row = future.result()
            rows.append(row)
            counts.update(row["counts"])
            rejections.update(row["rejections"])
            if n % 24 == 0 or n == len(spec["sources"]):
                print(json.dumps({"sessions_verified": n, "bursts_verified": counts["prestate_qualified_bursts"]}), flush=True)
    assert sum(r["source_rows"] for r in rows) == result["source_rows"]
    assert dict(counts) == result["group_counters"] and dict(rejections) == result["seed_failures"]
    errors = sorted([e for r in rows for e in r["errors"]], key=lambda r: (r["date"], r["symbol"]))
    assert errors == result["source_errors"]
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(), "source_sessions_verified": len(rows),
             "source_rows_verified": result["source_rows"], "group_counters": dict(counts),
             "candidate_windows_verified": sum(r["candidate_windows"] for r in rows),
             "seed_rejections": dict(rejections), "selected_events_verified": 0, "unknown_symbol_sessions": errors,
             "scope": "All native source groups independently reconstructed from F_LAST boundaries; complete side/price/clock/prestate/size filtering and all nine qualifying bursts matched. Every candidate signal window independently checked from raw completed books and trades, proving zero seeds under the frozen predicates. No production parser, burst detector or price-survival function imported.",
             "results_sha256": sha(OUT / "screen_results.json"), "auditor_sha256": sha(Path(__file__)),
             "future_returns_evaluated": False, "economic_implementations_run": 0, "reliable_edge_established": False}
    with (OUT / "independent_verification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
