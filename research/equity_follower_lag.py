"""Causal cross-ETF displacement budget after a verified SPY source sweep."""

from decimal import ROUND_FLOOR, Decimal

import numpy as np

from research.equity_resilience import optimistic_cash

NS, MS = 1000000000, 1000000
MULTIPLIERS = {"SSO": 2, "UPRO": 3, "SH": -1, "SDS": -2, "SPXU": -3}


def snapshot(prepared, cutoff, age):
    qt, qe, bid, ask, bq, aq, valid, source = prepared[:8]
    i = int(np.searchsorted(qt, np.int64(cutoff), side="left")) - 1
    if i < 0 or not valid[i]:
        return None, "invalid_latest_book"
    if not (0 < cutoff - int(qt[i]) <= age and 0 <= cutoff - int(qe[i]) <= age):
        return None, "quote_age_or_native_clock"
    b, a = int(bid[i]), int(ask[i])
    if b % 10000000 or a % 10000000:
        return None, "noncent_price"
    if (a - b) * 20000 > 5 * (a + b):
        return None, "spread"
    return {"quote_index": i, "source_index": int(source[i]), "receive_ns": int(qt[i]),
            "event_ns": int(qe[i]), "bid_int": b, "ask_int": a,
            "bid_size": int(bq[i]), "ask_size": int(aq[i])}, None


def leader(prepared, group, opening):
    decision = (group["burst_receive_ns"] // MS + 2) * MS
    if not opening + 5 * NS <= decision <= opening + 570 * NS:
        return None, "outside_schedule"
    cutoff, anchor = decision - MS, decision - MS - NS
    now, why = snapshot(prepared, cutoff, 5 * MS)
    if why:
        return None, "leader_current_" + why
    if now["source_index"] < group["burst_last_source"]:
        return None, "leader_burst_incomplete"
    old, why = snapshot(prepared, anchor, 250 * MS)
    if why:
        return None, "leader_reference_" + why
    sign = group["direction"]
    if min(sign * (now[k] - old[k]) for k in ("bid_int", "ask_int")) <= 0:
        return None, "leader_both_sides_not_displaced_over_1s"
    return {"decision_ns": decision, "cutoff_ns": cutoff, "anchor_ns": anchor,
            "leader_current": now, "leader_reference": old, "group": group}, None


def follower(prepared, symbol, signal):
    beta, sign = MULTIPLIERS[symbol], signal["group"]["direction"]
    if beta * sign < 0:
        return None, "wrong_long_direction", None
    now, why = snapshot(prepared, signal["cutoff_ns"], 250 * MS)
    if why:
        return None, "follower_current_" + why, None
    old, why = snapshot(prepared, signal["anchor_ns"], 250 * MS)
    if why:
        return None, "follower_reference_" + why, None
    limit = ((now["ask_int"] * 102 + NS - 1) // NS) * 10000000
    q = min(10000 * NS // limit, now["bid_size"] // 10, now["ask_size"] // 10)
    if q <= 0:
        return None, "quantity", None
    leader_now, leader_old = signal["leader_current"], signal["leader_reference"]
    l1 = leader_now["bid_int"] + leader_now["ask_int"]
    l0 = leader_old["bid_int"] + leader_old["ask_int"]
    # Daily target multiplier is only a short-horizon modeling assumption, not arbitrage proof.
    factor = Decimal(1) + Decimal(beta * (l1 - l0)) / l0
    projected_mid = Decimal(old["bid_int"] + old["ask_int"]) / 2 * factor
    projected_bid = projected_mid - Decimal(now["ask_int"] - now["bid_int"]) / 2
    exit_int = int((projected_bid / 10000000).to_integral_value(rounding=ROUND_FLOOR)) * 10000000
    if exit_int <= 0:
        return None, "nonpositive_projected_price", None
    cash = optimistic_cash(now["ask_int"], exit_int, q)
    current = optimistic_cash(now["ask_int"], now["bid_int"], q)
    entry_value = Decimal(q * now["ask_int"]) / NS
    net_bp = Decimal(cash["net"]) * 10000 / entry_value
    cost_bp = -Decimal(current["net"]) * 10000 / entry_value
    detail = {**signal, "symbol": symbol, "multiplier": beta,
              "follower_current": now, "follower_reference": old,
              "quantity": q, "entry_limit_int": limit,
              "leader_move_bp": str(Decimal(l1 - l0) * 10000 / l0),
              "projected_mid_int": str(projected_mid), "projected_exit_int": exit_int,
              "projected_cash": cash, "projected_net_bp": str(net_bp),
              "causal_cost_bp": str(cost_bp), "rule": "spy_follower_lag_long"}
    if cost_bp > 12:
        return None, "causal_cost_above_12bp", detail
    if net_bp < 2:
        return None, "projected_net_below_2bp", detail
    return detail, None, detail


def select(events):
    ranked = sorted(events, key=lambda r: (r["decision_ns"], -Decimal(r["projected_cash"]["net"]),
                                           -Decimal(r["projected_net_bp"]), r["symbol"],
                                           r["group"]["burst_last_source"]))
    chosen, last, symbols = [], -10**30, {}
    for e in ranked:
        t = e["decision_ns"]
        if t - last >= 6 * NS and t - symbols.get(e["symbol"], -10**30) >= 60 * NS:
            chosen.append(e)
            last, symbols[e["symbol"]] = t, t
    return chosen
