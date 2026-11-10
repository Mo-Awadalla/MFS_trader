"""Independent original-CSV proof of the observed no-entry replay outcomes."""

import calendar
import csv
import json
from datetime import UTC, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from research_scout.prepare_databento_fast_20261002 import ROOT, sha, write

PARENT = ROOT / "research_scout/databento_public_mbo_20261003"
OUT = PARENT / "passive_probe_v1"


@lru_cache(maxsize=86400)
def seconds(text):
    return calendar.timegm(datetime.strptime(text, "%Y-%m-%dT%H:%M:%S").timetuple())


def clock(text):
    whole, fraction = text.removesuffix("Z").split(".")
    assert len(fraction) == 9
    return seconds(whole) * 1000000000 + int(fraction)


def price(text):
    if not text:
        return None
    value = Decimal(text) * 1000000000
    assert value == value.to_integral_value()
    return int(value)


def best(orders, side):
    same = [v for v in orders.values() if v[0] == side]
    if not same:
        return [None, 0, 0]
    px = (max if side == "B" else min)(v[1] for v in same)
    sizes = [v[2] for v in same if v[1] == px]
    return [px, sum(sizes), len(sizes)]


def main():
    assert not (OUT / "independent_verification.json").exists()
    spec = json.loads((OUT / "specification.json").read_text())
    results = json.loads((OUT / "results.json").read_text())
    assert results["specification_sha256"] == sha(OUT / "specification.json")
    source = PARENT / "sources/xnas_itch_mbo.csv"
    assert sha(source) == spec["source"]["source_sha256"]
    for path, expected in spec["pinned_sha256"].items():
        assert sha(ROOT / path) == expected
    event = spec["events"][0]
    contexts, actions = {}, []
    for c in spec["cases"]:
        name, delay, shift, d = c["name"], c["latency_ns"], c["clock_ns"], event["decision_ns"]
        times = (d + 50000 + delay + shift, d + 1000050000 + delay + shift,
                 d + 1000100000 + 3 * delay + shift, d + 5000050000 + delay + shift,
                 d + 5000100000 + 3 * delay + shift)
        kinds = ("post_bid", "cancel_bid", "post_ask", "cancel_ask", "force_exit")
        contexts[name] = {"start": times[0], "stop": times[1], "active": False, "ahead": {},
                          "ledger": [], "resting_bid_fills": 0, "reaching_fills": 0}
        actions.extend((t, name, kind) for t, kind in zip(times, kinds, strict=True))
    actions.sort()
    orders, previous, action_index, count = {}, None, 0, 0
    with source.open(newline="", encoding="utf-8") as handle:
        for ordinal, raw in enumerate(csv.DictReader(handle)):
            count += 1
            r = {"source_row": ordinal, "ts_event": clock(raw["ts_event"]), "ts_recv": clock(raw["ts_recv"]),
                 "action": raw["action"], "side": raw["side"], "price": price(raw["price"]),
                 "order_id": int(raw["order_id"]), "size": int(raw["size"]), "sequence": int(raw["sequence"])}
            assert (raw["publisher_id"], raw["instrument_id"], raw["symbol"]) == ("2", "11667", "NVDA")
            if previous is not None:
                assert all(r[k] >= previous[k] for k in ("ts_event", "ts_recv", "sequence"))
                assert r["ts_recv"] - r["ts_event"] == int(raw["ts_in_delta"])
                assert not int(raw["flags"]) & 12
            else:
                assert ordinal == 0 and r["action"] == "R" and raw["flags"] == "8"
            while action_index < len(actions) and actions[action_index][0] <= r["ts_event"]:
                time, name, kind = actions[action_index]
                state = contexts[name]
                relevant = kind in ("post_bid", "cancel_bid")
                assert not relevant or time != r["ts_event"]
                state["ledger"].append({"kind": "scheduled_action", "action": kind, "event_ns": time,
                                        "source_before": previous["source_row"], "source_after": ordinal,
                                        "native_before": previous["ts_event"], "native_after": r["ts_event"], "relevant": relevant})
                if kind == "post_bid":
                    state["active"] = True
                    state["ahead"] = {oid: v[2] for oid, v in orders.items() if (v[0], v[1]) == ("B", event["bid_price_int"])}
                    bid, ask = best(orders, "B"), best(orders, "A")
                    assert 0 < bid[0] < ask[0] and event["bid_price_int"] < ask[0]
                    state["initial_ahead_quantity"] = sum(state["ahead"].values())
                    state["ledger"].append({"kind": "posted", "order": "bid", "arrival_ns": time,
                                            "side": "B", "price_int": event["bid_price_int"], "requested_quantity": event["quantity"],
                                            "initial_ahead": {str(k): v for k, v in state["ahead"].items()}, "bid": bid, "ask": ask})
                elif kind == "cancel_bid":
                    state["active"] = False
                    state["remaining_ahead_at_cancel"] = sum(state["ahead"].values())
                action_index += 1
            if action_index == len(actions):
                assert ordinal == results["source_last_row"] and r["ts_event"] == results["source_last_event_ns"]
                break
            action, side, oid, px, qty = (r[k] for k in ("action", "side", "order_id", "price", "size"))
            for state in contexts.values():
                if not state["active"]:
                    continue
                assert action != "R"
                if action == "F" and side == "B":
                    state["resting_bid_fills"] += 1
                    resting = orders[oid]
                    assert resting[0] == "B" and 0 < qty <= resting[2]
                    if min(resting[1], px) <= event["bid_price_int"]:
                        state["reaching_fills"] += 1
                if action == "C" and oid in state["ahead"]:
                    state["ahead"][oid] -= qty
                    assert state["ahead"][oid] >= 0
                    if state["ahead"][oid] == 0:
                        del state["ahead"][oid]
                    state["ledger"].append({"kind": "queue_cancel", "order": "bid", "source_row": ordinal,
                                            "order_id": oid, "quantity": qty, "ahead_after": sum(state["ahead"].values())})
            if action == "R":
                assert ordinal == 0
                orders.clear()
            elif action == "A":
                assert oid not in orders and side in ("A", "B") and px > 0 and qty > 0
                orders[oid] = [side, px, qty]
            elif action == "C":
                v = orders[oid]
                assert (v[0], v[1]) == (side, px) and 0 < qty <= v[2]
                v[2] -= qty
                if not v[2]:
                    del orders[oid]
            elif action == "F":
                v = orders[oid]
                assert v[0] == side and 0 < qty <= v[2]
            else:
                assert action in ("T", "N"), "Unexpected source action needs independent treatment"
            previous = r
    assert count == results["source_prefix_rows"] and action_index == len(actions)
    details = []
    for reported in results["cases"]:
        state = contexts[reported["case"]]
        assert state["reaching_fills"] == 0, "No-fill proof fails; a full independent queue replay would be required"
        assert state["ledger"] == reported["ledger"]
        assert reported["status"] == "no_entry_fill" and reported["unknown_reason"] is None
        assert reported["fills"] == [] and reported["bought"] == reported["sold"] == reported["residual_known_inventory"] == 0
        assert reported["cash"] == reported["known_cash_component"]
        assert all(Decimal(v) == 0 for v in reported["cash"].values())
        details.append({"case": reported["case"], **{k: state[k] for k in (
            "start", "stop", "initial_ahead_quantity", "remaining_ahead_at_cancel", "resting_bid_fills", "reaching_fills")}})
    verification = {"verified": True, "completed_at_utc": datetime.now(UTC).isoformat(), "original_csv_rows": count,
                    "cases": details, "specification_sha256": sha(OUT / "specification.json"),
                    "results_sha256": sha(OUT / "results.json"), "audit_code_sha256": sha(Path(__file__)),
                    "source_sha256": sha(source), "scope": "Independent stdlib original-CSV clock/price parsing and plain-dictionary book. Every posted queue, native action bracket and queue cancellation matches. No resting-side F with either display or execution price at/below our bid occurs during ANY entry lifetime, so zero entry follows even without a queue model. Empty cash flows, fees and inventory independently verified. This audits these no-fill observations; it is not an independent validation of unused filled-entry/exit branches or actual posting.",
                    "actual_execution_verified": False, "reliable_edge_established": False, "paid_calls": 0}
    write(OUT / "independent_verification.json", verification)
    print(json.dumps(verification), flush=True)


if __name__ == "__main__":
    main()
