"""Bounded full-universe source recovery, three streaming workers, no P&L."""

import gzip
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import requests

from research.bybit_full_state_recovery import COLUMNS, advance_snapshots
from research_scout.prepare_bybit_funding_20261002 import OUT, ROOT


def sha(path):
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b""):
            digest.update(block)
    return digest.hexdigest()


def download(job,plan):
    path=OUT/"all_states"/f"{job['date']}_PERPETUALS.csv.gz"
    sidecar=path.with_suffix(path.suffix+".json")
    if sidecar.exists():
        record=json.loads(sidecar.read_text())
        if record["complete"]:
            assert sha(path)==record["sha256"]
        return record
    partial=path.with_suffix(path.suffix+".partial")
    record={"date":job["date"],"url":job["url"],"path":str(path.relative_to(ROOT)),"complete":False,"authenticated":False}
    session=requests.Session()
    session.trust_env=False
    started=time.monotonic()
    try:
        assert not path.exists() and not partial.exists(), "Preserve existing transfer instead of overwriting it"
        digest,size,reported=hashlib.sha256(),0,0
        with session.get(job["url"],stream=True,allow_redirects=False,timeout=(15,90)) as response:
            record["http_status"]=response.status_code
            response.raise_for_status()
            assert response.status_code==200 and int(response.headers["Content-Length"])==job["content_length"]
            with partial.open("xb") as stream:
                for block in response.iter_content(256*1024):
                    size+=len(block)
                    if size>plan["per_file_cap"] or size>job["content_length"] or time.monotonic()-started>900:
                        raise ValueError("Frozen transfer bound exceeded")
                    stream.write(block)
                    digest.update(block)
                    if size//128_000_000>reported:
                        reported=size//128_000_000
                        print(json.dumps({"date":job["date"],"phase":"download","bytes":size,"expected":job["content_length"]}),flush=True)
        assert size==job["content_length"]
        with gzip.open(partial,"rt") as stream:
            assert set(COLUMNS).issubset(stream.readline().strip().split(","))
        assert path.resolve().is_relative_to(ROOT.resolve()) and partial.resolve().is_relative_to(ROOT.resolve())
        partial.rename(path)
        record.update(complete=True,compressed_bytes=size,sha256=digest.hexdigest())
    except Exception as error:
        record.update(error_type=type(error).__name__,error=str(error),partial_path=str(partial.relative_to(ROOT)))
    sidecar.write_text(json.dumps(record,indent=2)+"\n")
    return record


def recover(job,plan):
    record=download(job,plan)
    if not record["complete"]:
        return record
    output=OUT/"all_states"/f"{job['date']}_asof.json"
    if output.exists():
        state=json.loads(output.read_text())
        assert state["source_sha256"]==record["sha256"]
        return {**record,"extraction":str(output.relative_to(ROOT)),"extraction_sha256":sha(output),"rows_inspected":state["rows_inspected"],"states":state["states_count"]}
    midnight=int(datetime.fromisoformat(job["date"]).replace(tzinfo=UTC).timestamp())*1_000_000
    cutoffs={hour:midnight+hour*3600*1_000_000-10_250_000 for hour in (8,16)}
    selected={hour:{} for hour in cutoffs}
    offset,previous,reported=0,-1,0
    dtypes={"exchange":"category","symbol":"category","timestamp":"int64","local_timestamp":"int64",
            "funding_timestamp":"float64","funding_rate":"float64","mark_price":"float64"}
    for frame in pd.read_csv(ROOT/record["path"],usecols=COLUMNS,dtype=dtypes,chunksize=250000):
        frame=frame.reset_index(drop=True)
        times=frame.local_timestamp.to_numpy(np.int64)
        assert frame.exchange.eq("bybit").all() and not (np.diff(times)<0).any() and times[0]>=previous
        previous=int(times[-1])
        advance_snapshots(frame,selected,offset,cutoffs)
        offset+=len(frame)
        if offset//5_000_000>reported:
            reported=offset//5_000_000
            print(json.dumps({"date":job["date"],"phase":"reconstruct","rows_inspected":offset}),flush=True)
    result={"date":job["date"],"source_sha256":record["sha256"],"rows_inspected":offset,"states_count":sum(len(x) for x in selected.values()),
            "cutoffs_us":cutoffs,"states":selected,"future_rows_used_for_decisions":False}
    with output.open("x") as stream:
        stream.write(json.dumps(result,indent=2,allow_nan=False)+"\n")
    return {**record,"extraction":str(output.relative_to(ROOT)),"extraction_sha256":sha(output),"rows_inspected":offset,"states":result["states_count"]}


def main():
    preflight=json.loads((OUT/"all_states_get_preflight.json").read_text())
    assert preflight["all_sizes_known"] and len(preflight["files"])==12
    assert preflight["aggregate_known_compressed_bytes"]==3274038156
    plan={"created_at_utc":datetime.now(UTC).isoformat(),"reason":"Complete source recovery for all predeclared 2024 native symbol/windows, including the 5,519 funding-rate observations missing from one-minute deltas. Original partial screens remain intact; no rate, fee, date or horizon threshold changes.",
          "preflight_sha256":sha(OUT/"all_states_get_preflight.json"),"native_states_sha256":sha(OUT/"native_states.parquet"),
          "expected_total_compressed_bytes":3274038156,"aggregate_cap":4000000000,"per_file_cap":512000000,"workers":3,
          "extraction":"Read every full source to validate capture ordering and gzip integrity. For each original cutoff, retain the last strictly earlier full CSV state per USDT symbol; no future values and no forward filling of explicitly unknown fields.",
          "code_sha256":{p:sha(ROOT/p) for p in ["research_scout/recover_all_bybit_states_20261002.py","research/bybit_full_state_recovery.py","tests/unit/test_bybit_full_state_recovery.py"]},
          "authenticated":False,"paid_fallback":False,"strategy_pnl_tested":False}
    assert sum(x["content_length"] for x in preflight["files"])<=plan["aggregate_cap"]
    assert max(x["content_length"] for x in preflight["files"])<=plan["per_file_cap"]
    plan_path=OUT/"all_states_recovery_plan.json"
    if plan_path.exists():
        prior=json.loads(plan_path.read_text())
        assert prior["code_sha256"]==plan["code_sha256"] and prior["preflight_sha256"]==plan["preflight_sha256"]
    else:
        plan_path.write_text(json.dumps(plan,indent=2)+"\n")
    (OUT/"all_states").mkdir(exist_ok=True)
    records=[]
    with ThreadPoolExecutor(max_workers=plan["workers"]) as pool:
        pending={pool.submit(recover,job,plan):job for job in preflight["files"]}
        for task in as_completed(pending):
            job=pending[task]
            try:
                result=task.result()
            except Exception as error:
                result={"date":job["date"],"complete":False,"error_type":type(error).__name__,"error":str(error),"stage":"extraction_or_cached_source_verification"}
            records.append(result)
            manifest={"files":records,"expected_files":12,"complete":len(records)==12 and all(r["complete"] and "extraction" in r for r in records),
                      "source_compressed_bytes":sum(r.get("compressed_bytes",0) for r in records),"rows_inspected":sum(r.get("rows_inspected",0) for r in records),
                      "plan_sha256":sha(plan_path),"strategy_pnl_tested":False}
            (OUT/"all_states_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
            print(json.dumps({k:result.get(k) for k in ("date","complete","rows_inspected","states","error")}),flush=True)
    print(json.dumps({k:v for k,v in manifest.items() if k!="files"}),flush=True)


if __name__=="__main__":
    main()
