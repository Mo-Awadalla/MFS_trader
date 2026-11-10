"""Independent full-envelope clock buckets and exact two-sided shock predicates."""

import bisect
import calendar
import gzip
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

import pandas as pd

from research_scout.prepare_perp_shock_20261002 import OUT, ROOT, sha

NS, STEP = 10**9, 250_000_000


def reconstruct(source):
    day, offset = source["date"], source["offset"]
    midnight = calendar.timegm(datetime.strptime(day, "%Y-%m-%d").timetuple()) * NS
    start = midnight + offset * 60 * NS
    cutoffs = list(range(start + 750_000_000, start + 58_750_000_000, STEP))
    updates, symbols, ids, maxima = [{} for _ in range(233)], set(), {}, {}
    counts, last, epoch = Counter(), start - 1, 0
    path = ROOT / source["path"]
    assert source["complete"] and sha(path) == source["compressed_sha256"]
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for number, line in enumerate(stream):
            if not line.strip():
                counts["disconnects"] += 1
                updates[bisect.bisect_right(cutoffs, last)].update(dict.fromkeys(symbols))
                ids.clear()
                maxima.clear()
                epoch += 1
                continue
            stamp, payload = line.strip().split(" ", 1)
            whole, fraction = stamp[:-1].split(".") if "." in stamp else (stamp[:-1], "0")
            clock = datetime.fromisoformat(whole)
            received = midnight + (clock.hour * 3600 + clock.minute * 60 + clock.second) * NS + int(fraction.ljust(9, "0"))
            assert stamp[:10] == day and start <= received < start + 60 * NS and received >= last
            last = received
            counts["native_messages"] += 1
            envelope = json.loads(payload)
            if envelope.get("stream", "").rsplit("@", 1)[-1] != "bookTicker":
                continue
            counts["book_messages"] += 1
            raw = envelope["data"]
            symbol = raw["s"]
            if not symbol.isalnum() or not symbol.endswith("USDT"):
                continue
            symbols.add(symbol)
            counts["universe_book_messages"] += 1
            uid = int(raw["u"])
            fingerprint = tuple(str(raw[k]) for k in ("b", "B", "a", "A", "T", "E"))
            previous = ids.get(symbol)
            if previous == (uid, fingerprint):
                counts["exact_duplicate_books"] += 1
                continue
            valid_sequence = previous is None or uid > previous[0]
            t, e = int(raw["T"]) * 10**6, int(raw["E"]) * 10**6
            ordered = symbol not in maxima or t >= maxima[symbol]
            if valid_sequence:
                ids[symbol] = uid, fingerprint
                if not ordered:
                    counts["regressing_matching_clocks"] += 1
                maxima[symbol] = max(t, maxima.get(symbol, t))
            else:
                counts["conflicting_or_regressing_books"] += 1
            updates[bisect.bisect_right(cutoffs, received)][symbol] = {
                "receive_ns": received, "source_line": number, "update_id": uid,
                "bid": str(raw["b"]), "ask": str(raw["a"]),
                "bid_quantity": str(raw["B"]), "ask_quantity": str(raw["A"]),
                "sequence_ok": valid_sequence, "venue": "perpetual", "transaction_ns": t,
                "publication_ns": e, "transaction_order_ok": ordered, "epoch": epoch}
    active, grids = {}, []
    for update in updates[:232]:
        active.update(update)
        grids.append(dict(active))
    return start, grids, symbols, counts


def quote_failure(quote, cutoff):
    if quote is None:
        return "missing_book"
    if not quote["sequence_ok"]:
        return "conflicting_or_regressing_id"
    if not quote["transaction_order_ok"]:
        return "regressing_matching_clock"
    b, a, bq, aq = [D(quote[k]) for k in ("bid", "ask", "bid_quantity", "ask_quantity")]
    if not all(x.is_finite() and x > 0 for x in (b, a, bq, aq)) or b >= a:
        return "invalid_book"
    capture, transaction, event = [quote[k] for k in ("receive_ns", "transaction_ns", "publication_ns")]
    if not cutoff - STEP <= capture < cutoff:
        return "capture_freshness_gate"
    if not (cutoff - STEP <= transaction < cutoff and cutoff - STEP <= event < cutoff
            and transaction <= event + 10**6 and max(transaction, event) <= capture + 10**6):
        return "native_clock_gate"
    return None


def predicate(old, new, decision):
    result = {"valid_endpoints": False, "supply": False, "direction": 0}
    for prefix, state, cutoff in (("anchor", old, decision - NS - STEP), ("current", new, decision - STEP)):
        error = quote_failure(state, cutoff)
        if error:
            return {**result, "reason": prefix + "_" + error}
    if old["epoch"] != new["epoch"]:
        return {**result, "reason": "disconnect_between_endpoints"}
    b0, a0, b1, a1 = (D(old["bid"]), D(old["ask"]), D(new["bid"]), D(new["ask"]))
    up = 10000 * (b1 - b0) >= 30 * b0 and 10000 * (a1 - a0) >= 30 * a0
    down = 10000 * (b1 - b0) <= -30 * b0 and 10000 * (a1 - a0) <= -30 * a0
    direction = 1 if up else -1 if down else 0
    spread = 2000 * (a0 - b0) <= a0 + b0 and 2000 * (a1 - b1) <= a1 + b1
    minimum = min(D(q[p]) * D(q[s]) for q in (old, new) for p, s in (("bid", "bid_quantity"), ("ask", "ask_quantity")))
    depth = minimum >= 2000
    supply = bool(direction and spread and depth)
    return {"valid_endpoints": True, "supply": supply, "direction": direction,
            "bid_return_bps": (b1 - b0) * 10000 / b0, "ask_return_bps": (a1 - a0) * 10000 / a0,
            "anchor_spread_bps": (a0 - b0) * 20000 / (a0 + b0),
            "current_spread_bps": (a1 - b1) * 20000 / (a1 + b1), "minimum_touch_usdt": minimum,
            "spread_gate": spread, "depth_gate": depth,
            "reason": "requires_native_trade_confirmation" if supply else "displacement_gate" if not direction else "spread_gate" if not spread else "depth_gate"}


