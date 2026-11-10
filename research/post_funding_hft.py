"""Native post-settlement source reconstruction and conservative execution."""

import bisect
import gzip
import hashlib
import json
from collections import Counter
from decimal import Decimal as D

from research.external_quote_hft import apply_external, fresh
from research.wide_tick_supply import stamp_ns

NS = 1_000_000_000


def ticker_update(message, received, source, previous):
    body, sequence = message["data"], int(message["cs"])
    snapshot = message["type"] == "snapshot"
    assert message["type"] in ("snapshot", "delta")
    ordered = previous is None or sequence > previous["sequence"] or (sequence == previous["sequence"] and body == previous["body"])
    valid = snapshot or ordered
    fields = {} if snapshot or previous is None or not ordered else dict(previous["fields"])
    provenance = {} if snapshot or previous is None or not ordered else dict(previous["provenance"])
    if valid:
        for name in ("nextFundingTime", "markPrice", "fundingRate"):
            if name in body:
                fields[name] = body[name]
                provenance[name] = source
    row = {"receive_ns": received, "publication_ns": int(message["ts"])*1_000_000,
           "source_index": source, "sequence": sequence, "valid": valid,
           "fields": fields, "provenance": provenance}
    return row, {"sequence": sequence, "body": body, "fields": fields, "provenance": provenance}


