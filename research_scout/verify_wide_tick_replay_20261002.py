"""Independent raw-message and Decimal audit; no imports from replay code."""

import bisect
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research_scout/wide_tick_hft_20260930"
RUN = BASE / "replay_v1_20261002"
NS = 1_000_000_000
ERRORS = defaultdict(float)
COUNTS = Counter()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def near(actual, expected, field, tolerance=0.000002):
    error = abs(float(actual) - float(expected))
    ERRORS[field] = max(ERRORS[field], error)
    assert error < tolerance, (field, actual, expected, error)


def ns(stamp):
    whole, fraction = stamp.rstrip("Z").split(".")
    return int(datetime.fromisoformat(whole).replace(tzinfo=UTC).timestamp())*NS + int(fraction.ljust(9, "0"))


def read_raw(day, files, symbols):
    """Only this run's clean native streams are admitted by this audit."""
    books, trades, depths, marks = (defaultdict(list) for _ in range(4))
    last_book, last_depth, last_trade = {}, {}, {}
    seen_trades = defaultdict(dict)
    source_index, prior_capture = 0, -1
    channel_counts = defaultdict(Counter)
    for source in sorted(files, key=lambda x: x["offset"]):
        path = ROOT / source["path"]
        assert sha(path) == source["compressed_sha256"]
        decoded = hashlib.sha256()
        with gzip.open(path, "rb") as stream:
            for line in stream:
                decoded.update(line)
                source_index += 1
                assert line.strip(), "Disconnect requires separate source-problem audit"
                stamp, payload = line.decode().split(" ", 1)
                received = ns(stamp)
                assert stamp.startswith(day) and received >= prior_capture
                midnight = int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())*NS
                assert midnight+source["offset"]*60*NS <= received < midnight+(source["offset"]+10)*60*NS
                prior_capture = received
                e = json.loads(payload)["data"]
                s, kind = e["s"], e["e"]
                assert s in symbols
                channel_counts[s][kind] += 1
                publication = int(e["E"])*1_000_000
                assert -1_000_000 <= received-publication <= 5*NS
                if kind == "markPriceUpdate":
                    assert D(e["p"]).is_finite() and D(e["p"]) > 0 and D(e["r"]).is_finite()
                    marks[s].append((received, publication, int(e["T"])*1_000_000, source_index))
                    continue
                t = int(e["T"])*1_000_000
                assert -1_000_000 <= received-t <= 5*NS and t <= publication+1_000_000
                if kind == "bookTicker":
                    u = int(e["u"])
                    values = tuple(D(e[k]) for k in ("b", "a", "B", "A"))
                    assert all(x.is_finite() and x > 0 for x in values) and values[0] < values[1]
                    old = last_book.get(s)
                    if old:
                        assert (u > old[0] and t >= old[1]) or (u == old[0] and (t, values) == old[1:])
                    last_book[s] = (u, t, values)
                    books[s].append((t, received, source_index, u, *values, publication))
                elif kind == "depthUpdate":
                    u, pu = int(e["u"]), int(e["pu"])
                    if s in last_depth:
                        assert pu == last_depth[s][0] and u > pu and t >= last_depth[s][1]
                    last_depth[s] = (u, t)
                    sides = [{D(p): D(q) for p, q in e[k]} for k in ("b", "a")]
                    assert all(p.is_finite() and p > 0 and q.is_finite() and q >= 0 for side in sides for p, q in side.items())
                    depths[s].append((t, source_index, u, pu, *sides))
                elif kind == "trade":
                    identity = int(e["t"])
                    signature = tuple(e[k] for k in ("p", "q", "T", "m", "X"))
                    if identity in seen_trades[s]:
                        assert signature == seen_trades[s][identity]
                        channel_counts[s]["duplicate_trade_id"] += 1
                        continue
                    seen_trades[s][identity] = signature
                    if e["X"] in {"INSURANCE_FUND", "ADL", "NA"}:
                        channel_counts[s]["off_book_trades"] += 1
                        continue
                    assert e["X"] == "MARKET" and isinstance(e["m"], bool)
                    if s in last_trade:
                        assert identity > last_trade[s][0] and t >= last_trade[s][1]
                    last_trade[s] = (identity, t)
                    p, q = D(e["p"]), D(e["q"])
                    assert p.is_finite() and q.is_finite() and p > 0 and q > 0
                    trades[s].append((t, identity, source_index, p, q, e["m"]))
                else:
                    raise AssertionError(kind)
        assert decoded.hexdigest() == source["decoded_sha256"]
        COUNTS["native_files"] += 1
    COUNTS["native_messages"] += source_index
    data = {}
    for symbol in symbols:
        b = books[symbol]
        physical = sorted(b, key=lambda x: (x[0], x[3], x[2]))
        tr = sorted(trades[symbol], key=lambda x: (x[0], x[1]))
        dep = sorted(depths[symbol], key=lambda x: (x[0], x[2]))
        data[symbol] = {"book": b, "capture": [x[1] for x in b], "physical": physical,
                        "physical_times": [x[0] for x in physical], "trade": tr, "trade_times": [x[0] for x in tr],
                        "depth": dep, "depth_times": [x[0] for x in dep], "mark": marks[symbol],
                        "mark_capture": [x[0] for x in marks[symbol]]}
    return data, {s: dict(c) for s, c in channel_counts.items()}


