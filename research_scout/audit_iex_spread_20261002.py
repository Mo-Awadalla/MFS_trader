"""Independent fixed-format raw PCAPNG/TOPS signal and budget reconstruction.

No production packet decoder, quote parser, eligibility or cash helper is used.
This audit accepts only the specific observed single-interface microsecond
Ethernet/IPv4 PCAPNG format. Unsupported source formats fail, not silently skip.
"""

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
OUT = ROOT / "research_scout/iex_spread_hft_20261002"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(day):
    path = OUT / "sessions" / (day + ".json")
    observed = json.loads(path.read_text())
    assert observed["status"] == "screened"
    source = Path(observed["prefix_path"])
    assert sha(source) == observed["prefix_sha256"]
    raw = zlib.decompressobj(31).decompress(source.read_bytes())
    cutoff = observed["decision_ns"] - 250_000_000
    start = cutoff - 30_000_000_000
    quotes, h, o, directories = {}, {}, {}, {}
    trades, breaks, counts = defaultdict(list), set(), Counter()
    pos, sequence, byte_offset, packet_count = 0, 1, 0, 0
    section_count, interface_count, previous_capture = 0, 0, -1
    stream_identity, reached = None, False
    previous_event = {}
    while pos + 12 <= len(raw):
        kind, size = struct.unpack_from("<II", raw, pos)
        assert size >= 12 and size % 4 == 0
        if pos + size > len(raw):
            break
        assert struct.unpack_from("<I", raw, pos + size - 4)[0] == size
        body = raw[pos + 8:pos + size - 4]
        pos += size
        if kind == 0x0A0D0D0A:
            section_count += 1
            assert section_count == 1 and body[:8] == b"\x4d\x3c\x2b\x1a\x01\x00\x00\x00"
            continue
        if kind == 1:
            interface_count += 1
            assert interface_count == 1 and struct.unpack_from("<HH", body) == (1, 0)
            j, resolution = 8, 6
            while j + 4 <= len(body):
                option, length = struct.unpack_from("<HH", body, j)
                value = body[j + 4:j + 4 + length]
                assert len(value) == length
                if option == 9:
                    assert value == b"\x06"
                    resolution = value[0]
                if option == 14:
                    assert value == b"\x00" * 8
                j += 4 + ((length + 3) // 4) * 4
                if option == 0:
                    break
            assert resolution == 6
            continue
        assert kind == 6 and section_count == interface_count == 1
        interface, high, low, captured, original = struct.unpack_from("<IIIII", body)
        assert interface == 0 and captured == original and len(body) >= 20 + captured
        capture = ((high << 32) + low) * 1000
        assert capture >= previous_capture
        previous_capture = capture
        if capture >= cutoff:
            reached = True
            break
        packet_count += 1
        frame = body[20:20 + captured]
        assert frame[12:14] == b"\x08\x00" and frame[14] == 0x45 and frame[23] == 17
        assert struct.unpack_from("!H", frame, 20)[0] & 0x3FFF == 0
        ip_length = struct.unpack_from("!H", frame, 16)[0]
        udp_length = struct.unpack_from("!H", frame, 38)[0]
        assert ip_length == udp_length + 20 and len(frame) >= 14 + ip_length
        payload = frame[42:14 + ip_length]
        version, reserved, protocol, channel, session, length, total, offset, first, sent = struct.unpack_from(
            "<BBHIIHHqqq", payload)
        assert version == 1 and reserved == 0 and protocol == 0x8003
        identity = (protocol, channel, session)
        if stream_identity is None:
            stream_identity = identity
        assert identity == stream_identity and (first, offset) == (sequence, byte_offset)
        assert len(payload) == length + 40 and sent <= cutoff
        at = 40
        for k in range(total):
            n = struct.unpack_from("<H", payload, at)[0]
            at += 2
            message = payload[at:at + n]
            assert len(message) == n and n >= 10
            at += n
            name, flags = chr(message[0]), message[1]
            event = struct.unpack_from("<q", message, 2)[0]
            assert event <= cutoff
            counts[name] += 1
            if n < 18:
                continue
            symbol = message[10:18].decode("ascii").rstrip(" ")
            pair = (name, symbol)
            assert event >= previous_event.get(pair, -1)
            previous_event[pair] = event
            common = {"type": name, "flags": flags, "event_ns": event, "symbol": symbol,
                      "capture_ns": capture, "send_ns": sent, "sequence": first + k}
            if name == "Q":
                assert n == 42
                bq, bp, ap, aq = struct.unpack_from("<IqqI", message, 18)
                quotes[symbol] = {**common, "bid_size": bq, "bid_price": bp,
                                  "ask_price": ap, "ask_size": aq}
            elif name in ("T", "B"):
                assert n == 38
                qty, price, trade_id = struct.unpack_from("<Iqq", message, 18)
                if name == "B":
                    breaks.add((symbol, trade_id))
                elif event >= start and (flags & (64 + 16 + 8)) == 0 and qty > 0 and price > 0:
                    trades[symbol].append({**common, "size": qty, "price": price, "trade_id": trade_id})
            elif name == "H":
                h[symbol] = flags
            elif name == "O":
                o[symbol] = flags
            elif name == "D":
                directories[symbol] = flags
        assert at == len(payload)
        sequence += total
        byte_offset += length
    assert reached
    assert sum(counts.values()) == observed["messages_checked"]
    assert dict(counts) == observed["types"] and packet_count == observed["packets_checked"]
    expected_costs = {r["symbol"]: r for r in observed["cost_rows"]}
    reasons, candidates, budget_count = Counter(), [], 0
    for symbol, quote in sorted(quotes.items()):
        bp, ap, bq, aq = (quote[k] for k in ("bid_price", "ask_price", "bid_size", "ask_size"))
        qty = min(100_000_000 // ap if ap > 0 else 0, bq // 10, aq // 10)
        flow = [t for t in trades[symbol] if (symbol, t["trade_id"]) not in breaks]
        flow_notional = sum(t["price"] * t["size"] for t in flow)
        if re.fullmatch("[A-Z]{1,5}", symbol) is None or directories.get(symbol, 0) & 128:
            reason = "symbol_or_test_security"
        elif h.get(symbol) != 84 or o.get(symbol) != 78:
            reason = "trading_status"
        elif quote["flags"] != 0 or bp <= 0 or ap <= bp or bq <= 0 or aq <= 0:
            reason = "invalid_current_quote"
        elif bp < 50_000 or ap > 10_000_000 or bp % 100 or ap % 100:
            reason = "price_or_cent_grid"
        elif (ap - bp) * 20000 > 50 * (bp + ap):
            reason = "spread_above_50bp"
        elif bp * bq < 20_000_000 or ap * aq < 20_000_000:
            reason = "displayed_notional_below_2000"
        elif qty < 1:
            reason = "no_causal_quantity"
        elif len(flow) < 10 or flow_notional < 100_000_000:
            reason = "insufficient_prior_activity"
        elif not bp <= flow[-1]["price"] <= ap:
            reason = "last_trade_outside_current_quote"
        else:
            buy_value = Decimal(bp * qty) / 10000
            sell_value = Decimal(ap * qty) / 10000
            net = (sell_value - buy_value - 2 * max(Decimal(1), Decimal(qty) / 200)
                   - (buy_value + sell_value) / 10000 - sell_value * Decimal("0.00003")
                   - Decimal(qty) * Decimal("0.000166"))
            budget_bp = net * 20000 / (buy_value + sell_value)
            row = expected_costs[symbol]
            assert quote == row["quote"] and flow[-1] == row["last_trade"]
            assert qty == row["quantity"] and len(flow) == row["prior_trade_count"]
            assert Decimal(flow_notional) / 10000 == Decimal(row["prior_trade_notional_usd"])
            assert net == Decimal(row["quoted_net_budget_usd"])
            assert budget_bp == Decimal(row["quoted_net_budget_bps"])
            budget_count += 1
            reason = "candidate" if budget_bp >= 2 else "spread_below_cost_plus_2bp"
            if reason == "candidate":
                candidates.append((symbol, budget_bp, Decimal(flow_notional) / 10000))
        reasons[reason] += 1
    candidates.sort(key=lambda row: (-row[1], -row[2], row[0]))
    assert dict(reasons) == observed["outcomes"]
    assert [r[0] for r in candidates] == [r["symbol"] for r in observed["candidates"]]
    assert [r[0] for r in candidates[:1]] == [r["symbol"] for r in observed["selected"]]
    assert budget_count == len(expected_costs)
    return {"date": day, "verified": True, "messages": sum(counts.values()),
            "symbols": len(quotes), "cost_budgets": budget_count, "candidates": len(candidates),
            "source_sha256": observed["prefix_sha256"], "session_sha256": sha(path)}


def main():
    source_results = json.loads((OUT / "screen_results.json").read_text())
    assert not source_results["errors"] and not source_results["insufficient_prefix_dates"]
    dates = sorted(source_results["session_hashes"])
    rows = []
    with ProcessPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(audit, day): day for day in dates}
        for job in as_completed(jobs):
            row = job.result()
            rows.append(row)
            print(json.dumps({"date": row["date"], "verified": True, "candidates": row["candidates"]}), flush=True)
    result = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
              "dates_verified": len(rows), "messages_verified": sum(r["messages"] for r in rows),
              "symbol_decisions_verified": sum(r["symbols"] for r in rows),
              "cost_budgets_verified": sum(r["cost_budgets"] for r in rows),
              "candidates_verified": sum(r["candidates"] for r in rows),
              "source_clock_monotonicity_per_message_type_symbol_checked": True,
              "source_results_sha256": sha(OUT / "screen_results.json"), "auditor_sha256": sha(Path(__file__)),
              "source_and_session_hashes": sorted(rows, key=lambda r: r["date"]),
              "execution_or_returns_evaluated": False, "full_gzip_checksum_verified": False}
    (OUT / "independent_verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "source_and_session_hashes"}), flush=True)


if __name__ == "__main__":
    main()
