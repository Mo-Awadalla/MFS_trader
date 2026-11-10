"""Inspect public full-universe funding source sizes; no price outcomes."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import requests

from research_scout.prepare_bybit_funding_20261002 import OUT


def inspect(day,use_get=False):
    url=f"https://datasets.tardis.dev/v1/bybit/derivative_ticker/{day.replace('-','/')}/PERPETUALS.csv.gz"
    session=requests.Session()
    session.trust_env=False
    result={"date":day,"url":url,"method":"GET" if use_get else "HEAD","body_bytes_consumed":0}
    try:
        with session.request("GET" if use_get else "HEAD",url,stream=True,allow_redirects=False,timeout=(15,30)) as response:
            result.update(http_status=response.status_code,content_length=int(response.headers["Content-Length"]) if "Content-Length" in response.headers else None,
                          content_type=response.headers.get("Content-Type"),etag=response.headers.get("ETag"))
            if use_get and response.status_code!=200:
                error_body=next(response.iter_content(4096),b"")
                result.update(provider_error_prefix=error_body.decode(errors="replace"),body_bytes_consumed=len(error_body))
            response.raise_for_status()
    except Exception as error:
        result.update(error_type=type(error).__name__,error=str(error))
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--get-retry",action="store_true")
    args=parser.parse_args()
    spec=json.loads((OUT/"specification.json").read_text())
    path=OUT/("all_states_get_preflight.json" if args.get_retry else "all_states_preflight.json")
    if path.exists():
        raise FileExistsError("Preserve the original preflight")
    records=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending=[pool.submit(inspect,day,args.get_retry) for day in spec["dates"]]
        for job in as_completed(pending):
            record=job.result()
            records.append(record)
            print(json.dumps(record),flush=True)
    result={"created_at_utc":datetime.now(UTC).isoformat(),"files":sorted(records,key=lambda x:x["date"]),
            "aggregate_known_compressed_bytes":sum(x.get("content_length") or 0 for x in records),
            "all_sizes_known":all(x.get("http_status")==200 and x.get("content_length") for x in records),
            "purpose":"Costed recovery of the 5,519 native states with unobserved funding rates; not additional strategy variants or a rate-threshold change.",
            "body_bytes_consumed":sum(x["body_bytes_consumed"] for x in records),"strategy_pnl_tested":False}
    if args.get_retry:
        result["reason_for_retry"]="HEAD returned HTTP 404 despite metadata and documentation advertising the grouped dataset. Check the documented GET method with streaming, without consuming successful dataset bodies; retain original HEAD results."
    path.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="files"}),flush=True)


if __name__=="__main__":
    main()
