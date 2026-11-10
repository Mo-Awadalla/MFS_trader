"""Independently reconstruct native grid buckets and every spot/perp screen flag."""

import bisect
import calendar
import gzip
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path
from statistics import median

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/spot_perp_hft_20261002"
N = 1_000_000_000


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rebuild(path, day, derivative):
    midnight = calendar.timegm(datetime.strptime(day, "%Y-%m-%d").timetuple()) * N
    start = midnight + 32400 * N
    cuts = [start + i * N - 250_000_000 for i in range(60)]
    changes = [{} for _ in range(61)]
    identity, symbols, counts = {}, set(), Counter()
    last = start - 1
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for number, line in enumerate(stream):
            if not line.strip():
                counts["disconnects"] += 1
                slot = bisect.bisect_right(cuts, last)
                for symbol in symbols:
                    changes[slot][symbol] = None
                identity.clear()
                continue
            timestamp, encoded = line.strip().split(" ", 1)
            whole, fraction = timestamp[:-1].split(".") if "." in timestamp else (timestamp[:-1], "0")
            second = calendar.timegm(datetime.strptime(whole, "%Y-%m-%dT%H:%M:%S").timetuple())
            receive = second * N + int(fraction.ljust(9, "0"))
            assert start <= receive < start + 60 * N and receive >= last
            last = receive
            counts["native_messages"] += 1
            envelope = json.loads(encoded)
            if envelope.get("stream", "").rsplit("@", 1)[-1] != "bookTicker":
                continue
            counts["book_messages"] += 1
            raw = envelope["data"]
            symbol = raw["s"]
            if not symbol.endswith("USDT") or not symbol.isalnum():
                continue
            symbols.add(symbol)
            update = int(raw["u"])
            fields = (raw["b"], raw["B"], raw["a"], raw["A"])
            if derivative:
                fields += (str(raw["T"]), str(raw["E"]))
            old = identity.get(symbol)
            if old == (update, fields):
                counts["exact_duplicate_books"] += 1
                continue
            valid_sequence = old is None or update > old[0]
            if valid_sequence:
                identity[symbol] = (update, fields)
            else:
                counts["conflicting_or_regressing_books"] += 1
            # Tuple layout differs from the production dictionaries.
            row = (receive, number, update, D(raw["b"]), D(raw["a"]),
                   D(raw["B"]), D(raw["A"]), valid_sequence,
                   int(raw["T"]) * 1_000_000 if derivative else None,
                   int(raw["E"]) * 1_000_000 if derivative else None)
            changes[bisect.bisect_right(cuts, receive)][symbol] = row
    running, samples = {}, []
    for bucket in changes[:60]:
        running.update(bucket)
        samples.append(dict(running))
    return samples, symbols, counts, start


def reason(state, clock):
    if state is None:
        return "missing_book"
    receive, _, _, bid, ask, bid_size, ask_size, ordered, match, public = state
    if not ordered:
        return "conflicting_or_regressing_id"
    if not all(x.is_finite() and x > 0 for x in (bid, ask, bid_size, ask_size)) or bid >= ask:
        return "invalid_values"
    if receive >= clock - 250_000_000 or not 0 < clock - receive <= N:
        return "capture_freshness_gate"
    if match is not None and (not 0 < clock - match <= N or not 0 < clock - public <= N
                              or match - public > 1_000_000
                              or max(match, public) - receive > 1_000_000):
        return "perpetual_clock_gate"
    return None


def evaluate(spot, perp, present, start, symbol, second):
    clock = start + second * N
    a, b = spot[second].get(symbol), perp[second].get(symbol)
    result = {"raw_eligible": False}
    if not present:
        return result, "missing_spot_symbol"
    for name, quote in (("spot", a), ("perpetual", b)):
        fail = reason(quote, clock)
        if fail:
            return result, name + "_" + fail
    result.update(spot_source_line=a[1], perpetual_source_line=b[1])
    history = []
    for i in range(second - 10, second):
        past_a, past_b = spot[i].get(symbol), perp[i].get(symbol)
        if reason(past_a, start + i * N) is None and reason(past_b, start + i * N) is None:
            history.append((past_b[3] + past_b[4]) / (past_a[3] + past_a[4]))
    result["anchor_observations"] = len(history)
    if len(history) < 8:
        return result, "insufficient_fresh_anchor"
    center = median(history)
    dispersion = median([abs(x - center) / center * 10000 for x in history])
    reference_price = (a[3] + a[4]) / 2 * center
    current_mid = (b[3] + b[4]) / 2
    delta = (current_mid - reference_price) / reference_price * 10000
    # The frozen specification defines the gap as a ratio minus one. Retain
    # that 28-digit Decimal comparison for direction when division rounds an
    # economically zero difference to exactly one; audit its magnitude using
    # the separate subtract-then-divide expression above.
    sign = -1 if current_mid / reference_price > 1 else 1
    entry = b[3] if sign < 0 else b[4]
    future = reference_price - sign * (b[4] - b[3]) / 2
    potential_net = sign * (future - entry) - (entry + future) * D(7) / 10000
    result.update(reference_ratio=center, anchor_mad_bps=dispersion, gap_bps=delta,
                  direction=sign, entry_quote=entry, projected_exit_quote=future,
                  projected_budget_bps=potential_net * 10000 / entry)
    if dispersion > 10:
        return result, "unstable_anchor"
    if abs(delta) < 25:
        return result, "gap_below_25bp"
    depth = min(q[3] * q[5] for q in (a, b))
    depth = min(depth, *(q[4] * q[6] for q in (a, b)))
    result["minimum_touch_notional"] = depth
    if depth < 2000:
        return result, "insufficient_displayed_depth"
    if result["projected_budget_bps"] <= 5:
        return result, "convergence_budget_below_buffer"
    result["raw_eligible"] = True
    return result, "requires_consecutive_confirmation"


