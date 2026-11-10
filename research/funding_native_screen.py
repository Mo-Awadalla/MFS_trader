"""Native publication/capture-clock funding prescreen; no execution returns."""

import json
import math
from decimal import Decimal

import pandas as pd


def snapshot(lines, settlement_ns):
    cutoff = int(settlement_ns)-30_000_000_000
    states, seen, previous, messages, resets = {}, set(), None, 0, 0
    for line_index, raw in enumerate(lines):
        if not raw.strip():
            states.clear()
            resets += 1
            continue
        stamp, payload = raw.rstrip().split(" ", 1)
        local = pd.Timestamp(stamp).value
        if previous is not None and local < previous:
            raise ValueError("Native capture stream not ordered")
        previous = local
        if local >= cutoff:
            break
        wrapper = json.loads(payload)
        data = wrapper.get("data")
        entries = data if isinstance(data, list) else [data]
        for record_index, event in enumerate(entries):
            if not isinstance(event, dict) or event.get("e") != "markPriceUpdate":
                raise ValueError("Unexpected message in markPrice source")
            symbol = event["s"]
            messages += 1
            if not symbol.endswith("USDT"):
                continue
            seen.add(symbol)
            states[symbol] = {"symbol": symbol, "receive_ns": local,
                              "event_ns": int(event["E"])*1_000_000,
                              "funding_time_ns": int(event["T"])*1_000_000,
                              "funding_rate_raw": event["r"], "mark_price_raw": event["p"],
                              "line_index": line_index, "record_index": record_index}
    rows = []
    for symbol in sorted(seen):
        base = {"symbol": symbol, "settlement_ns": int(settlement_ns), "decision_ns": cutoff,
                "usable": False, "large_binance_rate": False}
        if symbol not in states:
            rows.append({**base, "reason": "state_cleared_by_disconnect"})
            continue
        r = {**base, **states[symbol]}
        if r["funding_rate_raw"] == "":
            r["reason"] = "missing_funding_rate"
        else:
            rate, mark = float(r["funding_rate_raw"]), float(r["mark_price_raw"])
            r.update(funding_rate=rate, mark_price=mark)
            if not math.isfinite(rate) or not math.isfinite(mark) or mark <= 0:
                r["reason"] = "invalid_rate_or_mark"
            elif r["funding_time_ns"] != settlement_ns:
                r["reason"] = "next_funding_time_differs"
            elif not (0 < cutoff-r["receive_ns"] <= 5_000_000_000
                      and 0 < cutoff-r["event_ns"] <= 5_000_000_000
                      and -1_000_000 <= r["receive_ns"]-r["event_ns"] <= 5_000_000_000):
                r["reason"] = "stale_or_inconsistent_source_clocks"
            else:
                r.update(usable=True, reason="usable", large_binance_rate=abs(Decimal(r["funding_rate_raw"])) >= Decimal(".0014"))
        rows.append(r)
    return rows, {"native_messages_before_decision": messages, "disconnect_markers": resets,
                  "observed_usdt_symbols": len(seen)}
