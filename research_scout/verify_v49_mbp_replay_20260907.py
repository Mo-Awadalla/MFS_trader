"""Independent signal/action reconstruction from the saved extracted quote states."""
from collections import Counter
from pathlib import Path
from statistics import median
import hashlib,json
import pandas as pd
import databento as db
from research_scout import audit_leveraged_etf_post_open_simplex_v49 as old

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'research_scout/v49_mbp_replay_20260907'

def main():
    result=json.loads((OUT/'original_gate_result.json').read_text())
    spec=json.loads((OUT/'specification.json').read_text())
    states={};errors=[]
    for p in sorted((OUT/'quote_cache').glob('*.json')):
        for row in json.loads(p.read_text())['quotes']:
            key=(row['session_date'],row['target'],row['symbol'])
            assert key not in states
            t=pd.Timestamp(row['session_date']+' '+row['target'],tz='America/New_York')
            assert 0 <= (pd.Timestamp(row['ts_event'])-t).total_seconds() <=60
            assert row['ask']>=row['bid']>0
            states[key]=row
    openings,_=old.load_openings()
    excluded=set(result['degraded_dates_excluded_union'])
    def reconstruct(clock,window):
        history=[];actions={};eligible=0
        for day,op in sorted(openings.items()):
            if not '2023-03-28'<=day<='2026-07-24' or day in excluded:continue
            if set(old.SYMBOLS)-set(op):continue
            qs=[states.get((day,clock,s)) for s in old.SYMBOLS]
            if any(q is None or q['equs_degraded'] for q in qs):continue
            if any(q['event_wait_seconds']>5 for q in qs):continue
            events=[pd.Timestamp(q['ts_event']) for q in qs]
            if (max(events)-min(events)).total_seconds()>5:continue
            boundary=pd.Timestamp(day+' 09:31:00',tz='America/New_York')
            if any(pd.Timestamp(q['ts_recv'])>=boundary for q in qs) or any(pd.Timestamp(op[s]['ts_recv'])>=boundary for s in old.SYMBOLS):continue
            returns={q['symbol']:((q['bid']+q['ask'])/2/op[q['symbol']]['price'])-1 for q in qs}
            fair=median([returns['SPY'],returns['SSO']/2,-returns['SH'],-returns['SDS']/2])
            residuals=(3*fair-returns['UPRO'],-3*fair-returns['SPXU'])
            if len(history)>=window:
                eligible+=1
                is_positive=[residuals[i]>median(h[i] for h in history[-window:]) for i in (0,1)]
                if sum(is_positive)==1:actions[day]='UPRO' if is_positive[0] else 'SPXU'
            history.append(residuals)
        return actions,eligible
    primary,eligible=reconstruct('09:30:05',20)
    assert primary=={d:r['symbol'] for d,r in result['signals'].items()}
    assert eligible==result['all_periods']['synchronized_warm_sessions']
    comparisons={}
    for label,clock,window in [('adjacent_09_30_01','09:30:01',20),('10','09:30:05',10),('40','09:30:05',40)]:
        actions,_=reconstruct(clock,window)
        union=primary.keys()|actions.keys()
        agree=sum(primary.get(d)==actions.get(d) for d in union)
        rate=100*agree/max(len(union),1)
        saved=result['stability']['adjacent_09_30_01'] if label.startswith('adjacent') else result['stability']['rolling_windows'][label]
        assert abs(rate-saved['identical_action_including_cash_pct'])<1e-10
        comparisons[label]={'matching_actions':agree,'days_either_rule_trades':len(union),'agreement_pct':rate}
    assert hashlib.sha256(Path(old.__file__).read_bytes()).hexdigest()==spec['source_code_sha256']
    # Re-read one source file per calendar year to check extraction separately
    # from the signal arithmetic, using per-symbol index minima.
    checked=[]
    for year in ('2023','2024','2025','2026'):
        entry=next(e for e in spec['files'] if Path(e['path']).name.startswith(year))
        path=ROOT/entry['path']; day=path.name[:10]
        raw=db.DBNStore.from_file(path).to_df().reset_index()
        cache=json.loads((OUT/'quote_cache'/(day+'.json')).read_text())
        assert hashlib.sha256(path.read_bytes()).hexdigest()==cache['source_sha256']
        for clock in spec['targets']:
            t=pd.Timestamp(day+' '+clock,tz='America/New_York')
            for symbol in old.SYMBOLS:
                sub=raw[(raw.symbol==symbol)&(raw.ts_event>=t)&(raw.ts_event<=t+pd.Timedelta(seconds=60))]
                sub=sub[(sub.bid_px_00>0)&(sub.ask_px_00>=sub.bid_px_00)&sub.bid_px_00.notna()&sub.ask_px_00.notna()]
                key=(day,clock,symbol)
                if sub.empty:assert key not in states;continue
                sub=sub[sub.ts_event==sub.ts_event.min()]
                row=sub.loc[sub.ts_recv.idxmin()]
                saved=states[key]
                assert pd.Timestamp(saved['ts_event'])==row.ts_event and pd.Timestamp(saved['ts_recv'])==row.ts_recv
                assert saved['bid']==row.bid_px_00 and saved['ask']==row.ask_px_00
        checked.append(day)
    verification={'errors':errors,'independently_reconstructed_signals':len(primary),'independently_reconstructed_warm_sessions':eligible,'comparisons':comparisons,'source_extraction_spotcheck_dates':checked,'original_code_hash_unchanged':True,'pnl_calculated':False,'passed':True}
    (OUT/'verification.json').write_text(json.dumps(verification,indent=2)+'\n')
    print(json.dumps(verification,indent=2))

if __name__=='__main__':main()
