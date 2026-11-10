"""Second-scale auction-information screen; aggregate quote execution is a proxy."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

SYMBOLS = ("SPY", "SH", "UPRO", "SPXU")
SCENARIOS = {"base": {"delay_s": 1, "fee_multiplier": 1, "adverse_bps": 1},
             "double_fees": {"delay_s": 1, "fee_multiplier": 2, "adverse_bps": 1},
             "latency_3s": {"delay_s": 3, "fee_multiplier": 1, "adverse_bps": 1},
             "extra_slippage": {"delay_s": 1, "fee_multiplier": 1, "adverse_bps": 2}}
RULES = ("indicative_gap_1x", "indicative_gap_3x", "indicative_leadership_3x", "price_momentum_3x")


def costs(quantity, entry, exit_price, multiplier=1., adverse_bps=1.):
    commission = (2 * max(1., quantity * .0075)) * multiplier
    sell_levies = quantity * (exit_price * .00003 + .0002) * multiplier
    adverse = quantity * (entry + exit_price) * adverse_bps / 10000
    return commission, sell_levies, adverse


def valid(row, max_age_ns):
    if row is None or row["ambiguous"] or row["bad_flags"]:
        return False
    values = np.array([row[key] for key in ("bid", "ask", "bid_qty", "ask_qty")])
    return bool(np.isfinite(values).all() and (values > 0).all() and (values[:2] < 1e7).all()
                and row["bid"] < row["ask"] and 0 <= row["age_ns"] <= max_age_ns
                and row["source_delay_ns"] >= -1000000)


def quote_targets():
    # Clock offsets from 09:30; one fixed decision at 09:29:50.
    targets = [("signal", -10., "capture"), ("prior30", -40., "capture")]
    for delay in (1, 3):
        entry = -10 + .25 + delay
        targets.append((f"entry_{delay}", entry, "event"))
        for hold in (15, 30):
            targets.append((f"exit_{delay}_{hold}", entry + delay + hold + delay, "event"))
    return targets


def extract_quotes(frame, day):
    opening = pd.Timestamp(day + " 09:30:00", tz="America/New_York").value
    rows, audits = [], []
    for symbol in SYMBOLS:
        source = frame.loc[frame.symbol.astype(str).eq(symbol) & (frame["flags"].to_numpy(int) & 128 != 0)]
        if source.ts_recv.isna().any() or source.ts_event.isna().any():
            raise ValueError("Missing source clock")
        receive = source.ts_recv.dt.as_unit("ns").astype("int64").to_numpy()
        event = source.ts_event.dt.as_unit("ns").astype("int64").to_numpy()
        if (np.diff(receive) < 0).any():
            raise ValueError("Nonmonotonic receive clock")
        backwards = np.flatnonzero(np.diff(event) < 0)
        intervals = [(int(event[i + 1]) - 250000000, int(event[i]) + 250000000) for i in backwards]
        order = np.argsort(event, kind="stable")
        for label, seconds, clock in quote_targets():
            target = opening + int(seconds * 1e9)
            axis = receive if clock == "capture" else event[order]
            index = np.searchsorted(axis, target, side="left") - 1
            record = {"date": day, "symbol": symbol, "label": label, "clock": clock,
                      "target_ns": target, "ambiguous": clock == "event" and any(low <= target <= high for low, high in intervals)}
            if index < 0:
                rows.append({**record, "age_ns": -1, "bad_flags": True,
                             **dict.fromkeys(("bid", "ask", "bid_qty", "ask_qty"), np.nan),
                             "receive_ns": -1, "event_ns": -1, "source_delay_ns": -1})
                continue
            pos = index if clock == "capture" else order[index]
            raw = source.iloc[pos]
            rows.append({**record, "bid": float(raw.bid_px_00), "ask": float(raw.ask_px_00),
                         "bid_qty": float(raw.bid_sz_00), "ask_qty": float(raw.ask_sz_00),
                         "receive_ns": int(receive[pos]), "event_ns": int(event[pos]),
                         "source_delay_ns": int(receive[pos] - event[pos]),
                         "age_ns": int(target - (receive[pos] if clock == "capture" else event[pos])),
                         "bad_flags": bool(int(raw["flags"]) & (4 | 8)), "flags": int(raw["flags"])})
        audits.append({"date": day, "symbol": symbol, "complete_event_rows": len(source),
                       "source_event_backtracks": len(backwards), "ambiguity_intervals_ns": intervals})
    return pd.DataFrame(rows), audits


def forecast(rule, quotes, early, late, decision_ns):
    if rule not in RULES:
        raise ValueError("Unknown frozen auction rule")
    spy = quotes.get(("SPY", "signal"))
    if not valid(spy, 1000000000):
        return None
    mid = (spy["bid"] + spy["ask"]) / 2
    if rule == "price_momentum_3x":
        prior = quotes.get(("SPY", "prior30"))
        if not valid(prior, 1000000000):
            return None
        underlying = mid / ((prior["bid"] + prior["ask"]) / 2) - 1
    else:
        if (late is None or late["receive_ns"] >= decision_ns or decision_ns - late["receive_ns"] > 2000000000
                or not 0 <= decision_ns - late["event_ns"] <= 2000000000):
            return None
        if late["auction_type"] != "M" or late["auction_status"] not in (0, 1):
            return None
        indicative, reference = late["ind_match_price"], late["ref_price"]
        if not np.isfinite(np.asarray([indicative, reference], dtype=float)).all() or indicative <= 0 or reference <= 0:
            return None
        underlying = indicative / mid - 1
        if rule == "indicative_leadership_3x":
            if early is None or not np.isfinite(np.asarray([early["ref_price"], early["ind_match_price"]], dtype=float)).all() or min(early["ref_price"], early["ind_match_price"]) <= 0:
                return None
            if early["auction_type"] != "M" or early["auction_status"] not in (0, 1):
                return None
            if early["receive_ns"] >= decision_ns - 110000000000 or decision_ns - 110000000000 - early["receive_ns"] > 2000000000:
                return None
            if not 0 <= decision_ns - 110000000000 - early["event_ns"] <= 2000000000:
                return None
            indicative_return = indicative / early["ind_match_price"] - 1
            underlying = indicative_return - (reference / early["ref_price"] - 1)
            if underlying * indicative_return <= 0:
                return None
    if not np.isfinite(underlying) or underlying == 0:
        return None
    leverage = 1 if rule.endswith("_1x") else 3
    positive, negative = ("SPY", "SH") if leverage == 1 else ("UPRO", "SPXU")
    return {"symbol": positive if underlying > 0 else negative,
            "underlying_prediction": underlying, "projected_return": abs(underlying) * leverage}


def replay_day(day, rows, early, late, rule, hold, scenario):
    q = {(row["symbol"], row["label"]): row for row in rows.to_dict("records")}
    decision = int(rows.loc[rows.label.eq("signal"), "target_ns"].iloc[0])
    record = {"date": day, "rule": rule, "hold_s": hold, "decision_ns": decision}
    prediction = forecast(rule, q, early, late, decision)
    if prediction is None:
        return {**record, "status": "no_causal_signal", "complete": True, "pnl": 0.}
    symbol = prediction["symbol"]
    signal = q.get((symbol, "signal"))
    record.update(prediction)
    if not valid(signal, 1000000000):
        return {**record, "status": "predecision_unknown", "complete": True, "pnl": 0.}
    intended = math.floor(min(10000 / (signal["ask"] * 1.01), signal["ask_qty"] * .1))
    record.update(quantity=intended, signal_ask=signal["ask"], signal_ask_qty=signal["ask_qty"], signal_receive_ns=signal["receive_ns"])
    if intended < 1:
        return {**record, "status": "predecision_size", "complete": True, "pnl": 0.}
    projected_exit = signal["bid"] * (1 + prediction["projected_return"])
    expected = intended * (projected_exit - signal["ask"]) - sum(costs(intended, signal["ask"], projected_exit))
    record.update(projected_exit=projected_exit, expected_net=expected)
    if expected <= intended * signal["ask"] / 10000:
        return {**record, "status": "below_cost_gate", "complete": True, "pnl": 0.}
    # Costs used for signal eligibility remain frozen across stresses.
    delay = scenario["delay_s"]
    limit = math.floor(signal["ask"] * 1.0005 * 100) / 100
    entry = q[symbol, f"entry_{delay}"]
    exit_row = q[symbol, f"exit_{delay}_{hold}"]
    record.update(limit=limit, entry_target_ns=entry["target_ns"], exit_target_ns=exit_row["target_ns"],
                  entry_ack_ns=entry["target_ns"] + delay * 1000000000,
                  exit_ack_ns=exit_row["target_ns"] + delay * 1000000000)
    if not valid(entry, 250000000):
        return {**record, "status": "unresolved_entry", "complete": False, "pnl": None}
    if entry["ask"] > limit + 1e-10:
        return {**record, "status": "rejected_fok", "complete": True, "pnl": 0.}
    if intended > entry["ask_qty"]:
        return {**record, "status": "unresolved_entry_depth", "complete": False, "pnl": None}
    record.update(entry=entry["ask"], entry_source_event_ns=entry["event_ns"])
    if not valid(exit_row, 250000000) or intended > exit_row["bid_qty"]:
        return {**record, "status": "unresolved_exit", "open_quantity": intended, "complete": False, "pnl": None}
    gross = intended * (exit_row["bid"] - entry["ask"])
    commission, levy, adverse = costs(intended, entry["ask"], exit_row["bid"], scenario["fee_multiplier"], scenario["adverse_bps"])
    return {**record, "status": "priced", "complete": True, "exit": exit_row["bid"],
            "exit_source_event_ns": exit_row["event_ns"], "closed_quantity": intended,
            "gross": gross, "commission": commission, "sell_levy": levy, "adverse": adverse,
            "pnl": gross - commission - levy - adverse}
