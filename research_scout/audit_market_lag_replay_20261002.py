"""Independent full native-clock, FOK, unknown-inventory and cash audit."""

import calendar
import gzip
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_FLOOR
from decimal import Decimal as D
from pathlib import Path

import pandas as pd

from research_scout.prepare_market_lag_replay_20261002 import FLOW, OUT, ROOT, TARGET, sha

NS = 10**9


def compare(actual, expected):
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys(), (actual.keys(), expected.keys())
        for key, value in expected.items():
            compare(actual[key], value)
    elif isinstance(expected, list):
        assert len(actual) == len(expected)
        for a, b in zip(actual, expected, strict=True):
            compare(a, b)
    elif isinstance(expected, D):
        assert D(str(actual)) == expected, (actual, expected)
    else:
        assert actual == expected, (actual, expected)


def raw_source(source, tick):
    books, marks, counts = [], [], Counter()
    last_receive, last_id, last_match, decoded = -1, -1, -1, 0
    start = calendar.timegm(datetime.strptime(source["date"], "%Y-%m-%d").timetuple()) * NS + source["offset"] * 60 * NS
    assert source["complete"] and sha(ROOT / source["path"]) == source["compressed_sha256"]
    with gzip.open(ROOT / source["path"], "rt", encoding="utf-8", newline="") as stream:
        for number, line in enumerate(stream):
            decoded += len(line.encode("utf-8"))
            assert line.strip(), "Observed cohort must have no unhandled disconnect"
            timestamp, encoded = line.strip().split(" ", 1)
            whole, fraction = timestamp[:-1].split(".")
            seconds = calendar.timegm(datetime.strptime(whole, "%Y-%m-%dT%H:%M:%S").timetuple())
            receive = seconds * NS + int(fraction.ljust(9, "0"))
            assert receive >= last_receive and start <= receive < start + 120 * NS
            last_receive = receive
            message = json.loads(encoded)
            raw = message["data"]
            assert raw["s"] == source["symbol"]
            counts["native_messages"] += 1
            if "@markPrice" in message["stream"]:
                assert type(raw["E"]) is int and type(raw["T"]) is int
                event, mark = raw["E"] * 10**6, D(raw["p"])
                assert event <= receive + 10**6 and mark.is_finite() and mark > 0
                marks.append({"receive_ns": receive, "publication_ns": event,
                              "next_funding_ns": raw["T"] * 10**6, "mark_price": mark,
                              "source_line": number, "valid": True})
                counts["mark_messages"] += 1
                continue
            assert message["stream"] == source["symbol"].lower() + "@bookTicker"
            assert all(type(raw[k]) is int for k in ("u", "T", "E"))
            uid, match, public = raw["u"], raw["T"] * 10**6, raw["E"] * 10**6
            assert uid > last_id and match >= last_match, "Actual cohort must have strictly increasing IDs and monotone T"
            last_id, last_match = uid, match
            bid, ask, bq, aq = [D(raw[k]) for k in ("b", "a", "B", "A")]
            assert all(v.is_finite() and v > 0 for v in (bid, ask, bq, aq)) and bid < ask
            assert bid % tick == ask % tick == 0
            assert max(match, public) <= receive + 10**6 and match <= public + 10**6
            books.append({"receive_ns": receive, "transaction_ns": match, "publication_ns": public,
                          "source_line": number, "update_id": uid, "valid": True,
                          "bid": bid, "ask": ask, "bid_quantity": bq, "ask_quantity": aq})
            counts["book_messages"] += 1
    assert decoded == source["decoded_bytes"]
    return books, marks, counts


def envelope(books, target, radius, is_buy):
    earlier = [r["transaction_ns"] for r in books if r["transaction_ns"] < target - radius]
    assert earlier
    predecessor = max(earlier)
    indices = [i for i, r in enumerate(books) if predecessor <= r["transaction_ns"] <= target + radius]
    first, stop = min(indices), max(indices) + 1
    assert stop < len(books)
    side = "ask" if is_buy else "bid"
    prices, sizes = [books[i][side] for i in indices], [books[i][side + "_quantity"] for i in indices]
    return {"known": True, "arrival_ns": target, "radius_ns": radius,
            "reason": "conditional_native_matching_clock", "first_index": first, "stop_index": stop,
            "successor_ns": books[stop]["transaction_ns"], "source_lines": [books[i]["source_line"] for i in indices],
            "prices": prices, "sizes": sizes, "price_lower": min(prices), "price_upper": max(prices),
            "minimum_touch_quantity": min(sizes)}


