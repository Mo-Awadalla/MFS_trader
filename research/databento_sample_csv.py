"""Lossless typed reader for public Databento MBO/MBP-1 sample CSV exports."""

from decimal import Decimal

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as csv

TYPES = {
    "ts_recv": pa.timestamp("ns", tz="UTC"), "ts_event": pa.timestamp("ns", tz="UTC"),
    "rtype": pa.uint8(), "publisher_id": pa.uint16(), "instrument_id": pa.uint32(),
    "action": pa.string(), "side": pa.string(), "symbol": pa.string(),
    "price": pa.decimal128(19, 9), "size": pa.uint32(), "channel_id": pa.uint8(),
    "order_id": pa.uint64(), "flags": pa.uint8(), "ts_in_delta": pa.int32(), "sequence": pa.uint32(),
    "depth": pa.uint8(), "bid_px_00": pa.decimal128(19, 9), "ask_px_00": pa.decimal128(19, 9),
    "bid_sz_00": pa.uint32(), "ask_sz_00": pa.uint32(), "bid_ct_00": pa.uint32(), "ask_ct_00": pa.uint32(),
}
PRICES = {"price", "bid_px_00", "ask_px_00"}


def reader(source):
    return csv.open_csv(source, read_options=csv.ReadOptions(block_size=8 * 1024 * 1024, use_threads=False),
                        convert_options=csv.ConvertOptions(column_types=TYPES, null_values=[""], strings_can_be_null=False))


def native_batch(batch):
    """Preserve null prices; convert ns timestamps and billionth-dollar prices exactly."""
    arrays, names = [], batch.schema.names
    assert set(names) <= set(TYPES)
    for name in names:
        values = batch.column(name)
        if name in PRICES:
            scale = pa.scalar(Decimal(1000000000), type=pa.decimal128(10, 0))
            values = pc.cast(pc.multiply(values, scale), pa.int64(), safe=True)
        elif name in ("ts_recv", "ts_event"):
            values = pc.cast(values, pa.int64(), safe=True)
        arrays.append(values)
    return pa.RecordBatch.from_arrays(arrays, names)
