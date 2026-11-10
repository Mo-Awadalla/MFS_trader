"""Causal trade activity at proposed DEEP bid/ask limits; no fill or return claim."""

from collections import Counter

from research.iex_deep_supply import deep_message, deep_segment
from research.iex_native_prefix import inflate_prefix, packets, udp_payload


def admit(candidate, rows, cutoff_ns):
    symbol, quantity = candidate["symbol"], candidate["quantity"]
    bid, ask = candidate["quote"]["bid_price"], candidate["quote"]["ask_price"]
    if not 0 < bid < ask or quantity <= 0:
        raise ValueError("Invalid frozen candidate")
    causal = [r for r in rows if r["symbol"] == symbol and r["capture_ns"] < cutoff_ns
              and r["send_ns"] <= cutoff_ns and r["event_ns"] <= cutoff_ns]
    broken = {r["trade_id"] for r in causal if r["type"] == "B"}
    trades = [r for r in causal if r["type"] == "T" and r["event_ns"] >= cutoff_ns - 30_000_000_000
              and r["flags"] & 0x58 == 0 and min(r["size"], r["price"]) > 0 and r["trade_id"] not in broken]
    if len({r["trade_id"] for r in trades}) != len(trades):
        raise ValueError("Repeated unbroken native trade identifier")
    buy = [r for r in trades if r["price"] <= bid]
    sell = [r for r in trades if r["price"] >= ask]
    buy_times, sell_times = len({r["event_ns"] for r in buy}), len({r["event_ns"] for r in sell})
    buy_volume, sell_volume = sum(r["size"] for r in buy), sum(r["size"] for r in sell)
    enough = min(buy_times, sell_times) >= 3 and min(buy_volume, sell_volume) >= 5 * quantity
    return {"symbol": symbol, "quantity": quantity, "qualified": enough,
            "required_distinct_timestamps_each_side": 3, "required_volume_each_side": 5 * quantity,
            "buy_limit_timestamps": buy_times, "sell_limit_timestamps": sell_times,
            "buy_limit_print_volume": buy_volume, "sell_limit_print_volume": sell_volume,
            "buy_limit_trades": buy, "sell_limit_trades": sell,
            "eligible_prior_trade_count": len(trades),
            "eligible_prior_notional_units": sum(r["size"] * r["price"] for r in trades),
            "execution_verified": False, "returns_calculated": False}


def collect(path, symbols, cutoff_ns):
    raw, complete = inflate_prefix(path)
    stats, streams, rows = Counter(), {}, []
    names = {s.encode().ljust(8, b" ") for s in symbols}
    last_capture, count = -1, 0
    for capture, frame in packets(raw, stats, allow_partial=not complete):
        if capture < last_capture:
            raise ValueError("Native capture reversal")
        last_capture = capture
        if capture >= cutoff_ns:
            return rows, {"source_messages_checked": count, "covered": True,
                          "first_packet_at_or_after_cutoff_ns": capture,
                          "full_gzip_checksum_verified": complete}
        key, first, offset, length, sent, messages = deep_segment(udp_payload(frame))
        if (first, offset) != streams.get(key, (1, 0)):
            raise ValueError("DEEP source sequence/offset discontinuity")
        streams[key] = (first + len(messages), offset + length)
        count += len(messages)
        for i, message in enumerate(messages):
            if message[0] not in (84, 66) or message[10:18] not in names:
                continue
            row = deep_message(message)
            row.update(capture_ns=capture, send_ns=sent, sequence=first + i)
            if row["event_ns"] > cutoff_ns or sent > cutoff_ns:
                raise ValueError("Native event/send exceeds causal cutoff")
            if row["type"] == "B" or row["event_ns"] >= cutoff_ns - 30_000_000_000:
                rows.append(row)
    return rows, {"source_messages_checked": count, "covered": False,
                  "last_capture_ns": last_capture, "full_gzip_checksum_verified": complete}