def check_order(books, event, intent, scenario):
    delay, radius = scenario["delay_ms"] * 10**6, scenario["clock_ms"] * 10**6
    arrival = event["decision_ns"] + 50_000_000 + delay
    departure = event["decision_ns"] + 15 * NS + 100_000_000 + 3 * delay
    long, quantity = intent["long"], intent["quantity"]
    entry, exit_quotes = envelope(books, arrival, radius, long), envelope(books, departure, radius, not long)
    can_cross = [(p <= intent["limit"] if long else p >= intent["limit"]) for p in entry["prices"]]
    outcome = "no_fill" if not any(can_cross) else "filled" if all(can_cross) and all(q >= quantity for q in entry["sizes"]) else "unknown"
    row = {"submitted": True, "status": "unknown_entry", "quantity": quantity, "long": long,
           "entry_arrival_ns": arrival, "exit_arrival_ns": departure,
           "inventory_schedule_upper_ns": departure - arrival + 2 * radius,
           "entry_quotes": entry, "exit_quotes": exit_quotes, "potential_inventory_quantity": [0, quantity],
           "entry_outcome": outcome}
    assert row["inventory_schedule_upper_ns"] <= 30 * NS
    if outcome == "no_fill":
        return {**row, "status": "no_fill", "potential_inventory_quantity": [0, 0]}, False
    if outcome == "unknown":
        return row, False
    if any(q < quantity for q in exit_quotes["sizes"]):
        return {**row, "status": "unknown_exit"}, False
    values = []
    for initial in sorted(set(entry["prices"])):
        for final in sorted(set(exit_quotes["prices"])):
            initial_notional, final_notional = initial * quantity, final * quantity
            gross = (final_notional - initial_notional) * (1 if long else -1)
            fees = (initial_notional + final_notional) * D(6 * scenario["fee_multiple"]) / 10000
            adverse = (initial_notional + final_notional) * D(scenario["adverse_multiple"]) / 10000
            values.append({"entry_price": initial, "exit_price": final, "gross": gross,
                           "fees": fees, "adverse": adverse, "net": gross - fees - adverse})
    return {**row, "status": "conditional_complete", "potential_inventory_quantity": [0, 0],
            "lower": min(values, key=lambda r: r["net"]), "upper": max(values, key=lambda r: r["net"])}, True