def main():
    specification = json.loads((OUT / "specification.json").read_text())
    implementation = json.loads((OUT / "screen_implementation.json").read_text())
    results = json.loads((OUT / "screen_results.json").read_text())
    assert sha(OUT / "specification.json") == implementation["specification_sha256"]
    assert sha(ROOT / "research/spot_perp_supply.py") == implementation["module_sha256"]
    assert sha(OUT / "grid_states.parquet") == results["grid_states_sha256"]
    assert sha(OUT / "selected.parquet") == results["selected_sha256"]
    manifests = {}
    for venue, path in (("spot", OUT / "spot_manifest.json"),
                        ("perpetual", ROOT / specification["perpetual_manifest"])):
        assert sha(path) == implementation[venue + "_manifest_sha256"]
        manifests[venue] = {r["date"]: r for r in json.loads(path.read_text())["files"]}
    frame = pd.read_parquet(OUT / "grid_states.parquet")
    counts, source_counts, reasons = Counter(), Counter(), Counter()
    largest_difference = D(0)
    selected_rows = []
    for day in specification["dates"]:
        rebuilt = {}
        for venue in ("spot", "perpetual"):
            record = manifests[venue][day]
            path = ROOT / record["path"]
            assert record["complete"] and sha(path) == record["compressed_sha256"]
            rebuilt[venue] = rebuild(path, day, venue == "perpetual")
            source_counts.update({venue + "_" + k: v for k, v in rebuilt[venue][2].items()})
            counts["source_files_verified"] += 1
        spot, spot_symbols, _, start = rebuilt["spot"]
        perp, perp_symbols, _, _ = rebuilt["perpetual"]
        indexed = frame.loc[frame.date.eq(day)].set_index(["symbol", "second"])
        assert len(indexed) == len(perp_symbols) * 50
        for symbol in sorted(perp_symbols):
            previous, already_selected = None, False
            for second in range(10, 60):
                wanted, label = evaluate(spot, perp, symbol in spot_symbols, start, symbol, second)
                chosen = False
                if (wanted["raw_eligible"] and previous and previous["raw_eligible"]
                        and wanted["direction"] == previous["direction"]):
                    chosen = not already_selected
                    label = "selected_for_native_execution_review" if chosen else "one_event_per_symbol_date"
                    already_selected = True
                wanted.update(reason=label, selected=chosen, decision_ns=start + second * N)
                stored = indexed.loc[(symbol, second)]
                for key, value in wanted.items():
                    if isinstance(value, D):
                        difference = abs(value - D(str(stored[key])))
                        largest_difference = max(largest_difference, difference)
                        assert difference < D("1e-10"), (day, symbol, second, key, difference)
                    else:
                        assert stored[key] == value, (day, symbol, second, key, stored[key], value)
                previous = wanted
                reasons[label] += 1
                counts["grid_decisions_verified"] += 1
                counts["raw_eligible_grids_verified"] += int(wanted["raw_eligible"])
                if chosen:
                    selected_rows.append((day, symbol, second))
        print(json.dumps({"date": day, "verified_grid_rows": len(indexed)}), flush=True)
    assert dict(source_counts) == results["source_counts"]
    assert dict(reasons) == results["reasons"]
    assert len(selected_rows) == results["selected_events"]
    selected = pd.read_parquet(OUT / "selected.parquet")
    assert list(selected[["date", "symbol", "second"]].itertuples(index=False, name=None)) == selected_rows
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
             "counts": dict(counts), "source_counts": dict(source_counts),
             "maximum_numeric_difference": str(largest_difference),
             "results_sha256": sha(OUT / "screen_results.json"), "auditor_sha256": sha(__file__),
             "scope": "Separate native-message parser, capture-time bucket construction, Decimal reference/dispersion/cost calculations and all grid/selection flags. No production screen imports.",
             "future_returns_evaluated": False, "actual_execution_verified": False,
             "reliable_edge_established": False}
    with (OUT / "independent_verification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