def envelope(data, time, epsilon):
    times = data["physical_times"]
    before = bisect.bisect_left(times, time-epsilon)-1
    assert before >= 0 and time-epsilon-times[before] <= 5*NS
    first = bisect.bisect_left(times, times[before])
    last = bisect.bisect_right(times, time+epsilon)
    return data["physical"][first:last]


def check_fill(data, lower, upper, outer, buy, price, quantity, ahead, proofs):
    first = (bisect.bisect_left if outer else bisect.bisect_right)(data["trade_times"], lower)
    last = (bisect.bisect_right if outer else bisect.bisect_left)(data["trade_times"], upper)
    cumulative, hurdle, allocated = D(0), ahead, D(0)
    expected = []
    for t, identity, source, p, q, sell in data["trade"][first:last]:
        if sell != buy or (p > price if buy else p < price):
            continue
        if p < price if buy else p > price:
            hurdle = min(hurdle, cumulative)
        cumulative += q
        total = min(quantity, max(D(0), cumulative-hurdle))
        increment = total-allocated
        if increment > D("0.000000000001"):
            expected.append((identity, t, source, p, q, increment))
        allocated = total
        if allocated == quantity:
            break
    assert len(expected) == len(proofs), (len(expected), len(proofs))
    for raw, proof in zip(expected, proofs, strict=True):
        assert raw[:3] == (proof["id"], proof["transaction_ns"], proof["source_index"])
        for value, name in zip(raw[3:], ("source_price", "source_quantity", "filled_quantity"), strict=True):
            near(proof[name], value, name)
        COUNTS["native_fill_proofs"] += 1
    COUNTS["queue_volume_paths"] += 1
    return allocated


