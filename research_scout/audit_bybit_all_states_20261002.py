"""Independent source/as-of reconstruction and funding-screen arithmetic audit."""

import gzip
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"research_scout/bybit_funding_hft_20261002"
OLD = ROOT/"research_scout/funding_universe_hft_20260930"
FIELDS = ["exchange", "symbol", "timestamp", "local_timestamp", "funding_timestamp", "funding_rate", "mark_price"]


def sha(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b""):
            result.update(block)
    return result.hexdigest()


def capture(stamp):
    seconds, fraction = stamp.removesuffix("Z").split(".")
    return int(datetime.fromisoformat(seconds).replace(tzinfo=UTC).timestamp())*1_000_000_000 + int(fraction.ljust(9, "0"))


def decimal(value):
    return None if value is None or pd.isna(value) or value == "" else D(str(value))


def equal(actual, expected, key):
    a, b = decimal(actual), decimal(expected)
    if a is None or b is None:
        assert a is b, (key, actual, expected)
    else:
        tolerance = D("1e-12") if key == "funding_rate" else abs(a)*D("1e-10") if key == "mark_price" else D(0)
        assert abs(a-b) <= tolerance, (key, actual, expected)


def audit_csv(source):
    path = ROOT/source["path"]
    assert sha(path) == source["sha256"]
    saved_path = ROOT/source["extraction"]
    assert sha(saved_path) == source["extraction_sha256"]
    saved = json.loads(saved_path.read_text())
    cutoffs = {int(k): v for k, v in saved["cutoffs_us"].items()}
    last = {h: {} for h in cutoffs}
    count, previous = 0, -1
    types = dict.fromkeys(FIELDS, "str")
    types.update(timestamp="int64", local_timestamp="int64")
    for block in pd.read_csv(path, usecols=FIELDS, dtype=types, chunksize=300_000):
        clock = block.local_timestamp.to_numpy(np.int64)
        assert clock[0] >= previous and np.all(clock[1:] >= clock[:-1])
        assert block.exchange.eq("bybit").all()
        previous = int(clock[-1])
        for hour, cutoff in cutoffs.items():
            length = int(np.searchsorted(clock, cutoff, side="left"))
            if not length:
                continue
            # Independent reduction: scatter source indices by symbol and take
            # each group's maximum; no production drop-duplicate helper.
            codes, symbols = pd.factorize(block.symbol.iloc[:length], sort=False)
            positions = np.full(len(symbols), -1, dtype=np.int64)
            np.maximum.at(positions, codes, np.arange(length))
            for position in positions:
                row = block.iloc[int(position)]
                if not row.symbol.endswith("USDT"):
                    continue
                last[hour][row.symbol] = {
                    "source_position": count+int(position), "receive_us": int(row.local_timestamp), "event_us": int(row.timestamp),
                    "funding_time_us": None if pd.isna(row.funding_timestamp) else int(D(row.funding_timestamp)),
                    "funding_rate": None if pd.isna(row.funding_rate) else row.funding_rate,
                    "mark_price": None if pd.isna(row.mark_price) else row.mark_price}
        count += len(block)
        if clock[-1] >= max(cutoffs.values()):
            break
    for hour, values in last.items():
        assert set(values) == set(saved["states"][str(hour)])
        for symbol, actual in values.items():
            expected = saved["states"][str(hour)][symbol]
            for key, value in actual.items():
                equal(value, expected[key], key)
    result = {"date": source["date"], "source_hash_verified": True, "prefix_rows_scanned": count,
              "states_verified": sum(len(v) for v in last.values())}
    return result, last


