"""Bounded native DEEP extraction and atomic venue-clock quote references."""

from collections import Counter

from research.iex_deep_supply import Book, deep_message, deep_segment
from research.iex_native_prefix import inflate_prefix, packets, udp_payload


def quote_tape(rows):
    """Execution references use native events; causal signals use separate capture-clock books."""
    levels = sorted((r for r in rows if r["type"] in ("8", "5")),
                    key=lambda r: (r["event_ns"], r["sequence"]))
    book, quotes = Book(), []
    for row in levels:
        quote = book.update(row)
        if quote is None:
            continue
        derived = {**quote, "type": "Q", "derived_from": "DEEP displayed levels after atomic completion",
                   "bid_levels": [list(x) for x in sorted(book.bid.items(), reverse=True)],
                   "ask_levels": [list(x) for x in sorted(book.ask.items())]}
        if quotes and quotes[-1]["event_ns"] == derived["event_ns"]:
            quotes[-1] = derived
        else:
            quotes.append(derived)
    if book.pending_event_ns is not None:
        raise ValueError("Selected symbol source ends within an atomic event")
    return [r for r in rows if r["type"] not in ("8", "5")] + quotes


def extract_symbol(path, symbol, endpoint_ns):
    data, complete = inflate_prefix(path)
    stats, streams, rows = Counter(), {}, []
    previous, covered = -1, False
    target = symbol.encode().ljust(8, b" ")
    total_messages = 0
    for capture, frame in packets(data, stats, allow_partial=not complete):
        if capture < previous:
            raise ValueError("DEEP source capture reversal")
        previous = capture
        if capture >= endpoint_ns:
            covered = True
            break
        key, seq, offset, length, sent, messages = deep_segment(udp_payload(frame))
        if (seq, offset) != streams.get(key, (1, 0)):
            raise ValueError("DEEP source sequence/offset discontinuity")
        streams[key] = (seq + len(messages), offset + length)
        total_messages += len(messages)
        for i, message in enumerate(messages):
            if message[10:18] == target:
                row = deep_message(message)
                row.update(capture_ns=capture, send_ns=sent, sequence=seq + i)
                rows.append(row)
    return rows, {"covered": covered, "last_capture_ns": previous,
                  "endpoint_ns": endpoint_ns, "messages_checked": total_messages,
                  "full_gzip_checksum_verified": complete, "full_session": False}
