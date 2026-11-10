"""Independent native source, conditional order allocation and Decimal cash audit."""

import gzip
import hashlib
import json
import struct
import zlib
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/iex_spread_hft_20261002/price_probe_v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native_rows(source, symbol, endpoint):
    raw = zlib.decompressobj(31).decompress(source.read_bytes())
    pos, sequence, offset, previous_capture = 0, 1, 0, -1
    sections = interfaces = count = 0
    identity, rows, event_clock = None, [], {}
    while pos + 12 <= len(raw):
        kind, length = struct.unpack_from("<II", raw, pos)
        assert length >= 12 and length % 4 == 0
        if pos + length > len(raw):
            break
        assert struct.unpack_from("<I", raw, pos + length - 4)[0] == length
        body = raw[pos + 8:pos + length - 4]
        pos += length
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
        if capture >= endpoint:
            return rows, count, capture
        frame = body[20:20 + captured]
        assert frame[12:14] == b"\x08\x00" and frame[14] == 0x45 and frame[23] == 17
        assert struct.unpack_from("!H", frame, 20)[0] & 0x3FFF == 0
        ip_length = struct.unpack_from("!H", frame, 16)[0]
        assert ip_length == struct.unpack_from("!H", frame, 38)[0] + 20
        payload = frame[42:14 + ip_length]
        version, reserved, protocol, channel, session, size, total, start_offset, first, sent = struct.unpack_from(
            "<BBHIIHHqqq", payload)
        assert version == 1 and reserved == 0 and protocol == 0x8003
        if identity is None:
            identity = (protocol, channel, session)
        assert (protocol, channel, session) == identity
        assert (first, start_offset) == (sequence, offset) and len(payload) == size + 40
        assert sent < endpoint
        at = 40
        for k in range(total):
            n = struct.unpack_from("<H", payload, at)[0]
            at += 2
            message = payload[at:at + n]
            at += n
            assert len(message) == n and n >= 10
            if message[10:18] != symbol.encode().ljust(8, b" "):
                continue
            name, flags = chr(message[0]), message[1]
            event = struct.unpack_from("<q", message, 2)[0]
            assert event_clock.get(name, -1) <= event < endpoint
            event_clock[name] = event
            row = {"type": name, "flags": flags, "event_ns": event, "symbol": symbol,
                   "capture_ns": capture, "send_ns": sent, "sequence": first + k}
            if name == "Q":
                assert n == 42
                bq, bp, ap, aq = struct.unpack_from("<IqqI", message, 18)
                row.update(bid_size=bq, bid_price=bp, ask_price=ap, ask_size=aq)
            elif name in ("T", "B"):
                assert n == 38
                qty, price, trade_id = struct.unpack_from("<Iqq", message, 18)
                row.update(size=qty, price=price, trade_id=trade_id)
            elif name == "D":
                assert n == 31
                row.update(round_lot=struct.unpack_from("<I", message, 18)[0],
                           adjusted_previous_close=struct.unpack_from("<q", message, 22)[0])
            rows.append(row)
        assert at == len(payload)
        sequence += total
        offset += size
        count += total
    raise AssertionError("Source endpoint not covered")


def ledger(orders, case):
    buys = [o for o in orders if o["side"] == "buy"]
    sells = [o for o in orders if o["side"] == "sell"]
    assert all(o["quantity"] > 0 for o in orders)
    assert sum(o["quantity"] for o in buys) == sum(o["quantity"] for o in sells)
    b = sum(Decimal(o["quantity"] * o["price"]) / 10000 for o in buys)
    s = sum(Decimal(o["quantity"] * o["price"]) / 10000 for o in sells)
    c = sum(max(Decimal(1), Decimal(o["quantity"]) / 200) for o in orders) * case["fee_factor"]
    a = (b + s) / 10000 * case["adverse_factor"]
    fee = (s * Decimal("0.00003") + sum(o["quantity"] for o in sells) * Decimal("0.000166")) * case["fee_factor"]
    return {"gross_usd": s - b, "commission_usd": c, "adverse_usd": a,
            "sell_levy_usd": fee, "net_usd": s - b - c - a - fee}


