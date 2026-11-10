"""Data-only reconciliation. No signals, returns, orders, or account changes."""
from pathlib import Path
import argparse, json, gzip, os
from datetime import datetime, timezone
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research_scout/blocker_reconciliation_20260907'
SYMBOLS = ['SPY','SSO','UPRO','SH','SDS','SPXU']
TARGETS = ['09:30:01','09:30:05','09:31:00','09:31:01','09:31:05','09:32:00','09:33:00','09:35:00']
DATES = [f'{y}-{m}-04' if m != '01' else f'{y}-01-05' for y in (2021,2022,2023) for m in ('01','05','08','10')]
# Dates fixed without reference to returns; all are weekdays and regular US sessions.
def save(name, value):
    OUT.mkdir(exist_ok=True)
    (OUT/name).write_text(json.dumps(value, indent=2), encoding='utf-8')

def local():
    import databento as db
    rows=[]
    paths=sorted((ROOT/'external_artifacts/databento_cash_etf_mbp1_open_v55/EQUS.MINI/mbp-1').glob('2023-*.dbn.zst'))
    for i,p in enumerate(paths):
        day=p.name[:10]
        df=db.DBNStore.from_file(p).to_df()
        rec={'date':day,'targets':{}}
        for clock in TARGETS:
            target=pd.Timestamp(f'{day} {clock}',tz='America/New_York').tz_convert('UTC')
            # Receive time controls what the researcher could observe. Retain event
            # time separately, so old event data arriving later cannot pass freshness.
            w=df.loc[target:target+pd.Timedelta(seconds=60)]
            states={}
            for s in SYMBOLS:
                z=w[(w.symbol==s)&(w.bid_px_00>0)&(w.ask_px_00>=w.bid_px_00)&(w.bid_sz_00>0)&(w.ask_sz_00>0)&(w.ts_event>=target)]
                if not z.empty:
                    r=z.iloc[0]
                    states[s]={'receive_wait_seconds':(z.index[0]-target).total_seconds(),'event_wait_seconds':(r.ts_event-target).total_seconds(),'event_time':str(r.ts_event),'receive_time':str(z.index[0])}
            rec['targets'][clock]=states
        rows.append(rec)
        if (i+1)%25==0: print(f'Local quote audit: {i+1}/{len(paths)} sessions',flush=True)
    summary={}
    for clock in TARGETS:
        summary[clock]={'sessions_all_six_within_60s':sum(len(r['targets'][clock])==6 for r in rows),'sessions_all_six_within_5s':sum(len(r['targets'][clock])==6 and max(v['receive_wait_seconds'] for v in r['targets'][clock].values())<=5 for r in rows)}
    save('local_exact_targets.json',{'sessions':len(rows),'first_date':rows[0]['date'],'last_date':rows[-1]['date'],'policy':'First positive-size non-crossed quote with both receive and event time at or after target; receive wait <=60s. Freshness diagnostic <=5s. Not original feature/signaling/official-statistic gate replay.','summary':summary,'rows':rows})
    print(json.dumps(summary),flush=True)

def sip():
    import requests
    from dotenv import dotenv_values
    env=dotenv_values(ROOT/'.env')
    def get(*names): return next((os.getenv(n) or env.get(n) for n in names if os.getenv(n) or env.get(n)),None)
    key=get('ALPACA_API_KEY','APCA_API_KEY_ID'); secret=get('ALPACA_API_SECRET','APCA_API_SECRET_KEY')
    if not key or not secret: raise RuntimeError('Historical data credentials unavailable')
    session=requests.Session(); session.headers.update({'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret})
    out=[]
    for day in DATES:
        for clock in ['09:30:01','10:30:00']:
            start=pd.Timestamp(f'{day} {clock}',tz='America/New_York').tz_convert('UTC')
            params={'symbols':','.join(SYMBOLS),'feed':'sip','start':start.isoformat(),'end':(start+pd.Timedelta(seconds=10)).isoformat(),'limit':10000}
            record={'date':day,'clock':clock,'pages':0,'complete':False}; quotes={s:[] for s in SYMBOLS}
            try:
                for page in range(10):
                    response=session.get('https://data.alpaca.markets/v2/stocks/quotes',params=params,timeout=25)
                    record['http_status']=response.status_code
                    if not response.ok: break
                    payload=response.json();record['pages']+=1
                    for s,rs in (payload.get('quotes') or {}).items(): quotes.setdefault(s,[]).extend(rs)
                    token=payload.get('next_page_token')
                    if not token: record['complete']=True;break
                    params['page_token']=token
                with gzip.open(OUT/f"sip_{day}_{clock.replace(':','')}.json.gz",'wt',encoding='utf-8') as f: json.dump(quotes,f)
                record['symbols']={}
                for s,rs in quotes.items():
                    valid=[r for r in rs if r.get('bp',0)>0 and r.get('ap',0)>=r['bp'] and r.get('bs',0)>0 and r.get('as',0)>0]
                    record['symbols'][s]={'rows':len(rs),'valid_rows':len(valid),'first_valid_wait_seconds':(pd.Timestamp(valid[0]['t'])-start).total_seconds() if valid else None,'fields':sorted(rs[0]) if rs else []}
            except Exception as e: record['error_type']=type(e).__name__
            out.append(record)
            save('sip_pilot.json',{'specification':'specification.json','probes':out,'account_changes':False,'returns_computed':False,'sample_not_full_calendar':True})
            print(f"SIP {day} {clock}: HTTP {record.get('http_status')} complete={record['complete']}",flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['spec','local','sip']);a=p.parse_args()
    OUT.mkdir(exist_ok=True)
    if a.mode=='spec': save('specification.json',{'created_utc':datetime.now(timezone.utc).isoformat(),'scope':'Read-only data QA, no P&L, unchanged old experiments.','local_dates':'All existing 2023 opening MBP-1 sessions','local_targets':TARGETS,'sip_dates':DATES,'sip_windows':['09:30:01 ET +10 seconds','10:30:00 ET +10 seconds'],'sip_symbols':SYMBOLS,'max_pages_per_window':10,'selection':'Calendar-only fixed dates, no return selection','interpretation':'Sample proves access/schema only, not complete period or strategy gate pass; SIP timestamps are not Databento ts_recv.'})
    elif a.mode=='local': local()
    else: sip()
