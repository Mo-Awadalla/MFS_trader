"""Independent source/book/grid/predicate reconstruction of the displacement admission."""

import argparse
import json
from collections import Counter, defaultdict, deque
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from research_scout.audit_iex_deep_20261002 import native
from research_scout.prepare_iex_fast_20261002 import OUT, ROOT, sha, write


def check(symbol, a, b, trades, broken, t):
    def recent(r, at, limit):
        return r is not None and at - limit <= r["capture_ns"] < at and (
            at - limit <= r["event_ns"] <= at and r["send_ns"] <= at)

    if not (1 <= len(symbol) <= 5 and all("A" <= char <= "Z" for char in symbol)):
        return "symbol", None
    if b is None:
        return "no_reference", None
    if a["test"] or b["test"]:
        return "test_security", None
    if (a["h"], a["o"], b["h"], b["o"]) != (84, 78, 84, 78):
        return "trading_status", None
    if a["pending"] or b["pending"]:
        return "atomic_event_pending", None
    x, y = a["trade"], b["trade"]
    if not recent(x, t, 100000000) or not recent(y, t - 1000000000, 250000000):
        return "trade_age", None
    if (symbol, x["trade_id"]) in broken or (symbol, y["trade_id"]) in broken:
        return "broken_anchor_or_current_trade", None
    delta = x["price"] - y["price"]
    if 10000 * abs(delta) < y["price"] * 30:
        return "move_below_30bp", None
    active = [r for r in trades if t - 1000000000 <= r["event_ns"] <= t]
    assert len({r["trade_id"] for r in active}) == len(active)
    timestamps = {r["event_ns"] for r in active}
    dollars_units = sum(r["size"] * r["price"] for r in active)
    if len(timestamps) < 5 or dollars_units < 250000000:
        return "one_second_activity", None
    qa, qb = a["quote"], b["quote"]
    if not recent(qa, t, 250000000) or not recent(qb, t - 1000000000, 250000000):
        return "quote_age", None
    for quote, trade, spread_cap in ((qa, x, 5), (qb, y, 50)):
        bid, ask = quote["bid_price"], quote["ask_price"]
        if bid < 50000 or ask > 10000000 or bid >= ask or bid % 100 or ask % 100:
            return "invalid_quote_price", None
        if quote["bid_size"] <= 0 or quote["ask_size"] <= 0:
            return "empty_touch", None
        if 20000 * (ask - bid) > spread_cap * (bid + ask):
            return "spread", None
        if trade["price"] < bid or trade["price"] > ask:
            return "trade_outside_quote", None
    up = delta > 0
    if up and (qa["bid_price"] <= qb["bid_price"] or qa["ask_price"] <= qb["ask_price"]):
        return "book_not_confirming", None
    if not up and (qa["bid_price"] >= qb["bid_price"] or qa["ask_price"] >= qb["ask_price"]):
        return "book_not_confirming", None
    cents, rem = divmod(qa["ask_price"] * 102, 10000)
    limit = (cents + bool(rem)) * 100
    quantity = min(100000000 // limit, qa["bid_size"] // 10, qa["ask_size"] // 10)
    if quantity < 1:
        return "quantity", None
    buy = Decimal(qa["ask_price"] * quantity) / 10000
    sell = Decimal(qa["bid_price"] * quantity) / 10000
    commission = max(Decimal("1"), Decimal(quantity) / 200)
    costs = buy - sell + commission + commission
    costs += (buy + sell) / 10000 + sell * Decimal(".00003") + Decimal(quantity) * Decimal(".000166")
    # The frozen engine divides the final numerator, so preserve its stated Decimal order.
    bp = costs * 10000 / buy
    move = Decimal(abs(delta) * 10000) / y["price"]
    if bp > 12 or move < 3 * bp:
        return "causal_cost_hurdle", None
    return "candidate", {"symbol": symbol, "rule": "follow_rise" if up else "fade_fall",
                          "decision_ns": t + 1000000, "cutoff_ns": t, "quantity": quantity,
                          "entry_limit": limit, "current": a, "reference": b,
                          "active_trades": active, "distinct_trade_times": len(timestamps),
                          "notional_units": dollars_units, "move_bp": str(move),
                          "causal_cost_usd": str(costs), "causal_cost_bp": str(bp),
                          "rank_margin_bp": str(move - 3 * bp)}


def audit(day, folder=OUT):
    result_path = folder / "screen_results.json"
    results = json.loads(result_path.read_text())
    observed_path = folder / "sessions" / (day + ".json")
    assert sha(observed_path) == results["session_hashes"][day]
    expected = json.loads(observed_path.read_text())
    spec = json.loads((folder / "specification.json").read_text())
    src = spec["sources"][day]
    path = Path(src["prefix_path"])
    assert sha(path) == src["prefix_sha256"] and expected["source"] == src
    begin, end = src["first_decision_ns"] - 1000000, src["final_decision_ns"] - 1000000
    next_cut = begin - 1000000000
    levels, pending, quotes = {}, {}, {}
    h, o, test, broken = {}, {}, {}, set()
    trades, history = defaultdict(deque), deque(maxlen=11)
    outcomes, types, candidates, selected = Counter(), Counter(), [], []
    symbol_grids = grids = 0
    maximum_clock = -1

    def advance(capture):
        nonlocal next_cut, grids, symbol_grids
        while next_cut <= end and next_cut <= capture:
            assert maximum_clock <= next_cut
            active = {}
            for symbol, rows in trades.items():
                while rows and rows[0]["capture_ns"] < next_cut - 1250000000:
                    rows.popleft()
                active[symbol] = [r for r in rows if (symbol, r["trade_id"]) not in broken]
            snapshot = {}
            for symbol in levels:
                live = active.get(symbol, [])
                snapshot[symbol] = {"quote": quotes.get(symbol), "pending": symbol in pending,
                                    "h": h.get(symbol), "o": o.get(symbol), "test": test.get(symbol, False),
                                    "trade": live[-1] if live else None}
            history.append((next_cut, snapshot))
            if next_cut >= begin:
                assert history[0][0] == next_cut - 1000000000
                grids += 1
                choices = []
                for symbol, current in snapshot.items():
                    symbol_grids += 1
                    reason, r = check(symbol, current, history[0][1].get(symbol), active.get(symbol, []), broken, next_cut)
                    outcomes[reason] += 1
                    if r is not None:
                        choices.append(r)
                candidates.extend(choices)
                for rule in ("follow_rise", "fade_fall"):
                    prior = [r for r in selected if r["rule"] == rule]
                    eligible = [r for r in choices if r["rule"] == rule and len(prior) < 6
                                and all(r["decision_ns"] - p["decision_ns"] >= 6000000000 for p in prior)
                                and all(r["decision_ns"] - p["decision_ns"] >= 30000000000
                                        for p in prior if p["symbol"] == r["symbol"])]
                    eligible.sort(key=lambda r: (-Decimal(r["rank_margin_bp"]), -r["notional_units"], r["symbol"]))
                    selected.extend(eligible[:1])
            next_cut += 100000000

    for row in native(path, end):
        capture, name, symbol = row.get("capture_ns"), row["type"], row.get("symbol")
        if capture is not None:
            advance(capture)
        maximum_clock = max(maximum_clock, row["event_ns"], row.get("send_ns", -1))
        types[name] += 1
        if symbol is None:
            continue
        if name in ("8", "5"):
            if symbol not in levels:
                levels[symbol] = {"8": {}, "5": {}}
            assert symbol not in pending or pending[symbol] == row["event_ns"]
            pending[symbol] = row["event_ns"]
            side = levels[symbol][name]
            if row["size"]:
                side[row["price"]] = row["size"]
            else:
                assert row["price"] in side
                del side[row["price"]]
            if row["flags"] == 1:
                del pending[symbol]
                bid, ask = max(levels[symbol]["8"], default=0), min(levels[symbol]["5"], default=0)
                quotes[symbol] = {"type": "derived_deep_bbo", "flags": 0, "symbol": symbol,
                                  "bid_price": bid, "ask_price": ask,
                                  "bid_size": levels[symbol]["8"].get(bid, 0),
                                  "ask_size": levels[symbol]["5"].get(ask, 0),
                                  "event_ns": row["event_ns"], "capture_ns": row["capture_ns"],
                                  "send_ns": row["send_ns"], "sequence": row["sequence"],
                                  "native_final_update": row}
        elif name == "H":
            h[symbol] = row["flags"]
        elif name == "O":
            o[symbol] = row["flags"]
        elif name == "D":
            test[symbol] = bool(row["flags"] & 128)
        elif name == "B":
            broken.add((symbol, row["trade_id"]))
        elif (name == "T" and capture >= begin - 1250000000 and not row["flags"] & 88
              and row["price"] > 0 and row["size"] > 0):
            trades[symbol].append(row)
    advance(end)
    assert grids == expected["decision_grids"] == (end - begin) // 100000000 + 1
    assert symbol_grids == expected["symbol_grids"]
    assert dict(outcomes) == expected["outcomes"]
    assert dict(types) == expected["types"] and sum(types.values()) == expected["source_messages_checked"]
    # Compare Decimal values numerically to avoid treating trailing zero spelling as a mismatch.
    def comparable(rows):
        return [{k: Decimal(v) if k in ("move_bp", "causal_cost_usd", "causal_cost_bp", "rank_margin_bp") else v
                 for k, v in r.items()} for r in rows]
    assert comparable(candidates) == comparable(expected["candidates"])
    assert comparable(selected) == comparable(expected["selected"])
    return {"date": day, "messages": sum(types.values()), "symbol_grids": symbol_grids,
            "candidates": len(candidates), "selected": len(selected), "session_sha256": sha(observed_path)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", type=Path, default=OUT)
    folder = parser.parse_args().folder
    results = json.loads((folder / "screen_results.json").read_text())
    assert not results["errors"] and results["intact_dates_screened"] == 23
    assert results["specification_sha256"] == sha(folder / "specification.json")
    jobs, errors = [], []
    with ProcessPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(audit, day, folder): day for day in results["session_hashes"]}
        for future in as_completed(futures):
            try:
                row = future.result()
                jobs.append(row)
                print(json.dumps(row), flush=True)
            except Exception as exc:
                failure = {"date": futures[future], "error": f"{type(exc).__name__}: {exc}"}
                errors.append(failure)
                print(json.dumps(failure), flush=True)
    assert not errors, errors
    report = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
              "dates_verified": len(jobs), "source_messages_verified": sum(r["messages"] for r in jobs),
              "symbol_grids_verified": sum(r["symbol_grids"] for r in jobs),
              "candidates_verified": sum(r["candidates"] for r in jobs),
              "selected_verified": sum(r["selected"] for r in jobs),
              "results_sha256": sha(folder / "screen_results.json"), "auditor_sha256": sha(Path(__file__)),
              "independent_decoder_sha256": sha(ROOT / "research_scout/audit_iex_deep_20261002.py"),
              "sessions": sorted(jobs, key=lambda r: r["date"]),
              "actual_execution_verified": False, "returns_calculated": False,
              "scope": "Full independent native source, capture grids, atomic books, trade activity, costs and causal ranking. No execution or future returns."}
    assert report["source_messages_verified"] == results["source_messages_checked"]
    assert report["symbol_grids_verified"] == results["symbol_grids"]
    assert report["candidates_verified"] == results["candidate_count"]
    assert report["selected_verified"] == len(results["selected"])
    write(folder / "independent_verification.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "sessions"}), flush=True)


if __name__ == "__main__":
    main()
