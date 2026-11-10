"""Bounded public source probe and frozen native funding windows."""

import argparse
import gzip
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from research_scout.prepare_bybit_funding_20261002 import OUT, ROOT


def request_payload(url, cap, params=None):
    session=requests.Session()
    session.trust_env=False
    with session.get(url,params=params,headers={"Accept-Encoding":"gzip"},stream=True,allow_redirects=False,timeout=(15,60)) as response:
        response.raise_for_status()
        if response.status_code!=200:
            raise ValueError("Unexpected response status")
        blocks,size=[],0
        for block in response.iter_content(65536):
            size+=len(block)
            if size>cap:
                raise ValueError("Frozen public-source bound exceeded")
            blocks.append(block)
    return b"".join(blocks)


def fetch(day,hour,config):
    path=OUT/"native"/f"{day}_{hour*60-1:04d}.ndjson.gz"
    sidecar=path.with_suffix(path.suffix+".json")
    if sidecar.exists():
        old=json.loads(sidecar.read_text())
        if old["complete"]:
            assert hashlib.sha256(path.read_bytes()).hexdigest()==old["compressed_sha256"]
        return old
    params={"from":day,"offset":hour*60-1,"sliceSize":1,"filters":json.dumps([{"channel":"tickers"}])}
    result={"date":day,"hour":hour,"params":params,"path":str(path.relative_to(ROOT)),"complete":False}
    try:
        data=request_payload("https://api.tardis.dev/v1/data-feeds/bybit",config["per_slice_decoded_cap"],params)
        if not data.strip():
            raise ValueError("Empty native source")
        encoded=gzip.compress(data,compresslevel=3,mtime=0)
        path.write_bytes(encoded)
        result.update(complete=True,decoded_bytes=len(data),compressed_bytes=len(encoded),
                      decoded_sha256=hashlib.sha256(data).hexdigest(),compressed_sha256=hashlib.sha256(encoded).hexdigest())
    except Exception as error:
        result.update(error_type=type(error).__name__,error=str(error))
    sidecar.write_text(json.dumps(result,indent=2)+"\n")
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--pilot",action="store_true")
    args=parser.parse_args()
    spec_path=OUT/"specification.json"
    spec=json.loads(spec_path.read_text())
    (OUT/"native").mkdir(exist_ok=True)
    if args.pilot:
        metadata_path=OUT/"bybit_metadata.json"
        if not metadata_path.exists():
            metadata_path.write_bytes(request_payload("https://api.tardis.dev/v1/exchanges/bybit",32000000))
        metadata=json.loads(metadata_path.read_text())
        special=[x for x in metadata.get("datasets",{}).get("symbols",[]) if x["id"] in {"PERPETUALS","FUTURES","DERIVATIVES","ALL"}]
        print(json.dumps({"special_datasets":special}),flush=True)
        print(json.dumps(fetch(spec["dates"][0],spec["settlement_hours_utc"][0],spec["download"])),flush=True)
        return
    jobs=[(d,h) for d in spec["dates"] for h in spec["settlement_hours_utc"]]
    files=[]
    with ThreadPoolExecutor(max_workers=spec["download"]["workers"]) as pool:
        pending=[pool.submit(fetch,d,h,spec["download"]) for d,h in jobs]
        for job in as_completed(pending):
            result=job.result()
            files.append(result)
            manifest={"files":files,"expected_files":len(jobs),"complete":len(files)==len(jobs) and all(f["complete"] for f in files),
                      "decoded_bytes":sum(f.get("decoded_bytes",0) for f in files),"specification_sha256":hashlib.sha256(spec_path.read_bytes()).hexdigest()}
            (OUT/"source_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
            print(json.dumps({k:result.get(k) for k in ("date","hour","complete","decoded_bytes","error")}),flush=True)


if __name__=="__main__":
    main()