def verify_case(event, rows, observed, case):
    types = {name: [r for r in rows if r["type"] == name] for name in ("Q", "H", "O", "T", "B")}

    def quote(t, boundary=False, successor=False):
        state = {name: next((r for r in reversed(types[name]) if r["event_ns"] <= t), None)
                 for name in ("Q", "H", "O")}
        if any(v is None for v in state.values()):
            return None
        q = state["Q"]
        if state["H"]["flags"] != 84 or state["O"]["flags"] != 78 or q["flags"] != 0:
            return None
        if q["bid_price"] <= 0 or q["bid_price"] >= q["ask_price"] or min(q["bid_size"], q["ask_size"]) <= 0:
            return None
        if boundary and any(v["event_ns"] == t for v in state.values()):
            return None
        if successor and not any(r["event_ns"] > t for r in types["Q"]):
            return None
        return q

    def halted(a, b):
        return any(a < r["event_ns"] <= b and r["flags"] != flag
                   for name, flag in (("H", 84), ("O", 78)) for r in types[name])

    def passive(side, limit, qty, a, b):
        used, remaining = [], qty
        for trade in types["T"]:
            price = trade["price"]
            eligible = price <= limit if side == "buy" else price >= limit
            if observed["fill_model"] == "strict_trade_through" and price == limit:
                eligible = False
            if not (a <= trade["event_ns"] <= b and eligible and trade["flags"] & 88 == 0
                    and price > 0 and trade["size"] > 0):
                continue
            if trade["event_ns"] in (a, b):
                return None, "ambiguous_trade_at_order_boundary"
            if quote(trade["event_ns"]) is None:
                return None, "invalid_state_during_used_trade"
            if trade["trade_id"] in {r["trade_id"] for r in types["B"]}:
                return None, "used_trade_broken_in_source_prefix"
            take = min(remaining, trade["size"])
            used.append({"quantity": take, "trade": trade})
            remaining -= take
            if not remaining:
                break
        return used, None

    d, lag = event["decision_ns"], case["latency_ns"]
    offsets = {"entry_arrival": 50_000_000 + lag, "entry_cancel_arrival": 5_000_000_000 + lag,
               "entry_cancel_ack": 5_000_000_000 + 2 * lag, "target_arrival": 5_050_000_000 + 3 * lag,
               "target_cancel_arrival": 15_000_000_000 + lag, "target_cancel_ack": 15_000_000_000 + 2 * lag,
               "forced_arrival": 15_050_000_000 + 3 * lag}
    t = {k: d + v for k, v in offsets.items()}
    assert t == observed["times_ns"] and observed["intended_quantity"] == event["quantity"]
    bid, ask = event["quote"]["bid_price"], event["quote"]["ask_price"]
    q = quote(t["entry_arrival"], boundary=True)
    expected, orders = None, []
    if q is None or halted(t["entry_arrival"], t["entry_cancel_arrival"]):
        expected = "unknown_entry_state"
    else:
        if q["ask_price"] <= bid:
            fills, error = [{"quantity": event["quantity"], "assumed_aggressive": True,
                             "event_ns": t["entry_arrival"], "reference_quote": q}], None
        else:
            fills, error = passive("buy", bid, event["quantity"], t["entry_arrival"], t["entry_cancel_arrival"])
        if error:
            expected = "unknown_entry_" + error
        else:
            bought = sum(f["quantity"] for f in fills)
            assert observed["entry_allocations"] == fills and observed["bought_quantity"] == bought
            if not bought:
                expected = "conditional_no_entry"
            else:
                first = min(f["event_ns"] if "event_ns" in f else f["trade"]["event_ns"] for f in fills)
                orders.append({"side": "buy", "quantity": bought, "price": bid, "role": "entry"})
                q = quote(t["target_arrival"], boundary=True)
                if halted(first, t["forced_arrival"]):
                    expected = "unknown_halt_with_inventory"
                elif q is None:
                    expected = "unknown_target_state_with_inventory"
                else:
                    if q["bid_price"] >= ask:
                        sales, error = [{"quantity": bought, "assumed_aggressive": True,
                                         "event_ns": t["target_arrival"], "reference_quote": q}], None
                    else:
                        sales, error = passive("sell", ask, bought, t["target_arrival"], t["target_cancel_arrival"])
                    if error:
                        expected = "unknown_target_" + error
                    else:
                        sold = sum(f["quantity"] for f in sales)
                        assert observed["target_quantity"] == sold and observed["target_allocations"] == sales
                        if sold:
                            orders.append({"side": "sell", "quantity": sold, "price": ask, "role": "target"})
                        rest = bought - sold
                        q = quote(t["forced_arrival"], boundary=True, successor=True)
                        if rest and q is None:
                            expected = "unknown_forced_exit_with_inventory"
                            assert observed["residual_quantity"] == rest
                        else:
                            if rest:
                                assert observed["forced_reference_quote"] == q
                                orders.append({"side": "sell", "quantity": rest, "price": q["bid_price"], "role": "forced"})
                                last = t["forced_arrival"]
                            else:
                                last = max(f["event_ns"] if "event_ns" in f else f["trade"]["event_ns"] for f in sales)
                            assert observed["forced_quantity"] == rest
                            assert observed["exposure_ns"] == last - first < 30_000_000_000
                            expected = "conditional_priced"
    assert expected == observed["outcome"] and orders == observed["orders"]
    if expected == "conditional_priced":
        for field, value in ledger(orders, case).items():
            assert value == Decimal(observed[field]), (event["date"], field)
    elif expected == "conditional_no_entry":
        assert observed["net_usd"] == "0"
    else:
        assert observed["net_usd"] is None


