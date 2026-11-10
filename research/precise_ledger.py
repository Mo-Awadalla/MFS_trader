"""Preserve integer nanosecond clocks when some ledger rows have no order."""

import pandas as pd


def ledger_frame(records):
    frame = pd.DataFrame(records)
    for column in frame.columns:
        if column.endswith("_ns"):
            # Rebuild from original Python integers, never cast already-rounded
            # float64 columns back to integers after pandas inserted NaN.
            frame[column] = pd.array([row.get(column) for row in records], dtype="Int64")
    return frame
