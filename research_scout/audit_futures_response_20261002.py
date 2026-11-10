"""Independent raw SIP/FOK/collateral/cash reconciliation for SPY responses."""

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_FLOOR
from decimal import Decimal as D
from pathlib import Path

import numpy as np
import pandas as pd

from research_scout.audit_futures_etf_20261002 import raw_quote

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"research_scout/futures_response_hft_20261002"
RUN = OUT/"replay_v1"
COUNTS = Counter()
MAX_ERROR = D(0)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def equal(a, b):
    global MAX_ERROR
    error = abs(D(str(a))-D(str(b)))
    MAX_ERROR = max(MAX_ERROR, error)
    assert error < D("1e-9"), (a, b)


def execution(frame, target, radius, buying):
    times = frame.timestamp.dt.as_unit("ns").astype("int64").to_numpy()
    before = times[times < target-radius]
    after = np.flatnonzero(times > target+radius)
    if not len(before) or not len(after):
        return None
    previous = int(before.max())
    positions = np.flatnonzero((times >= previous) & (times <= target+radius))
    group = frame.iloc[positions]
    values = group[["bid_price", "ask_price", "bid_size", "ask_size"]].to_numpy(float)
    if (not np.isfinite(values).all() or not (values > 0).all() or not (values[:, 0] < values[:, 1]).all()
            or not (values[:, 1] < 1e7).all() or not group.conditions.eq('["R"]').all()
            or not group.bid_exchange.fillna("").str.len().gt(0).all() or not group.ask_exchange.fillna("").str.len().gt(0).all()):
        return None
    prefix = "ask" if buying else "bid"
    prices = [D(str(p)) for p in group[prefix+"_price"]]
    quantities = [D(str(q))*100 for q in group[prefix+"_size"]]
    return {"prices": prices, "quantities": quantities, "first": int(positions[0]), "stop": int(positions[-1])+1,
            "successor": int(times[after[0]])}


def check_envelope(saved, raw):
    if raw is None:
        assert not saved["known"]
        return
    assert saved["known"] and (saved["first_index"], saved["stop_index"], saved["successor_ns"]) == (raw["first"], raw["stop"], raw["successor"])
    equal(saved["price_lower"], min(raw["prices"]))
    equal(saved["price_upper"], max(raw["prices"]))
    equal(saved["minimum_touch_shares"], min(raw["quantities"]))
    COUNTS["quote_envelopes_verified"] += 1


def verify_intent(event, intent, raw):
    quote, index = raw_quote(raw, event["signal_cutoff_ns"])
    assert intent["signal_index"] == index
    if quote is None:
        assert not intent["eligible"] and intent["reason"] == "missing_invalid_or_tied_signal"
        COUNTS["predecision_rejections_verified"] += 1
        return
    long = (D(str(event["current_price"])) > D(str(event["reference_price"]))) == (intent["rule"] == "follow_impulse")
    bid, ask = quote["bid"], quote["ask"]
    anchor, depth = (ask, quote["aq"]) if long else (bid, quote["bq"])
    quantity = int(min(D(10000)/(anchor*D("1.01")), depth/10))
    limit = (anchor*(D("1.001") if long else D("0.999"))/D("0.01")).to_integral_value(rounding=ROUND_FLOOR if long else ROUND_CEILING)*D("0.01")
    mark = max(ask, limit)
    reserve = quantity*mark+4*max(D(1), quantity*D("0.0075"))+2*(quantity*mark*D("0.00003")+quantity*D("0.0002"))+quantity*mark*D("0.0004")
    if not long:
        reserve += quantity*mark*D("0.1")/365
    spread = (ask-bid)*20000/(ask+bid)
    eligible = spread <= 20 and quantity*anchor >= 100
    assert intent["long"] == long and intent["quantity"] == quantity and intent["eligible"] == eligible
    assert intent["signal_quote_ns"] == quote["time"]
    for name, value in (("limit", limit), ("capital_reserved", reserve), ("spread_bps", spread), ("signal_bid", bid), ("signal_ask", ask)):
        equal(intent[name], value)
    COUNTS["entry_intents_verified"] += 1


