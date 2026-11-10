"""Verify expanded source clocks and every screen flag with independent buckets."""

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

from research_scout.audit_spot_perp_20261002 import evaluate
from research_scout.prepare_spot_perp_clock_20261002 import OUT, ROOT, sha

NS = 1_000_000_000


def reconstruct(path, day, derivative, offset):
    day_dt = datetime.strptime(day, "%Y-%m-%d")
    day_seconds = calendar.timegm(day_dt.timetuple())
    start = (day_seconds + offset * 60) * NS
    cutoffs = [start + second * NS - 250_000_000 for second in range(60)]
    updates = [{} for _ in range(61)]
    previous_ids, symbols, counts = {}, set(), Counter()
    last = start - 1
    with gzip.open(path, "rt", encoding="utf-8") as source:
        for number, line in enumerate(source):
            if not line.strip():
                counts["disconnects"] += 1
                bucket = bisect.bisect_right(cutoffs, last)
                for symbol in symbols:
                    updates[bucket][symbol] = None
                previous_ids.clear()
                continue
            stamp, text = line.strip().split(" ", 1)
            assert stamp[:10] == day
            whole, fractional = stamp[:-1].split(".") if "." in stamp else (stamp[:-1], "0")
            parsed = datetime.fromisoformat(whole)
            # Integer whole seconds and a separate fraction preserve the native
            # seventh decimal place instead of rounding through a float epoch.
            seconds = day_seconds + (parsed - day_dt).seconds
            received = seconds * NS + int(fractional.ljust(9, "0"))
            assert start <= received < start + 60 * NS and last <= received
            last = received
            counts["native_messages"] += 1
            message = json.loads(text)
            if message.get("stream", "").rsplit("@", 1)[-1] != "bookTicker":
                continue
            counts["book_messages"] += 1
            raw = message["data"]
            symbol = raw["s"]
            if not symbol.endswith("USDT") or not symbol.isalnum():
                continue
            symbols.add(symbol)
            update_id = int(raw["u"])
            fingerprint = (raw["b"], raw["B"], raw["a"], raw["A"])
            if derivative:
                fingerprint += (str(raw["T"]), str(raw["E"]))
            previous = previous_ids.get(symbol)
            if previous == (update_id, fingerprint):
                counts["exact_duplicate_books"] += 1
                continue
            ordered = previous is None or update_id > previous[0]
            if ordered:
                previous_ids[symbol] = update_id, fingerprint
            else:
                counts["conflicting_or_regressing_books"] += 1
            row = (received, number, update_id, D(raw["b"]), D(raw["a"]), D(raw["B"]), D(raw["A"]),
                   ordered, int(raw["T"]) * 1_000_000 if derivative else None,
                   int(raw["E"]) * 1_000_000 if derivative else None)
            updates[bisect.bisect_right(cutoffs, received)][symbol] = row
    states, grids = {}, []
    for bucket in updates[:60]:
        states.update(bucket)
        grids.append(dict(states))
    return grids, symbols, counts, start


def verify_window(job):
    window, sources = job
    day, offset = window["date"], window["offset_minutes"]
    rebuilt, counts = {}, Counter()
    for venue in ("spot", "perpetual"):
        source = sources[venue]
        path = ROOT / source["path"]
        assert source["complete"] and sha(path) == source["compressed_sha256"]
        rebuilt[venue] = reconstruct(path, day, venue == "perpetual", offset)
        counts.update({venue + "_" + key: value for key, value in rebuilt[venue][2].items()})
    spot, spot_symbols, _, start = rebuilt["spot"]
    perp, perp_symbols, _, _ = rebuilt["perpetual"]
    path = ROOT / window["path"]
    assert sha(path) == window["sha256"]
    frame = pd.read_parquet(path)
    assert len(frame) == len(perp_symbols) * 50
    stored = {(r["symbol"], r["second"]): r for r in frame.to_dict("records")}
    assert len(stored) == len(frame)
    selected, reasons, raw_eligible = [], Counter(), 0
    maximum_difference = D(0)
    for symbol in sorted(perp_symbols):
        previous, already_selected = None, False
        for second in range(10, 60):
            wanted, label = evaluate(spot, perp, symbol in spot_symbols, start, symbol, second)
            chosen = False
            if (wanted["raw_eligible"] and previous and previous["raw_eligible"]
                    and wanted["direction"] == previous["direction"]):
                chosen = not already_selected
                already_selected = True
                label = "selected_for_native_execution_review" if chosen else "one_event_per_symbol_date"
            wanted.update(reason=label, selected=chosen, date=day, symbol=symbol,
                          second=second, offset_minutes=offset, decision_ns=start + second * NS)
            record = stored[(symbol, second)]
            for field, expected in wanted.items():
                if isinstance(expected, D):
                    difference = abs(expected - D(str(record[field])))
                    maximum_difference = max(maximum_difference, difference)
                    assert difference < D("1e-10"), (day, offset, symbol, second, field, difference)
                else:
                    assert record[field] == expected, (day, offset, symbol, second, field, record[field], expected)
            previous = wanted
            reasons[label] += 1
            raw_eligible += int(wanted["raw_eligible"])
            if chosen:
                selected.append((day, offset, symbol, second))
    assert dict(reasons) == window["reasons"]
    assert dict(counts) == window["source_counts"]
    assert len(selected) == window["selected_events"]
    assert raw_eligible == window["raw_eligible_grids"]
    assert len(spot_symbols) == window["spot_symbols"] and len(perp_symbols) == window["perpetual_symbols"]
    return {"date": day, "offset_minutes": offset, "grid_rows": len(frame),
            "selected": selected, "source_counts": dict(counts), "reasons": dict(reasons),
            "raw_eligible_grids": raw_eligible, "maximum_numeric_difference": str(maximum_difference)}


