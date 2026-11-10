"""Independent external signal/cancel and Decimal cash audit, no replay imports."""

import bisect
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/"research_scout/external_quote_hft_20261002"
RUN = BASE/"replay_v1"
NS, DELAY, AGE = 1_000_000_000, 250_000_000, 5_000_000_000
COUNTS = Counter()
MAX_ERROR = 0.


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(actual, expected):
    global MAX_ERROR
    error = abs(float(actual)-float(expected))
    MAX_ERROR = max(MAX_ERROR, error)
    assert error < 0.000001, (actual, expected)


def capture(stamp):
    whole, fraction = stamp.rstrip("Z").split(".")
    return int(datetime.fromisoformat(whole).replace(tzinfo=UTC).timestamp())*NS+int(fraction.ljust(9,"0"))


def external_states(files, symbols):
    states, series = {s:{} for s in symbols}, defaultdict(list)
    ids = {}
    index, previous_capture = 0, -1
    for source in sorted(files, key=lambda x:x["offset"]):
        path = ROOT/source["path"]
        assert digest(path) == source["compressed_sha256"]
        raw_hash = hashlib.sha256()
        with gzip.open(path,"rb") as stream:
            for raw in stream:
                index += 1
                raw_hash.update(raw)
                if not raw.strip():
                    for s in symbols:
                        states[s] = {}
                        ids.pop(s,None)
                        series[s].append({"cap":previous_capture,"source":index,"valid":False})
                    COUNTS["disconnects"] += 1
                    continue
                stamp, payload = raw.decode().split(" ",1)
                cap = capture(stamp)
                assert cap >= previous_capture
                previous_capture = cap
                message = json.loads(payload)
                e = message["data"]
                s, u, seq = e["s"],e["u"],e["seq"]
                assert message["topic"] == "orderbook.1."+s and s in symbols
                pub, cts = message["ts"]*1_000_000,message["cts"]*1_000_000
                assert -1_000_000 <= cap-pub <= AGE and -1_000_000 <= cap-cts <= AGE and cts <= pub+1_000_000
                snapshot = message["type"] == "snapshot"
                old = ids.get(s)
                old_state = dict(states[s])
                if old and not (snapshot and u == 1):
                    assert seq >= old[1] and u >= old[0]
                    assert snapshot or u == old[0]+1
                if snapshot:
                    states[s] = {}
                for side in ("b","a"):
                    values = {D(p):D(q) for p,q in e[side]}
                    assert all(p>0 and q>=0 for p,q in values.items())
                    positive = {p:q for p,q in values.items() if q>0}
                    assert len(positive)<=1
                    if positive:
                        p,q = next(iter(positive.items()))
                        states[s][side] = (p,q,index)
                    elif side in states[s] and values.get(states[s][side][0]) == 0:
                        states[s].pop(side)
                if snapshot and old and u == old[0] and u != 1 and all(k in old_state for k in ("b","a")):
                    assert all(states[s][k][:2] == old_state[k][:2] for k in ("b","a"))
                    COUNTS["independent_snapshot_reconciliations"] += 1
                ids[s] = (u,seq)
                valid = all(k in states[s] for k in ("b","a"))
                if valid:
                    assert states[s]["b"][0] < states[s]["a"][0]
                series[s].append({"cap":cap,"pub":pub,"cts":cts,"source":index,"valid":valid,**states[s]})
                COUNTS["external_native_messages"] += 1
        assert raw_hash.hexdigest() == source["decoded_sha256"]
    return series


def valid_at(row, cutoff):
    return row["valid"] and all(0<cutoff-row[k]<=AGE for k in ("cap","pub","cts"))


def budget(row, price, buy):
    anchor = row["b" if buy else "a"][0]
    return (anchor-price if buy else price-anchor)-price*D("0.0004")-anchor*D("0.0007")


def verify_plan(row, external, caps, scenario):
    plan = row["external_plan"]
    decision = row["decision_ns"]
    start = bisect.bisect_left(caps,decision-DELAY)-1
    valid = start>=0 and valid_at(external[start],decision-DELAY)
    if not valid:
        assert not plan["eligible"] and row["status"] == "predecision_no_order"
        return
    state = external[start]
    assert (plan["source_index"],plan["receive_ns"],plan["publication_ns"],plan["transaction_ns"]) == (state["source"],state["cap"],state["pub"],state["cts"])
    assert D(str(plan["bid"])) == state["b"][0] and D(str(plan["ask"])) == state["a"][0]
    assert (plan["bid_seed_source"],plan["ask_seed_source"]) == (state["b"][2],state["a"][2])
    if "intended_quantity" not in row:
        assert not plan["eligible"] and not plan["buy"]["admitted"] and not plan["sell"]["admitted"]
        COUNTS["no_external_budget"] += 1
        return
    last_cancel = row["scheduled_cancel_ns"]
    outbound = scenario["delay_ns"]
    last_send = last_cancel-outbound
    stop = bisect.bisect_right(caps,last_send-DELAY-1)
    for buy,name in ((True,"buy"),(False,"sell")):
        price = D(str(row["bid_limit" if buy else "ask_limit"]))
        expected = budget(state,price,buy)
        assert plan[name]["admitted"] == (expected>0)
        close(plan[name]["cushion_per_unit"],expected)
        if expected<=0:
            assert row[name+"_acceptance"] == "not_submitted" and row[name+"_quantity_bounds"] == [0,0]
            continue
        candidates = [(last_send,2,0,"scheduled",None)]
        # Enumerate all possible triggers independently, then take the earliest.
        for i in range(start,stop):
            current = external[i]
            available = current["cap"]+DELAY+1
            if i>start and (not valid_at(current,available-DELAY) or budget(current,price,buy)<=0):
                reason = "external_state_invalid" if not valid_at(current,available-DELAY) else "external_cushion_exhausted"
                candidates.append((available,1,i,reason,current["source"]))
            if current["valid"]:
                expiration = min(current[k] for k in ("cap","pub","cts"))+AGE+DELAY+1
                next_available = external[i+1]["cap"]+DELAY+1 if i+1<len(external) else last_send+NS
                if decision<expiration<=last_send and expiration<=next_available:
                    candidates.append((expiration,0,i,"external_freshness_expired",current["source"]))
        trigger,_,_,reason,source = min(candidates)
        assert plan[name]["cancel_ns"] == trigger+outbound
        assert (plan[name]["trigger_ns"],plan[name]["reason"],plan[name]["source_index"]) == (trigger,reason,source)
        COUNTS["independent_cancellation_paths"] += 1
    assert row["flatten_ns"] == max(plan[k]["cancel_ns"] for k in ("buy","sell") if plan[k]["admitted"])+2*outbound
    COUNTS["admitted_cycle_plans"] += 1