def main():
    replay = OUT / "replay_v1"
    implementation = json.loads((replay / "implementation.json").read_text())
    spec = json.loads((OUT / "specification.json").read_text())
    result = json.loads((replay / "results.json").read_text())
    sources = json.loads((OUT / "source_manifest.json").read_text())
    assert sources["complete"] and sha(OUT / "specification.json") == implementation["specification_sha256"]
    assert sha(OUT / "source_manifest.json") == implementation["source_manifest_sha256"]
    assert sha(TARGET / "independent_verification.json") == implementation["quote_audit_sha256"]
    assert sha(FLOW / "independent_verification.json") == implementation["flow_audit_sha256"]
    for path, digest in implementation["code_sha256"].items():
        assert sha(ROOT / path) == digest
    assert sha(ROOT / spec["events_path"]) == spec["events_sha256"] == implementation["events_sha256"]
    events = sorted(pd.read_parquet(ROOT / spec["events_path"]).to_dict("records"), key=lambda r: (r["decision_ns"], r["symbol"]))
    plans = json.loads((replay / "intents.json").read_text())
    summaries = json.loads((replay / "native_summary.json").read_text())
    all_books, all_intents, counts, intent_count = {}, {}, Counter(), 0
    for event in events:
        source = next(s for s in sources["files"] if s["date"] == event["date"] and s["symbol"] == event["symbol"])
        tick = D(spec["grids"][event["symbol"]])
        books, marks, native_counts = raw_source(source, tick)
        counts.update(native_counts)
        summary = next(s for s in summaries if s["date"] == event["date"] and s["symbol"] == event["symbol"])
        compare(summary, {"date": event["date"], "offset": int(event["offset_minutes"]), "symbol": event["symbol"],
                          "counts": dict(native_counts), "physical_ordered": True, "book_rows": len(books), "mark_rows": len(marks)})
        decision = int(event["decision_ns"])
        key, cutoff = (event["date"], event["symbol"], decision), decision - 250_000_000
        quote = [b for b in books if b["receive_ns"] < cutoff][-1]
        mark = [m for m in marks if m["receive_ns"] < cutoff][-1]
        assert all(0 < cutoff - quote[k] <= 250_000_000 for k in ("receive_ns", "transaction_ns", "publication_ns"))
        assert all(0 < decision - mark[k] <= 5 * NS for k in ("receive_ns", "publication_ns"))
        assert mark["next_funding_ns"] > decision + 25_200_000_000
        stored_plan = next(p for p in plans if (p["date"], p["symbol"], p["decision_ns"]) == key)
        all_books[key], all_intents[key] = books, {}
        for rule in spec["rules"]:
            direction = int(event["direction"]) * (1 if rule == "follow_common_move" else -1)
            is_buy = direction > 0
            price = quote["ask" if is_buy else "bid"]
            available = quote["ask_quantity" if is_buy else "bid_quantity"]
            quantity = int((min(D(200) / price / D("1.01"), available / 10) / 10).to_integral_value(rounding=ROUND_FLOOR)) * 10
            limit = (price * (1 + D(direction) / 1000) / tick).to_integral_value(rounding=ROUND_FLOOR if is_buy else ROUND_CEILING) * tick
            reserve = quantity * max(limit, quote["ask"]) * D("1.02")
            assert quantity * price >= 100 and reserve <= 10000
            intent = {"eligible": True, "signal_cutoff_ns": cutoff, "long": is_buy,
                      "quantity": quantity, "limit": limit, "capital_reserved": reserve,
                      "signal_book": quote, "signal_mark": mark, "reason": "conditional_plan"}
            compare(stored_plan["intents"][rule], intent)
            all_intents[key][rule] = intent
            intent_count += 1
    assert dict(counts) == result["source_counts"] and intent_count == result["eligible_intents"] == 2
    envelopes, rectangles, complete_scenarios, positive_scenarios = 0, 0, 0, 0
    for stored in result["scenarios"]:
        rule, name = stored["rule"], stored["scenario"]
        scenario = next(s for s in spec["scenarios"] if s["name"] == name)
        halted, busy, rows = set(), {}, []
        daily = defaultdict(lambda: D(0))
        lower, upper = D(0), D(0)
        for event in events:
            key = event["date"], event["symbol"], event["decision_ns"]
            day, decision = event["date"], event["decision_ns"]
            daily[day] += D(0)
            if day in halted:
                outcome = {"submitted": False, "status": "halted_after_unknown_inventory"}
            elif decision <= busy.get(day, -1):
                outcome = {"submitted": False, "status": "busy_with_prior_order"}
            else:
                outcome, has_cash = check_order(all_books[key], event, all_intents[key][rule], scenario)
                envelopes += 2
                rectangles += int(has_cash)
                if outcome["status"].startswith("unknown"):
                    halted.add(day)
                elif outcome["status"] == "conditional_complete":
                    lower += outcome["lower"]["net"]
                    upper += outcome["upper"]["net"]
                    daily[day] += outcome["lower"]["net"]
                    busy[day] = outcome["exit_arrival_ns"] + (scenario["delay_ms"] + scenario["clock_ms"]) * 10**6
                elif outcome["status"] == "no_fill":
                    busy[day] = outcome["entry_arrival_ns"] + (scenario["delay_ms"] + scenario["clock_ms"]) * 10**6
            rows.append({"date": day, "symbol": event["symbol"], "decision_ns": decision, "result": outcome})
        complete = not halted
        expected = {"rule": rule, "scenario": name, "complete": complete,
                    "net_lower": lower if complete else None, "net_upper": upper if complete else None,
                    "known_component_lower": lower, "known_component_upper": upper,
                    "completed_round_trips": sum(r["result"]["status"] == "conditional_complete" for r in rows),
                    "outcomes": dict(Counter(r["result"]["status"] for r in rows)),
                    "daily_lower": dict(daily) if complete else None,
                    "drop_best_three_dates_lower": sum(sorted(daily.values())[:-3], D(0)) if complete else None,
                    "unknown_dates": sorted(halted), "rows": rows, "actual_execution_verified": False}
        compare(stored, expected)
        compare(json.loads((replay / f"{rule}_{name}.json").read_text()), expected)
        complete_scenarios += int(complete)
        positive_scenarios += int(complete and lower > 0)
    assert complete_scenarios == result["complete_scenarios"]
    assert positive_scenarios == result["positive_complete_scenarios"]
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
             "source_files_verified": len(sources["files"]), "source_counts": dict(counts),
             "intents_verified": intent_count, "quote_envelopes_verified": envelopes,
             "cash_rectangles_verified": rectangles, "scenario_aggregates_verified": len(result["scenarios"]),
             "maximum_numeric_difference": "0", "results_sha256": sha(replay / "results.json"),
             "auditor_sha256": sha(Path(__file__)),
             "scope": "Every native quote/mark and capture/transaction/publication clock, funding clearance, both direction plans, all observed compatible FOK and exit states, distinct cash outcomes, unknown-inventory halts and full aggregates independently reconciled. No production replay/parser import. Cohort has no disconnect, duplicate, invalid book or clock regression.",
             "actual_execution_verified": False, "historical_order_filters_verified": False,
             "reliable_edge_established": False}
    with (replay / "independent_verification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