def native_states(source, cutoff, bybit):
    path = ROOT/source["path"]
    assert sha(path) == source["compressed_sha256"]
    raw = gzip.decompress(path.read_bytes())
    assert hashlib.sha256(raw).hexdigest() == source["decoded_sha256"]
    state, seen, previous, messages = {}, set(), -1, 0
    for index, line in enumerate(raw.decode().splitlines(), 1):
        if not line.strip():
            if previous < cutoff:
                state.clear()
            continue
        stamp, payload = line.split(" ", 1)
        now = capture(stamp)
        assert now >= previous
        previous = now
        message = json.loads(payload)
        messages += 1
        if now >= cutoff:
            continue
        if not bybit:
            entries = message["data"]
            for record_index, row in enumerate(entries if isinstance(entries, list) else [entries]):
                assert row["e"] == "markPriceUpdate"
                state[row["s"]] = {"receive_ns": now, "event_ns": int(row["E"])*1_000_000,
                                   "funding_time_ns": int(row["T"])*1_000_000, "funding_rate": row["r"] or None,
                                   "mark_price": row["p"], "line_index": index-1, "record_index": record_index}
            continue
        symbol, body = message["topic"].split(".", 1)[1], message["data"]
        assert message["topic"] == "tickers."+symbol and body.get("symbol", symbol) == symbol
        if not symbol.endswith("USDT"):
            continue
        seen.add(symbol)
        older = state.get(symbol)
        sequence = int(message["cs"])
        sequence_ok = older is None or sequence > older["sequence"] or (sequence == older["sequence"] and body == older["body"])
        reset = message["type"] == "snapshot"
        assert message["type"] in ("delta", "snapshot")
        values = {} if older is None or reset or not sequence_ok else dict(older["fields"])
        provenance = {} if older is None or reset or not sequence_ok else dict(older["provenance"])
        event = int(message["ts"])*1_000_000
        for key in ("fundingRate", "nextFundingTime", "markPrice"):
            if key in body:
                values[key] = body[key]
                provenance[key] = {"line_index": index, "capture_ns": now, "event_ns": event}
        state[symbol] = {"capture_ns": now, "event_ns": event, "line_index": index, "sequence": sequence,
                         "sequence_ok": sequence_ok or reset, "fields": values, "provenance": provenance, "body": body}
    return state, seen, messages


def fresh(state, cutoff, target, unit):
    if state is None:
        return False
    rate, mark = decimal(state["funding_rate"]), decimal(state["mark_price"])
    if rate is None or mark is None or not rate.is_finite() or not mark.is_finite() or mark <= 0:
        return False
    mult = 1000 if unit == "us" else 1
    observed, published = state["receive_"+unit]*mult, state["event_"+unit]*mult
    return (state["funding_time_"+unit] is not None and state["funding_time_"+unit]*mult == target
            and 0 < cutoff-observed <= 5_000_000_000 and 0 < cutoff-published <= 5_000_000_000
            and -1_000_000 <= observed-published <= 5_000_000_000)


