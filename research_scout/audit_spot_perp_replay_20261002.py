"""Independent raw-clock, entry-plan, FOK and Decimal cash reconciliation."""

import calendar
import gzip
import json
from collections import Counter
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_FLOOR
from decimal import Decimal as D
from pathlib import Path

import pandas as pd

from research_scout.prepare_spot_perp_replay_20261002 import OUT, ROOT, sha

NS = 1_000_000_000


def raw_source(path):
    books, marks, counts = [], [], Counter()
    last_receive, last_id, last_match = -1, -1, -1
    with gzip.open(path, "rt", encoding="utf-8") as source:
        for number, line in enumerate(source):
            assert line.strip(), "Actual cohort must not contain an unaudited disconnect"
            timestamp, encoded = line.strip().split(" ", 1)
            whole, fraction = timestamp[:-1].split(".")
            seconds = calendar.timegm(datetime.strptime(whole, "%Y-%m-%dT%H:%M:%S").timetuple())
            receive = seconds * NS + int(fraction.ljust(9, "0"))
            assert receive >= last_receive
            last_receive = receive
            message = json.loads(encoded)
            data = message["data"]
            assert data["s"] == "ENAUSDT"
            counts["native_messages"] += 1
            if "@markPrice" in message["stream"]:
                event = int(data["E"]) * 1_000_000
                mark = D(data["p"])
                assert event <= receive + 1_000_000 and mark.is_finite() and mark > 0
                marks.append({"receive_ns": receive, "publication_ns": event,
                              "next_funding_ns": int(data["T"]) * 1_000_000,
                              "mark_price": mark, "source_line": number, "valid": True})
                counts["mark_messages"] += 1
                continue
            assert message["stream"] == "enausdt@bookTicker"
            uid, match, public = int(data["u"]), int(data["T"]) * 1_000_000, int(data["E"]) * 1_000_000
            assert uid > last_id and match >= last_match
            last_id, last_match = uid, match
            bid, ask, bq, aq = [D(data[k]) for k in ("b", "a", "B", "A")]
            assert all(x.is_finite() and x > 0 for x in (bid, ask, bq, aq)) and bid < ask
            assert bid % D("0.0001") == ask % D("0.0001") == 0
            assert max(match, public) <= receive + 1_000_000 and match <= public + 1_000_000
            books.append({"receive_ns": receive, "transaction_ns": match, "publication_ns": public,
                          "source_line": number, "update_id": uid, "valid": True,
                          "bid": bid, "ask": ask, "bid_quantity": bq, "ask_quantity": aq})
            counts["book_messages"] += 1
    return books, marks, counts


def compare(actual, expected):
    if isinstance(expected, dict):
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


def envelope(books, target, radius, is_buy):
    old_times = [r["transaction_ns"] for r in books if r["transaction_ns"] < target - radius]
    assert old_times
    first_time = max(old_times)
    indices = [i for i, r in enumerate(books) if first_time <= r["transaction_ns"] <= target + radius]
    first, stop = min(indices), max(indices) + 1
    assert stop < len(books)
    side = "ask" if is_buy else "bid"
    prices = [books[i][side] for i in indices]
    sizes = [books[i][side + "_quantity"] for i in indices]
    return {"known": True, "arrival_ns": target, "radius_ns": radius,
            "reason": "conditional_native_matching_clock", "first_index": first, "stop_index": stop,
            "successor_ns": books[stop]["transaction_ns"], "source_lines": [books[i]["source_line"] for i in indices],
            "prices": prices, "sizes": sizes, "price_lower": min(prices), "price_upper": max(prices),
            "minimum_touch_quantity": min(sizes)}


