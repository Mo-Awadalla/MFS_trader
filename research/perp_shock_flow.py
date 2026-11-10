"""Causal raw execution confirmation; never reads future returns."""

import json
from collections import Counter
from decimal import Decimal as D

from research.spot_perp_supply import capture_ns, midnight_ns

NS, MS = 10**9, 10**6


def parse(lines, day, offset, symbols):
    midnight = midnight_ns(day)
    start = midnight + offset * 60 * NS
    trades, disconnects, counts, last = [], [], Counter(), start - 1
    for number, line in enumerate(lines):
        if not line.strip():
            counts["disconnects"] += 1
            disconnects.append(last)
            continue
        stamp, payload = line.rstrip("\r\n").split(" ", 1)
        received = capture_ns(stamp, midnight)
        assert stamp[:10] == day and start <= received < start + 60 * NS and received >= last
        last = received
        counts["native_messages"] += 1
        envelope = json.loads(payload)
        if not envelope.get("stream", "").endswith("@trade"):
            continue
        raw = envelope["data"]
        if raw["s"] not in symbols:
            continue
        assert envelope["stream"] == raw["s"].lower() + "@trade" and raw["e"] == "trade"
        counts["relevant_trade_messages"] += 1
        trades.append({"source_line": number, "receive_ns": received, "symbol": raw["s"], "raw": raw})
    return trades, disconnects, dict(counts)


def confirm(trades, disconnects, event):
    cutoff = int(event["decision_ns"]) - 250_000_000
    beginning = cutoff - NS
    seen, maximum_id, faults, ledger = {}, None, set(), []
    buy, sell, count = D(0), D(0), 0
    if any(t < cutoff for t in disconnects):
        faults.add("disconnect_before_cutoff")
    for trade in trades:
        if trade["symbol"] != event["symbol"] or trade["receive_ns"] >= cutoff:
            continue
        raw = trade["raw"]
        row = {"source_line": trade["source_line"], "receive_ns": trade["receive_ns"],
               "symbol": trade["symbol"], "counted": False}
        ledger.append(row)
        if not all(type(raw.get(k)) is int for k in ("t", "T", "E")) or type(raw.get("m")) is not bool:
            faults.add("invalid_native_schema")
            row["reason"] = "invalid_native_schema"
            continue
        uid, match, published = raw["t"], raw["T"] * MS, raw["E"] * MS
        fingerprint = tuple(str(raw.get(k)) for k in ("T", "E", "p", "q", "m", "X"))
        row.update(trade_id=uid, match_ns=match, publication_ns=published,
                   price=raw["p"], quantity=raw["q"], execution_type=raw.get("X"),
                   aggressor="sell" if raw["m"] else "buy")
        if uid in seen:
            if seen[uid] != fingerprint:
                faults.add("conflicting_trade_id")
                row["reason"] = "conflicting_trade_id"
            else:
                row["reason"] = "exact_duplicate"
            continue
        seen[uid] = fingerprint
        if maximum_id is not None and uid != maximum_id + 1:
            faults.add("regressing_trade_id" if uid <= maximum_id else "interior_trade_id_gap")
        maximum_id = uid if maximum_id is None else max(uid, maximum_id)
        if match < beginning or match >= cutoff:
            row["reason"] = "outside_matching_interval"
            continue
        price, quantity = D(raw["p"]), D(raw["q"])
        if uid < 0 or not all(x.is_finite() and x > 0 for x in (price, quantity)):
            faults.add("invalid_window_trade")
            row["reason"] = "invalid_window_trade"
            continue
        if not (match <= published + MS and max(match, published) <= trade["receive_ns"] + MS
                and trade["receive_ns"] - match <= 250_000_000):
            faults.add("inconsistent_window_trade_clocks")
            row["reason"] = "inconsistent_window_trade_clocks"
            continue
        if raw.get("X") != "MARKET":
            row["reason"] = "non_market_execution"
            continue
        notional = price * quantity
        if raw["m"]:
            sell += notional
        else:
            buy += notional
        count += 1
        row.update(counted=True, notional_usdt=str(notional), reason="counted_past_market_execution")
    total = buy + sell
    aligned = buy if event["direction"] > 0 else sell
    flow = count >= 5 and total >= 5000 and aligned >= total * D(".75")
    return {"date": event["date"], "offset_minutes": event["offset_minutes"], "symbol": event["symbol"],
            "decision_ns": int(event["decision_ns"]), "direction": int(event["direction"]),
            "window_start_ns": beginning, "cutoff_ns": cutoff, "native_market_trade_count": count,
            "buy_notional_usdt": str(buy), "sell_notional_usdt": str(sell), "total_notional_usdt": str(total),
            "aligned_notional_usdt": str(aligned), "aligned_fraction": str(aligned / total) if total else None,
            "source_integrity_ok": not faults, "integrity_problems": "|".join(sorted(faults)),
            "flow_gate": flow, "selected": flow and not faults,
            "reason": "source_integrity_unknown" if faults else "requires_response_replay" if flow else "insufficient_aligned_market_activity"}, ledger
