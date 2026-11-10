"""Inventory complete free samples and create lossless typed local copies; no strategy."""

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from research.databento_sample_csv import native_batch, reader
from research_scout.inspect_databento_public_sample_20261003 import OUT
from research_scout.prepare_databento_fast_20261002 import ROOT, sha, write


def inventory(source):
    path = Path(source["path"])
    assert source["reached_response_eof"] and path.stat().st_size == source["bytes"]
    assert sha(path) == source["sha256"]
    folder = OUT / "typed"
    folder.mkdir(exist_ok=True)
    output = folder / (source["schema"] + ".parquet")
    assert not output.exists()
    counts = {name: Counter() for name in ("action", "side", "symbol", "publisher_id", "instrument_id", "rtype", "flags")}
    total, writer, first, last = 0, None, {}, {}
    clocks = {"receive_backwards": 0, "event_backwards": 0, "sequence_backwards": 0, "timestamp_delta_mismatches": 0}
    quality, resets = [], []
    try:
        for raw in reader(str(path)):
            batch = native_batch(raw)
            values = {name: batch.column(name).to_numpy(zero_copy_only=False) for name in ("ts_recv", "ts_event", "flags", "ts_in_delta", "sequence")}
            for name in counts:
                for pair in pc.value_counts(batch.column(name)).to_pylist():
                    counts[name][str(pair["values"])] += pair["counts"]
            for name, metric in (("ts_recv", "receive_backwards"), ("ts_event", "event_backwards"), ("sequence", "sequence_backwards")):
                column = values[name]
                if name not in first:
                    first[name] = int(column[0])
                if name in last:
                    clocks[metric] += int(column[0] < last[name])
                clocks[metric] += int(np.count_nonzero(column[1:] < column[:-1]))
                last[name] = int(column[-1])
            good = (values["flags"] & 8) == 0
            clocks["timestamp_delta_mismatches"] += int(np.count_nonzero(good & (values["ts_recv"] - values["ts_event"] != values["ts_in_delta"])))
            bad = np.flatnonzero(values["flags"] & 12)
            for index in bad:
                if len(quality) < 20:
                    quality.append({"source_row": total + int(index), **{name: batch.column(name)[int(index)].as_py() for name in batch.schema.names}})
            for index in np.flatnonzero(batch.column("action").to_numpy(zero_copy_only=False) == "R"):
                if len(resets) < 20:
                    resets.append({"source_row": total + int(index), **{name: batch.column(name)[int(index)].as_py() for name in batch.schema.names}})
            batch = batch.append_column("source_row", pa.array(np.arange(total, total + len(batch), dtype=np.int64)))
            if writer is None:
                writer = pq.ParquetWriter(output, batch.schema, compression="zstd")
            writer.write_batch(batch)
            total += len(batch)
    finally:
        if writer is not None:
            writer.close()
    assert total + 1 == source["newline_count"]
    result = {"schema": source["schema"], "rows": total, "source_sha256": source["sha256"],
              "counts": {name: dict(counter) for name, counter in counts.items()}, "first": first, "last": last,
              "clock_checks": clocks, "first_quality_flagged_rows": quality, "first_resets": resets,
              "typed_path": str(output), "typed_sha256": sha(output), "typed_bytes": output.stat().st_size,
              "timestamp_unit": "integer epoch nanoseconds", "price_unit": "integer billionths of USD, null preserved",
              "order_ids": "native uint64", "returns_calculated": False}
    print(json.dumps(result), flush=True)
    return result


def main():
    acquisition = json.loads((OUT / "acquisition.json").read_text())
    assert not (OUT / "inventory.json").exists()
    results = [inventory(source) for source in acquisition["sources"]]
    report = {"created_at_utc": datetime.now(UTC).isoformat(), "sources": results,
              "acquisition_sha256": sha(OUT / "acquisition.json"), "inventory_code_sha256": sha(Path(__file__)),
              "csv_parser_sha256": sha(ROOT / "research/databento_sample_csv.py"),
              "strategy_return_computations": 0, "paid_calls": 0, "reliable_edge_established": False}
    write(OUT / "inventory.json", report)


if __name__ == "__main__":
    main()