def verify_cash(row,scenario):
    buy,sell = [tuple(D(str(v)) for v in row[k]) for k in ("buy_quantity_bounds","sell_quantity_bounds")]
    limits = [D(str(row[k])) for k in ("bid_limit","ask_limit")]
    candidates = {(x,y) for x in buy for y in sell}
    lower,upper = max(buy[0],sell[0]),min(buy[1],sell[1])
    if lower<=upper:
        candidates |= {(lower,lower),(upper,upper)}
    maker,taker,adverse = [D(str(scenario[k]))/10000 for k in ("maker_bps","taker_bps","adverse_bps")]
    values = []
    for bought,sold in candidates:
        for bid,ask in row["exit_price_pairs"]:
            bid,ask = D(str(bid)),D(str(ask))
            long,short = max(D(0),bought-sold),max(D(0),sold-bought)
            entry = bought*limits[0]+sold*limits[1]
            exit_notional = long*bid+short*ask
            values.append(sold*limits[1]+long*bid-bought*limits[0]-short*ask-entry*(maker+adverse)-exit_notional*(taker+adverse))
    close(row["net_low"],min(values))
    close(row["net_high"],max(values))
    COUNTS["decimal_cash_rectangles"] += 1
    return min(values),max(values)


def main():
    freeze=json.loads((RUN/"implementation.json").read_text())
    results=json.loads((RUN/"results.json").read_text())
    source=json.loads((BASE/"source_manifest_network_retry1.json").read_text())
    spec=json.loads((BASE/"specification.json").read_text())
    manifest=json.loads((RUN/"ledger_manifest.json").read_text())
    daily={(x["date"],x["rest_seconds"],x["scenario"]):x for x in json.loads((RUN/"daily_results.json").read_text())}
    for folder,hashes in ((ROOT,freeze["code_sha256"]),(ROOT,freeze["inputs_sha256"]),(RUN,results["artifacts_sha256"])):
        for file,sha in hashes.items():
            assert digest(folder/file)==sha
    totals=defaultdict(lambda:[D(0),D(0)])
    for cohort in spec["cohorts"]:
        day=cohort["date"]
        external=external_states([f for f in source["files"] if f["date"]==day],cohort["symbols"])
        caps={s:[r["cap"] for r in rows] for s,rows in external.items()}
        for ledger in (x for x in manifest if x["date"]==day):
            path=RUN/ledger["file"]; assert digest(path)==ledger["sha256"]
            rows=[json.loads(x) for x in path.read_text().splitlines()]
            assert len(rows)==ledger["rows"]
            scenario=freeze["execution_scenarios"][ledger["scenario"]]
            low,high=D(0),D(0)
            for row in rows:
                if "external_plan" in row:
                    verify_plan(row,external[row["symbol"]],caps[row["symbol"]],scenario)
                if row["status"]=="bounded_complete":
                    a,b=verify_cash(row,scenario); low+=a; high+=b
                else:
                    assert row["status"]=="predecision_no_order" and row["net_low"]==row["net_high"]==0
                COUNTS["ledger_rows"]+=1
            key=(day,ledger["rest_seconds"],ledger["scenario"])
            assert daily[key]["complete"]
            close(daily[key]["net_low"],low); close(daily[key]["net_high"],high)
            total=totals[key[1:]]; total[0]+=low; total[1]+=high
        print(json.dumps({"audited_date":day}),flush=True)
    for row in results["scenario_results"]:
        low,high=totals[(row["rest_seconds"],row["scenario"])]
        assert row["complete"]
        close(row["net_low"],low); close(row["net_high"],high)
    assert COUNTS["ledger_rows"]==8736 and COUNTS["external_native_messages"]==316327
    audit={"verified_at_utc":datetime.now(UTC).isoformat(),"passed":True,"counts":dict(COUNTS),"maximum_numeric_discrepancy":MAX_ERROR,
           "scope":"Independent raw Bybit reconstruction, decision predecessor, source freshness, enabled-side budgets, every causal cancellation path and Decimal cash extrema/aggregates. Frozen input/code and ledger hashes verified.",
           "limits":"This new audit does not independently replay native Binance fills under the changed cancellation intervals. The parent fixed-schedule Binance engine had a full independent audit; this extension has focused execution tests. No positive strategy advances on this limited audit.",
           "independent_external_signals_and_cash_verified":True,"full_independent_execution_verified":False,"actual_execution_verified":False,"reliable_edge_established":False,
           "auditor_sha256":digest(Path(__file__)),"results_sha256":digest(RUN/"results.json")}
    with (RUN/"signal_and_cash_verification.json").open("x") as stream:
        stream.write(json.dumps(audit,indent=2)+"\n")
    print(json.dumps(audit),flush=True)


if __name__=="__main__":
    main()