def verify_submission(event, intent, row, frame, scenario, capital):
    effective = event["decision_ns"]+(scenario["feed_ms"]-100)*1_000_000
    entry = effective+50_000_000+scenario["outbound_ms"]*1_000_000
    exit_time = entry+scenario["ack_ms"]*1_000_000+15_000_000_000+50_000_000+scenario["outbound_ms"]*1_000_000
    radius = scenario["clock_ms"]*1_000_000
    assert row["entry_arrival_ns"] == entry and row["exit_arrival_ns"] == exit_time
    assert row["inventory_schedule_upper_ns"] == exit_time-entry+2*radius <= 30_000_000_000
    long, quantity, limit = intent["long"], intent["quantity"], D(intent["limit"])
    entering, exiting = execution(frame, entry, radius, long), execution(frame, exit_time, radius, not long)
    check_envelope(row["entry_quotes"], entering)
    check_envelope(row["exit_quotes"], exiting)
    fill = "unknown"
    if entering is not None:
        marketable = [(p <= limit if long else p >= limit) for p in entering["prices"]]
        if not any(marketable):
            fill = "no_fill"
        elif all(marketable) and all(q >= quantity for q in entering["quantities"]):
            fill = "filled"
    assert row["entry_outcome"] == fill
    if fill == "no_fill":
        expected = "no_fill"
    elif fill == "unknown":
        expected = "unknown_entry"
    elif max(entering["prices"])*quantity > capital:
        expected = "unknown_entry_collateral"
    elif exiting is None or min(exiting["quantities"]) < quantity:
        expected = "unknown_exit"
    else:
        expected = "conditional_complete"
    assert row["status"] == expected
    if expected.startswith("unknown"):
        assert row["potential_inventory_quantity"] == [0, quantity]
        COUNTS["submitted_unknowns_verified"] += 1
        return None
    assert row["potential_inventory_quantity"] == [0, 0]
    if expected == "no_fill":
        return D(0), D(0)
    outcomes = []
    # Enumerate every observed distinct entry/exit price combination; do not
    # assume the production four-corner calculation is sufficient.
    for start in set(entering["prices"]):
        for end in set(exiting["prices"]):
            gross = quantity*(end-start)*(1 if long else -1)
            commission = 2*max(D(1), quantity*D("0.0075"))*scenario["fee_multiple"]
            sold = end if long else start
            sell = (quantity*sold*D("0.00003")+quantity*D("0.0002"))*scenario["fee_multiple"]
            adverse = quantity*(start+end)*D("0.0001")*scenario["adverse_multiple"]
            borrow = D(0) if long else quantity*max(start, end)*D("0.05")/365*scenario["fee_multiple"]
            outcomes.append({"entry_price": start, "exit_price": end, "gross": gross, "commissions": commission,
                             "sell_charges": sell, "adverse": adverse, "borrow": borrow, "net": gross-commission-sell-adverse-borrow})
    low, high = min(outcomes, key=lambda r: r["net"]), max(outcomes, key=lambda r: r["net"])
    for name, expected_cash in (("lower", low), ("upper", high)):
        for key, value in expected_cash.items():
            equal(row[name][key], value)
    COUNTS["cash_rectangles_verified"] += 1
    return low["net"], high["net"]


