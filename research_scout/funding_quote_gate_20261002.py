"""Check spreads and displayed liquidity for every fee-only funding candidate."""

import bisect
import gzip
import hashlib
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal as D

import pandas as pd

from research.external_quote_hft import fresh, load_external
from research.wide_tick_replay import load_day
from research_scout.fetch_bybit_funding_20261002 import request_payload
from research_scout.prepare_bybit_funding_20261002 import OUT, ROOT


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(job):
    path=OUT/"quotes"/f"{job['date']}_{job['hour']}_{job['symbol']}_{job['exchange']}.ndjson.gz"
    sidecar=path.with_suffix(path.suffix+".json")
    if sidecar.exists():
        old=json.loads(sidecar.read_text())
        if old["complete"]:
            assert sha(path)==old["compressed_sha256"]
        return old
    symbol=job["symbol"].lower() if job["exchange"]=="binance-futures" else job["symbol"]
    channel="bookTicker" if job["exchange"]=="binance-futures" else "orderbook.1"
    params={"from":job["date"],"offset":job["hour"]*60-1,"sliceSize":1,"filters":json.dumps([{"channel":channel,"symbols":[symbol]}])}
    row={**job,"offset":params["offset"],"params":params,"path":str(path.relative_to(ROOT)),"complete":False}
    try:
        payload=request_payload("https://api.tardis.dev/v1/data-feeds/"+job["exchange"],96000000,params)
        assert payload.strip()
        encoded=gzip.compress(payload,compresslevel=3,mtime=0)
        path.write_bytes(encoded)
        row.update(complete=True,decoded_bytes=len(payload),compressed_bytes=len(encoded),decoded_sha256=hashlib.sha256(payload).hexdigest(),compressed_sha256=sha(path))
    except Exception as error:
        row.update(error_type=type(error).__name__,error=str(error))
    sidecar.write_text(json.dumps(row,indent=2)+"\n")
    return row


