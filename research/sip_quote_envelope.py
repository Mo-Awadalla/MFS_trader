"""Conditional historical SIP quote-price envelope; not a live-fill bound."""

import numpy as np


def envelope(frame, target_ns, quantity, radius_ns):
    times = frame.timestamp.dt.as_unit("ns").astype("int64").to_numpy()
    assert not (np.diff(times) < 0).any()
    low, high = int(target_ns) - radius_ns, int(target_ns) + radius_ns
    first = int(np.searchsorted(times, low, side="left")) - 1
    stop = int(np.searchsorted(times, high, side="right"))
    record = {"target_ns": int(target_ns), "radius_ns": radius_ns, "first_index": first, "stop_index": stop,
              "quantity": quantity, "complete": False}
    if first < 0 or stop >= len(frame):
        return {**record, "reason": "unbracketed_quote_window"}
    states = frame.iloc[first:stop]
    values = states[["bid_price", "ask_price", "bid_size", "ask_size"]].to_numpy(float)
    valid = (np.isfinite(values).all() and (values > 0).all() and (values[:, 0] < values[:, 1]).all()
             and (values[:, 1] < 1e7).all() and (values[:, 2] >= quantity).all()
             and states.conditions.eq('["R"]').all()
             and states.bid_exchange.str.len().gt(0).all() and states.ask_exchange.str.len().gt(0).all())
    if not valid:
        return {**record, "reason": "unknown_quote_state_or_depth", "states": len(states)}
    return {**record, "complete": True, "reason": "observed_sip_state_envelope", "states": len(states),
            "bid_lower": float(states.bid_price.min()), "bid_upper": float(states.bid_price.max()),
            "first_ns": int(times[first]), "last_ns": int(times[stop - 1]), "successor_ns": int(times[stop]),
            "oldest_standing_age_ns": int(target_ns) - int(times[first])}