def load_window(root, source, midnight):
    assert source["complete"]
    path = root/source["path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == source["compressed_sha256"]
    books = {s: [] for s in source["symbols"]}
    tickers = {s: [] for s in source["symbols"]}
    book_state = {s: {} for s in books}
    ticker_state = dict.fromkeys(books)
    previous, counts = -1, Counter()
    digest = hashlib.sha256()
    with gzip.open(path, "rb") as stream:
        for index, raw in enumerate(stream, 1):
            digest.update(raw)
            if not raw.strip():
                counts["disconnects"] += 1
                for symbol in books:
                    books[symbol].append({"receive_ns": previous, "source_index": index, "valid": False,
                                          "reason": "disconnect", "transaction_ns": None})
                    tickers[symbol].append({"receive_ns": previous, "source_index": index, "valid": False, "fields": {}, "provenance": {}})
                    book_state[symbol], ticker_state[symbol] = {}, None
                continue
            stamp, payload = raw.decode().split(" ", 1)
            received = stamp_ns(stamp, midnight)
            assert stamp.startswith(source["date"]) and received >= previous
            assert midnight+source["offset"]*60*NS <= received < midnight+(source["offset"]+source["slice_minutes"])*60*NS
            previous = received
            message = json.loads(payload)
            topic = message["topic"]
            symbol = topic.rsplit(".", 1)[1]
            assert symbol in books
            counts["native_messages"] += 1
            if topic.startswith("orderbook.1."):
                row, state = apply_external(message, received, index, book_state[symbol])
                books[symbol].append(row)
                book_state[symbol] = state
                counts["book_messages"] += 1
                counts["book_"+row["reason"]] += 1
            else:
                assert topic == "tickers."+symbol
                row, state = ticker_update(message, received, index, ticker_state[symbol])
                tickers[symbol].append(row)
                ticker_state[symbol] = state
                counts["ticker_messages"] += 1
    assert digest.hexdigest() == source["decoded_sha256"]
    return books, tickers, dict(counts)


def before(rows, cutoff):
    index = bisect.bisect_left([r["receive_ns"] for r in rows], cutoff)-1
    return rows[index] if index >= 0 else None


def entry_plan(books, tickers, target):
    cutoff = target+9_750_000_000
    book, ticker = before(books, cutoff), before(tickers, cutoff)
    plan = {"eligible": False, "signal_cutoff_ns": cutoff, "reason": "missing_or_invalid_native_book"}
    if book is None or book.get("transaction_ns") is None or not fresh(book, cutoff):
        return plan
    plan["book_source_index"] = book["source_index"]
    if ticker is None or not ticker["valid"] or not all(0 < cutoff-ticker[k] <= 5*NS for k in ("receive_ns", "publication_ns")) or not -1_000_000 <= ticker["receive_ns"]-ticker["publication_ns"] <= 5*NS:
        plan["reason"] = "missing_stale_or_invalid_native_ticker"
        return plan
    plan["ticker_source_index"] = ticker["source_index"]
    funding = ticker["fields"].get("nextFundingTime")
    if funding is None:
        plan["reason"] = "funding_cycle_advance_unobserved"
        return plan
    try:
        funding_ns = int(funding)*1_000_000
    except (ValueError, TypeError):
        plan["reason"] = "invalid_native_funding_time"
        return plan
    plan.update(next_funding_ns=funding_ns, funding_time_source_index=ticker["provenance"]["nextFundingTime"])
    if funding_ns <= target+35*NS:
        plan["reason"] = "funding_cycle_not_safely_advanced"
        return plan
    bid, ask, bq, aq = [D(str(book[k])) for k in ("bid", "ask", "bid_quantity", "ask_quantity")]
    assert all(x.is_finite() and x > 0 for x in (bid, ask, bq, aq)) and bid < ask
    spread = (ask-bid)*20000/(bid+ask)
    quantity = int(min(D(200)/ask, bq/10, aq/10)//10)*10
    plan.update(bid=float(bid), ask=float(ask), bid_quantity=float(bq), ask_quantity=float(aq),
                spread_bps=float(spread), quantity=quantity)
    if spread > 20:
        plan["reason"] = "spread_above_frozen_gate"
    elif quantity*bid < 100:
        plan["reason"] = "insufficient_displayed_size"
    else:
        plan.update(eligible=True, reason="eligible")
    return plan


def possible_quotes(rows, arrival, uncertainty, quantity, buying):
    """Retrospective physical states compatible with the clock interval."""
    # Missing matching time or a regressing clock makes the affected replay
    # unknown; do not reorder the captured feed into an invented valid stream.
    previous = -1
    for row in rows:
        physical = row.get("transaction_ns")
        if physical is None:
            if arrival-6*NS <= row["receive_ns"] <= arrival+6*NS:
                return {"known": False, "reason": "unbounded_physical_state"}
            continue
        if physical < previous:
            return {"known": False, "reason": "regressing_matching_clock"}
        previous = physical
    physical_rows = [r for r in rows if r.get("transaction_ns") is not None]
    times = [r["transaction_ns"] for r in physical_rows]
    lower, upper = arrival-uncertainty, arrival+uncertainty
    left = bisect.bisect_left(times, lower)-1
    right = bisect.bisect_right(times, upper)
    if left < 0 or right >= len(times):
        return {"known": False, "reason": "physical_interval_not_bracketed"}
    # At the predecessor timestamp all tied records could describe the state
    # immediately before the lower bound. Include that entire tie group.
    left = bisect.bisect_left(times, times[left])
    selected = physical_rows[left:right]
    side, depth = ("ask", "ask_quantity") if buying else ("bid", "bid_quantity")
    prices = []
    for row in selected:
        if (not row["valid"] or row["transaction_ns"] < lower-5*NS
                or not -1_000_000 <= row["receive_ns"]-row["transaction_ns"] <= 5*NS
                or D(str(row[depth])) < quantity):
            return {"known": False, "reason": "invalid_stale_or_insufficient_physical_depth"}
        prices.append(D(str(row[side])))
    return {"known": True, "price_min": min(prices), "price_max": max(prices),
            "source_indices": [r["source_index"] for r in selected],
            "arrival_lower_ns": lower, "arrival_upper_ns": upper}


def cash(quantity, long, entry, exit_price, fee_bps, adverse_bps):
    q, start, end = D(str(quantity)), D(str(entry)), D(str(exit_price))
    gross = q*(end-start)*(1 if long else -1)
    turnover = q*(start+end)
    fees, adverse = turnover*D(str(fee_bps))/10000, turnover*D(str(adverse_bps))/10000
    return {"gross": gross, "fees": fees, "adverse": adverse, "net": gross-fees-adverse}


def replay(books, tickers, event, plan, rule, scenario):
    target = int(event["settlement_ns"])
    long = (event["bybit_funding_rate"] > 0) == (rule == "unwind_continuation")
    quantity = plan["quantity"]
    delay, uncertainty = scenario["latency_seconds"]*NS, scenario["clock_ms"]*1_000_000
    entry, exit_time = target+10*NS+delay, target+25*NS+delay
    result = {"submitted": True, "known": False, "long": long, "quantity": quantity,
              "entry_arrival_ns": entry, "exit_arrival_ns": exit_time, "inventory_upper_ns": exit_time-entry+2*uncertainty}
    assert result["inventory_upper_ns"] <= 30*NS
    # Require observed, coherent ticker continuity across the entire submitted
    # period; loss of source state cannot become an assumed zero funding charge.
    relevant = [r for r in tickers if plan["signal_cutoff_ns"] <= r["receive_ns"] <= exit_time+uncertainty+5*NS]
    latest = before(tickers, plan["signal_cutoff_ns"])
    for row in relevant:
        if not row["valid"] or latest is None or row["receive_ns"]-latest["receive_ns"] > 5*NS:
            result["reason"] = "unknown_ticker_continuity_after_submission"
            return result
        next_time = row["fields"].get("nextFundingTime")
        try:
            funding_known = next_time is not None and int(next_time)*1_000_000 > exit_time+uncertainty
        except (TypeError, ValueError):
            funding_known = False
        if not funding_known:
            result["reason"] = "unknown_funding_cash_after_submission"
            return result
        latest = row
        if row["receive_ns"] >= exit_time+uncertainty:
            break
    if latest is None or latest["receive_ns"] < exit_time+uncertainty:
        result["reason"] = "ticker_continuity_not_bracketed"
        return result
    entering = possible_quotes(books, entry, uncertainty, quantity, long)
    exiting = possible_quotes(books, exit_time, uncertainty, quantity, not long)
    result.update(entry=entering, exit=exiting)
    if not entering["known"] or not exiting["known"]:
        result["reason"] = "unknown_entry_or_exit_execution"
        return result
    outcomes = []
    for start in (entering["price_min"], entering["price_max"]):
        for end in (exiting["price_min"], exiting["price_max"]):
            outcomes.append({"entry_price": start, "exit_price": end, **cash(quantity, long, start, end, scenario["taker_bps"], scenario["adverse_bps"])})
    lower = min(outcomes, key=lambda r: r["net"])
    upper = max(outcomes, key=lambda r: r["net"])
    result.update(known=True, reason="conditional_taker_execution", lower=lower, upper=upper)
    return result
