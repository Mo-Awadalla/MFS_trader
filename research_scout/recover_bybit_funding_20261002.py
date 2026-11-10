"""Recover known large-rate observations and match causal Binance funding."""

import gzip
import hashlib
import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal as D

import pandas as pd
import requests

from research.wide_tick_supply import stamp_ns
from research_scout.funding_counterparts_20260930 import asof_states
from research_scout.prepare_bybit_funding_20261002 import OUT, ROOT

OLD = ROOT/"research_scout/funding_universe_hft_20260930"
TOTAL = 0
LOCK = threading.Lock()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reserve(amount, maximum):
    global TOTAL
    with LOCK:
        TOTAL += amount
        if maximum < TOTAL:
            raise ValueError("Frozen aggregate compressed acquisition cap exceeded")


def download(job, plan):
    path=OUT/"full_states"/f"{job['date']}_{job['symbol']}.csv.gz"
    sidecar=path.with_suffix(path.suffix+".json")
    if sidecar.exists():
        old=json.loads(sidecar.read_text())
        if old["complete"]:
            assert sha(ROOT/old["path"])==old["sha256"]
            reserve(old["compressed_bytes"],plan["aggregate_compressed_cap"])
        return old
    cached=OLD/"counterparts"/path.name
    cached_sidecar=cached.with_suffix(cached.suffix+".json")
    if cached_sidecar.exists():
        record=json.loads(cached_sidecar.read_text())
        if record["complete"]:
            assert sha(cached)==record["sha256"]
            reserve(record["compressed_bytes"],plan["aggregate_compressed_cap"])
            record.update(reused_verified_cache=True,original_sidecar_sha256=sha(cached_sidecar))
            sidecar.write_text(json.dumps(record,indent=2)+"\n")
            return record
    url=f"https://datasets.tardis.dev/v1/bybit/derivative_ticker/{job['date'].replace('-','/')}/{job['symbol']}.csv.gz"
    record={**job,"url":url,"path":str(path.relative_to(ROOT)),"complete":False,"authenticated":False}
    session=requests.Session()
    session.trust_env=False
    started=time.monotonic()
    try:
        with session.get(url,stream=True,allow_redirects=False,timeout=(15,60)) as response:
            record["http_status"]=response.status_code
            if response.status_code!=200:
                record["provider_error_prefix"]=next(response.iter_content(4096),b"").decode(errors="replace")
            response.raise_for_status()
            if response.status_code!=200:
                raise ValueError("Unexpected response status")
            chunks,size=[],0
            for block in response.iter_content(65536):
                reserve(len(block),plan["aggregate_compressed_cap"])
                size+=len(block)
                if size>plan["per_file_compressed_cap"] or time.monotonic()-started>180:
                    raise ValueError("Frozen per-file acquisition bound exceeded")
                chunks.append(block)
            payload=b"".join(chunks)
        path.write_bytes(payload)
        with gzip.open(path,"rt") as stream:
            columns=stream.readline().strip().split(",")
            assert {"exchange","symbol","timestamp","local_timestamp","funding_timestamp","funding_rate","mark_price"}.issubset(columns)
        record.update(complete=True,compressed_bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest())
    except Exception as error:
        record.update(error_type=type(error).__name__,error=str(error))
    sidecar.write_text(json.dumps(record,indent=2)+"\n")
    return record


def binance_states(source,target,cutoff):
    path=ROOT/source["path"]
    assert source["complete"] and sha(path)==source["compressed_sha256"]
    raw=gzip.decompress(path.read_bytes())
    assert hashlib.sha256(raw).hexdigest()==source["decoded_sha256"]
    state,prior={},-1
    midnight=target//(86400*1_000_000_000)*(86400*1_000_000_000)
    for index,line in enumerate(raw.decode().splitlines()):
        if not line.strip():
            state.clear()
            continue
        stamp,payload=line.split(" ",1)
        cap=stamp_ns(stamp,midnight)
        assert cap>=prior
        prior=cap
        if cap>=cutoff:
            break
        entries=json.loads(payload)["data"]
        for record_index,e in enumerate(entries if isinstance(entries,list) else [entries]):
            assert e["e"]=="markPriceUpdate"
            state[e["s"]]={"receive_ns":cap,"event_ns":int(e["E"])*1_000_000,"funding_time_ns":int(e["T"])*1_000_000,
                             "funding_rate":None if e["r"]=="" else float(e["r"]),"mark_price":float(e["p"]),
                             "line_index":index,"record_index":record_index}
    return state