def main():
    output = OUT/"all_states_independent_verification.json"
    assert not output.exists(), "Preserve completed independent audit"
    manifest = json.loads((OUT/"all_states_manifest.json").read_text())
    assert manifest["complete"]
    for name in ("all_states_recovery_plan.json", "all_states_screen_implementation.json", "screen_implementation.json"):
        plan = json.loads((OUT/name).read_text())
        for path, expected in plan["code_sha256"].items():
            assert sha(ROOT/path) == expected, path
    normalized, audits = {}, []
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [pool.submit(audit_csv, source) for source in manifest["files"]]
        for job in as_completed(jobs):
            result, states = job.result()
            normalized[result["date"]] = states
            audits.append(result)
            print(json.dumps(result), flush=True)
    original = pd.read_parquet(OUT/"native_states.parquet")
    pairs = pd.read_parquet(OUT/"all_funding_pairs.parquet")
    assert len(original) == len(pairs) == 8857
    pair_map = {(r["date"], r["hour"], r["symbol"]): r for r in pairs.to_dict("records")}
    ymanifest = json.loads((OUT/"source_manifest.json").read_text())
    bmanifest = json.loads((OLD/"native_manifest.json").read_text())
    native_messages, fields_checked, decisions, eligible = 0, 0, 0, 0
    for (date, hour), group in original.groupby(["date", "hour"]):
        events = group.to_dict("records")
        cutoff, target = events[0]["decision_ns"], events[0]["settlement_ns"]
        ys = next(s for s in ymanifest["files"] if (s["date"], s["hour"]) == (date, hour))
        bs = next(s for s in bmanifest["files"] if (s["date"], s["hour"]) == (date, hour))
        ystates, seen, count = native_states(ys, cutoff, True)
        bstates, _, bcount = native_states(bs, cutoff, False)
        native_messages += count+bcount
        assert seen == set(group.symbol)
        for event in events:
            symbol = event["symbol"]
            output_row = pair_map[(date, hour, symbol)]
            y = normalized[date][hour].get(symbol)
            b = bstates.get(symbol)
            n = ystates.get(symbol)
            fields = {}
            if n is not None:
                fields = n["fields"]
                assert fields == json.loads(event["known_fields"])
                assert n["provenance"] == json.loads(event["field_provenance"])
                for key in ("capture_ns", "event_ns", "line_index", "sequence", "sequence_ok"):
                    assert n[key] == event[key], (date, hour, symbol, key)
                fields_checked += len(fields)
            assert bool(output_row["recovered_state"]) == (y is not None)
            if y:
                for key, value in y.items():
                    equal(value, output_row["bybit_"+key], key)
            native_good = n is not None and n["sequence_ok"] and all(0 < cutoff-n[k] <= 5_000_000_000 for k in ("capture_ns", "event_ns")) and -1_000_000 <= n["capture_ns"]-n["event_ns"] <= 5_000_000_000
            field_agreement = False
            if native_good and fresh(y, cutoff, target, "us"):
                conflicts = []
                for raw_key, recovered_key, mult in (("fundingRate", "funding_rate", 1), ("markPrice", "mark_price", 1), ("nextFundingTime", "funding_time_us", 1000)):
                    if raw_key not in fields:
                        continue
                    try:
                        equal(D(fields[raw_key])*mult, y[recovered_key], recovered_key)
                    except (AssertionError, ArithmeticError):
                        conflicts.append(raw_key)
                assert ",".join(conflicts) == output_row["native_conflicting_fields"]
                field_agreement = not conflicts
            bybit_good = native_good and fresh(y, cutoff, target, "us") and field_agreement
            large = bybit_good and abs(D(y["funding_rate"]))*10000 >= 14
            usable = large and fresh(b, cutoff, target, "ns")
            candidate = False
            if usable:
                difference = D(y["funding_rate"])*D(y["mark_price"])-D(b["funding_rate"])*D(b["mark_price"])
                basis_points = abs(difference)/max(D(y["mark_price"]), D(b["mark_price"]))*10000
                candidate = basis_points > 28
                assert abs(float(basis_points)-output_row["quoted_payment_difference_bps"]) < 1e-8
                assert output_row["sell_exchange"] == ("bybit" if difference > 0 else "binance-futures")
                for key, value in b.items():
                    equal(value, output_row["binance_"+key], key)
            for name, value in (("bybit_valid", bybit_good), ("native_fields_reconciled", field_agreement), ("large_bybit_rate", large), ("usable", usable), ("eligible", candidate)):
                assert bool(output_row[name]) == bool(value), (date, hour, symbol, name, value, output_row[name])
            decisions += 1
            eligible += candidate
    results = json.loads((OUT/"all_states_screen_results.json").read_text())
    assert sha(OUT/"all_funding_pairs.parquet") == results["pairs_sha256"]
    assert results["pairs_above_cost_before_execution"] == eligible
    assert results["outcomes"] == pairs.reason.value_counts().to_dict()
    verification = {"verified_at_utc": datetime.now(UTC).isoformat(), "verified": True,
                    "auditor_sha256": sha(Path(__file__)), "source_manifest_sha256": sha(OUT/"all_states_manifest.json"),
                    "pairs_sha256": results["pairs_sha256"], "csv_source_files": audits,
                    "independent_csv_prefix_rows_scanned": sum(a["prefix_rows_scanned"] for a in audits),
                    "independent_csv_states_verified": sum(a["states_verified"] for a in audits),
                    "native_messages_checked": native_messages, "native_fields_reconciled": fields_checked,
                    "decisions_verified": decisions, "fee_only_candidates_verified": int(eligible),
                    "scope": "Independently reconstructed all CSV as-of states and native one-minute input fields; reconciled every screen availability/eligibility flag and paired funding calculation. Original source recovery reads EOF for gzip integrity; this audit scans each prefix through the final cutoff and verifies every entire compressed-file hash.",
                    "limits": "Normalized carried-field initialization and disconnect continuity before the one-minute native window are not independently established. No execution or credited funding cash flow has been tested.",
                    "strategy_pnl_tested": False, "reliable_edge_established": False}
    output.write_text(json.dumps(verification, indent=2)+"\n")
    print(json.dumps({k: v for k, v in verification.items() if k != "csv_source_files"}), flush=True)


if __name__ == "__main__":
    main()
