"""Independent full-envelope parsing, causal buckets and FDUSD budget checks."""

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

from research_scout.prepare_fdusd_maker_20261002 import OUT, ROOT, sha

NS = 1_000_000_000


def independent_source(source):
    day, offset = source["date"], source["offset"]
    midnight = calendar.timegm(datetime.strptime(day, "%Y-%m-%d").timetuple()) * NS
    start = midnight + offset * 60 * NS
    cuts = [start + second * NS - 250_000_000 for second in range(10, 60)]
    changes = [{} for _ in range(51)]
    ids, seen, counts = {}, set(), Counter()
    last = start - 1
    path = ROOT / source["path"]
    assert source["complete"] and sha(path) == source["compressed_sha256"]
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for number, line in enumerate(stream):
            if not line.strip():
                counts["disconnects"] += 1
                for symbol in seen | {"FDUSDUSDT"}:
                    changes[bisect.bisect_right(cuts, last)][symbol] = None
                ids.clear()
                continue
            stamp, encoded = line.strip().split(" ", 1)
            assert stamp[:10] == day
            time_of_day = datetime.fromisoformat(stamp[:19])
            received = midnight + (time_of_day.hour * 3600 + time_of_day.minute * 60 + time_of_day.second) * NS
            received += int(stamp[20:-1].ljust(9, "0")) if "." in stamp else 0
            assert start <= received < start + 60 * NS and received >= last
            last = received
            counts["native_messages"] += 1
            message = json.loads(encoded)
            if message.get("stream", "").rsplit("@", 1)[-1] != "bookTicker":
                continue
            raw = message["data"]
            symbol = raw["s"]
            if not (symbol.endswith("FDUSD") and symbol.isalnum()) and symbol != "FDUSDUSDT":
                continue
            counts["relevant_book_messages"] += 1
            if symbol.endswith("FDUSD"):
                seen.add(symbol)
            uid = int(raw["u"])
            fingerprint = tuple(raw[k] for k in ("b", "B", "a", "A"))
            old = ids.get(symbol)
            if old == (uid, fingerprint):
                counts["exact_duplicate_books"] += 1
                continue
            sequence = old is None or uid > old[0]
            if sequence:
                ids[symbol] = uid, fingerprint
            else:
                counts["conflicting_or_regressing_books"] += 1
            record = {"receive_ns": received, "source_line": number, "update_id": uid,
                      "bid": D(raw["b"]), "ask": D(raw["a"]),
                      "bid_quantity": D(raw["B"]), "ask_quantity": D(raw["A"]),
                      "sequence_ok": sequence, "venue": "spot"}
            changes[bisect.bisect_right(cuts, received)][symbol] = record
    active, grids = {}, []
    for bucket in changes[:50]:
        active.update(bucket)
        grids.append(dict(active))
    return grids, seen, counts, start


def evaluate(quote, decision, not_yet_seen=False):
    result = {"valid": False, "supply": False, "reason": "not_observed_before_cutoff" if not_yet_seen else "missing_state"}
    if quote is None:
        return result
    result.update(quote)
    if not quote["sequence_ok"]:
        return {**result, "reason": "conflicting_or_regressing_update"}
    b, a, bq, aq = [quote[k] for k in ("bid", "ask", "bid_quantity", "ask_quantity")]
    if not all(x.is_finite() and x > 0 for x in (b, a, bq, aq)) or b >= a:
        return {**result, "reason": "invalid_book"}
    if not 250_000_000 < decision - quote["receive_ns"] <= 5 * NS:
        return {**result, "reason": "signal_freshness_gate"}
    # Separate cash-flow expressions, with exact multiplication for threshold
    # gates instead of comparing rounded reported basis-point strings.
    gain = a * D("0.9998") - b * D("1.0002")
    stress = a * D("0.9997") - b * D("1.0003")
    forced_loss = b * D("0.0013")
    supply = 8 * (a + b) <= 20000 * (a - b) <= 100 * (a + b) and min(b * bq, a * aq) >= 2000
    return {**result, "valid": True, "supply": supply,
            "spread_bps": 20000 * (a - b) / (a + b), "passive_budget_bps": 10000 * gain / b,
            "double_fee_reserve_budget_bps": 10000 * stress / b,
            "double_adverse_budget_bps": 10000 * stress / b,
            "flat_forced_exit_bps": D(-13), "minimum_touch_fdusd": min(b * bq, a * aq),
            "simplified_required_passive_exit_fraction": forced_loss / (forced_loss + gain) if gain > 0 else None,
            "reason": "spread_and_depth_supply" if supply else "spread_or_depth_gate"}


def compare(record, expected):
    maximum = D(0)
    for key, value in expected.items():
        if value is None:
            assert pd.isna(record[key])
        elif isinstance(value, D):
            difference = abs(D(str(record[key])) - value)
            maximum = max(maximum, difference)
            assert difference < D("1e-18"), (key, record[key], value)
        else:
            assert record[key] == value, (key, record[key], value)
    return maximum