def one_day(day, expected_hash):
    path = OUT / "sessions" / (day + ".json")
    assert sha(path) == expected_hash
    session = json.loads(path.read_text())
    source = Path(session["prefix_path"])
    assert sha(source) == session["prefix_sha256"]
    record_path = Path(session["records_path"])
    assert sha(record_path) == session["records_sha256"]
    rows, count, endpoint_capture = native_rows(source, session["event"]["symbol"], session["coverage"]["endpoint_ns"])
    with gzip.open(record_path, "rt", encoding="utf-8") as handle:
        assert rows == [json.loads(line) for line in handle]
    assert count == session["source_messages_checked"] and len(rows) == session["selected_symbol_messages"]
    assert endpoint_capture == session["coverage"]["last_capture_ns"]
    spec = json.loads((OUT / "specification.json").read_text())
    cases = {c["name"]: c for c in spec["cases"]}
    for observed in session["outcomes"]:
        verify_case(session["event"], rows, observed, cases[observed["case"]])
    return {"date": day, "source_messages": count, "symbol_messages": len(rows),
            "cases": len(session["outcomes"]), "session_sha256": expected_hash}


def main():
    result_path = OUT / "results.json"
    results = json.loads(result_path.read_text())
    assert not results["errors"] and results["sessions_completed"] == results["events"]
    verified = []
    with ProcessPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(one_day, d, h): d for d, h in results["session_hashes"].items()}
        for job in as_completed(jobs):
            row = job.result()
            verified.append(row)
            print(json.dumps(row), flush=True)
    all_rows = []
    for day in results["session_hashes"]:
        all_rows.extend(json.loads((OUT / "sessions" / (day + ".json")).read_text())["outcomes"])
    for aggregate in results["scenario_results"]:
        rows = [r for r in all_rows if (r["case"], r["fill_model"]) == (aggregate["case"], aggregate["fill_model"])]
        known = [r for r in rows if r["net_usd"] is not None]
        values = sorted((Decimal(r["net_usd"]) for r in known), reverse=True)
        total, drop = sum(values, Decimal(0)), sum(values[3:], Decimal(0))
        assert aggregate["events"] == len(rows) and aggregate["known_events"] == len(known)
        assert aggregate["unknown_events"] == len(rows) - len(known)
        assert aggregate["outcomes"] == dict(Counter(r["outcome"] for r in rows))
        assert Decimal(aggregate["known_component_usd"]) == total
        assert Decimal(aggregate["drop_best_three_known_component_usd"]) == drop
        if len(known) == len(rows):
            assert Decimal(aggregate["full_conditional_net_usd"]) == total
            assert Decimal(aggregate["drop_best_three_full_conditional_net_usd"]) == drop
        else:
            assert aggregate["full_conditional_net_usd"] is aggregate["drop_best_three_full_conditional_net_usd"] is None
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
             "source_messages_verified": sum(r["source_messages"] for r in verified),
             "selected_symbol_messages_verified": sum(r["symbol_messages"] for r in verified),
             "event_case_rows_verified": len(all_rows), "aggregate_cases_verified": len(results["scenario_results"]),
             "results_sha256": sha(result_path), "auditor_sha256": sha(Path(__file__)),
             "sessions": sorted(verified, key=lambda r: r["date"]),
             "actual_execution_verified": False, "reliable_edge_established": False,
             "scope": "Independent source decoding, conditional price/print allocation and cash. No proof of counterfactual order acceptance, queue execution, hidden liquidity, depth or historical NBBO protection."}
    (OUT / "independent_verification.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps({k: v for k, v in audit.items() if k != "sessions"}), flush=True)


if __name__ == "__main__":
    main()
