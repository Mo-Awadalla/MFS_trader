"""Native DEEP atomic displayed-book reconstruction and causal spread admission."""

import struct
from collections import Counter, defaultdict
from decimal import Decimal

from research.iex_native_prefix import decode_message, inflate_prefix, packets, udp_payload
from research.iex_spread_supply import eligibility


def deep_segment(payload):
    if len(payload) < 40:
        raise ValueError("Short DEEP transport header")
    version, reserved, protocol, channel, session, length, count, offset, sequence, sent = struct.unpack_from(
        "<BBHIIHHqqq", payload)
    if version != 1 or reserved or protocol != 0x8004 or len(payload) != 40 + length:
        raise ValueError("Wrong DEEP transport identity or length")
    messages, at = [], 40
    for _ in range(count):
        if at + 2 > len(payload):
            raise ValueError("Missing DEEP message length")
        size = struct.unpack_from("<H", payload, at)[0]
        at += 2
        if size < 10 or at + size > len(payload):
            raise ValueError("Incomplete DEEP message")
        messages.append(payload[at:at + size])
        at += size
    if at != len(payload):
        raise ValueError("DEEP message count mismatch")
    return (protocol, channel, session), sequence, offset, length, sent, messages


def deep_message(data):
    row = decode_message(data)
    if row["type"] in ("8", "5"):
        if len(data) != 30 or row["flags"] not in (0, 1):
            raise ValueError("Invalid DEEP price level update")
        row.update(size=struct.unpack_from("<I", data, 18)[0],
                   price=struct.unpack_from("<q", data, 22)[0])
    return row


class Book:
    def __init__(self):
        self.bid, self.ask = {}, {}
        self.pending_event_ns = None
        self.quote = None
        self.last_event_by_side = {}

    def update(self, row):
        if row["type"] not in ("8", "5") or row["flags"] not in (0, 1):
            raise ValueError("Unsupported book update")
        t, price, size = row["event_ns"], row["price"], row["size"]
        if price <= 0 or size < 0:
            raise ValueError("Invalid native price/size")
        if self.pending_event_ns is not None and self.pending_event_ns != t:
            raise ValueError("Incomplete atomic event before a different event")
        if t < self.last_event_by_side.get(row["type"], -1):
            raise ValueError("Price-level event clock reversal")
        self.last_event_by_side[row["type"]] = t
        self.pending_event_ns = t
        side = self.bid if row["type"] == "8" else self.ask
        if size:
            side[price] = size
        else:
            if price not in side:
                raise ValueError("Deletion without previously observed displayed level")
            del side[price]
        if row["flags"] == 0:
            return None
        bid, ask = max(self.bid, default=0), min(self.ask, default=0)
        self.quote = {
            "type": "derived_deep_bbo", "flags": 0, "symbol": row["symbol"],
            "bid_price": bid, "ask_price": ask, "bid_size": self.bid.get(bid, 0),
            "ask_size": self.ask.get(ask, 0), "event_ns": t,
            "capture_ns": row["capture_ns"], "send_ns": row["send_ns"],
            "sequence": row["sequence"], "native_final_update": row,
        }
        self.pending_event_ns = None
        return self.quote

    def protected(self, round_lot=100):
        def one(side, reverse):
            quantity = 0
            for price, qty in sorted(side.items(), reverse=reverse):
                quantity += qty
                if quantity >= round_lot:
                    return {"price": price, "size": quantity}
            return {"price": 0, "size": 0}
        if self.pending_event_ns is not None:
            return None
        return {"bid": one(self.bid, True), "ask": one(self.ask, False),
                "assumed_round_lot": round_lot}


def screen(path, decision_ns, compare_symbols=()):
    cutoff, start = decision_ns - 250_000_000, decision_ns - 30_250_000_000
    data, complete = inflate_prefix(path)
    stats, types, streams, books = Counter(), Counter(), {}, defaultdict(Book)
    trades, breaks, h, o, directories = defaultdict(list), set(), {}, {}, {}
    last_capture, messages, covered = -1, 0, False
    for capture, frame in packets(data, stats, allow_partial=not complete):
        if capture < last_capture:
            raise ValueError("DEEP capture clock reversal")
        last_capture = capture
        if capture >= cutoff:
            covered = True
            break
        key, seq, offset, length, sent, native = deep_segment(udp_payload(frame))
        if (seq, offset) != streams.get(key, (1, 0)):
            raise ValueError("DEEP sequence or byte-offset gap")
        streams[key] = (seq + len(native), offset + length)
        messages += len(native)
        for i, raw in enumerate(native):
            row = deep_message(raw)
            types[row["type"]] += 1
            symbol, kind = row.get("symbol"), row["type"]
            if symbol is None:
                continue
            row.update(capture_ns=capture, send_ns=sent, sequence=seq + i)
            if row["event_ns"] > cutoff or sent > cutoff:
                raise ValueError("DEEP source crosses causal information cutoff")
            if kind in ("8", "5"):
                books[symbol].update(row)
            elif kind == "H":
                h[symbol] = row["flags"]
            elif kind == "O":
                o[symbol] = row["flags"]
            elif kind == "D":
                directories[symbol] = row
            elif kind == "B":
                breaks.add((symbol, row["trade_id"]))
            elif kind == "T" and row["event_ns"] >= start:
                if row["flags"] & 0x58 == 0 and min(row["price"], row["size"]) > 0:
                    trades[symbol].append(row)
    if not covered:
        return {"status": "insufficient_prefix", "last_capture_ns": last_capture,
                "required_cutoff_ns": cutoff, "messages_checked": messages, "returns_calculated": False}
    outcomes, candidates, costs, comparisons = Counter(), [], [], []
    for symbol in sorted(books):
        book = books[symbol]
        if book.pending_event_ns is not None:
            outcomes["atomic_book_event_incomplete_at_cutoff"] += 1
            continue
        if book.quote is None:
            outcomes["no_completed_book_state"] += 1
            continue
        flow = [r for r in trades[symbol] if (symbol, r["trade_id"]) not in breaks]
        reason, detail = eligibility(book.quote, flow, h.get(symbol), o.get(symbol),
                                     bool(directories.get(symbol, {}).get("flags", 0) & 128))
        outcomes[reason] += 1
        if detail is not None:
            costs.append(detail)
        if reason == "candidate":
            candidates.append(detail)
        if symbol in compare_symbols:
            comparisons.append({"symbol": symbol, "deep_quote": book.quote,
                                "protected_aggregation_assuming_100_shares": book.protected(),
                                "causal_outcome": reason, "cost_detail": detail,
                                "displayed_bids": sorted(book.bid.items(), reverse=True),
                                "displayed_asks": sorted(book.ask.items())})
    candidates.sort(key=lambda r: (-Decimal(r["quoted_net_budget_bps"]),
                                  -Decimal(r["prior_trade_notional_usd"]), r["symbol"]))
    return {"status": "screened", "decision_ns": decision_ns, "cutoff_ns": cutoff,
            "messages_checked": messages, "types": dict(types), "symbols_with_book": len(books),
            "outcomes": dict(outcomes), "candidates": candidates, "selected": candidates[:1],
            "cost_rows": costs, "tops_candidate_comparisons": comparisons,
            "gzip_complete": complete, "returns_calculated": False, "execution_verified": False,
            "queue_or_hidden_liquidity_observed": False, "instrument_classification_confirmed": False}