def main():
    replay_path = OUT / "replay_v1"
    implementation = json.loads((replay_path / "implementation.json").read_text())
    specification = json.loads((OUT / "specification.json").read_text())
    result = json.loads((replay_path / "results.json").read_text())
    source = json.loads((OUT / "source_manifest.json").read_text())
    assert sha(OUT / "specification.json") == implementation["specification_sha256"]
    assert sha(OUT / "source_manifest.json") == implementation["source_manifest_sha256"]
    assert source["complete"] and sha(ROOT / source["path"]) == source["compressed_sha256"]
    for path, digest in implementation["code_sha256"].items():
        assert sha(ROOT / path) == digest
    assert sha(ROOT / specification["events_path"]) == implementation["events_sha256"]
    event = pd.read_parquet(ROOT / specification["events_path"]).to_dict("records")[0]
    books, marks, counts = raw_source(ROOT / source["path"])
    assert dict(counts) == result["source_counts"]
    decision = int(event["decision_ns"])
    cutoff = decision - 250_000_000
    quote = [r for r in books if r["receive_ns"] < cutoff][-1]
    mark = [r for r in marks if r["receive_ns"] < cutoff][-1]
    assert all(0 < decision - quote[k] <= NS for k in ("receive_ns", "transaction_ns", "publication_ns"))
    assert all(0 < decision - mark[k] <= 5 * NS for k in ("receive_ns", "publication_ns"))
    assert mark["next_funding_ns"] > decision + 25_200_000_000
    plans = json.loads((replay_path / "intents.json").read_text())
    intents = {}
    for rule in specification["rules"]:
        direction = int(event["direction"]) * (1 if rule == "fade_basis" else -1)
        long = direction > 0
        price = quote["ask" if long else "bid"]
        size = quote["ask_quantity" if long else "bid_quantity"]
        units = min(D(200) / price / D("1.01"), size / 10)
        quantity = int((units / 100).to_integral_value(rounding=ROUND_FLOOR)) * 100
        tick = D(specification["grid"]["price_tick"])
        limit = (price * (1 + D(direction) / 1000) / tick).to_integral_value(
            rounding=ROUND_FLOOR if long else ROUND_CEILING) * tick
        reserve = quantity * max(limit, quote["ask"]) * D("1.02")
        assert quantity * price >= 100 and reserve <= 10000
        intents[rule] = {"eligible": True, "signal_cutoff_ns": cutoff, "long": long,
                         "quantity": quantity, "limit": limit, "capital_reserved": reserve,
                         "signal_book": quote, "signal_mark": mark, "reason": "conditional_plan"}
        compare(plans[rule], intents[rule])
    totals, rectangles = [], 0
    for stored in result["scenarios"]:
        rule, name = stored["rule"], stored["scenario"]
        scenario = next(s for s in specification["scenarios"] if s["name"] == name)
        intent = intents[rule]
        long, q = intent["long"], D(intent["quantity"])
        delay = scenario["delay_ms"] * 1_000_000
        entry_time = decision + 50_000_000 + delay
        exit_time = decision + 15 * NS + 100_000_000 + 3 * delay
        radius = scenario["clock_ms"] * 1_000_000
        entry = envelope(books, entry_time, radius, long)
        exit_quotes = envelope(books, exit_time, radius, not long)
        # All actual cohort paths are complete. This audit checks the complete
        # observed path rather than assuming those statuses from the report.
        assert all((p <= intent["limit"] if long else p >= intent["limit"]) for p in entry["prices"])
        assert min(entry["sizes"]) >= q and min(exit_quotes["sizes"]) >= q
        values = []
        for initial in set(entry["prices"]):
            for final in set(exit_quotes["prices"]):
                entry_notional, exit_notional = initial * q, final * q
                gross = (exit_notional - entry_notional) * (1 if long else -1)
                fees = (entry_notional + exit_notional) * D(6 * scenario["fee_multiple"]) / 10000
                adverse = (entry_notional + exit_notional) * D(scenario["adverse_multiple"]) / 10000
                values.append({"entry_price": initial, "exit_price": final, "gross": gross,
                               "fees": fees, "adverse": adverse, "net": gross - fees - adverse})
        lower, upper = min(values, key=lambda r: r["net"]), max(values, key=lambda r: r["net"])
        expected = {"submitted": True, "status": "conditional_complete", "quantity": int(q), "long": long,
                    "entry_arrival_ns": entry_time, "exit_arrival_ns": exit_time,
                    "inventory_schedule_upper_ns": exit_time - entry_time + 2 * radius,
                    "entry_quotes": entry, "exit_quotes": exit_quotes, "entry_outcome": "filled",
                    "potential_inventory_quantity": [0, 0], "lower": lower, "upper": upper}
        assert expected["inventory_schedule_upper_ns"] <= 30 * NS
        compare(stored["result"], expected)
        compare(stored, {"complete": True, "net_lower": lower["net"], "net_upper": upper["net"],
                         "outcome": "conditional_complete"})
        compare(json.loads((replay_path / f"{rule}_{name}.json").read_text()), stored)
        totals.append(lower["net"])
        rectangles += 1
    assert len(totals) == result["complete_scenarios"] == 12
    assert sum(x > 0 for x in totals) == result["positive_complete_scenarios"] == 0
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
             "source_counts": dict(counts), "intents_verified": len(intents),
             "quote_envelopes_verified": 24, "cash_rectangles_verified": rectangles,
             "scenario_aggregates_verified": len(totals), "maximum_numeric_difference": "0",
             "results_sha256": sha(replay_path / "results.json"), "auditor_sha256": sha(Path(__file__)),
             "scope": "Independently parsed every native BBO/funding message, verified source order and matching clocks, predecision funding clearance and sizing, all compatible FOK/exit states and every observed distinct price-pair cash outcome. No production replay/parser imports.",
             "actual_execution_verified": False, "historical_lot_size_and_permissions_verified": False,
             "reliable_edge_established": False}
    dump_path = replay_path / "independent_verification.json"
    with dump_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