def good(values,cutoff,target,scale):
    rate,mark=values["funding_rate"],values["mark_price"]
    return (rate is not None and mark is not None and math.isfinite(rate) and math.isfinite(mark) and mark>0
            and values["funding_time_"+scale]==target
            and 0<cutoff-values["receive_"+scale]<=5_000_000_000//(1000 if scale=="us" else 1)
            and 0<cutoff-values["event_"+scale]<=5_000_000_000//(1000 if scale=="us" else 1)
            and -1_000_000//(1000 if scale=="us" else 1)<=values["receive_"+scale]-values["event_"+scale]<=5_000_000_000//(1000 if scale=="us" else 1))


def main():
    if (OUT/"pair_screen_results.json").exists():
        raise FileExistsError("Preserve original pair screen")
    routing=json.loads((OUT/"rate_routing_results.json").read_text())
    assert sha(OUT/"recovery_candidates.parquet")==routing["candidates_sha256"]
    events=pd.read_parquet(OUT/"recovery_candidates.parquet")
    plan=json.loads((OUT/"field_recovery_plan.json").read_text())
    jobs=events[["date","symbol"]].drop_duplicates().sort_values(["date","symbol"]).to_dict("records")
    (OUT/"full_states").mkdir(exist_ok=True)
    freeze_path=OUT/"full_state_implementation.json"
    freeze={"created_at_utc":datetime.now(UTC).isoformat(),"jobs":jobs,"candidates_sha256":routing["candidates_sha256"],
            "code_sha256":{p:sha(ROOT/p) for p in ["research_scout/recover_bybit_funding_20261002.py","research_scout/funding_counterparts_20260930.py"]},
            "routing_plan_sha256":sha(OUT/"field_recovery_plan.json"),"strategy_pnl_tested":False}
    if freeze_path.exists():
        old=json.loads(freeze_path.read_text())
        assert old["code_sha256"]==freeze["code_sha256"] and old["candidates_sha256"]==freeze["candidates_sha256"]
    else:
        freeze_path.write_text(json.dumps(freeze,indent=2)+"\n")
    records=[]
    with ThreadPoolExecutor(max_workers=plan["workers"]) as pool:
        pending=[pool.submit(download,job,plan) for job in jobs]
        for task in as_completed(pending):
            record=task.result()
            records.append(record)
            (OUT/"full_state_manifest.json").write_text(json.dumps({"files":records,"expected_files":len(jobs),
                    "complete":len(records)==len(jobs) and all(r["complete"] for r in records),"reserved_compressed_bytes":TOTAL},indent=2)+"\n")
            print(json.dumps({k:record.get(k) for k in ("date","symbol","complete","compressed_bytes","http_status")}),flush=True)
    source={(r["date"],r["symbol"]):r for r in records}
    recovered,raw_count={},0
    for job in jobs:
        cohort=events.loc[(events.date==job["date"]) & (events.symbol==job["symbol"])].to_dict("records")
        item=source[(job["date"],job["symbol"])]
        if item["complete"]:
            states,count=asof_states(item,cohort)
            raw_count+=count
            for hour,value in states.items():
                recovered[(job["date"],hour,job["symbol"])]=value
    bm=json.loads((OLD/"native_manifest.json").read_text())
    binance={}
    for row in events.to_dict("records"):
        key=(row["date"],row["hour"])
        if key not in binance:
            item=next(x for x in bm["files"] if (x["date"],x["hour"])==key)
            binance[key]=binance_states(item,row["settlement_ns"],row["decision_ns"])
    pairs=[]
    for event in events.to_dict("records"):
        key=(event["date"],event["hour"],event["symbol"])
        row={k:event[k] for k in ("date","hour","symbol","settlement_ns","decision_ns")}
        row.update(native_bybit_rate=event["funding_rate"],usable=False,eligible=False,reason="unknown_recovered_bybit_source")
        y=recovered.get(key)
        b=binance[key[:2]].get(event["symbol"])
        if y:
            row.update({"bybit_"+k:v for k,v in y.items()})
            if not good(y,event["decision_ns"]//1000,event["settlement_ns"]//1000,"us"):
                row["reason"]="stale_invalid_or_wrong_bybit_funding_time"
            elif abs(y["funding_rate"]-event["funding_rate"])>1e-12:
                row["reason"]="native_normalized_rate_disagreement"
            elif b is None:
                row["reason"]="missing_exact_binance_symbol"
            else:
                row.update({"binance_"+k:v for k,v in b.items()})
                if not good(b,event["decision_ns"],event["settlement_ns"],"ns"):
                    row["reason"]="stale_invalid_or_wrong_binance_funding_time"
                else:
                    difference=D(str(y["funding_rate"]))*D(str(y["mark_price"]))-D(str(b["funding_rate"]))*D(str(b["mark_price"]))
                    bps=abs(difference)/max(D(str(y["mark_price"])),D(str(b["mark_price"]))) * 10000
                    row.update(usable=True,quoted_payment_difference_bps=float(bps),eligible=bps>28,
                               sell_exchange="bybit" if difference>0 else "binance-futures",
                               reason="requires_lifecycle_and_execution_review" if bps>28 else "payment_difference_below_cost_hurdle")
        pairs.append(row)
    frame=pd.DataFrame(pairs)
    for name in frame:
        if name.endswith("_ns") or name.endswith("_us") or name.endswith("_position") or name.endswith("_index"):
            frame[name]=pd.array([r.get(name) for r in pairs],dtype="Int64")
    frame.to_parquet(OUT/"funding_pairs.parquet",index=False)
    result={"routed_events":len(frame),"recovered_symbol_dates":sum(r["complete"] for r in records),"source_symbol_dates":len(records),
            "normalized_rows":raw_count,"compressed_bytes":sum(r.get("compressed_bytes",0) for r in records),
            "usable_pairs":int(frame.usable.sum()),"pairs_above_cost_before_execution":int(frame.eligible.sum()),
            "outcomes":frame.reason.value_counts().to_dict(),"pairs_sha256":sha(OUT/"funding_pairs.parquet"),
            "lifecycle_checked":False,"actual_execution_verified":False,"strategy_pnl_tested":False,"reliable_edge_established":False,
            "coverage_limit":"5,519 native observations lacked a funding-rate field and remain unresolved; this conditional recovery does not exhaust the full Bybit universe."}
    (OUT/"pair_screen_results.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result),flush=True)
    print(frame.loc[frame.eligible,["date","hour","symbol","native_bybit_rate","binance_funding_rate","quoted_payment_difference_bps"]].to_string(index=False),flush=True)


if __name__=="__main__":
    main()
