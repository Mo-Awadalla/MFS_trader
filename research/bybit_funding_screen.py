"""Causal ticker-field reconstruction and rate-only recovery routing."""

import json
from collections import Counter
from decimal import Decimal, InvalidOperation

from research.wide_tick_supply import stamp_ns

NS = 1_000_000_000
NEEDED = ("fundingRate", "nextFundingTime", "markPrice")


def snapshot(lines, target):
    cutoff = target-10_250_000_000
    midnight = target//(86400*NS)*(86400*NS)
    state, seen, prior, count = {}, set(), -1, Counter()
    for index, line in enumerate(lines, 1):
        if not line.strip():
            count["disconnects"] += 1
            if prior < cutoff:
                state.clear()
            continue
        stamp, payload = line.split(" ", 1)
        capture = stamp_ns(stamp, midnight)
        assert capture >= prior
        prior = capture
        message = json.loads(payload)
        count["native_messages"] += 1
        data = message["data"]
        symbol = data.get("symbol", message["topic"].split(".",1)[1])
        if not symbol.endswith("USDT"):
            count["other_symbols"] += 1
            continue
        if capture >= cutoff:
            continue
        count["precutoff_usdt_messages"] += 1
        seen.add(symbol)
        assert message["topic"] == "tickers."+symbol
        event = int(message["ts"])*1_000_000
        seq = int(message["cs"])
        previous = state.get(symbol)
        ordered = previous is None or seq > previous["sequence"] or (seq == previous["sequence"] and data == previous["message_data"])
        reset = message["type"] == "snapshot"
        if reset or previous is None or not ordered:
            current = {"fields": {}, "field_sources": {}}
        else:
            current = {"fields": dict(previous["fields"]), "field_sources": dict(previous["field_sources"])}
        assert message["type"] in {"snapshot", "delta"}
        for key in NEEDED:
            if key in data:
                current["fields"][key] = data[key]
                current["field_sources"][key] = {"line_index": index, "capture_ns": capture, "event_ns": event}
        current.update(capture_ns=capture,event_ns=event,line_index=index,sequence=seq,sequence_ok=ordered or reset,message_data=data)
        state[symbol] = current
    rows = []
    for symbol in sorted(seen):
        row = {"symbol":symbol,"settlement_ns":target,"decision_ns":cutoff,"route_for_recovery":False,"native_complete":False,"reason":"missing_state_after_disconnect"}
        current = state.get(symbol)
        if current is None:
            rows.append(row)
            continue
        values = current["fields"]
        row.update({k:current[k] for k in ("capture_ns","event_ns","line_index","sequence","sequence_ok")})
        row["known_fields"] = json.dumps(values,sort_keys=True)
        row["field_provenance"] = json.dumps(current["field_sources"],sort_keys=True)
        row["missing_fields"] = ",".join(k for k in NEEDED if k not in values)
        if (not current["sequence_ok"] or not 0<cutoff-current["capture_ns"]<=5*NS
                or not 0<cutoff-current["event_ns"]<=5*NS or not -1_000_000<=current["capture_ns"]-current["event_ns"]<=5*NS):
            row["reason"] = "stale_or_invalid_publication"
        elif "fundingRate" not in values:
            row["reason"] = "unobserved_funding_rate"
        else:
            try:
                rate = Decimal(values["fundingRate"])
            except InvalidOperation:
                rate = Decimal("NaN")
            if not rate.is_finite():
                row["reason"] = "invalid_funding_rate"
            else:
                row["funding_rate"] = float(rate)
                row["absolute_rate_bps"] = float(abs(rate)*10000)
                row["route_for_recovery"] = abs(rate)*10000>=14
                row["native_complete"] = not row["missing_fields"]
                row["reason"] = "large_rate_requires_full_state" if row["route_for_recovery"] else "rate_below_prescreen_hurdle"
        rows.append(row)
    return rows,dict(count)
