"""Parameterized native clock reader; the original nine-o'clock reader is frozen."""

import json
from collections import Counter

from research.spot_perp_supply import NS, capture_ns, midnight_ns, update_book


def sample_native_at(lines, day, venue, start_minute):
    if start_minute not in (0, 360, 720, 1080):
        raise ValueError("Clock outside the frozen expansion")
    midnight = midnight_ns(day)
    start = midnight + start_minute * 60 * NS
    grids = [start + i * NS for i in range(60)]
    states, ids, seen, samples = {}, {}, set(), []
    counts = Counter()
    previous, cursor = -1, 0
    for index, line in enumerate(lines):
        if not line.strip():
            counts["disconnects"] += 1
            states.clear()
            ids.clear()
            continue
        stamp, payload = line.rstrip("\r\n").split(" ", 1)
        assert stamp[:10] == day
        received = capture_ns(stamp, midnight)
        if received < previous or not start <= received < start + 60 * NS:
            raise ValueError("Capture order or frozen slice boundary violated")
        previous = received
        while cursor < len(grids) and grids[cursor] - 250_000_000 <= received:
            samples.append(dict(states))
            cursor += 1
        message = json.loads(payload)
        counts["native_messages"] += 1
        if not message.get("stream", "").endswith("@bookTicker"):
            continue
        raw = message["data"]
        symbol = raw["s"]
        counts["book_messages"] += 1
        if not symbol.endswith("USDT") or not symbol.isalnum():
            continue
        seen.add(symbol)
        update_book(raw, received, index, venue, states, ids, counts)
    while cursor < len(grids):
        samples.append(dict(states))
        cursor += 1
    return {"samples": samples, "symbols": seen, "grids": grids, "counts": dict(counts)}
