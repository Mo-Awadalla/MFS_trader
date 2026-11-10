"""Capture-ordered aggregate quote envelopes; not a matching-engine simulator.

Holding an unchanged valid book state is intentional. Price/size/quality checks
still apply to every possible execution state. Never select a favorable FOK
branch or silently drop an entry whose execution cannot be resolved from L1.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from research.auction_hft_event import SYMBOLS, costs, forecast, quote_targets, valid

SCENARIOS = {
    "base": {"delay_s": 1, "alignment_ms": 1, "fee_multiplier": 1, "adverse_bps": 1},
    "double_fees": {"delay_s": 1, "alignment_ms": 1, "fee_multiplier": 2, "adverse_bps": 1},
    "latency_3s": {"delay_s": 3, "alignment_ms": 1, "fee_multiplier": 1, "adverse_bps": 1},
    "extra_slippage": {"delay_s": 1, "alignment_ms": 1, "fee_multiplier": 1, "adverse_bps": 2},
    "alignment_100ms": {"delay_s": 1, "alignment_ms": 100, "fee_multiplier": 1, "adverse_bps": 1},
}


def extract_envelopes(frame, day):
    opening = pd.Timestamp(day + " 09:30", tz="America/New_York").value
    rows, audits = [], []
    for symbol in SYMBOLS:
        source = frame.loc[frame.symbol.astype(str).eq(symbol) & (frame["flags"].to_numpy(int) & 128 != 0)]
        receive = source.ts_recv.dt.as_unit("ns").astype("int64").to_numpy()
        if source.ts_recv.isna().any() or (np.diff(receive) < 0).any():
            raise ValueError("Invalid capture chronology")
        for label, seconds, clock in quote_targets():
            if clock != "event":
                continue
            target = opening + int(seconds * 1e9)
            for width in (1, 100):
                lower, upper = target - width * 1000000, target + width * 1000000
                left = int(np.searchsorted(receive, lower, side="left")) - 1
                right = int(np.searchsorted(receive, upper, side="right"))
                context = {"date": day, "symbol": symbol, "label": label, "alignment_ms": width,
                           "target_ns": target, "window_low_ns": lower, "window_high_ns": upper}
                if left < 0 or not len(receive) or receive[-1] <= upper:
                    rows.append({**context, "missing_boundary": True, "source_position": -1,
                                 "receive_ns": -1, "event_ns": -1, "flags": 12,
                                 "bid": np.nan, "ask": np.nan, "bid_qty": np.nan, "ask_qty": np.nan})
                    continue
                # Include the standing state before the lower boundary, then all
                # updates through the upper boundary. Preserve capture tie order.
                for pos in range(left, right):
                    raw = source.iloc[pos]
                    rows.append({**context, "missing_boundary": False, "source_position": pos,
                                 "receive_ns": int(receive[pos]), "event_ns": int(raw.ts_event.value),
                                 "flags": int(raw["flags"]), "bid": float(raw.bid_px_00),
                                 "ask": float(raw.ask_px_00), "bid_qty": float(raw.bid_sz_00),
                                 "ask_qty": float(raw.ask_sz_00)})
        audits.append({"symbol": symbol, "source_rows": len(source),
                       "capture_backsteps": int((np.diff(receive) < 0).sum())})
    return pd.DataFrame(rows), audits


def usable(envelope):
    if envelope.empty or envelope.missing_boundary.any() or (envelope["flags"].to_numpy(int) & 12 != 0).any():
        return False
    values = envelope[["bid", "ask", "bid_qty", "ask_qty"]].to_numpy(float)
    return bool(np.isfinite(values).all() and (values > 0).all() and (values[:, :2] < 1e7).all()
                and (values[:, 0] < values[:, 1]).all())


def replay_day(day, signals, envelopes, early, late, rule, hold, scenario):
    quotes = {(row["symbol"], row["label"]): row for row in signals.to_dict("records")}
    decision = int(signals.loc[signals.label.eq("signal"), "target_ns"].iloc[0])
    record = {"date": day, "rule": rule, "hold_s": hold, "decision_ns": decision}

    def no_order(status):
        return {**record, "status": status, "complete": True, "pnl_lower": 0., "pnl_upper": 0.}

    def unknown(status, possible_open=0):
        return {**record, "status": status, "complete": False, "pnl_lower": None, "pnl_upper": None,
                "possible_open_quantity": possible_open}

    prediction = forecast(rule, quotes, early, late, decision)
    if prediction is None:
        return no_order("no_causal_signal")
    record.update(prediction)
    symbol = prediction["symbol"]
    signal = quotes.get((symbol, "signal"))
    if not valid(signal, 1000000000):
        return no_order("predecision_unknown")
    q = math.floor(min(10000 / (signal["ask"] * 1.01), .1 * signal["ask_qty"]))
    record.update(quantity=q, signal_ask=signal["ask"], signal_ask_qty=signal["ask_qty"],
                  signal_receive_ns=signal["receive_ns"])
    if q < 1:
        return no_order("predecision_size")
    projected_exit = signal["bid"] * (1 + prediction["projected_return"])
    expected = q * (projected_exit - signal["ask"]) - sum(costs(q, signal["ask"], projected_exit))
    record.update(projected_exit=projected_exit, expected_net=expected)
    if expected <= q * signal["ask"] / 10000:
        return no_order("below_cost_gate")

    delay, width = scenario["delay_s"], scenario["alignment_ms"]
    entry_target = decision + 250000000 + delay * 1000000000
    exit_target = entry_target + (2 * delay + hold) * 1000000000
    limit = math.floor(signal["ask"] * 1.0005 * 100) / 100
    record.update(limit=limit, entry_target_ns=entry_target, exit_target_ns=exit_target,
                  entry_ack_ns=entry_target + delay * 1000000000,
                  exit_ack_ns=exit_target + delay * 1000000000, alignment_ms=width)
    instrument = envelopes.loc[envelopes.symbol.eq(symbol) & envelopes.alignment_ms.eq(width)]
    entry = instrument.loc[instrument.label.eq(f"entry_{delay}")]
    end = instrument.loc[instrument.label.eq(f"exit_{delay}_{hold}")]
    if not usable(entry):
        return unknown("unresolved_entry")
    through_collar = entry.ask.le(limit + 1e-10)
    if not through_collar.any():
        return no_order("rejected_fok")
    if (through_collar & entry.ask_qty.lt(q)).any():
        # L1 cannot exclude additional volume within the FOK limit.
        return unknown("unresolved_entry_depth", q)
    possible_fills = entry.loc[through_collar]
    record.update(entry_min=float(possible_fills.ask.min()), entry_max=float(possible_fills.ask.max()),
                  fill_may_reject=bool((~through_collar).any()), entry_state_count=len(entry))
    if not usable(end) or end.bid_qty.lt(q).any():
        return unknown("unresolved_exit", q)
    record.update(exit_min=float(end.bid.min()), exit_max=float(end.bid.max()), exit_state_count=len(end))
    fee, adverse = scenario["fee_multiplier"], scenario["adverse_bps"]
    lower = q * (record["exit_min"] - record["entry_max"]) - sum(costs(q, record["entry_max"], record["exit_min"], fee, adverse))
    upper = q * (record["exit_max"] - record["entry_min"]) - sum(costs(q, record["entry_min"], record["exit_max"], fee, adverse))
    record.update(filled_pnl_lower=lower, filled_pnl_upper=upper)
    if record["fill_may_reject"]:
        lower, upper = min(lower, 0.), max(upper, 0.)
    return {**record, "status": "bounded_fill_or_reject" if record["fill_may_reject"] else "bounded_fill",
            "complete": True, "pnl_lower": lower, "pnl_upper": upper}
