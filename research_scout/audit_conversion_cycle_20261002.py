"""Independent native buckets and algebraic three-market cash identities."""

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

from research_scout.prepare_conversion_cycle_20261002 import OUT, ROOT, sha

NS = 10**9
BRIDGES = ("BTC", "ETH", "BNB")


def source_grids(source):
    day, offset = source["date"], source["offset"]
    midnight = calendar.timegm(datetime.strptime(day, "%Y-%m-%d").timetuple()) * NS
    start = midnight + offset * 60 * NS
    cuts = [start + i * NS - 250_000_000 for i in range(10, 60)]
    changes, symbols, ids, counts = [{} for _ in range(51)], set(), {}, Counter()
    last = start - 1
    path = ROOT / source["path"]
    assert source["complete"] and sha(path) == source["compressed_sha256"]
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for number, line in enumerate(stream):
            if not line.strip():
                counts["disconnects"] += 1
                changes[bisect.bisect_right(cuts, last)].update(dict.fromkeys(symbols))
                ids.clear()
                continue
            stamp, payload = line.strip().split(" ", 1)
            clock = datetime.fromisoformat(stamp[:19])
            received = midnight + (clock.hour * 3600 + clock.minute * 60 + clock.second) * NS
            received += int(stamp[20:-1].ljust(9, "0")) if "." in stamp else 0
            assert stamp[:10] == day and start <= received < start + 60 * NS and received >= last
            last = received
            counts["native_messages"] += 1
            envelope = json.loads(payload)
            if envelope.get("stream", "").rsplit("@", 1)[-1] != "bookTicker":
                continue
            raw = envelope["data"]
            symbol = raw["s"]
            if not symbol.isalnum() or not symbol.endswith(("USDT", *BRIDGES)):
                continue
            symbols.add(symbol)
            counts["relevant_book_messages"] += 1
            uid, fingerprint = int(raw["u"]), tuple(raw[k] for k in ("b", "B", "a", "A"))
            previous = ids.get(symbol)
            if previous == (uid, fingerprint):
                counts["exact_duplicate_books"] += 1
                continue
            sequence = previous is None or uid > previous[0]
            if sequence:
                ids[symbol] = uid, fingerprint
            else:
                counts["conflicting_or_regressing_books"] += 1
            changes[bisect.bisect_right(cuts, received)][symbol] = {
                "bid": raw["b"], "ask": raw["a"], "bid_quantity": raw["B"], "ask_quantity": raw["A"],
                "sequence_ok": sequence, "receive_ns": received, "source_line": number,
                "update_id": uid, "venue": "spot"}
    active, grids = {}, []
    for change in changes[:50]:
        active.update(change)
        grids.append(dict(active))
    return start, grids, symbols, counts


def gate(quote, decision):
    if quote is None:
        return "missing_book"
    if not quote["sequence_ok"]:
        return "conflicting_or_regressing_id"
    b, a, bq, aq = [D(quote[k]) for k in ("bid", "ask", "bid_quantity", "ask_quantity")]
    if not all(x.is_finite() and x > 0 for x in (b, a, bq, aq)) or b >= a:
        return "invalid_values"
    if not 250_000_000 < decision - quote["receive_ns"] <= NS:
        return "capture_freshness_gate"
    return None


def algebra(books, direction, fee, adverse):
    direct, cross, bridge = books
    if direction == "base_first":
        d, c, b = D(direct["ask"]), D(cross["bid"]), D(bridge["bid"])
        final = D(200) * c * b * (1 - fee)**3 * (1 - adverse)**2 / (d * (1 + adverse))
        q0 = D(200) / (d * (1 + adverse))
        q1 = q0 * (1 - fee)
        q2 = q1 * c * (1 - adverse) * (1 - fee)
        depths = [D(direct["ask_quantity"]), D(cross["bid_quantity"]), D(bridge["bid_quantity"])]
    else:
        d, c, b = D(direct["bid"]), D(cross["ask"]), D(bridge["ask"])
        final = D(200) * d * (1 - fee)**3 * (1 - adverse) / (b * c * (1 + adverse)**2)
        q0 = D(200) / (b * (1 + adverse))
        q1 = q0 * (1 - fee) / (c * (1 + adverse))
        q2 = q1 * (1 - fee)
        depths = [D(bridge["ask_quantity"]), D(cross["ask_quantity"]), D(direct["bid_quantity"])]
    return final, all(10 * q <= depth for q, depth in zip((q0, q1, q2), depths, strict=True))


def expected_route(books, decision, direction):
    for number, quote in enumerate(books):
        error = gate(quote, decision)
        if error:
            return {"valid_books": False, "supply": False, "reason": f"leg{number}_{error}"}
    final, depth = algebra(books, direction, D(".001"), D(".0001"))
    gross, _ = algebra(books, direction, D(0), D(0))
    fees, _ = algebra(books, direction, D(".002"), D(".0001"))
    adverse, _ = algebra(books, direction, D(".001"), D(".0002"))
    price = final > D("200.04")
    return {"valid_books": True, "supply": depth and price, "depth_gate": depth, "price_gate": price,
            "base_final_usdt": final, "base_budget_bps": (final - 200) * 50,
            "gross_budget_bps": (gross - 200) * 50,
            "double_fee_budget_bps": (fees - 200) * 50, "double_adverse_budget_bps": (adverse - 200) * 50,
            "reason": "requires_sequential_execution_study" if depth and price else "depth_gate" if not depth else "net_budget_gate"}


