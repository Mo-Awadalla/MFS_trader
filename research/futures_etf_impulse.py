"""Return-blind, causal futures impulse routing for a subsequent SPY test."""

import numpy as np
import pandas as pd


def screen(frame, decisions):
    caps = frame.capture_ns.to_numpy(np.int64)
    assert len(caps) and np.all(caps[1:] >= caps[:-1])
    cutoff = np.asarray(decisions, dtype=np.int64)-100_000_000
    right = np.searchsorted(caps, cutoff, side="left")
    left = np.searchsorted(caps, cutoff-1_000_000_000, side="left")
    now, past = right-1, left-1
    ni, pi = np.maximum(now, 0), np.maximum(past, 0)
    price = frame.price.to_numpy(float)
    quantity = frame["size"].to_numpy(np.int64)
    events = frame.event_ns.to_numpy(np.int64)
    flags = frame.flags_value.to_numpy(np.int64)
    side = frame.side.to_numpy()
    bad = ((~np.isfinite(price)) | (price <= 0) | (quantity <= 0)
           | ~np.isin(side, ["A", "B"]) | ((flags & ~128) != 0)
           | (caps-events < -1_000_000) | (caps-events > 100_000_000))
    volume_prefix = np.r_[0, np.cumsum(quantity)]
    signed_prefix = np.r_[0, np.cumsum(quantity*np.where(side == "B", 1, np.where(side == "A", -1, 0)))]
    bad_prefix = np.r_[0, np.cumsum(bad.astype(np.int64))]
    volume = volume_prefix[right]-volume_prefix[left]
    signed = signed_prefix[right]-signed_prefix[left]
    bad_count = bad_prefix[right]-bad_prefix[left]
    with np.errstate(divide="ignore", invalid="ignore"):
        returns = 10000*(price[ni]/price[pi]-1)
        alignment = np.sign(returns)*signed/volume
    identifiers = frame.instrument_id.to_numpy(np.int64)
    fresh = ((now >= 0) & (past >= 0) & (cutoff-caps[ni] > 0) & (cutoff-caps[ni] <= 250_000_000)
             & (cutoff-1_000_000_000-caps[pi] > 0) & (cutoff-1_000_000_000-caps[pi] <= 250_000_000))
    valid = fresh & ~bad[ni] & ~bad[pi] & (bad_count == 0) & (identifiers[ni] == identifiers[pi])
    qualifies = valid & (np.abs(returns) >= 4) & (volume >= 100) & (alignment >= .75)
    reasons = np.where(~fresh, "missing_or_stale_reference", np.where(~valid, "invalid_source_or_contract_change",
                       np.where(np.abs(returns) < 4, "move_below_hurdle", np.where(volume < 100, "volume_below_hurdle",
                       np.where(alignment < .75, "flow_not_aligned", "eligible")))))
    admitted = np.zeros(len(cutoff), dtype=bool)
    available = -1
    for index in np.flatnonzero(qualifies):
        if decisions[index] >= available:
            admitted[index] = True
            available = int(decisions[index])+30_000_000_000
        else:
            reasons[index] = "frozen_30_second_cooldown"
    return pd.DataFrame({"decision_ns": decisions, "signal_cutoff_ns": cutoff,
                         "current_source_position": now, "reference_source_position": past,
                         "current_capture_ns": caps[ni], "reference_capture_ns": caps[pi],
                         "instrument_id": identifiers[ni], "current_price": price[ni], "reference_price": price[pi],
                         "return_bps": returns, "one_second_contracts": volume, "signed_contracts": signed,
                         "aligned_flow_fraction": alignment, "invalid_window_records": bad_count,
                         "valid": valid, "qualifies": qualifies, "selected": admitted, "reason": reasons})