def compare(actual, expected):
    maximum = D(0)
    for key, value in expected.items():
        if isinstance(value, D):
            difference = abs(D(str(actual[key])) - value)
            assert difference < D("1e-18"), (key, actual[key], value)
            maximum = max(maximum, difference)
        else:
            assert actual[key] == value, (key, actual[key], value)
    for key in actual.keys() - expected.keys():
        assert pd.isna(actual[key]), (key, actual[key])
    return maximum


def verify(job):
    source, window = job
    start, grids, symbols, counts = reconstruct(source)
    assert dict(counts) == window["source_counts"] and len(symbols) == window["symbols"]
    for name in ("quotes", "signals"):
        assert sha(ROOT / window[name + "_path"]) == window[name + "_sha256"]
    quotes = pd.read_parquet(ROOT / window["quotes_path"]).to_dict("records")
    signals = pd.read_parquet(ROOT / window["signals_path"]).to_dict("records")
    assert len(quotes) == len(symbols) * 232 == window["quote_rows"]
    assert len(signals) == len(symbols) * 228 == window["signal_rows"]
    reasons, selected = Counter(), []
    quote_index, signal_index, valid, raw_shocks, maximum = 0, 0, 0, 0, D(0)
    for symbol in sorted(symbols):
        last_event = start - 30 * NS
        for i, snapshot in enumerate(grids):
            decision = start + NS + i * STEP
            meta = {"date": source["date"], "offset_minutes": source["offset"], "symbol": symbol, "decision_ns": decision}
            compare(quotes[quote_index], {**meta, **(snapshot.get(symbol) or {})})
            quote_index += 1
            if i < 4:
                continue
            expected = {**meta, **predicate(grids[i - 4].get(symbol), snapshot.get(symbol), decision)}
            chosen = expected["supply"] and decision - last_event >= 30 * NS
            if chosen:
                last_event = decision
            expected["selected"] = chosen
            maximum = max(maximum, compare(signals[signal_index], expected))
            valid += int(expected["valid_endpoints"])
            raw_shocks += int(expected["supply"])
            reasons[expected["reason"]] += 1
            if chosen:
                selected.append(signals[signal_index])
            signal_index += 1
    assert valid == window["valid_endpoints"] and raw_shocks == window["raw_shock_rows"]
    assert dict(reasons) == window["reasons"] and selected == window["selected"]
    return {"date": source["date"], "offset": source["offset"], "source_counts": dict(counts),
            "signal_rows": len(signals), "quote_rows": len(quotes), "selected_events": len(selected),
            "maximum_numeric_difference": str(maximum)}


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    results = json.loads((OUT / "screen_results.json").read_text())
    impl = json.loads((OUT / "screen_implementation.json").read_text())
    assert results["implementation_sha256"] == sha(OUT / "screen_implementation.json")
    assert impl["specification_sha256"] == sha(OUT / "specification.json")
    for path, digest in impl["code_sha256"].items():
        assert sha(ROOT / path) == digest
    indexed = {(s["date"], s["offset"]): s for s in spec["sources"]}
    jobs = [(indexed[(w["date"], w["offset"])], w) for w in results["windows"]]
    assert len(jobs) == len(indexed) == 60
    verified, counts = [], Counter()
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(verify, job) for job in jobs]
        for future in as_completed(futures):
            row = future.result()
            verified.append(row)
            counts.update(row["source_counts"])
            print(json.dumps({k: row[k] for k in ("date", "offset", "signal_rows", "selected_events")}), flush=True)
    assert dict(counts) == results["source_counts"]
    assert sum(r["selected_events"] for r in verified) == results["selected_events"]
    assert sha(OUT / "selected.parquet") == results["selected_sha256"]
    assert pd.read_parquet(OUT / "selected.parquet").to_dict("records") == [r for w in results["windows"] for r in w["selected"]]
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
             "source_files_verified": len(verified), "source_counts": dict(counts),
             "signal_rows_verified": sum(r["signal_rows"] for r in verified),
             "quote_rows_verified": sum(r["quote_rows"] for r in verified),
             "selected_events_verified": sum(r["selected_events"] for r in verified),
             "maximum_numeric_difference": str(max(D(r["maximum_numeric_difference"]) for r in verified)),
             "results_sha256": sha(OUT / "screen_results.json"), "auditor_sha256": sha(Path(__file__)),
             "scope": "Independent raw parser and exact quarter-second information buckets; every quote, source clock, integrity state, both-sided displacement, spread/depth predicate, cooldown, selected event and aggregate. No production signal/parser import.",
             "economic_implementations": 0, "future_returns_evaluated": False,
             "actual_execution_verified": False, "reliable_edge_established": False}
    with (OUT / "independent_verification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