def check_row(actual, expected):
    maximum = D(0)
    for key, value in expected.items():
        if isinstance(value, D):
            error = abs(D(str(actual[key])) - value)
            maximum = max(maximum, error)
            assert error < D("1e-18"), (key, actual[key], value)
        else:
            assert actual[key] == value, (key, actual[key], value)
    for key, value in actual.items():
        if key not in expected:
            assert pd.isna(value), (key, value)
    return maximum


def verify(job):
    source, window = job
    start, grids, symbols, counts = source_grids(source)
    assert dict(counts) == window["source_counts"]
    cycles = []
    for bridge in BRIDGES:
        if bridge + "USDT" not in symbols:
            continue
        for cross in sorted(s for s in symbols if s.endswith(bridge)):
            base = cross[:-len(bridge)]
            if base and base not in ("USDT", bridge) and base + "USDT" in symbols:
                cycles.append((base, bridge, (base + "USDT", cross, bridge + "USDT")))
    assert len(cycles) == window["cycles"]
    needed = sorted({symbol for _, _, path in cycles for symbol in path})
    for name in ("quotes", "routes"):
        assert sha(ROOT / window[name + "_path"]) == window[name + "_sha256"]
    quotes = pd.read_parquet(ROOT / window["quotes_path"]).to_dict("records")
    assert len(quotes) == len(needed) * 50 == window["quote_rows"]
    position = 0
    for i, grid in enumerate(grids):
        decision = start + (i + 10) * NS
        for symbol in needed:
            expected = {"symbol": symbol, "decision_ns": decision, **(grid.get(symbol) or {})}
            check_row(quotes[position], expected)
            position += 1
    routes = pd.read_parquet(ROOT / window["routes_path"]).to_dict("records")
    assert len(routes) == len(cycles) * 100 == window["route_rows"]
    reasons, selected, best, maximum = Counter(), [], None, D(0)
    position, valid, supplies = 0, 0, 0
    for base, bridge, path in cycles:
        for direction in ("base_first", "bridge_first"):
            previous, last_selected = False, start - 30 * NS
            for i, grid in enumerate(grids):
                decision = start + (i + 10) * NS
                expected = expected_route([grid.get(symbol) for symbol in path], decision, direction)
                confirmed = previous and expected["supply"]
                chosen = confirmed and decision - last_selected >= 30 * NS
                if chosen:
                    last_selected = decision
                expected.update(date=source["date"], offset_minutes=source["offset"],
                                base=base, bridge=bridge, direction=direction, decision_ns=decision,
                                confirmed=confirmed, selected=chosen)
                maximum = max(maximum, check_row(routes[position], expected))
                if chosen:
                    selected.append(routes[position])
                valid += int(expected["valid_books"])
                supplies += int(expected["supply"])
                reasons[expected["reason"]] += 1
                if expected.get("depth_gate"):
                    value = expected["base_budget_bps"]
                    best = value if best is None else max(value, best)
                previous = expected["supply"]
                position += 1
    assert valid == window["valid_books"] and supplies == window["supply_rows"]
    assert dict(reasons) == window["reasons"]
    # Saved selected records contain no missing optional fields when valid.
    assert selected == window["selected"]
    if best is None:
        assert window["best_depth_eligible_budget_bps"] is None
    else:
        assert abs(best - D(window["best_depth_eligible_budget_bps"])) < D("1e-18")
    return {"date": source["date"], "offset": source["offset"], "source_counts": dict(counts),
            "quote_rows": len(quotes), "route_rows": len(routes), "selected_events": len(selected),
            "maximum_numeric_difference": str(maximum)}


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    results = json.loads((OUT / "screen_results.json").read_text())
    impl = json.loads((OUT / "screen_implementation.json").read_text())
    assert results["implementation_sha256"] == sha(OUT / "screen_implementation.json")
    assert impl["specification_sha256"] == sha(OUT / "specification.json")
    for path, digest in impl["code_sha256"].items():
        assert sha(ROOT / path) == digest
    sources = {(s["date"], s["offset"]): s for s in spec["sources"]}
    jobs = [(sources[(w["date"], w["offset"])], w) for w in results["windows"]]
    assert len(jobs) == len(sources) == 60
    verified, counts = [], Counter()
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(verify, job) for job in jobs]
        for future in as_completed(futures):
            row = future.result()
            verified.append(row)
            counts.update(row["source_counts"])
            print(json.dumps({k: row[k] for k in ("date", "offset", "route_rows", "selected_events")}), flush=True)
    assert dict(counts) == results["source_counts"]
    assert sum(r["selected_events"] for r in verified) == results["selected_events"]
    assert sha(OUT / "selected.parquet") == results["selected_sha256"]
    assert pd.read_parquet(OUT / "selected.parquet").to_dict("records") == [r for w in results["windows"] for r in w["selected"]]
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
             "source_files_verified": len(verified), "source_counts": dict(counts),
             "route_rows_verified": sum(r["route_rows"] for r in verified),
             "quote_rows_verified": sum(r["quote_rows"] for r in verified),
             "selected_events_verified": sum(r["selected_events"] for r in verified),
             "maximum_numeric_difference": str(max(D(r["maximum_numeric_difference"]) for r in verified)),
             "results_sha256": sha(OUT / "screen_results.json"), "auditor_sha256": sha(Path(__file__)),
             "scope": "Independent full native-envelope parser, exact capture buckets and quote states, all route universes/gates, direct algebraic product identities and separate depth quantities, all confirmations/cooldowns and aggregate selection. No production signal/price/parser imports.",
             "economic_implementations": 0, "future_returns_evaluated": False,
             "actual_execution_verified": False, "reliable_edge_established": False}
    with (OUT / "independent_verification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