def verify_row(row, data, scenario, available_cash):
    decision = row["decision_ns"]
    delay, epsilon = scenario["delay_ns"], scenario["epsilon_ns"]
    arrival = decision+delay
    cancel = arrival+row["rest_seconds"]*NS
    flatten = cancel+2*delay
    assert (arrival, cancel, flatten) == (row["arrival_ns"], row["cancel_ns"], row["flatten_ns"])
    cutoff = decision-250_000_000
    source = bisect.bisect_left(data["capture"], cutoff)-1
    assert source >= 0
    signal = data["book"][source]
    t, received, source_index, update, bid, ask, bq, aq, publication = signal
    assert 0 < cutoff-received <= 5*NS and 0 < cutoff-t <= 5*NS
    assert t <= received+1_000_000 and publication <= received+1_000_000 and t <= publication+1_000_000
    supply = D(12) <= (ask-bid)*20000/(ask+bid) <= D(100) and min(bid*bq, ask*aq) >= 2000
    if not supply:
        assert row["status"] == "predecision_no_order" and row["reason"] == "signal_spread_or_depth_below_gate"
        assert row["net_low"] == row["net_high"] == 0
        COUNTS["causal_gate_rejections"] += 1
        return D(0), D(0), D(0)
    quantity = (min(D(200)/ask, bq/10, aq/10)//10)*10
    assert quantity*bid >= 100 and available_cash >= quantity*ask*D("1.01")
    mark_index = bisect.bisect_left(data["mark_capture"], cutoff)-1
    assert mark_index >= 0
    mc, mp, funding, _ = data["mark"][mark_index]
    assert 0 < cutoff-mc <= 5*NS and 0 < cutoff-mp <= 5*NS and funding > flatten+epsilon
    assert (source_index, received, t) == (row["signal_source_index"], row["signal_receive_ns"], row["signal_transaction_ns"])
    assert D(str(row["bid_limit"])) == bid and D(str(row["ask_limit"])) == ask
    assert row["intended_quantity"] == quantity
    reserved = quantity*ask*D("1.01")
    observed = envelope(data, arrival, epsilon)
    assert [b[2] for b in observed] == row["arrival_sources"]
    quantities = []
    for buy, name, price in ((True, "buy", bid), (False, "sell", ask)):
        accept = [price < b[5] if buy else price > b[4] for b in observed]
        if not any(accept):
            assert row[name+"_acceptance"] == "rejected" and row[name+"_quantity_bounds"] == [0, 0]
            quantities.append((D(0), D(0)))
            continue
        candidates = [bq if buy else aq]
        candidates += [b[6 if buy else 7] for b in observed if b[4 if buy else 5] == price]
        lo = bisect.bisect_left(data["depth_times"], t-epsilon)
        hi = bisect.bisect_right(data["depth_times"], arrival+epsilon)
        depth_slice = data["depth"][lo:hi]
        covering = any(x[3] <= update <= x[2] for x in depth_slice)
        assert covering or all(b[4 if buy else 5] == price for b in observed)
        proof_sources = []
        for event in depth_slice:
            if event[2] > update and price in event[4 if buy else 5]:
                candidates.append(event[4 if buy else 5][price])
                proof_sources.append(event[1])
        ahead = max(candidates)*D(str(scenario["queue_factor"]))
        near(row[name+"_queue_ahead"], ahead, "queue_ahead")
        assert row[name+"_queue_sources"] == proof_sources
        if all(accept):
            assert row[name+"_acceptance"] == "accepted"
            qlow = check_fill(data, arrival+epsilon, cancel-epsilon, False, buy, price, quantity, ahead, row[name+"_lower_fills"])
        else:
            assert row[name+"_acceptance"] == "bounded_acceptance" and row[name+"_lower_fills"] == []
            qlow = D(0)
        qhigh = check_fill(data, arrival-epsilon, cancel+epsilon, True, buy, price, quantity, ahead, row[name+"_upper_fills"])
        near(row[name+"_quantity_bounds"][0], qlow, "fill_quantity_low")
        near(row[name+"_quantity_bounds"][1], qhigh, "fill_quantity_high")
        assert qlow <= qhigh <= quantity
        quantities.append((qlow, qhigh))
    buy, sell = quantities
    long, short = max(D(0), buy[1]-sell[0]), max(D(0), sell[1]-buy[0])
    near(row["maximum_long_residual"], long, "long_residual")
    near(row["maximum_short_residual"], short, "short_residual")
    exit_prices = [(D(0), D(0))]
    if max(long, short) > D("0.0000000001"):
        exits = envelope(data, flatten, epsilon)
        enough = long <= min(b[6] for b in exits)+D("0.0000000001") and short <= min(b[7] for b in exits)+D("0.0000000001")
        if not enough:
            assert row["status"] == "unknown" and row["reason"] == "insufficient_forced_exit_depth"
            assert row["net_low"] is None and row["net_high"] is None
            COUNTS["correct_unknown_inventory"] += 1
            return None, None, reserved
        assert row["exit_sources"] == [b[2] for b in exits]
        exit_prices = [(b[4], b[5]) for b in exits]
    assert [[float(b), float(a)] for b, a in exit_prices] == row["exit_price_pairs"]
    assert all(not (arrival-epsilon <= m[2] <= flatten+epsilon) for m in data["mark"] if received <= m[0] <= flatten+epsilon)
    # Linear cashflow over two rectangles split by the zero-inventory diagonal.
    vertices = {(x, y) for x in buy for y in sell}
    intersection = max(buy[0], sell[0]), min(buy[1], sell[1])
    if intersection[0] <= intersection[1]:
        vertices |= {(q, q) for q in intersection}
    maker_cost = D(str(scenario["maker_bps"]))/10000
    taker_cost = D(str(scenario["taker_bps"]))/10000
    adverse_cost = D(str(scenario["adverse_bps"]))/10000
    values = []
    for bought, sold in vertices:
        for eb, ea in exit_prices:
            change = bought-sold
            exit_price = eb if change >= 0 else ea
            maker_notional = bought*bid+sold*ask
            taker_notional = abs(change)*exit_price
            gross = sold*ask + max(change, D(0))*eb - bought*bid - max(-change, D(0))*ea
            values.append(gross-maker_notional*(maker_cost+adverse_cost)-taker_notional*(taker_cost+adverse_cost))
    low, high = min(values), max(values)
    assert row["status"] == "bounded_complete"
    near(row["net_low"], low, "cash_low")
    near(row["net_high"], high, "cash_high")
    for label, bound in (("worst_cash", low), ("best_cash", high)):
        c = row[label]
        x, y, p = (D(str(c[k])) for k in ("buy_quantity", "sell_quantity", "exit_price"))
        assert buy[0]-D("0.000002") <= x <= buy[1]+D("0.000002") and sell[0]-D("0.000002") <= y <= sell[1]+D("0.000002")
        mn, tn = x*bid+y*ask, abs(x-y)*p
        gross = y*ask-x*bid+(x-y)*p
        checks = {"net": gross-mn*maker_cost-tn*taker_cost-(mn+tn)*adverse_cost,
                  "gross": gross, "fees": mn*maker_cost+tn*taker_cost, "adverse": (mn+tn)*adverse_cost,
                  "maker_notional": mn, "taker_notional": tn, "residual": x-y}
        for key, value in checks.items():
            near(c[key], value, "cash_proof_"+key)
        near(c["net"], bound, "cash_proof_extreme")
    COUNTS["cash_rectangles"] += 1
    return low, high, reserved


def main():
    freeze = json.loads((RUN/"implementation.json").read_text())
    results = json.loads((RUN/"results.json").read_text())
    spec = json.loads((BASE/"replay_specification.json").read_text())
    source_manifest = json.loads((BASE/"replay_manifest.json").read_text())
    ledgers = json.loads((RUN/"ledger_manifest.json").read_text())
    recorded_days = {(x["date"], x["rest_seconds"], x["scenario"]): x for x in json.loads((RUN/"daily_results.json").read_text())}
    diagnostic = {x["date"]: x for x in json.loads((RUN/"source_diagnostics.json").read_text())}
    for folder, expected in ((BASE, freeze["inputs_sha256"]), (ROOT, freeze["implementation_sha256"]), (RUN, results["artifacts_sha256"])):
        for name, digest in expected.items():
            assert sha(folder/name) == digest, name
    totals = defaultdict(lambda: [D(0), D(0), True])
    for cohort in spec["cohorts"]:
        day, symbols = cohort["date"], sorted(cohort["symbols"])
        data, counts = read_raw(day, [s for s in source_manifest["files"] if s["date"] == day], symbols)
        assert counts == diagnostic[day]["symbols"]
        for entry in (r for r in ledgers if r["date"] == day):
            path = RUN/entry["file"]
            assert sha(path) == entry["sha256"]
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            assert len(rows) == entry["rows"] == 28*len(symbols)
            scenario = freeze["execution_scenarios"][entry["scenario"]]
            cash_low, cash_high, stopped = D(10000), D(10000), False
            for n in range(28):
                reserved, batch = D(0), []
                for i, symbol in enumerate(symbols):
                    row = rows[n*len(symbols)+i]
                    assert row["symbol"] == symbol and row["date"] == day
                    assert (row["rest_seconds"], row["scenario"]) == (entry["rest_seconds"], entry["scenario"])
                    midnight = int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())*NS
                    assert row["decision_ns"] == midnight+(9*3600+(n+2)*60)*NS
                    if stopped:
                        assert row["status"] == "halted_after_unknown_inventory" and row["net_low"] is None and row["net_high"] is None
                        COUNTS["correct_halted_decisions"] += 1
                        continue
                    low, high, reserve = verify_row(row, data[symbol], scenario, cash_low-reserved)
                    reserved += reserve
                    batch.append((low, high))
                    COUNTS["decisions_independently_reconstructed"] += 1
                for low, high in batch:
                    if low is None:
                        stopped = True
                    else:
                        cash_low += low
                        cash_high += high
            saved = recorded_days[(day, entry["rest_seconds"], entry["scenario"])]
            assert saved["complete"] == (not stopped)
            assert saved["statuses"] == dict(Counter(r["status"] for r in rows))
            near(saved["closed_portion_net_low"], cash_low-10000, "day_closed_low")
            near(saved["closed_portion_net_high"], cash_high-10000, "day_closed_high")
            if stopped:
                assert saved["net_low"] is None and saved["net_high"] is None
            else:
                near(saved["net_low"], cash_low-10000, "day_full_low")
                near(saved["net_high"], cash_high-10000, "day_full_high")
            total = totals[(entry["rest_seconds"], entry["scenario"])]
            total[0] += cash_low-10000
            total[1] += cash_high-10000
            total[2] = total[2] and not stopped
            COUNTS["day_ledgers"] += 1
        print(json.dumps({"date": day, "verified_ledgers": COUNTS["day_ledgers"]}), flush=True)
    for row in results["scenario_results"]:
        low, high, complete = totals[(row["rest_seconds"], row["scenario"])]
        assert row["complete"] == complete
        near(row["closed_portion_net_low"], low, "scenario_closed_low")
        near(row["closed_portion_net_high"], high, "scenario_closed_high")
        if complete:
            near(row["net_low"], low, "scenario_full_low")
            near(row["net_high"], high, "scenario_full_high")
        else:
            assert row["net_low"] is None and row["net_high"] is None
    assert COUNTS["native_messages"] == results["source_native_messages"] == 2212109
    assert COUNTS["day_ledgers"] == 120
    assert COUNTS["decisions_independently_reconstructed"]+COUNTS["correct_halted_decisions"] == 8736
    verification = {"verified_at_utc": datetime.now(UTC).isoformat(), "passed": True,
                    "scope": "Independent native parsing, causal gates, queue-volume allocation, partial-fill bounds, Decimal cashflow extrema, capital reservation, whole-date unknown halt and aggregate reconciliation for this frozen public-tape model.",
                    "counts": dict(COUNTS), "max_absolute_errors": dict(ERRORS),
                    "auditor_sha256": sha(Path(__file__)), "results_sha256": sha(RUN/"results.json"),
                    "actual_execution_verified": False, "historical_order_filters_verified": False,
                    "independent_public_tape_accounting_verified": True, "reliable_edge_established": False}
    with (RUN/"independent_verification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(verification, indent=2)+"\n")
    print(json.dumps(verification), flush=True)


if __name__ == "__main__":
    main()
