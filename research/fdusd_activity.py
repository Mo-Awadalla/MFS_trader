"""Past-only native spot trade activity; no queue or profit claims."""

import json
from collections import Counter
from decimal import Decimal as D

from research.spot_perp_supply import NS, capture_ns, midnight_ns


def screen(lines, day, offset, symbols):
    midnight = midnight_ns(day)
    start = midnight + offset * 60 * NS
    beginning, cutoff = start + 10 * NS, start + 60 * NS - 250_000_000
    totals = {s: {"buy_count": 0, "sell_count": 0, "buy_notional_fdusd": D(0),
                  "sell_notional_fdusd": D(0)} for s in symbols}
    problems, seen, last_ids = {s: set() for s in symbols}, {}, {}
    counts, ledger, last_capture = Counter(), [], start - 1
    for number, line in enumerate(lines):
        if not line.strip():
            counts["disconnects"] += 1
            if last_capture < cutoff:
                for faults in problems.values():
                    faults.add("disconnect_before_cutoff")
            continue
        stamp, encoded = line.rstrip("\r\n").split(" ", 1)
        received = capture_ns(stamp, midnight)
        assert stamp[:10] == day and start <= received < start + 60 * NS and received >= last_capture
        last_capture = received
        counts["native_messages"] += 1
        envelope = json.loads(encoded)
        raw = envelope["data"]
        symbol = raw["s"]
        assert envelope["stream"] == symbol.lower() + "@trade" and raw["e"] == "trade"
        assert symbol in totals and type(raw["m"]) is bool
        assert all(type(raw[k]) is int for k in ("t", "T", "E"))
        uid, match, published = raw["t"], raw["T"] * 1_000_000, raw["E"] * 1_000_000
        price, quantity = D(raw["p"]), D(raw["q"])
        row = {"date": day, "offset_minutes": offset, "symbol": symbol, "source_line": number,
               "receive_ns": received, "match_ns": match, "publication_ns": published,
               "trade_id": uid, "price": raw["p"], "quantity": raw["q"],
               "aggressor": "sell" if raw["m"] else "buy", "counted": False}
        ledger.append(row)
        if received >= cutoff:
            row["reason"] = "unavailable_at_cutoff"
            continue
        fingerprint = raw["T"], raw["E"], raw["p"], raw["q"], raw["m"]
        key = symbol, uid
        if key in seen:
            if seen[key] == fingerprint:
                counts["exact_duplicate_trades"] += 1
                row["reason"] = "exact_duplicate"
            else:
                problems[symbol].add("conflicting_trade_id")
                row["reason"] = "conflicting_trade_id"
            continue
        seen[key] = fingerprint
        previous = last_ids.get(symbol)
        if previous is not None and uid != previous + 1:
            problems[symbol].add("regressing_trade_id" if uid <= previous else "interior_trade_id_gap")
        last_ids[symbol] = max(uid, previous) if previous is not None else uid
        if uid < 0 or not all(x.is_finite() and x > 0 for x in (price, quantity)):
            problems[symbol].add("invalid_trade_fields")
            row["reason"] = "invalid_trade_fields"
            continue
        if match < beginning:
            row["reason"] = "before_counting_interval"
            continue
        if not match <= published <= received + 1_000_000 or received - match > NS:
            problems[symbol].add("invalid_or_stale_trade_clock")
            row["reason"] = "invalid_or_stale_trade_clock"
            continue
        if match >= cutoff:
            row["reason"] = "matching_after_cutoff"
            continue
        side = row["aggressor"]
        totals[symbol][side + "_count"] += 1
        totals[symbol][side + "_notional_fdusd"] += price * quantity
        row.update(counted=True, notional_fdusd=str(price * quantity), reason="counted_past_execution")
    summaries = []
    for symbol in sorted(symbols):
        total = totals[symbol]
        activity = all(total[s + "_count"] >= 10 and total[s + "_notional_fdusd"] >= 2000 for s in ("buy", "sell"))
        faults = sorted(problems[symbol])
        summaries.append({"date": day, "offset_minutes": offset, "symbol": symbol,
                          **{k: str(v) if isinstance(v, D) else v for k, v in total.items()},
                          "source_integrity_ok": not faults, "integrity_problems": "|".join(faults),
                          "activity_gate": activity, "selected": activity and not faults,
                          "reason": "source_integrity_failure" if faults else "requires_queue_replay" if activity else "insufficient_two_sided_activity"})
    return summaries, ledger, dict(counts)