def main():
    implementation = json.loads((OUT / "screen_implementation.json").read_text())
    results = json.loads((OUT / "screen_results.json").read_text())
    assert sha(OUT / "screen_implementation.json") == results["implementation_sha256"]
    for key, path in (
        ("manifest_sha256", OUT / "source_manifest.json"),
        ("specification_sha256", OUT / "specification.json"),
        ("reader_sha256", ROOT / "research/spot_perp_clock_supply.py"),
        ("original_signal_module_sha256", ROOT / "research/spot_perp_supply.py"),
        ("runner_sha256", ROOT / "research_scout/screen_spot_perp_clock_20261002.py"),
    ):
        assert sha(path) == implementation[key]
    parent_path = ROOT / "research_scout/spot_perp_hft_20261002/independent_verification.json"
    parent = json.loads(parent_path.read_text())
    parent_auditor = ROOT / "research_scout/audit_spot_perp_20261002.py"
    assert parent["verified"] and sha(parent_auditor) == parent["auditor_sha256"]
    sources = {(r["date"], r["offset"], r["venue"]): r
               for r in json.loads((OUT / "source_manifest.json").read_text())["files"]}
    jobs = [(window, {venue: sources[(window["date"], window["offset_minutes"], venue)]
                     for venue in ("spot", "perpetual")}) for window in results["windows"]]
    windows, counts, reasons = [], Counter(), Counter()
    with ProcessPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(verify_window, job) for job in jobs]
        for task in as_completed(tasks):
            window = task.result()
            windows.append(window)
            counts.update(window["source_counts"])
            reasons.update(window["reasons"])
            print(json.dumps({k: window[k] for k in ("date", "offset_minutes", "grid_rows", "raw_eligible_grids")}), flush=True)
    windows.sort(key=lambda w: (w["date"], w["offset_minutes"]))
    selected = [tuple(row) for window in windows for row in window["selected"]]
    assert sha(OUT / "selected.parquet") == results["selected_sha256"]
    cohort = pd.read_parquet(OUT / "selected.parquet")
    assert list(cohort[["date", "offset_minutes", "symbol", "second"]].itertuples(index=False, name=None)) == selected
    assert len(selected) == results["selected_events"]
    assert dict(counts) == results["source_counts"] and dict(reasons) == results["reasons"]
    assert sum(w["grid_rows"] for w in windows) == results["grid_rows"]
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
             "source_files_verified": 2 * len(windows), "grid_decisions_verified": results["grid_rows"],
             "selected_events_verified": len(selected), "source_counts": dict(counts),
             "maximum_numeric_difference": str(max(D(w["maximum_numeric_difference"]) for w in windows)),
             "results_sha256": sha(OUT / "screen_results.json"), "auditor_sha256": sha(Path(__file__)),
             "independent_formula_auditor_sha256": sha(parent_auditor),
             "scope": "All expanded native source hashes, exact capture/event clocks, independently bucketed quote grids, historical reference ratios, costs, gates and selected candidates reconciled. Imports independent formula audit only, no production parser or signal functions.",
             "economic_implementations": 0, "future_returns_evaluated": False,
             "actual_execution_verified": False, "reliable_edge_established": False}
    with (OUT / "independent_verification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
