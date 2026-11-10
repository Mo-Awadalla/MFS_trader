"""Independent source/as-of audit and additive instrument-lifecycle correction."""

import calendar
import csv
import gzip
import hashlib
import json
import math
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/funding_universe_hft_20260930"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def epoch_ns(value):
    whole = calendar.timegm(datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S").timetuple())
    tail = value[19:].removesuffix("Z")
    return whole * 1_000_000_000 + (int(tail[1:].ljust(9, "0")) if tail else 0)


def main():
    if (OUT / "verification.json").exists():
        raise RuntimeError("Preserve independent verification")
    a = json.loads((OUT / "stage_a_results.json").read_text())
    b = json.loads((OUT / "stage_b_results.json").read_text())
    manifest = json.loads((OUT / "native_manifest.json").read_text())
    counterpart = json.loads((OUT / "counterpart_manifest.json").read_text())
    frozen_a = json.loads((OUT / "stage_a_implementation.json").read_text())
    frozen_b = json.loads((OUT / "stage_b_implementation.json").read_text())
    assert sha(OUT / "specification.json") == frozen_a["protocol_sha256"] == manifest["specification_sha256"]
    assert sha(OUT / "native_manifest.json") == frozen_a["manifest_sha256"]
    for name, expected in frozen_a["implementation_sha256"].items():
        assert sha(ROOT / name) == expected
    assert sha(ROOT / "research_scout/funding_counterparts_20260930.py") == frozen_b["code_sha256"]
    assert sha(OUT / "stage_a_results.json") == frozen_b["stage_a_sha256"]
    for name, expected in [("binance_snapshots.parquet", a["snapshots_sha256"]),
                           ("large_binance_rates.parquet", a["large_rates_sha256"]),
                           ("funding_pairs.parquet", b["pairs_sha256"])]:
        assert sha(OUT / name) == expected
    snapshots = pd.read_parquet(OUT / "binance_snapshots.parquet")
    selected = pd.read_parquet(OUT / "large_binance_rates.parquet")
    pairs = pd.read_parquet(OUT / "funding_pairs.parquet")
    checks, native_rows, raw_bytes, compressed_bytes = 0, 0, 0, 0
    reconstructed = {}
    for source in manifest["files"]:
        assert source["complete"]
        path = ROOT / source["path"]
        assert sha(path) == source["compressed_sha256"]
        payload = gzip.decompress(path.read_bytes())
        assert hashlib.sha256(payload).hexdigest() == source["decoded_sha256"]
        raw_bytes += len(payload)
        compressed_bytes += path.stat().st_size
        target = epoch_ns(f"{source['date']}T{source['hour']:02d}:00:00Z")
        decision = target - 30_000_000_000
        states, seen, previous = {}, set(), -1
        for line_number, line in enumerate(payload.decode().splitlines()):
            if not line.strip():
                if previous < decision:
                    states.clear()
                continue
            capture, body = line.split(" ", 1)
            received = epoch_ns(capture)
            assert received >= previous
            previous = received
            message = json.loads(body)["data"]
            events = message if isinstance(message, list) else [message]
            native_rows += len(events)
            if received >= decision:
                continue
            for index, event in enumerate(events):
                assert event["e"] == "markPriceUpdate"
                if not event["s"].endswith("USDT"):
                    continue
                seen.add(event["s"])
                states[event["s"]] = (received, event, line_number, index)
        actual = snapshots[(snapshots.date == source["date"]) & (snapshots.hour == source["hour"])].set_index("symbol")
        assert set(actual.index) == seen
        for symbol in seen:
            row = actual.loc[symbol]
            assert int(row.settlement_ns) == target and int(row.decision_ns) == decision
            assert symbol in states  # All original snapshots had a valid post-disconnect state.
            received, event, line_number, index = states[symbol]
            publication = int(event["E"]) * 1_000_000
            funding_at = int(event["T"]) * 1_000_000
            rate = Decimal(event["r"])
            mark = Decimal(event["p"])
            clock_ok = (0 < decision-received <= 5_000_000_000
                        and 0 < decision-publication <= 5_000_000_000
                        and -1_000_000 <= received-publication <= 5_000_000_000)
            usable = (rate.is_finite() and mark.is_finite() and mark > 0 and funding_at == target and clock_ok)
            assert (int(row.receive_ns), int(row.event_ns), int(row.funding_time_ns),
                    int(row.line_index), int(row.record_index)) == (received, publication, funding_at, line_number, index)
            assert row.funding_rate_raw == event["r"] and row.mark_price_raw == event["p"]
            assert float(row.funding_rate) == float(rate) and float(row.mark_price) == float(mark)
            assert bool(row.usable) == usable
            assert bool(row.large_binance_rate) == (usable and abs(rate) >= Decimal("0.0014"))
            reconstructed[(source["date"], source["hour"], symbol)] = (float(rate), float(mark))
            checks += 1
    pd.testing.assert_frame_equal(snapshots.loc[snapshots.large_binance_rate].reset_index(drop=True), selected.reset_index(drop=True))
    assert checks == a["native_symbol_event_states"] == 6552
    assert len(pairs) == len(selected) == 18
    bybit_rows, max_error, pair_checks = 0, 0.0, 0
    for source in counterpart["files"]:
        cohort = pairs[(pairs.date == source["date"]) & (pairs.symbol == source["symbol"])].to_dict("records")
        observed = {}
        if source["complete"]:
            path = ROOT / source["path"]
            assert sha(path) == source["sha256"]
            previous = -1
            with gzip.open(path, "rt", newline="") as handle:
                for position, record in enumerate(csv.DictReader(handle)):
                    assert record["exchange"] == "bybit" and record["symbol"] == source["symbol"]
                    received = int(record["local_timestamp"])
                    assert received >= previous
                    previous = received
                    bybit_rows += 1
                    for event in cohort:
                        if received * 1000 < event["decision_ns"]:
                            observed[event["hour"]] = (position, record)
        for event in cohort:
            rate, mark = reconstructed[(event["date"], event["hour"], event["symbol"])]
            assert (event["binance_rate"], event["binance_mark"]) == (rate, mark)
            if event["hour"] not in observed:
                assert event["reason"] == "unknown_counterpart_source"
                pair_checks += 1
                continue
            position, record = observed[event["hour"]]
            for column, raw in [("source_position", position), ("receive_us", record["local_timestamp"]),
                                ("event_us", record["timestamp"]), ("funding_time_us", record["funding_timestamp"])]:
                assert int(event["bybit_"+column]) == int(raw)
            for column in ["funding_rate", "mark_price"]:
                assert event["bybit_"+column] == float(record[column])
            cutoff = event["decision_ns"] // 1000
            valid = (0 < cutoff-int(record["local_timestamp"]) <= 5_000_000
                     and 0 < cutoff-int(record["timestamp"]) <= 5_000_000
                     and int(record["funding_timestamp"]) * 1000 == event["settlement_ns"]
                     and math.isfinite(float(record["funding_rate"]))
                     and math.isfinite(float(record["mark_price"])) and float(record["mark_price"]) > 0)
            assert event["usable"] == valid
            if valid:
                gap = Decimal(str(rate))*Decimal(str(mark)) - Decimal(record["funding_rate"])*Decimal(record["mark_price"])
                bps = float(abs(gap)/max(Decimal(str(mark)), Decimal(record["mark_price"]))*10000)
                error = abs(event["quoted_payment_difference_bps"]-bps)
                assert error < 1e-10
                max_error = max(max_error, error)
                assert event["eligible"] == (bps > 28)
                assert event["sell_exchange"] == ("binance-futures" if gap > 0 else "bybit")
            else:
                assert not event["eligible"] and event["reason"] == "stale_invalid_or_wrong_funding_time_counterpart"
            pair_checks += 1
    assert bybit_rows == b["counterpart_native_normalized_rows"] == 1_419_702
    facts = json.loads((OUT / "lifecycle_facts.json").read_text())
    corrected = pairs.copy()
    corrected["original_reason"] = corrected.reason
    corrected["known_contract_closed"] = False
    corrected["lifecycle_source"] = ""
    for fact in facts["known_new_position_prohibitions"]:
        start = epoch_ns(fact["new_positions_prohibited_from_utc"])
        end = epoch_ns(fact["apply_through_utc_exclusive"])
        assert fact["announcement_publication_date"] < "2024-04-01"
        mask = corrected.symbol.isin(fact["symbols"]) & (corrected.decision_ns >= start) & (corrected.decision_ns < end)
        corrected.loc[mask, "known_contract_closed"] = True
        corrected.loc[mask, "lifecycle_source"] = fact["source"]
        corrected.loc[mask, "eligible"] = False
        corrected.loc[mask, "reason"] = "known_new_positions_prohibited"
    corrected.to_parquet(OUT / "funding_pairs_lifecycle_v1.parquet", index=False)
    diagnostic = json.loads((OUT / "lifecycle_sources/fet_source_diagnostic.txt").read_text())
    assert diagnostic["code"] == 140 and diagnostic["datasetInfo"]["availableTo"] == "2024-06-08T00:00:00.000Z"
    result = {"verified_at_utc": datetime.now(UTC).isoformat(), "native_slices_verified": len(manifest["files"]),
              "native_messages_examined": native_rows, "native_decoded_bytes": raw_bytes,
              "native_compressed_bytes": compressed_bytes, "binance_asof_snapshots_verified": checks,
              "bybit_normalized_files_verified": sum(r["complete"] for r in counterpart["files"]),
              "bybit_normalized_rows_examined": bybit_rows, "paired_events_verified": pair_checks,
              "maximum_payment_gap_reconstruction_error_bps": max_error,
              "known_closed_contract_events": int(corrected.known_contract_closed.sum()),
              "eligible_after_lifecycle_correction": int(corrected.eligible.sum()),
              "corrected_outcomes": corrected.reason.value_counts().to_dict(),
              "implementation_sha256": sha(Path(__file__)), "lifecycle_facts_sha256": sha(OUT / "lifecycle_facts.json"),
              "corrected_pairs_sha256": sha(OUT / "funding_pairs_lifecycle_v1.parquet"),
              "original_pairs_sha256": b["pairs_sha256"], "bybit_native_normalization_verified": False,
              "all_contract_lifecycles_verified": False, "strategy_pnl_tested": False, "reliable_edge_established": False}
    (OUT / "verification.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