def main():
    output = RUN/"independent_verification.json"
    assert not output.exists()
    spec = json.loads((OUT/"specification.json").read_text())
    freeze = json.loads((RUN/"implementation.json").read_text())
    for filename, expected in freeze["code_sha256"].items():
        assert sha(ROOT/filename) == expected
    assert sha(OUT/"specification.json") == freeze["specification_sha256"]
    assert sha(ROOT/spec["events_path"]) == freeze["events_sha256"]
    assert sha(ROOT/spec["quote_manifest_path"]) == freeze["quote_manifest_sha256"]
    events = pd.read_parquet(ROOT/spec["events_path"]).to_dict("records")
    event_map = {(r["date"], r["decision_ns"]): r for r in events}
    raw = {}
    for item in json.loads((ROOT/spec["quote_manifest_path"]).read_text())["files"]:
        assert item["complete"] and sha(ROOT/item["path"]) == item["sha256"]
        raw[item["window_id"]] = pd.read_parquet(ROOT/item["path"])
        COUNTS["sip_source_records_verified"] += len(raw[item["window_id"]])
    intents = json.loads((RUN/"intents.json").read_text())
    intent_map = {}
    for rule, values in intents.items():
        for intent in values:
            key = intent["date"], intent["decision_ns"]
            verify_intent(event_map[key], intent, raw[intent["window_id"]])
            intent_map[(rule, *key)] = intent
    result = json.loads((RUN/"results.json").read_text())
    assert sha(RUN/"intents.json") == result["intents_sha256"]
    for summary in result["scenarios"]:
        path = RUN/summary["ledger"]
        assert sha(path) == summary["ledger_sha256"]
        ledger = json.loads(path.read_text())["events"]
        assert len(ledger) == len(events)
        scenario = next(s for s in spec["scenarios"] if s["name"] == summary["scenario"])
        accounts = {}
        for row in ledger:
            key = row["date"], row["decision_ns"]
            intent = intent_map[(summary["rule"], *key)]
            account = accounts.setdefault(row["date"], [D(10000), D(10000), False])
            equal(row["cash_lower_before"], account[0])
            equal(row["cash_upper_before"], account[1])
            if account[2]:
                assert not row["submitted"] and row["status"] == "halted_after_unknown_inventory"
                COUNTS["subsequent_inventory_halts_verified"] += 1
            elif not intent["eligible"] or D(intent["capital_reserved"]) > account[0]:
                assert not row["submitted"] and row["status"] == "predecision_no_order"
            else:
                assert row["submitted"]
                cash = verify_submission(event_map[key], intent, row, raw[row["window_id"]], scenario, account[0])
                if cash is None:
                    account[2] = True
                else:
                    account[0] += cash[0]
                    account[1] += cash[1]
            equal(row["cash_lower_after"], account[0])
            equal(row["cash_upper_after"], account[1])
            assert row["halted_after"] == account[2]
            COUNTS["ledger_rows_verified"] += 1
        lower, upper = D(0), D(0)
        daily_values = []
        for day in summary["by_date"]:
            account = accounts[day["date"]]
            lower += account[0]-10000
            upper += account[1]-10000
            assert day["complete"] == (not account[2])
            equal(day["known_component_lower"], account[0]-10000)
            equal(day["known_component_upper"], account[1]-10000)
            if account[2]:
                assert day["net_lower"] is None and day["net_upper"] is None
            else:
                equal(day["net_lower"], account[0]-10000)
                equal(day["net_upper"], account[1]-10000)
                daily_values.append(account[0]-10000)
        complete = all(not a[2] for a in accounts.values())
        assert summary["complete"] == complete
        equal(summary["known_component_lower"], lower)
        equal(summary["known_component_upper"], upper)
        if complete:
            equal(summary["net_lower"], lower)
            equal(summary["net_upper"], upper)
            equal(summary["drop_best_three_dates_lower"], lower-sum(sorted(daily_values, reverse=True)[:3], D(0)))
        else:
            assert summary["net_lower"] is None and summary["net_upper"] is None and summary["drop_best_three_dates_lower"] is None
        assert summary["outcomes"] == dict(Counter(r["status"] for r in ledger))
        COUNTS["scenario_aggregates_verified"] += 1
    verification = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(), "counts": dict(COUNTS),
                    "maximum_numeric_difference": str(MAX_ERROR), "auditor_sha256": sha(Path(__file__)),
                    "independent_signal_quote_parser_sha256": sha(ROOT/"research_scout/audit_futures_etf_20261002.py"),
                    "results_sha256": sha(RUN/"results.json"),
                    "scope": "All causal intents, raw SIP clock/depth/FOK paths, collateral gates, post-unknown halts, every observed distinct price-pair cash outcome and account/day/scenario aggregates independently reconciled. No production replay imports.",
                    "actual_execution_verified": False, "historical_borrow_and_permissions_verified": False,
                    "reliable_edge_established": False}
    output.write_text(json.dumps(verification, indent=2)+"\n")
    print(json.dumps(verification), flush=True)


if __name__ == "__main__":
    main()