def verify_window(job):
    source, window = job
    grids, symbols, counts, start = independent_source(source)
    assert dict(counts) == window["source_counts"]
    grid_path, fx_path = ROOT / window["grid_path"], ROOT / window["fx_path"]
    assert sha(grid_path) == window["grid_sha256"] and sha(fx_path) == window["fx_sha256"]
    frame, fx = pd.read_parquet(grid_path), pd.read_parquet(fx_path)
    assert len(frame) == len(symbols) * 50 and len(fx) == 50
    indexed = {(r["symbol"], r["decision_ns"]): r for r in frame.to_dict("records")}
    reasons, summaries, maximum = Counter(), [], D(0)
    for symbol in sorted(symbols):
        valid, supply = 0, 0
        for i, grid in enumerate(grids):
            decision = start + (i + 10) * NS
            expected = evaluate(grid.get(symbol), decision, symbol not in grid)
            expected.update(date=source["date"], offset_minutes=source["offset"], symbol=symbol, decision_ns=decision)
            maximum = max(maximum, compare(indexed[(symbol, decision)], expected))
            valid += int(expected["valid"])
            supply += int(expected["supply"])
            reasons[expected["reason"]] += 1
        selected = valid >= 40 and supply >= 30
        summaries.append({"date": source["date"], "offset_minutes": source["offset"], "symbol": symbol,
                          "grid_points": 50, "valid_grids": valid, "supply_grids": supply, "selected": selected,
                          "reason": "requires_native_queue_study" if selected else "insufficient_valid_coverage" if valid < 40 else "insufficient_spread_depth_persistence"})
    for i, record in enumerate(fx.to_dict("records")):
        decision = start + (i + 10) * NS
        evaluated = evaluate(grids[i].get("FDUSDUSDT"), decision)
        expected = {"decision_ns": decision, "base_currency": "FDUSD", "quote_currency": "USDT",
                    "valid": evaluated["valid"], "reason": "valid_fx_quote" if evaluated["valid"] else evaluated["reason"],
                    **{k: evaluated[k] for k in ("receive_ns", "source_line", "update_id", "bid", "ask", "bid_quantity", "ask_quantity") if k in evaluated}}
        maximum = max(maximum, compare(record, expected))
    assert summaries == window["symbol_windows"] and dict(reasons) == window["reasons"]
    return {"date": source["date"], "offset_minutes": source["offset"], "grid_rows": len(frame),
            "source_counts": dict(counts), "symbol_windows": summaries,
            "maximum_numeric_difference": str(maximum), "fx_rows": len(fx)}


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    results = json.loads((OUT / "screen_results.json").read_text())
    impl = json.loads((OUT / "screen_implementation.json").read_text())
    assert sha(OUT / "screen_implementation.json") == results["implementation_sha256"]
    assert sha(OUT / "specification.json") == impl["specification_sha256"]
    for path, digest in impl["code_sha256"].items():
        assert sha(ROOT / path) == digest
    sources = {(r["date"], r["offset"]): r for r in spec["sources"]}
    jobs = [(sources[(w["date"], w["offset_minutes"])], w) for w in results["windows"]]
    verified, counts = [], Counter()
    with ProcessPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(verify_window, job) for job in jobs]
        for task in as_completed(tasks):
            result = task.result()
            verified.append(result)
            counts.update(result["source_counts"])
            print(json.dumps({k: result[k] for k in ("date", "offset_minutes", "grid_rows")}), flush=True)
    verified.sort(key=lambda r: (r["date"], r["offset_minutes"]))
    summaries = [r for w in verified for r in w["symbol_windows"]]
    assert sha(OUT / "symbol_window_supply.parquet") == results["summaries_sha256"]
    assert sha(OUT / "selected.parquet") == results["selected_sha256"]
    assert pd.read_parquet(OUT / "symbol_window_supply.parquet").to_dict("records") == summaries
    selected = [r for r in summaries if r["selected"]]
    assert pd.read_parquet(OUT / "selected.parquet").to_dict("records") == selected
    assert dict(counts) == results["source_counts"] and len(selected) == results["selected_windows"]
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
             "source_files_verified": len(verified), "source_counts": dict(counts),
             "grid_rows_verified": sum(r["grid_rows"] for r in verified), "fx_rows_verified": sum(r["fx_rows"] for r in verified),
             "symbol_windows_verified": len(summaries), "selected_windows_verified": len(selected),
             "maximum_numeric_difference": str(max(D(r["maximum_numeric_difference"]) for r in verified)),
             "results_sha256": sha(OUT / "screen_results.json"), "auditor_sha256": sha(Path(__file__)),
             "scope": "Every source envelope decoded, all native capture clocks and relevant IDs checked, independent causal buckets and Decimal cost/size gates reconciled, all selected windows and separate observed FX quotes verified. No production parsing, budget or selection imports.",
             "economic_implementations": 0, "future_returns_evaluated": False,
             "actual_execution_verified": False, "reliable_edge_established": False}
    with (OUT / "independent_verification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
