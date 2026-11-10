"""Independent native-state, signal, conditional execution and cash checks."""

import gzip
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"research_scout/post_funding_hft_20261002"
RUN = OUT/"replay_v1"
SOURCE = ROOT/"research_scout/single_funding_hft_20261002"
NS = 1_000_000_000
COUNTS = Counter()
MAX_ERROR = D(0)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def equal(a, b):
    global MAX_ERROR
    delta = abs(D(str(a))-D(str(b)))
    MAX_ERROR = max(MAX_ERROR, delta)
    assert delta < D("1e-9"), (a, b)


def stamp(value):
    whole, fraction = value.rstrip("Z").split(".")
    return int(datetime.fromisoformat(whole).replace(tzinfo=UTC).timestamp())*NS+int(fraction.ljust(9, "0"))


def sources(item):
    path = ROOT/item["path"]
    assert sha(path) == item["compressed_sha256"]
    raw = gzip.decompress(path.read_bytes())
    assert hashlib.sha256(raw).hexdigest() == item["decoded_sha256"]
    books, tickers = {s: [] for s in item["symbols"]}, {s: [] for s in item["symbols"]}
    levels, ids, fields, metadata = {}, {}, {}, {}
    previous = -1
    for index, line in enumerate(raw.decode().splitlines(), 1):
        if not line.strip():
            for symbol in books:
                books[symbol].append({"cap": previous, "id": index, "ok": False, "cts": None})
                tickers[symbol].append({"cap": previous, "id": index, "ok": False, "next": None})
            levels, ids, fields, metadata = {}, {}, {}, {}
            COUNTS["disconnects"] += 1
            continue
        recorded, payload = line.split(" ", 1)
        cap = stamp(recorded)
        assert cap >= previous
        previous = cap
        event = json.loads(payload)
        symbol = event["topic"].rsplit(".", 1)[1]
        body, pub = event["data"], int(event["ts"])*1_000_000
        snapshot = event["type"] == "snapshot"
        assert symbol in books and event["type"] in ("snapshot", "delta")
        COUNTS["native_messages"] += 1
        if event["topic"].startswith("tickers."):
            old = metadata.get(symbol)
            seq = int(event["cs"])
            ordered = old is None or seq > old[0] or (seq == old[0] and body == old[1])
            if snapshot or old is None or not ordered:
                fields[symbol] = {}
            if snapshot or ordered:
                if "nextFundingTime" in body:
                    fields[symbol] = {"next": body["nextFundingTime"], "seed": index}
            metadata[symbol] = (seq, body)
            tickers[symbol].append({"cap": cap, "pub": pub, "id": index, "ok": snapshot or ordered,
                                    "next": fields[symbol].get("next"), "seed": fields[symbol].get("seed")})
            COUNTS["ticker_messages"] += 1
            continue
        assert event["topic"] == "orderbook.1."+symbol and body["s"] == symbol
        cts = int(event["cts"])*1_000_000 if "cts" in event else None
        update, sequence = int(body["u"]), int(body["seq"])
        old = ids.get(symbol)
        prior_levels = dict(levels.get(symbol, {}))
        good = -1_000_000 <= cap-pub <= 5*NS
        if cts is not None:
            good &= -1_000_000 <= cap-cts <= 5*NS and cts <= pub+1_000_000
        if old and not (snapshot and update == 1):
            good &= sequence >= old[1] and update >= old[0] and (snapshot or update == old[0]+1)
        if snapshot or not good:
            levels[symbol] = {}
        else:
            levels.setdefault(symbol, {})
        for side in ("b", "a"):
            values = [(D(p), D(q)) for p, q in body[side]]
            assert all(p.is_finite() and q.is_finite() and p > 0 and q >= 0 for p, q in values)
            positive = [(p, q) for p, q in values if q > 0]
            assert len(positive) <= 1
            if positive:
                levels[symbol][side] = (*positive[0], index)
            elif side in levels[symbol] and any(p == levels[symbol][side][0] and q == 0 for p, q in values):
                levels[symbol].pop(side)
        if old and snapshot and update == old[0] and update != 1 and all(k in prior_levels for k in ("a", "b")):
            good &= all(levels[symbol].get(k, ())[:2] == prior_levels[k][:2] for k in ("a", "b"))
        complete = all(k in levels[symbol] for k in ("a", "b"))
        uncrossed = not complete or levels[symbol]["b"][0] < levels[symbol]["a"][0]
        good &= uncrossed
        row = {"cap": cap, "pub": pub, "cts": cts, "id": index, "ok": good and complete, **levels[symbol]}
        books[symbol].append(row)
        if not good:
            levels[symbol] = {}
        ids[symbol] = (update, sequence)
        COUNTS["book_messages"] += 1
    return books, tickers


def prior(rows, cutoff):
    earlier = [r for r in rows if r["cap"] < cutoff]
    return earlier[-1] if earlier else None


