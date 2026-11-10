"""Capture-time information, exchange-time execution, without a signal leak."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.liquidation_event_replay import FIELDS, sweep


def extract_dual_clock(path, day, targets):
    start = pd.Timestamp(day, tz="UTC").value // 1000
    requested = targets.target_us.to_numpy(np.int64)
    is_signal = targets.label.eq("signal").to_numpy()
    best = np.full(len(targets), -1, np.int64)
    selected_local = np.full(len(targets), -1, np.int64)
    selected_exchange = np.full(len(targets), -1, np.int64)
    selected = np.full((len(targets), len(FIELDS)), np.nan)
    ambiguities, previous_local, previous_exchange, rows = [], None, None, 0
    for chunk in pd.read_csv(path, usecols=["timestamp", "local_timestamp", *FIELDS], chunksize=200_000):
        local = chunk.local_timestamp.to_numpy(np.int64) - start
        exchange = chunk.timestamp.to_numpy(np.int64) - start
        if (np.diff(local) < 0).any() or (previous_local is not None and local[0] < previous_local):
            raise ValueError("Capture stream is not ordered")
        combined_exchange = np.r_[previous_exchange, exchange] if previous_exchange is not None else exchange
        back = np.flatnonzero(np.diff(combined_exchange) < 0)
        for index in back:
            ambiguities.append((int(combined_exchange[index + 1]) - 250_000,
                                int(combined_exchange[index]) + 250_000))
        previous_local, previous_exchange = int(local[-1]), int(exchange[-1])
        rows += len(chunk)
        values = chunk[FIELDS].to_numpy(float)
        for signal, axis in ((True, local), (False, exchange)):
            dest = np.flatnonzero(is_signal == signal)
            # Sorting here reconstructs execution state only. Signals always use
            # capture order and cannot see subsequently captured messages.
            order = np.arange(len(axis)) if signal else np.argsort(axis, kind="stable")
            positions = np.searchsorted(axis[order], requested[dest], side="left") - 1
            valid = positions >= 0
            dest, source = dest[valid], order[positions[valid]]
            replace = axis[source] >= best[dest]
            dest, source = dest[replace], source[replace]
            best[dest] = axis[source]
            selected[dest] = values[source]
            selected_local[dest], selected_exchange[dest] = local[source], exchange[source]
    result = targets.copy()
    result[FIELDS] = selected
    result["quote_local_us"], result["quote_exchange_us"] = selected_local, selected_exchange
    result["clock_kind"] = np.where(is_signal, "capture", "exchange")
    result["capture_age_us"] = requested - selected_local
    result["exchange_age_us"] = requested - selected_exchange
    result["quote_age_us"] = np.where(is_signal, requested - selected_local, requested - selected_exchange)
    result["source_delay_us"] = selected_local - selected_exchange
    ambiguous = np.zeros(len(result), bool)
    for low, high in ambiguities:
        ambiguous |= (~is_signal) & (requested >= low) & (requested <= high)
    result["exchange_clock_ambiguous"] = ambiguous
    return result, {"date": day, "raw_rows": rows, "exchange_backtracks": len(ambiguities),
                    "ambiguous_target_count": int(ambiguous.sum()), "ambiguity_intervals_us": ambiguities,
                    "execution_snapshots_captured_after_target": int(((selected_local >= requested) & ~is_signal).sum()),
                    "signals_captured_after_target": int(((selected_local >= requested) & is_signal).sum())}


def physical_fill(row, direction, quantity, limit=None):
    if row["clock_kind"] != "exchange":
        raise ValueError("Execution must use exchange time, never delayed capture state")
    if row["exchange_clock_ambiguous"] or not 0 <= row["exchange_age_us"] <= 250_000:
        return {"status": "unknown_exchange_clock"}
    if row["source_delay_us"] < -1000:
        return {"status": "unknown_clock_skew"}
    # The shared depth walker validates all five levels. Its legacy freshness
    # fields describe the evaluation clock; capture latency cannot disqualify a
    # known historical exchange state. Original actual delays stay in the panel.
    evaluation = {**row, "quote_age_us": row["exchange_age_us"], "source_delay_us": 0}
    return sweep(evaluation, direction, quantity, limit)
