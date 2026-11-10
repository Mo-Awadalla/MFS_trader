"""As-of funding states from ordered full-state CSV chunks, without future data."""

import math

import numpy as np

COLUMNS = ["exchange","symbol","timestamp","local_timestamp","funding_timestamp","funding_rate","mark_price"]


def advance_snapshots(frame, selected, offset, cutoffs):
    times=frame.local_timestamp.to_numpy(np.int64)
    relevant=frame.symbol.astype(str).str.endswith("USDT").to_numpy()
    for hour,cutoff in cutoffs.items():
        positions=np.flatnonzero((times<cutoff) & relevant)
        if not len(positions):
            continue
        view=frame.iloc[positions].drop_duplicates("symbol",keep="last")
        for index,row in view.iterrows():
            funding=None if not math.isfinite(float(row.funding_timestamp)) else int(row.funding_timestamp)
            rate=float(row.funding_rate)
            mark=float(row.mark_price)
            selected[hour][str(row.symbol)]={"receive_us":int(row.local_timestamp),"event_us":int(row.timestamp),
                                             "funding_time_us":funding,"funding_rate":rate if math.isfinite(rate) else None,
                                             "mark_price":mark if math.isfinite(mark) else None,"source_position":offset+int(index)}