def verify_plan(event, plan, books, tickers, capital):
    target, cutoff = event["settlement_ns"], event["settlement_ns"]+9_750_000_000
    b, t = prior(books, cutoff), prior(tickers, cutoff)
    eligible, quantity = False, None
    if b is None or not b["ok"] or b["cts"] is None or not all(0 < cutoff-b[k] <= 5*NS for k in ("cap", "pub", "cts")):
        reason = "missing_or_invalid_native_book"
    else:
        assert plan["book_source_index"] == b["id"]
        if t is None or not t["ok"] or not all(0 < cutoff-t[k] <= 5*NS for k in ("cap", "pub")) or not -1_000_000 <= t["cap"]-t["pub"] <= 5*NS:
            reason = "missing_stale_or_invalid_native_ticker"
        else:
            assert plan["ticker_source_index"] == t["id"]
            if t["next"] is None:
                reason = "funding_cycle_advance_unobserved"
            else:
                future = int(t["next"])*1_000_000
                assert future == plan["next_funding_ns"] and t["seed"] == plan["funding_time_source_index"]
                if future <= target+35*NS:
                    reason = "funding_cycle_not_safely_advanced"
                else:
                    bid, ask, bq, aq = b["b"][0], b["a"][0], b["b"][1], b["a"][1]
                    spread = 20000*(ask-bid)/(ask+bid)
                    quantity = int(min(D(200)/ask, bq/10, aq/10)//10)*10
                    equal(spread, plan["spread_bps"])
                    assert plan["quantity"] == quantity
                    for key, value in (("bid", bid), ("ask", ask), ("bid_quantity", bq), ("ask_quantity", aq)):
                        equal(plan[key], value)
                    reason = "spread_above_frozen_gate" if spread > 20 else "insufficient_displayed_size" if quantity*bid < 100 else "eligible"
                    if reason == "eligible":
                        reserve = quantity*ask*D("1.0014")
                        if capital[event["date"]]+reserve > 10000:
                            reason = "insufficient_fully_collateralized_capital"
                        else:
                            capital[event["date"]] += reserve
                            equal(plan["capital_reserved"], reserve)
                            eligible = True
    assert plan["reason"] == reason and plan["eligible"] == eligible
    COUNTS["signal_plans_verified"] += 1


def continuity(tickers, cutoff, end):
    previous = prior(tickers, cutoff)
    for row in [r for r in tickers if cutoff <= r["cap"] <= end+5*NS]:
        if not row["ok"] or previous is None or row["cap"]-previous["cap"] > 5*NS:
            return "unknown_ticker_continuity_after_submission"
        if row["next"] is None or int(row["next"])*1_000_000 <= end:
            return "unknown_funding_cash_after_submission"
        previous = row
        if row["cap"] >= end:
            return None
    return "ticker_continuity_not_bracketed"


def compatible(books, arrival, radius, quantity, buy):
    previous = -1
    for row in books:
        if row["cts"] is None:
            if arrival-6*NS <= row["cap"] <= arrival+6*NS:
                return None
        else:
            if row["cts"] < previous:
                return None
            previous = row["cts"]
    physical = [r for r in books if r["cts"] is not None]
    earlier = [r["cts"] for r in physical if r["cts"] < arrival-radius]
    if not earlier or not any(r["cts"] > arrival+radius for r in physical):
        return None
    predecessor = max(earlier)
    possible = [r for r in physical if predecessor <= r["cts"] <= arrival+radius]
    side = "a" if buy else "b"
    if any(not r["ok"] or r["cts"] < arrival-radius-5*NS or not -1_000_000 <= r["cap"]-r["cts"] <= 5*NS or r[side][1] < quantity for r in possible):
        return None
    COUNTS["compatible_physical_paths_verified"] += 1
    return [r[side][0] for r in possible], [r["id"] for r in possible]


def verify_trade(event, plan, row, books, tickers, scenario):
    target = event["settlement_ns"]
    delay, radius = scenario["latency_seconds"]*NS, scenario["clock_ms"]*1_000_000
    entering, leaving = target+10*NS+delay, target+25*NS+delay
    long = (D(str(event["bybit_funding_rate"])) > 0) == (row["rule"] == "unwind_continuation")
    quantity = plan["quantity"]
    assert row["long"] == long and row["quantity"] == quantity
    assert (row["entry_arrival_ns"], row["exit_arrival_ns"], row["inventory_upper_ns"]) == (entering, leaving, 15*NS+2*radius)
    error = continuity(tickers, plan["signal_cutoff_ns"], leaving+radius)
    if error:
        assert not row["known"] and row["reason"] == error
        COUNTS["submitted_unknowns_verified"] += 1
        return None
    entry = compatible(books, entering, radius, quantity, long)
    exit_prices = compatible(books, leaving, radius, quantity, not long)
    if entry is None or exit_prices is None:
        assert not row["known"] and row["reason"] == "unknown_entry_or_exit_execution"
        COUNTS["submitted_unknowns_verified"] += 1
        return None
    assert row["known"] and row["reason"] == "conditional_taker_execution"
    for name, values in (("entry", entry), ("exit", exit_prices)):
        assert row[name]["source_indices"] == values[1]
        equal(row[name]["price_min"], min(values[0]))
        equal(row[name]["price_max"], max(values[0]))
    possibilities = []
    for start in (min(entry[0]), max(entry[0])):
        for end in (min(exit_prices[0]), max(exit_prices[0])):
            gross = quantity*(end-start)*(1 if long else -1)
            fees = quantity*(start+end)*D(scenario["taker_bps"])/10000
            adverse = quantity*(start+end)*D(scenario["adverse_bps"])/10000
            possibilities.append({"entry_price": start, "exit_price": end, "gross": gross, "fees": fees,
                                  "adverse": adverse, "net": gross-fees-adverse})
    bounds = min(possibilities, key=lambda p: p["net"]), max(possibilities, key=lambda p: p["net"])
    for name, expected in zip(("lower", "upper"), bounds, strict=True):
        for key, value in expected.items():
            equal(row[name][key], value)
    COUNTS["cash_rectangles_verified"] += 1
    return bounds[0]["net"], bounds[1]["net"]


def main():
    verification_path = RUN/"independent_verification.json"
    assert not verification_path.exists()
    freeze = json.loads((RUN/"implementation.json").read_text())
    for path, expected in freeze["code_sha256"].items():
        assert sha(ROOT/path) == expected
    assert sha(SOURCE/"native_manifest.json") == freeze["source_manifest_sha256"]
    spec = json.loads((OUT/"specification.json").read_text())
    assert sha(ROOT/spec["events_path"]) == spec["events_sha256"]
    events = pd.read_parquet(ROOT/spec["events_path"]).sort_values(["date", "hour", "symbol"]).to_dict("records")
    event_map = {(r["date"], r["hour"], r["symbol"]): r for r in events}
    manifest = json.loads((SOURCE/"native_manifest.json").read_text())
    windows = {(s["date"], s["hour"]): sources(s) for s in manifest["files"]}
    plans = json.loads((RUN/"plans.json").read_text())
    plan_map = {(r["date"], r["hour"], r["symbol"]): r for r in plans["events"]}
    capital = Counter()
    for event in events:
        key = event["date"], event["hour"], event["symbol"]
        books, tickers = windows[key[:2]]
        verify_plan(event, plan_map[key], books[key[2]], tickers[key[2]], capital)
    result = json.loads((RUN/"results.json").read_text())
    assert sha(RUN/"plans.json") == result["plans_sha256"]
    for summary in result["scenarios"]:
        path = RUN/summary["ledger"]
        assert sha(path) == summary["ledger_sha256"]
        rows = json.loads(path.read_text())["events"]
        assert len(rows) == 90
        scenario = next(s for s in spec["scenarios"] if s["name"] == summary["scenario"])
        lower, upper, unknown, submitted, known = D(0), D(0), 0, 0, 0
        daily = {d["date"]: [D(0), D(0), 0] for d in summary["by_date"]}
        for row in rows:
            key = row["date"], row["hour"], row["symbol"]
            plan = plan_map[key]
            assert row["submitted"] == plan["eligible"]
            values = None
            if row["submitted"]:
                books, tickers = windows[key[:2]]
                values = verify_trade(event_map[key], plan, row, books[key[2]], tickers[key[2]], scenario)
                submitted += 1
                unknown += values is None
                known += values is not None
                daily[row["date"]][2] += values is None
            else:
                assert row["known"] and row["reason"] == plan["reason"]
            if values is not None:
                lower += values[0]
                upper += values[1]
                daily[row["date"]][0] += values[0]
                daily[row["date"]][1] += values[1]
            COUNTS["ledger_rows_verified"] += 1
        assert (summary["submitted"], summary["unknown_events"], summary["known_submitted"]) == (submitted, unknown, known)
        assert summary["complete"] == (unknown == 0)
        equal(summary["known_component_lower"], lower)
        equal(summary["known_component_upper"], upper)
        if unknown:
            assert summary["net_lower"] is None and summary["net_upper"] is None
        for row in summary["by_date"]:
            expected = daily[row["date"]]
            assert row["complete"] == (expected[2] == 0) and row["unknown"] == expected[2]
            equal(row["known_component_lower"], expected[0])
            equal(row["known_component_upper"], expected[1])
            if not row["complete"]:
                assert row["net_lower"] is None and row["net_upper"] is None
            else:
                equal(row["net_lower"], expected[0])
                equal(row["net_upper"], expected[1])
        COUNTS["scenario_aggregates_verified"] += 1
    verification = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
                    "auditor_sha256": sha(Path(__file__)), "results_sha256": sha(RUN/"results.json"),
                    "counts": dict(COUNTS), "maximum_numeric_difference": str(MAX_ERROR),
                    "scope": "Independent raw native level-one/ticker reconstruction, all signal gates, clock/depth bounds, all submitted unknowns, Decimal cash rectangles and date/scenario totals. No production replay functions imported.",
                    "actual_execution_verified": False, "historical_contract_permissions_verified": False,
                    "funding_payment_assumed": False, "reliable_edge_established": False}
    verification_path.write_text(json.dumps(verification, indent=2)+"\n")
    print(json.dumps(verification), flush=True)


if __name__ == "__main__":
    main()
