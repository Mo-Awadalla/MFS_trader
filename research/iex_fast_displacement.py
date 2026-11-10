"""Past-only trade-confirmed displacement on atomic native IEX DEEP books."""

from collections import Counter, defaultdict, deque
from decimal import Decimal

from research.iex_deep_supply import Book, deep_message, deep_segment
from research.iex_native_prefix import inflate_prefix, packets, udp_payload

NS = 1_000_000_000
D = Decimal


def fresh(row, cutoff, age):
    return row is not None and 0 < cutoff - row["capture_ns"] <= age and (
        0 <= cutoff - row["event_ns"] <= age and row["send_ns"] <= cutoff)


def admission(symbol, current, reference, flow, broken, cutoff):
    """No future references; exact prices, sizes and clocks. Return rejection or candidate."""
    if not (symbol.isascii() and symbol.isalpha() and symbol.isupper() and 1 <= len(symbol) <= 5):
        return "symbol", None
    if reference is None:
        return "no_reference", None
    if current["test"] or reference["test"]:
        return "test_security", None
    if any(s["h"] != 84 or s["o"] != 78 for s in (current, reference)):
        return "trading_status", None
    if current["pending"] or reference["pending"]:
        return "atomic_event_pending", None
    now, old = current["trade"], reference["trade"]
    if not fresh(now, cutoff, 100_000_000) or not fresh(old, cutoff - NS, 250_000_000):
        return "trade_age", None
    if (symbol, now["trade_id"]) in broken or (symbol, old["trade_id"]) in broken:
        return "broken_anchor_or_current_trade", None
    change = now["price"] - old["price"]
    if abs(change) * 10000 < 30 * old["price"]:
        return "move_below_30bp", None
    active = [r for r in flow if cutoff - NS <= r["event_ns"] <= cutoff]
    ids = [r["trade_id"] for r in active]
    if len(ids) != len(set(ids)):
        raise ValueError("Repeated unbroken trade ID in active signal window")
    distinct = len({r["event_ns"] for r in active})
    notional = sum(r["price"] * r["size"] for r in active)
    if distinct < 5 or notional < 25000 * 10000:
        return "one_second_activity", None
    q, prior = current["quote"], reference["quote"]
    if not fresh(q, cutoff, 250_000_000) or not fresh(prior, cutoff - NS, 250_000_000):
        return "quote_age", None
    for quote, trade, cap in ((q, now, 5), (prior, old, 50)):
        bid, ask = quote["bid_price"], quote["ask_price"]
        if not (50000 <= bid < ask <= 10000000 and bid % 100 == ask % 100 == 0):
            return "invalid_quote_price", None
        if min(quote["bid_size"], quote["ask_size"]) <= 0:
            return "empty_touch", None
        if (ask - bid) * 20000 > cap * (ask + bid):
            return "spread", None
        if not bid <= trade["price"] <= ask:
            return "trade_outside_quote", None
    sign = 1 if change > 0 else -1
    if min(sign * (q[k] - prior[k]) for k in ("bid_price", "ask_price")) <= 0:
        return "book_not_confirming", None
    # Whole-cent buy limit 2% above the observed ask; quantity cannot exceed $10,000 there.
    limit = ((q["ask_price"] * 102 + 9999) // 10000) * 100
    quantity = min(10000 * 10000 // limit, q["bid_size"] // 10, q["ask_size"] // 10)
    if quantity <= 0:
        return "quantity", None
    entry, sale = D(quantity * q["ask_price"]) / 10000, D(quantity * q["bid_price"]) / 10000
    fees = 2 * max(D(1), D(".005") * quantity) + D(".00003") * sale + D(".000166") * quantity
    adverse = D(".0001") * (entry + sale)
    cost = entry - sale + fees + adverse
    cost_bp, move_bp = cost * 10000 / entry, D(abs(change) * 10000) / old["price"]
    if cost_bp > 12 or move_bp < 3 * cost_bp:
        return "causal_cost_hurdle", None
    return "candidate", {
        "symbol": symbol, "rule": "follow_rise" if sign > 0 else "fade_fall",
        "decision_ns": cutoff + 1_000_000, "cutoff_ns": cutoff,
        "quantity": quantity, "entry_limit": limit, "current": current, "reference": reference,
        "active_trades": active, "distinct_trade_times": distinct, "notional_units": notional,
        "move_bp": str(move_bp), "causal_cost_usd": str(cost), "causal_cost_bp": str(cost_bp),
        "rank_margin_bp": str(move_bp - 3 * cost_bp),
    }


def choose(candidates, state):
    """One $10k slot per rule; six-second global and thirty-second symbol cooldowns."""
    chosen = []
    for rule in ("follow_rise", "fade_fall"):
        eligible = []
        old = state.setdefault(rule, {"last": -10**30, "symbols": {}, "count": 0})
        for r in candidates:
            if r["rule"] != rule or old["count"] >= 6:
                continue
            t = r["decision_ns"]
            if t - old["last"] < 6 * NS or t - old["symbols"].get(r["symbol"], -10**30) < 30 * NS:
                continue
            eligible.append(r)
        eligible.sort(key=lambda r: (-D(r["rank_margin_bp"]), -r["notional_units"], r["symbol"]))
        if eligible:
            r = eligible[0]
            old["last"] = r["decision_ns"]
            old["symbols"][r["symbol"]] = r["decision_ns"]
            old["count"] += 1
            chosen.append(r)
    return chosen


class State:
    def __init__(self, first_decision, final_decision):
        self.first, self.last = first_decision, final_decision
        self.cutoff = first_decision - NS - 1_000_000
        self.books, self.flow = defaultdict(Book), defaultdict(deque)
        self.h, self.o, self.directory, self.broken = {}, {}, {}, set()
        self.history, self.selection = deque(maxlen=11), {}
        self.outcomes, self.types = Counter(), Counter()
        self.candidates, self.selected = [], []
        self.max_clock, self.messages, self.grids, self.symbol_grids = -1, 0, 0, 0

    def apply(self, row):
        self.messages += 1
        self.types[row["type"]] += 1
        self.max_clock = max(self.max_clock, row["event_ns"], row["send_ns"])
        symbol, kind = row.get("symbol"), row["type"]
        if symbol is None:
            return
        if kind in ("8", "5"):
            self.books[symbol].update(row)
        elif kind == "H":
            self.h[symbol] = row["flags"]
        elif kind == "O":
            self.o[symbol] = row["flags"]
        elif kind == "D":
            self.directory[symbol] = bool(row["flags"] & 128)
        elif kind == "B":
            self.broken.add((symbol, row["trade_id"]))
        elif (kind == "T" and row["capture_ns"] >= self.first - 1_251_000_000
              and not row["flags"] & 0x58 and min(row["price"], row["size"]) > 0):
            self.flow[symbol].append(row)

    def advance(self, capture):
        while capture >= self.cutoff and self.cutoff <= self.last - 1_000_000:
            if self.max_clock > self.cutoff:
                raise ValueError("Native event/send clock crosses decision information cutoff")
            snap, flows = {}, {}
            for symbol, queue in self.flow.items():
                while queue and queue[0]["capture_ns"] < self.cutoff - 1_250_000_000:
                    queue.popleft()
                flows[symbol] = [r for r in queue if (symbol, r["trade_id"]) not in self.broken]
            for symbol, book in self.books.items():
                trades = flows.get(symbol, [])
                snap[symbol] = {"quote": book.quote, "pending": book.pending_event_ns is not None,
                                "h": self.h.get(symbol), "o": self.o.get(symbol),
                                "test": self.directory.get(symbol, False),
                                "trade": trades[-1] if trades else None}
            self.history.append((self.cutoff, snap))
            if self.cutoff >= self.first - 1_000_000:
                self.grids += 1
                assert self.history[0][0] == self.cutoff - NS
                reference = self.history[0][1]
                candidates = []
                for symbol, current in snap.items():
                    self.symbol_grids += 1
                    reason, detail = admission(symbol, current, reference.get(symbol),
                                               flows.get(symbol, []), self.broken, self.cutoff)
                    self.outcomes[reason] += 1
                    if detail is not None:
                        candidates.append(detail)
                self.candidates.extend(candidates)
                self.selected.extend(choose(candidates, self.selection))
            self.cutoff += 100_000_000


def screen(path, first_decision, final_decision):
    data, complete = inflate_prefix(path)
    stats, streams, event_clock = Counter(), {}, {}
    state = State(first_decision, final_decision)
    previous, covered = -1, False
    for capture, frame in packets(data, stats, allow_partial=not complete):
        if capture < previous:
            raise ValueError("Capture clock reversal")
        previous = capture
        state.advance(capture)
        if state.cutoff > final_decision - 1_000_000:
            covered = True
            break
        key, seq, offset, length, sent, native = deep_segment(udp_payload(frame))
        if (seq, offset) != streams.get(key, (1, 0)):
            raise ValueError("Native sequence or byte-offset discontinuity")
        streams[key] = seq + len(native), offset + length
        for i, raw in enumerate(native):
            row = deep_message(raw)
            row.update(capture_ns=capture, send_ns=sent, sequence=seq + i)
            clock_key = (row["type"], row.get("symbol"))
            if row["event_ns"] < event_clock.get(clock_key, -1):
                raise ValueError("Per-type/symbol native clock reversal")
            event_clock[clock_key] = row["event_ns"]
            state.apply(row)
    return {"covered": covered, "last_capture_ns": previous, "full_gzip_checksum_verified": complete,
            "source_messages_checked": state.messages, "types": dict(state.types),
            "decision_grids": state.grids, "symbol_grids": state.symbol_grids,
            "outcomes": dict(state.outcomes), "candidates": state.candidates, "selected": state.selected,
            "returns_calculated": False, "actual_execution_verified": False}
