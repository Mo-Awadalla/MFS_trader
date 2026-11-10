"""Causal native IEX spread/size/activity admission; no future-price evaluation."""

import re
from collections import Counter, defaultdict
from decimal import Decimal

from research.iex_native_prefix import decode_message, inflate_prefix, packets, segment, udp_payload

SCALE = Decimal(10000)


def eligibility(quote, trades, trading, operational, test_security=False):
    if not re.fullmatch(r"[A-Z]{1,5}", quote["symbol"]) or test_security:
        return "symbol_or_test_security", None
    if trading != ord("T") or operational != ord("N"):
        return "trading_status", None
    bid, ask = quote["bid_price"], quote["ask_price"]
    bq, aq = quote["bid_size"], quote["ask_size"]
    if quote["flags"] != 0 or not 0 < bid < ask or min(bq, aq) <= 0:
        return "invalid_current_quote", None
    if not 50_000 <= bid < ask <= 10_000_000 or bid % 100 or ask % 100:
        return "price_or_cent_grid", None
    mid = Decimal(bid + ask) / (2 * SCALE)
    spread_bp = Decimal(ask - bid) * 20000 / Decimal(bid + ask)
    if spread_bp > 50:
        return "spread_above_50bp", None
    if min(bid * bq, ask * aq) < 20_000_000:
        return "displayed_notional_below_2000", None
    quantity = min(100_000_000 // ask, bq // 10, aq // 10)
    if quantity <= 0:
        return "no_causal_quantity", None
    notional = sum(t["price"] * t["size"] for t in trades)
    if len(trades) < 10 or notional < 100_000_000:
        return "insufficient_prior_activity", None
    last = trades[-1]
    if not bid <= last["price"] <= ask:
        return "last_trade_outside_current_quote", None
    purchase = Decimal(quantity * bid) / SCALE
    sale = Decimal(quantity * ask) / SCALE
    commission = 2 * max(Decimal(1), Decimal(quantity) * Decimal("0.005"))
    adverse = (purchase + sale) * Decimal("0.0001")
    levy = sale * Decimal("0.00003") + Decimal(quantity) * Decimal("0.000166")
    budget = sale - purchase - commission - adverse - levy
    budget_bp = budget * 10000 / (quantity * mid)
    detail = {"symbol": quote["symbol"], "quote": quote, "quantity": quantity,
              "prior_trade_count": len(trades), "prior_trade_notional_usd": str(Decimal(notional) / SCALE),
              "spread_bps": str(spread_bp), "quoted_net_budget_usd": str(budget),
              "quoted_net_budget_bps": str(budget_bp), "last_trade": last}
    if budget_bp < 2:
        return "spread_below_cost_plus_2bp", detail
    return "candidate", detail


def screen(path, decision_ns):
    cutoff = decision_ns - 250_000_000
    window_start = cutoff - 30_000_000_000
    data, gzip_complete = inflate_prefix(path)
    stats, types, streams = Counter(), Counter(), {}
    quotes, trading, operational, directories = {}, {}, {}, {}
    trade_lists, broken = defaultdict(list), set()
    prefix_covers_cutoff = False
    last_capture, messages_checked = None, 0
    for capture, frame in packets(data, stats, allow_partial=not gzip_complete):
        if last_capture is not None and capture < last_capture:
            raise ValueError("Nonmonotonic source capture")
        last_capture = capture
        if capture >= cutoff:
            prefix_covers_cutoff = True
            break
        key, seq, offset, length, sent, raw_messages = segment(udp_payload(frame))
        if (seq, offset) != streams.get(key, (1, 0)):
            raise ValueError("IEX source gap or duplicate")
        streams[key] = (seq + len(raw_messages), offset + length)
        for k, raw in enumerate(raw_messages):
            messages_checked += 1
            row = decode_message(raw)
            types[row["type"]] += 1
            symbol, kind = row.get("symbol"), row["type"]
            if symbol is None:
                continue
            row.update(capture_ns=capture, send_ns=sent, sequence=seq + k)
            if row["event_ns"] > cutoff or sent > cutoff:
                raise ValueError("Native publication/event clock crosses causal cutoff")
            if kind == "Q":
                quotes[symbol] = row
            elif kind == "H":
                trading[symbol] = row["flags"]
            elif kind == "O":
                operational[symbol] = row["flags"]
            elif kind == "D":
                directories[symbol] = row
            elif kind == "B":
                broken.add((symbol, row["trade_id"]))
            elif kind == "T" and row["event_ns"] >= window_start:
                if row["flags"] & 0x58 == 0 and row["size"] > 0 and row["price"] > 0:
                    trade_lists[symbol].append(row)
    if not prefix_covers_cutoff:
        return {"status": "insufficient_prefix", "last_capture_ns": last_capture,
                "required_cutoff_ns": cutoff, "returns_calculated": False}
    counters, qualified, cost_rows = Counter(), [], []
    for symbol in sorted(quotes):
        trades = [r for r in trade_lists[symbol] if (symbol, r["trade_id"]) not in broken]
        reason, detail = eligibility(quotes[symbol], trades, trading.get(symbol), operational.get(symbol),
                                     bool(directories.get(symbol, {}).get("flags", 0) & 0x80))
        counters[reason] += 1
        if detail is not None:
            cost_rows.append(detail)
        if reason == "candidate":
            qualified.append(detail)
    qualified.sort(key=lambda r: (-Decimal(r["quoted_net_budget_bps"]),
                                  -Decimal(r["prior_trade_notional_usd"]), r["symbol"]))
    return {"status": "screened", "decision_ns": decision_ns, "cutoff_ns": cutoff,
            "messages_checked": messages_checked, "packets_checked": stats["packets"] - 1,
            "types": dict(types), "symbols_with_quote": len(quotes), "outcomes": dict(counters),
            "candidates": qualified, "selected": qualified[:1], "cost_rows": cost_rows,
            "native_quote_age_cap_used": False,
            "maintained_book_basis": "Contiguous native sequence and byte offsets from stream start; current valid status/quote retained even when unchanged.",
            "instrument_classification_confirmed": False, "execution_verified": False,
            "returns_calculated": False, "gzip_complete": gzip_complete}