def main():
    events=pd.read_parquet(OUT/"funding_pairs.parquet")
    selected=events.loc[events.eligible].to_dict("records")
    (OUT/"quotes").mkdir(exist_ok=True)
    plan_path=OUT/"quote_gate_specification.json"
    plan={"created_at_utc":datetime.now(UTC).isoformat(),"pairs_sha256":sha(OUT/"funding_pairs.parquet"),
          "events":[{k:r[k] for k in ("date","hour","symbol","decision_ns","settlement_ns")} for r in selected],
          "rule":"Use only fresh positive uncrossed native best quotes captured before the original funding-signal cutoff. Subtract both full displayed spreads and 7bp times the sum of the four bid/ask prices from the projected funding payment per matched underlying unit. This is the payment-alone budget assuming unchanged quotes, not strategy P&L or a guarantee. A candidate must have positive remaining budget and sufficient known size before an execution replay is justified.",
          "size":"Common multiple of ten whole underlying units, <=200 USDT per leg and <=10% of all four touch quantities. Require >=100 USDT bid notional per venue. Historical order grid remains conditional.",
          "known_lifecycle_fact":{"symbol":"AXLUSDT","binance_launch_utc":"2024-03-01T15:30:00Z","first_funding_utc":"2024-03-01T16:00:00Z","tick_size":"0.0001","source":"https://www.binance.com/en/support/announcement/detail/4ec6916d881444c0949ab906352043cc"},
          "code_sha256":{p:sha(ROOT/p) for p in ["research_scout/funding_quote_gate_20261002.py","research/external_quote_hft.py","research/wide_tick_replay.py"]},
          "strategy_pnl_tested":False}
    if plan_path.exists():
        old=json.loads(plan_path.read_text())
        assert old["code_sha256"]==plan["code_sha256"] and old["pairs_sha256"]==plan["pairs_sha256"]
    else:
        plan_path.write_text(json.dumps(plan,indent=2)+"\n")
    jobs=[{k:r[k] for k in ("date","hour","symbol")} | {"exchange":venue} for r in selected for venue in ("binance-futures","bybit")]
    records=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending=[pool.submit(fetch,job) for job in jobs]
        for task in as_completed(pending):
            records.append(task.result())
    (OUT/"quote_manifest.json").write_text(json.dumps({"files":records,"complete":all(r["complete"] for r in records)},indent=2)+"\n")
    rows=[]
    for event in selected:
        row={k:event[k] for k in ("date","hour","symbol","decision_ns","settlement_ns")}
        row.update(eligible=False,reason="unknown_quote_source")
        files=[r for r in records if (r["date"],r["hour"],r["symbol"])==(event["date"],event["hour"],event["symbol"])]
        if not all(r["complete"] for r in files):
            rows.append(row)
            continue
        midnight=int(datetime.fromisoformat(event["date"]).replace(tzinfo=UTC).timestamp())*1_000_000_000
        bn,bdiag=load_day(ROOT,[r for r in files if r["exchange"]=="binance-futures"],event["date"],midnight,[event["symbol"]])
        by,ydiag=load_external(ROOT,[r for r in files if r["exchange"]=="bybit"],event["date"],midnight,[event["symbol"]])
        cutoff=event["decision_ns"]
        b=bn[event["symbol"]].signal(cutoff)
        yt=by[event["symbol"]]
        yi=bisect.bisect_left(yt.captures,cutoff)-1
        y=yt.rows[yi] if yi>=0 else None
        bvalid=b is not None and b["clock_ok"] and b["sequence_ok"] and all(0<cutoff-b[k]<=5_000_000_000 for k in ("receive_ns","transaction_ns","publication_ns"))
        if not bvalid or y is None or not fresh(y,cutoff):
            row["reason"]="stale_or_invalid_native_quote"
            rows.append(row)
            continue
        bp,ap,bq,aq=(D(b[k]) for k in ("bid","ask","bid_quantity","ask_quantity"))
        yb,ya,ybq,yaq=(D(str(y[k])) for k in ("bid","ask","bid_quantity","ask_quantity"))
        assert all(v.is_finite() and v>0 for v in (bp,ap,bq,aq,yb,ya,ybq,yaq)) and bp<ap and yb<ya
        funding=abs(D(str(event["bybit_funding_rate"]))*D(str(event["bybit_mark_price"]))-D(str(event["binance_funding_rate"]))*D(str(event["binance_mark_price"])))
        spreads=ap-bp+ya-yb
        costs=(bp+ap+yb+ya)*D("0.0007")
        budget=funding-spreads-costs
        quantity=math.floor(min(D(200)/max(ap,ya),min(bq,aq,ybq,yaq)/10)/10)*10
        size_ok=quantity*min(bp,yb)>=100
        row.update(binance_quote_source_index=b["source_index"],bybit_quote_source_index=y["source_index"],
                   binance_bid=float(bp),binance_ask=float(ap),bybit_bid=float(yb),bybit_ask=float(ya),
                   quoted_funding_per_unit=float(funding),spread_cost_per_unit=float(spreads),fees_and_adverse_per_unit=float(costs),
                   payment_budget_after_spread_per_unit=float(budget),payment_budget_bps=float(budget/max(D(str(event["bybit_mark_price"])),D(str(event["binance_mark_price"]))))*10000,
                   conditional_quantity=quantity,size_ok=size_ok,eligible=budget>0 and size_ok,
                   reason="requires_paired_execution_replay" if budget>0 and size_ok else "insufficient_displayed_size" if not size_ok else "payment_budget_below_total_cost",
                   diagnostics={"binance":bdiag,"bybit":ydiag})
        rows.append(row)
    result={"events":rows,"eligible_events":sum(r["eligible"] for r in rows),"strategy_pnl_tested":False,"reliable_edge_established":False}
    (OUT/"quote_gate_results.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result),flush=True)


if __name__=="__main__":
    main()
