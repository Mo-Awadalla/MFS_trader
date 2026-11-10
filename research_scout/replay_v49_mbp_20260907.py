"""Replay original V49 signal-only gates with explicitly substituted MBP-1 data."""
from pathlib import Path
from datetime import datetime, timezone
import json, hashlib
import numpy as np
import pandas as pd
import databento as db
from unittest.mock import patch
from research_scout import audit_leveraged_etf_post_open_simplex_v49 as original

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'research_scout/v49_mbp_replay_20260907'
SOURCE=ROOT/'external_artifacts/databento_cash_etf_mbp1_open_v55/EQUS.MINI/mbp-1'
TARGETS=['09:30:01','09:30:05','09:31:01','09:31:05','09:32:00','09:35:00']

def write(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

def main():
    OUT.mkdir(exist_ok=True)
    cache=OUT/'quote_cache';cache.mkdir(exist_ok=True)
    files=sorted(p for p in SOURCE.glob('*.dbn.zst') if '2023-03-28'<=p.name[:10]<='2026-07-24')
    audit=original.shared.load_json(original.shared.AUDIT)
    degraded=set(audit['degraded_dates']['EQUS.MINI'])
    spec={'created_utc':datetime.now(timezone.utc).isoformat(),'source_code_sha256':hashlib.sha256(Path(original.__file__).read_bytes()).hexdigest(),'scope':'Original V49 code and thresholds, all available local MBP sessions through original 2026-07-24 boundary. No P&L unless every original gate passes.','measurement_amendment':'Full MBP-1 quote updates replace trade-event-conditioned TBBO. Select earliest valid event timestamp in original target through target+60s; stable receive-time tiebreak. Original positive non-crossed price filter retained. Sizes retained for independent execution QA, not a new signal filter. This is a feed-amended replay, not an exact historical replication.','targets':TARGETS,'files':[{ 'path':str(p.relative_to(ROOT)), 'bytes':p.stat().st_size } for p in files],'missing_period_policy':'Do not fabricate missing sessions or count unobserved 2026 days as known no-signal days. Original gates calculated on observed data, with coverage limitation reported.','historical_exposure':'Historical data; not prospective or untouched out-of-sample confirmation.','parameters_changed':False,'account_or_network_operations':False}
    if not (OUT/'specification.json').exists():write('specification.json',spec)
    all_quotes=[];quality=[]
    for i,p in enumerate(files):
        dest=cache/(p.name[:10]+'.json')
        if dest.exists(): rec=json.loads(dest.read_text())
        else:
            df=db.DBNStore.from_file(p).to_df()
            if not df.index.is_monotonic_increasing: raise ValueError('Nonmonotonic receive timestamps')
            df=df.reset_index()
            good=np.isfinite(df.bid_px_00)&np.isfinite(df.ask_px_00)&(df.bid_px_00>0)&(df.ask_px_00>=df.bid_px_00)
            day=p.name[:10]; rows=[]
            for clock in TARGETS:
                t=pd.Timestamp(day+' '+clock,tz='America/New_York').tz_convert('UTC')
                w=df.loc[good&(df.ts_event>=t)&(df.ts_event<=t+pd.Timedelta(seconds=60))]
                first=w.sort_values(['ts_event','ts_recv'],kind='stable').groupby('symbol',observed=True).head(1)
                for r in first.itertuples(index=False):
                    if str(r.symbol) not in original.SYMBOLS:continue
                    rows.append({'session_date':day,'symbol':str(r.symbol),'target':clock,'ts_event':r.ts_event.isoformat(),'ts_recv':r.ts_recv.isoformat(),'event_wait_seconds':(r.ts_event-t).total_seconds(),'bid':float(r.bid_px_00),'ask':float(r.ask_px_00),'bid_size':int(r.bid_sz_00),'ask_size':int(r.ask_sz_00),'equs_degraded':day in degraded,'segment':'full_mbp1_opening_replay'})
            rec={'date':day,'quotes':rows,'source_rows':len(df),'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            dest.write_text(json.dumps(rec),encoding='utf-8')
        all_quotes.extend(rec['quotes']);quality.append({'date':rec['date'],'states':len(rec['quotes']),'source_rows':rec['source_rows']})
        if (i+1)%25==0:print(f'MBP extraction {i+1}/{len(files)}',flush=True)
    payload={'returns_read':False,'quotes':all_quotes}
    write('extraction_summary.json',{'files':len(files),'quote_states':len(all_quotes),'source_rows':sum(r['source_rows'] for r in quality),'nonpositive_size_states':sum(r['bid_size']<=0 or r['ask_size']<=0 for r in all_quotes),'sessions':quality})
    real_load=original.shared.load_json
    def load(path):return payload if path==original.shared.TARGET_QUOTES else real_load(path)
    # Original signal generation, window comparisons, denominators and gates execute
    # unchanged; only source data and destination are adapted in this process.
    with patch.object(original.shared,'load_json',side_effect=load), patch.object(original,'OUTPUT',OUT/'original_gate_result.json'):
        original.main()
    result=json.loads((OUT/'original_gate_result.json').read_text())
    quotes=original.shared.quote_map(payload)
    openings,_=original.load_openings()
    excluded=set(audit['degraded_dates']['ARCX.PILLAR'])|degraded
    dev_openings={d:r for d,r in openings.items() if d<='2023-12-31'}
    primary,_,_=original.feature_rows(dev_openings,quotes,excluded,original.PRIMARY_OBSERVATION,20)
    dev_comparisons={}
    for label,clock,window in [('adjacent_clock','09:30:01',20),('rolling_10','09:30:05',10),('rolling_40','09:30:05',40)]:
        actions,_,_=original.feature_rows(dev_openings,quotes,excluded,clock,window)
        dev_comparisons[label]=original.compare(primary,actions)
    write('development_stability_diagnostic.json',dev_comparisons)
    assert hashlib.sha256(Path(original.__file__).read_bytes()).hexdigest()==spec['source_code_sha256']
    print('Completed; P&L permitted by gates:',result['gate_passed'],flush=True)

if __name__=='__main__':main()
