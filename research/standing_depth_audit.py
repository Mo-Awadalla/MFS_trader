"""Check a recorded top-five state against subsequent native depth deltas."""

import json

import numpy as np
import pandas as pd


def parse_depth(payload, day, symbol):
    start = pd.Timestamp(day, tz="UTC").value // 1000
    rows, last_capture = [], -1
    for i, line in enumerate(payload.decode().splitlines()):
        if not line.strip():
            rows.append({"disconnect": True, "source_line": i})
            continue
        stamp, encoded = line.split(" ", 1)
        wrapper = json.loads(encoded)
        raw = wrapper.get("data", wrapper)
        if raw.get("e") != "depthUpdate" or raw.get("s") != symbol:
            raise ValueError("Unexpected native depth message")
        capture = pd.Timestamp(stamp).value // 1000 - start
        if capture < last_capture:
            raise ValueError("Native capture clock backtracked")
        last_capture = capture
        rows.append({"disconnect": False, "source_line": i, "local_us": capture,
                     "E_us": int(raw["E"]) * 1000 - start, "T_us": int(raw["T"]) * 1000 - start,
                     "U": int(raw["U"]), "u": int(raw["u"]), "pu": int(raw["pu"]),
                     "b": raw["b"], "a": raw["a"]})
    return rows


def unchanged_topfive(rows, quote, tick):
    matches = [i for i, row in enumerate(rows) if not row["disconnect"] and row["local_us"] == quote["quote_local_us"]]
    result = {"verified_unchanged": False, "source_capture_matches": len(matches)}
    if len(matches) != 1:
        return {**result, "reason": "ambiguous_or_missing_source_capture"}
    pos = matches[0]
    first = rows[pos]
    matches_e = first["E_us"] == quote["quote_exchange_us"]
    matches_t = first["T_us"] == quote["quote_exchange_us"]
    result.update(csv_clock_matches_E=matches_e, csv_clock_matches_T=matches_t,
                  source_E_minus_T_us=first["E_us"] - first["T_us"],
                  source_native_T_us=first["T_us"], source_native_E_us=first["E_us"])
    if not matches_e and not matches_t:
        return {**result, "reason": "source_time_matches_neither_native_clock"}
    known = {side: {int(round(quote[f"{name}[{i}].price"] / tick)): quote[f"{name}[{i}].amount"]
                    for i in range(5)} for side, name in (("b", "bids"), ("a", "asks"))}
    boundary = {"b": min(known["b"]), "a": max(known["a"])}
    last_id, last_t = first["u"], first["T_us"]
    for traversed, raw in enumerate(rows[pos + 1:]):
        if raw["disconnect"]:
            return {**result, "reason": "disconnect_before_successor"}
        if raw["pu"] != last_id or raw["u"] <= last_id or raw["U"] > raw["u"]:
            return {**result, "reason": "native_sequence_gap"}
        if raw["T_us"] < last_t:
            return {**result, "reason": "native_transaction_clock_backtrack"}
        last_id, last_t = raw["u"], raw["T_us"]
        if raw["T_us"] >= quote["target_us"]:
            if raw["T_us"] == quote["target_us"]:
                return {**result, "reason": "transaction_timestamp_tie_at_order"}
            return {**result, "verified_unchanged": True, "reason": "top_five_unchanged_with_native_sequence_continuity",
                    "updates_between_source_and_target": traversed, "successor_T_us": raw["T_us"],
                    "successor_E_us": raw["E_us"], "successor_local_us": raw["local_us"]}
        for side in ("b", "a"):
            for price, amount in raw[side]:
                level, quantity = int(round(float(price) / tick)), float(amount)
                within = level >= boundary[side] if side == "b" else level <= boundary[side]
                if within and not np.isclose(quantity, known[side].get(level, 0.), rtol=1e-9, atol=1e-9):
                    return {**result, "reason": "top_five_changed_before_transaction_time_target",
                            "change_T_us": raw["T_us"], "change_E_us": raw["E_us"], "side": side}
    return {**result, "reason": "no_native_successor_in_slice"}
