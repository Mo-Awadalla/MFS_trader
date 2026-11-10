"""Independently reconstruct DEEP displayed books, causal costs and TOPS comparisons."""

import hashlib
import json
import re
import struct
import zlib
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/iex_deep_hft_20261002"
PARENT = ROOT / "research_scout/iex_spread_hft_20261002"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native(source, cutoff):
    raw = zlib.decompressobj(31).decompress(source.read_bytes())
    pos, sequence, offset, previous_capture = 0, 1, 0, -1
    sections = interfaces = 0
    identity, event_clock = None, {}
    while pos + 12 <= len(raw):
        kind, size = struct.unpack_from("<II", raw, pos)
        assert size >= 12 and size % 4 == 0
        if pos + size > len(raw):
            break
        assert struct.unpack_from("<I", raw, pos + size - 4)[0] == size
        body = raw[pos + 8:pos + size - 4]
        pos += size
        if kind == 0x0A0D0D0A:
            sections += 1
            assert sections == 1 and body[:8] == b"\x4d\x3c\x2b\x1a\x01\x00\x00\x00"
            continue
        if kind == 1:
            interfaces += 1
            assert interfaces == 1 and struct.unpack_from("<HH", body) == (1, 0)
            at = 8
            while at + 4 <= len(body):
                option, n = struct.unpack_from("<HH", body, at)
                value = body[at + 4:at + 4 + n]
                assert len(value) == n
                if option == 9:
                    assert value == b"\x06"
                if option == 14:
                    assert value == b"\x00" * 8
                at += 4 + ((n + 3) // 4) * 4
                if option == 0:
                    break
            continue
        assert kind == 6 and sections == interfaces == 1
        interface, high, low, captured, original = struct.unpack_from("<IIIII", body)
        assert interface == 0 and captured == original and len(body) >= 20 + captured
        capture = ((high << 32) + low) * 1000
        assert capture >= previous_capture
        previous_capture = capture
        if capture >= cutoff:
            return
        frame = body[20:20 + captured]
        assert frame[12:14] == b"\x08\x00" and frame[14] == 0x45 and frame[23] == 17
        assert struct.unpack_from("!H", frame, 20)[0] & 0x3FFF == 0
        ip_length = struct.unpack_from("!H", frame, 16)[0]
        assert ip_length == struct.unpack_from("!H", frame, 38)[0] + 20
        payload = frame[42:14 + ip_length]
        version, reserved, protocol, channel, session, length, count, byte_offset, first, sent = struct.unpack_from(
            "<BBHIIHHqqq", payload)
        assert version == 1 and reserved == 0 and protocol == 0x8004
        if identity is None:
            identity = (protocol, channel, session)
        assert identity == (protocol, channel, session)
        if (first, byte_offset) != (sequence, offset):
            raise ValueError(json.dumps({"issue": "native_sequence_or_byte_offset_discontinuity",
                                        "expected_sequence": sequence, "received_sequence": first,
                                        "expected_offset": offset, "received_offset": byte_offset,
                                        "capture_ns": capture, "send_ns": sent,
                                        "previous_messages": sequence - 1}))
        assert len(payload) == length + 40
        assert sent <= cutoff
        at = 40
        for k in range(count):
            n = struct.unpack_from("<H", payload, at)[0]
            at += 2
            message = payload[at:at + n]
            at += n
            assert len(message) == n and n >= 10
            name, flags = chr(message[0]), message[1]
            event = struct.unpack_from("<q", message, 2)[0]
            assert event <= cutoff
            row = {"type": name, "flags": flags, "event_ns": event}
            if n >= 18:
                symbol = message[10:18].decode("ascii").rstrip(" ")
                assert event_clock.get((name, symbol), -1) <= event
                event_clock[name, symbol] = event
                row.update(symbol=symbol, capture_ns=capture, send_ns=sent, sequence=first + k)
                if name in ("8", "5"):
                    assert n == 30 and flags in (0, 1)
                    quantity, price = struct.unpack_from("<Iq", message, 18)
                    row.update(size=quantity, price=price)
                elif name in ("T", "B"):
                    assert n == 38
                    quantity, price, trade_id = struct.unpack_from("<Iqq", message, 18)
                    row.update(size=quantity, price=price, trade_id=trade_id)
                elif name == "D":
                    assert n == 31
                    row.update(round_lot=struct.unpack_from("<I", message, 18)[0],
                               adjusted_previous_close=struct.unpack_from("<q", message, 22)[0])
            yield row
        assert at == len(payload)
        sequence += count
        offset += length
    raise AssertionError("DEEP causal cutoff not covered")


def audit(day, expected_hash):
    path = OUT / "sessions" / (day + ".json")
    assert sha(path) == expected_hash
    observed = json.loads(path.read_text())
    source = Path(observed["prefix_path"])
    assert observed["status"] == "screened" and sha(source) == observed["prefix_sha256"]
    cutoff = observed["decision_ns"] - 250_000_000
    books, processing, quotes, h, o, directories = {}, {}, {}, {}, {}, {}
    trades, breaks, types = defaultdict(list), set(), Counter()
    for row in native(source, cutoff):
        name, symbol = row["type"], row.get("symbol")
        types[name] += 1
        if symbol is None:
            continue
        if name in ("8", "5"):
            if symbol not in books:
                books[symbol] = {"8": {}, "5": {}}
            assert symbol not in processing or processing[symbol] == row["event_ns"]
            processing[symbol] = row["event_ns"]
            side = books[symbol][name]
            price, size = row["price"], row["size"]
            assert price > 0 and size >= 0
            if size:
                side[price] = size
            else:
                assert price in side
                del side[price]
            if row["flags"]:
                del processing[symbol]
                bid, ask = max(books[symbol]["8"], default=0), min(books[symbol]["5"], default=0)
                quotes[symbol] = {"type": "derived_deep_bbo", "flags": 0, "symbol": symbol,
                                  "bid_price": bid, "ask_price": ask,
                                  "bid_size": books[symbol]["8"].get(bid, 0),
                                  "ask_size": books[symbol]["5"].get(ask, 0),
                                  "event_ns": row["event_ns"], "capture_ns": row["capture_ns"],
                                  "send_ns": row["send_ns"], "sequence": row["sequence"],
                                  "native_final_update": row}
        elif name == "H":
            h[symbol] = row["flags"]
        elif name == "O":
            o[symbol] = row["flags"]
        elif name == "D":
            directories[symbol] = row["flags"]
        elif name == "B":
            breaks.add((symbol, row["trade_id"]))
        elif name == "T" and row["event_ns"] >= cutoff - 30_000_000_000:
            if not row["flags"] & 88 and row["size"] > 0 and row["price"] > 0:
                trades[symbol].append(row)
    assert sum(types.values()) == observed["messages_checked"] and dict(types) == observed["types"]
    assert len(books) == observed["symbols_with_book"]
    costs = {r["symbol"]: r for r in observed["cost_rows"]}
    outcomes, selected, cost_count = Counter(), [], 0
    reasons = {}
    for symbol in sorted(books):
        if symbol in processing:
            reason = "atomic_book_event_incomplete_at_cutoff"
        elif symbol not in quotes:
            reason = "no_completed_book_state"
        else:
            q = quotes[symbol]
            bp, ap, bq, aq = (q[k] for k in ("bid_price", "ask_price", "bid_size", "ask_size"))
            quantity = min(100_000_000 // ap if ap else 0, bq // 10, aq // 10)
            flow = [t for t in trades[symbol] if (symbol, t["trade_id"]) not in breaks]
            notional = sum(t["price"] * t["size"] for t in flow)
            if not re.fullmatch("[A-Z]{1,5}", symbol) or directories.get(symbol, 0) & 128:
                reason = "symbol_or_test_security"
            elif h.get(symbol) != 84 or o.get(symbol) != 78:
                reason = "trading_status"
            elif bp <= 0 or ap <= bp or bq <= 0 or aq <= 0:
                reason = "invalid_current_quote"
            elif bp < 50_000 or ap > 10_000_000 or bp % 100 or ap % 100:
                reason = "price_or_cent_grid"
            elif (ap - bp) * 20000 > 50 * (bp + ap):
                reason = "spread_above_50bp"
            elif min(bp * bq, ap * aq) < 20_000_000:
                reason = "displayed_notional_below_2000"
            elif quantity < 1:
                reason = "no_causal_quantity"
            elif len(flow) < 10 or notional < 100_000_000:
                reason = "insufficient_prior_activity"
            elif not bp <= flow[-1]["price"] <= ap:
                reason = "last_trade_outside_current_quote"
            else:
                buy, sell = Decimal(bp * quantity) / 10000, Decimal(ap * quantity) / 10000
                budget = sell - buy - 2 * max(Decimal(1), Decimal(quantity) / 200)
                budget -= (sell + buy) / 10000 + sell * Decimal("0.00003") + quantity * Decimal("0.000166")
                bp_budget = budget * 20000 / (sell + buy)
                actual = costs[symbol]
                assert actual["quote"] == q and actual["last_trade"] == flow[-1]
                assert actual["quantity"] == quantity and actual["prior_trade_count"] == len(flow)
                assert Decimal(actual["prior_trade_notional_usd"]) == Decimal(notional) / 10000
                assert Decimal(actual["quoted_net_budget_usd"]) == budget
                assert Decimal(actual["quoted_net_budget_bps"]) == bp_budget
                cost_count += 1
                reason = "candidate" if bp_budget >= 2 else "spread_below_cost_plus_2bp"
                if reason == "candidate":
                    selected.append((symbol, bp_budget, notional))
        outcomes[reason] += 1
        reasons[symbol] = reason
    selected.sort(key=lambda r: (-r[1], -r[2], r[0]))
    assert dict(outcomes) == observed["outcomes"] and cost_count == len(costs)
    assert [r[0] for r in selected] == [r["symbol"] for r in observed["candidates"]]
    assert [r[0] for r in selected[:1]] == [r["symbol"] for r in observed["selected"]]
    parent_path = PARENT / "sessions" / (day + ".json")
    assert sha(parent_path) == observed["parent_session_sha256"]
    parent = {r["symbol"]: r for r in json.loads(parent_path.read_text())["candidates"]}
    expected_compared = sorted(s for s in parent if s in books and s not in processing and s in quotes)
    assert expected_compared == [r["symbol"] for r in observed["tops_candidate_comparisons"]]
    for row in observed["tops_candidate_comparisons"]:
        symbol = row["symbol"]
        assert row["deep_quote"] == quotes[symbol] and row["causal_outcome"] == reasons[symbol]
        assert row["cost_detail"] == costs.get(symbol)
        protected = {"assumed_round_lot": 100}
        for side, label, key, reverse in (("8", "bid", "displayed_bids", True), ("5", "ask", "displayed_asks", False)):
            levels = sorted(books[symbol][side].items(), reverse=reverse)
            assert [list(pair) for pair in levels] == row[key]
            cumulative = 0
            protected[label] = {"price": 0, "size": 0}
            for price, qty in levels:
                cumulative += qty
                if cumulative >= 100:
                    protected[label] = {"price": price, "size": cumulative}
                    break
        assert protected == row["protected_aggregation_assuming_100_shares"]
        old, q = parent[symbol]["quote"], quotes[symbol]
        assert old == row["tops_quote_at_same_capture_cutoff"]
        assert row["tops_original_budget_usd"] == parent[symbol]["quoted_net_budget_usd"]
        assert row["better_displayed_bid_exists"] == (q["bid_price"] > old["bid_price"])
        assert row["better_displayed_ask_exists"] == (0 < q["ask_price"] < old["ask_price"])
        same = all(protected[side] == {"price": old[side + "_price"], "size": old[side + "_size"]}
                   for side in ("bid", "ask"))
        assert row["protected_matches_tops_at_cutoff"] == same
    return {"date": day, "source_messages": sum(types.values()), "symbol_decisions": len(books),
            "cost_budgets": cost_count, "candidates": len(selected),
            "tops_comparisons": len(expected_compared), "session_sha256": expected_hash}


def main():
    result_path = OUT / "screen_results.json"
    result = json.loads(result_path.read_text())
    assert not result["incomplete_prefix_dates"]
    assert result["dates_screened"] + len(result["errors"]) == result["dates_requested"]
    assert result["dates_screened"] == len(result["session_hashes"])
    source_issues = []
    for error in result["errors"]:
        assert error["error"] == "ValueError: DEEP sequence or byte-offset gap"
        source = OUT / "sources" / error["date"] / "prefix.gz"
        parent = json.loads((PARENT / "sessions" / (error["date"] + ".json")).read_text())
        try:
            for _ in native(source, parent["cutoff_ns"]):
                pass
        except ValueError as exc:
            issue = json.loads(str(exc))
            assert issue["issue"] == "native_sequence_or_byte_offset_discontinuity"
            source_issues.append({"date": error["date"], "source_sha256": sha(source), **issue})
        else:
            raise AssertionError("Reported source failure was not independently reproduced")
    verified = []
    with ProcessPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(audit, d, h): d for d, h in result["session_hashes"].items()}
        for job in as_completed(jobs):
            row = job.result()
            verified.append(row)
            print(json.dumps(row), flush=True)
    assert sum(r["candidates"] for r in verified) == result["candidates"]
    assert sum(r["source_messages"] for r in verified) == result["source_messages"]
    output = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
              "dates_verified": len(verified),
              "requested_dates": result["dates_requested"], "unknown_source_dates": source_issues,
              "full_cohort_source_complete": not source_issues,
              **{k + "_verified": sum(r[k] for r in verified) for k in (
                  "source_messages", "symbol_decisions", "cost_budgets", "candidates", "tops_comparisons")},
              "results_sha256": sha(result_path), "auditor_sha256": sha(Path(__file__)),
              "sessions": sorted(verified, key=lambda r: r["date"]),
              "actual_execution_verified": False, "reliable_edge_established": False,
              "scope": "Independent raw DEEP decoding, atomic displayed books, causal eligibility/ranking/costs, TOPS comparisons; no future returns, queue or hidden execution proof."}
    (OUT / "independent_verification.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({k: v for k, v in output.items() if k != "sessions"}), flush=True)


if __name__ == "__main__":
    main()
