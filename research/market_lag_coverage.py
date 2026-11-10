"""Past-only normalized acquisition prefilter; never a native execution model."""

import numpy as np


def sample(times, bid, ask, start_us, minutes=1440):
    assert times.dtype == np.int64 and len(times) == len(bid) == len(ask)
    assert len(times) and np.all(times[1:] >= times[:-1])
    seconds = np.arange(2_000_000, 59_000_000, 250_000, dtype=np.int64)
    decisions = (start_us + np.arange(minutes, dtype=np.int64)[:, None] * 60_000_000 + seconds).ravel()
    old_cut, new_cut = decisions - 1_250_000, decisions - 250_000
    old = np.searchsorted(times, old_cut, side="left") - 1
    new = np.searchsorted(times, new_cut, side="left") - 1
    a, b = np.maximum(old, 0), np.maximum(new, 0)
    valid = (old >= 0) & (new >= 0) & ((old_cut - times[a]) <= 1_000_000) & ((new_cut - times[b]) <= 1_000_000)
    for i in (a, b):
        valid &= np.isfinite(bid[i]) & np.isfinite(ask[i]) & (bid[i] > 0) & (ask[i] > bid[i])
    with np.errstate(divide="ignore", invalid="ignore"):
        rb, ra = (bid[b] / bid[a] - 1) * 10000, (ask[b] / ask[a] - 1) * 10000
    direction = np.where((rb >= 15) & (ra >= 15), 1, np.where((rb <= -15) & (ra <= -15), -1, 0))
    near = valid & ((np.abs(np.abs(rb) - 15) <= 1e-8) | (np.abs(np.abs(ra) - 15) <= 1e-8))
    candidate = valid & (direction != 0)
    return {"decision_us": decisions, "anchor_row": old, "current_row": new,
            "valid": valid, "direction": direction, "bid_return_bps": rb, "ask_return_bps": ra,
            "candidate": candidate, "near_boundary": near}
