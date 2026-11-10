"""Freeze and scan all native pre-settlement Bybit funding-rate observations."""

import gzip
import hashlib
import json
from datetime import UTC, datetime

import pandas as pd

from research.bybit_funding_screen import snapshot
from research_scout.prepare_bybit_funding_20261002 import OUT, ROOT


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest=json.loads((OUT/"source_manifest.json").read_text())
    assert manifest["complete"] and len(manifest["files"])==24
    assert sha(OUT/"specification.json")==manifest["specification_sha256"]
    recovery={"created_at_utc":datetime.now(UTC).isoformat(),"stage":"Before the rate-only recovery routing screen",
              "evidence":"Pilot: 293 USDT symbols, 9,788 pre-cutoff deltas each carrying fundingRate, but zero nextFundingTime fields. No full native state can yet be established from this slice.",
              "routing":"Retain every native state. Route every fresh finite abs(rate)>=14bp observation for full-state recovery regardless of whether mark or funding time is missing. This is only a data-download router, not evidence of a qualifying payment or executable trade. The original final gates remain unchanged.",
              "recovery":"Fetch a full-day normalized Bybit derivative_ticker file for every routed symbol/date, reusing matching verified cached files when available. Check native funding-rate agreement at the causal cutoff. Preserve missing sources and fields; do not substitute zero.",
              "per_file_compressed_cap":32000000,"aggregate_compressed_cap":1200000000,"workers":3,
              "economic_thresholds_changed":False,"future_prices_or_realized_funding_used":False}
    with (OUT/"field_recovery_plan.json").open("x") as stream:
        stream.write(json.dumps(recovery,indent=2)+"\n")
    freeze={"created_at_utc":datetime.now(UTC).isoformat(),"manifest_sha256":sha(OUT/"source_manifest.json"),
            "code_sha256":{p:sha(ROOT/p) for p in ["research/bybit_funding_screen.py","research_scout/screen_bybit_funding_20261002.py","tests/unit/test_bybit_funding_screen.py"]},
            "recovery_plan_sha256":sha(OUT/"field_recovery_plan.json")}
    with (OUT/"screen_implementation.json").open("x") as stream:
        stream.write(json.dumps(freeze,indent=2)+"\n")
    rows,diagnostics=[],[]
    for source in sorted(manifest["files"],key=lambda r:(r["date"],r["hour"])):
        path=ROOT/source["path"]
        assert sha(path)==source["compressed_sha256"]
        payload=gzip.decompress(path.read_bytes())
        assert hashlib.sha256(payload).hexdigest()==source["decoded_sha256"]
        target=int(datetime.fromisoformat(source["date"]).replace(tzinfo=UTC).timestamp())*1_000_000_000+source["hour"]*3600*1_000_000_000
        records,diag=snapshot(payload.decode().splitlines(),target)
        rows.extend({"date":source["date"],"hour":source["hour"],**r} for r in records)
        diagnostics.append({"date":source["date"],"hour":source["hour"],**diag})
    frame=pd.DataFrame(rows)
    for name in frame:
        if name.endswith("_ns") or name in {"line_index","sequence"}:
            frame[name]=pd.array([r.get(name) for r in rows],dtype="Int64")
    selected=frame.loc[frame.route_for_recovery]
    frame.to_parquet(OUT/"native_states.parquet",index=False)
    selected.to_parquet(OUT/"recovery_candidates.parquet",index=False)
    results={"native_states":len(frame),"unique_symbols":int(frame.symbol.nunique()),"routed_rate_observations":len(selected),
             "recovery_symbol_dates":len(selected[["date","symbol"]].drop_duplicates()),"native_full_states":int(frame.native_complete.sum()),
             "reasons":frame.reason.value_counts().to_dict(),"diagnostics":diagnostics,"native_messages":sum(d["native_messages"] for d in diagnostics),
             "states_sha256":sha(OUT/"native_states.parquet"),"candidates_sha256":sha(OUT/"recovery_candidates.parquet"),
             "economic_implementations_run":0,"reliable_edge_established":False}
    (OUT/"rate_routing_results.json").write_text(json.dumps(results,indent=2)+"\n")
    print(json.dumps({k:v for k,v in results.items() if k!="diagnostics"}),flush=True)
    print(selected[["date","hour","symbol","funding_rate","missing_fields"]].to_string(index=False),flush=True)


if __name__=="__main__":
    main()
