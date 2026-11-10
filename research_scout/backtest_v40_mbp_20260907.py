"""Frozen V40 economics after original feasibility pass; entirely offline."""
import json,math,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from research_scout import audit_leveraged_etf_official_open_basis_v48 as statlib

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'research_scout/v40_mbp_replay_20260907'
CACHE=ROOT/'research_scout/v49_mbp_replay_20260907/quote_cache'

def save(name,r):
    (OUT/name).write_text(json.dumps(r,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def metrics(daily,trades):
    a=np.asarray(daily,dtype=float);wealth=np.r_[100.,100*np.cumprod(1+a)]
    rr=np.array([r['net_return'] for r in trades]);loss=-rr[rr<0].sum();sd=a.std(ddof=1) if len(a)>1 else 0
    return {'sessions':len(a),'trades':len(rr),'ending_cash':float(wealth[-1]),'total_return':float(wealth[-1]/100-1),'fixed_100_pnl':float(rr.sum()*100),'sharpe':float(a.mean()/sd*np.sqrt(252)) if sd else 0.,'max_daily_drawdown':float((wealth/np.maximum.accumulate(wealth)-1).min()),'win_rate':float((rr>0).mean()) if len(rr) else None,'profit_factor':float(rr[rr>0].sum()/loss) if loss>0 else None,'mean_trade_bps':float(rr.mean()*1e4) if len(rr) else None}

def main():
    gates=json.loads((OUT/'gate_result.json').read_text());assert gates['gate_passed']
    assert not (OUT/'economic_result.json').exists(),'Preserve frozen result'
    allrows=[r for p in sorted(CACHE.glob('*.json')) for r in json.loads(p.read_text())['quotes']]
    q={(r['session_date'],r['symbol'],r['target']):r for r in allrows}
    source=ROOT/'data/parquet/equity/yahoo_chart/SPY_1d.parquet'
    spy=pd.read_parquet(source);spy.index=pd.to_datetime(spy.timestamp,utc=True).dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d');spy=spy.sort_index()
    assert not spy.index.duplicated().any()
    rawdaily=spy.close.pct_change()
    localdays={p.stem for p in CACHE.glob('*.json')}
    extension_days=list(spy.loc['2026-01-01':'2026-07-24'].index)
    first_missing=next(d for d in extension_days if d not in localdays)
    prefix_end=extension_days[extension_days.index(first_missing)-1]
    stages={'development':('2023-03-28','2023-12-31'),'contaminated_validation':('2024-01-01','2025-12-31'),'extension_complete_prefix':('2026-01-01',prefix_end)}
    save('economic_scope.json',{'stage_dates':stages,'extension_first_missing_local_session':first_missing,'extension_policy':'Use complete quote-calendar prefix for equity and benchmark. Later observed fills do not bridge missing sessions; list unresolved signals separately. This choice is based only on data availability.','benchmark_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'benchmark_provenance':'scripts/download_etf_tsm_yahoo_daily.py rescales OHLC by adj_close/close; total-return proxy, not independently reconstructed dividends.','fees_assumptions':'1bp per side plus fixed sell fee 0.0000051 notional + 0.000119/share; cent stress additional to these. Zero commission assumed.'})
    actions={d:r['symbol'] for d,r in gates['signals'].items()}
    openings,prior_closes,_=statlib.load_statistics()
    opdays=sorted(openings);prevday={b:a for a,b in zip(opdays,opdays[1:])}
    def trade(day,symbol,entry='09:31:05',cent=0.):
        a=q.get((day,symbol,entry));b=q.get((day,symbol,'09:35:00'))
        if not a or not b or a['equs_degraded'] or b['equs_degraded']:return None
        if min(a['bid_size'],a['ask_size'],b['bid_size'],b['ask_size'])<=0:return None
        signal=gates['signals'].get(day)
        if signal:assert pd.Timestamp(a['ts_recv'])>pd.Timestamp(signal['signal_ts_recv'])
        assert pd.Timestamp(a['ts_recv'])<pd.Timestamp(b['ts_recv'])
        assert pd.Timestamp(a['ts_recv']).tz_convert('America/New_York').strftime('%Y-%m-%d')==day==pd.Timestamp(b['ts_recv']).tz_convert('America/New_York').strftime('%Y-%m-%d')
        buy=(a['ask']+cent)*1.0001;sell=(b['bid']-cent)*.9999
        net=(sell*(1-.0000051)-.000119)/buy-1
        return {'day':day,'symbol':symbol,'entry_target':entry,'entry_recv':a['ts_recv'],'exit_recv':b['ts_recv'],'entry_ask':a['ask'],'entry_bid':a['bid'],'exit_bid':b['bid'],'exit_ask':b['ask'],'entry_fill':buy,'exit_fill':sell,'net_return':net,'midpoint_return':((b['bid']+b['ask'])/(a['bid']+a['ask']))-1,'entry_wait':a['event_wait_seconds'],'exit_wait':b['event_wait_seconds'],'cent_stress':cent}
    results={};ledger=[];daily_evidence={}
    def summarize(trades,days):
        values=pd.Series(0.,index=days)
        assert len({r['day'] for r in trades})==len(trades)
        for r in trades:values.loc[r['day']]=r['net_return']
        return metrics(values,trades),values
    def control_symbol(day,name):
        s=gates['signals'][day]
        if name=='same_window_SPY':return 'SPY'
        if name=='prior_session_consensus':return actions.get(prevday.get(day,''))
        if name=='overnight_direction':value=s['spy_official_overnight_return']
        elif name=='raw_quantity_balance':
            z=s['quantities'];value=z['UPRO']+z['SSO']-z['SPXU']-z['SDS']
        else:
            prev=prior_closes.get(day);op=openings.get(day)
            if not prev or not op:return None
            value=op['UPRO']['price']/prev['UPRO']-op['SPXU']['price']/prev['SPXU']
        return None if value is None or value==0 else ('UPRO' if value>0 else 'SPXU')
    for name,(start,end) in stages.items():
        days=list(spy.loc[start:end].index)
        assert all(d in localdays for d in days),'Unobserved sessions must not become cash days'
        selected=[d for d in days if d in actions]
        primary=[trade(d,actions[d]) for d in selected];assert all(r is not None for r in primary)
        m,values=summarize(primary,days)
        bm=spy.loc[days,'close'].pct_change();bm.iloc[0]=spy.loc[days[0],'close']/spy.loc[days[0],'open']-1
        assert bm.notna().all()
        benchmark=metrics(bm,[])
        stress=[trade(d,actions[d],cent=.01) for d in selected];assert all(r is not None for r in stress)
        sm,_=summarize(stress,days)
        remove={r['day'] for r in sorted(primary,key=lambda r:r['net_return'],reverse=True)[:10]}
        trimmed,_=summarize([r for r in primary if r['day'] not in remove],days)
        delays={}
        for clock in ['09:31:01','09:32:00']:
            alt=[trade(d,actions[d],entry=clock) for d in selected];alt=[r for r in alt if r]
            matched={r['day'] for r in alt};base,_=summarize([r for r in primary if r['day'] in matched],days)
            delays[clock]={'delayed':summarize(alt,days)[0],'matched_primary':base}
        controls={}
        for c in ['same_window_SPY','overnight_direction','opening_price_pair','raw_quantity_balance','prior_session_consensus']:
            cr=[];missing=[];cash=[]
            for day in selected:
                symbol=control_symbol(day,c)
                if not symbol:cash.append(day);continue
                row=trade(day,symbol)
                if row is None:missing.append(day)
                else:cr.append(row)
            controls[c]={'metrics':summarize(cr,days)[0],'missing_execution_dates':missing,'cash_or_undefined_dates':cash,'scope':'Matched primary signal dates; not standalone strategy test'}
        for level in (1,2,3):
            cr=[trade(d,({'UPRO':['SPY','SSO','UPRO'],'SPXU':['SH','SDS','SPXU']}[actions[d]])[level-1]) for d in selected]
            controls[f'leverage_{level}x']={'metrics':summarize([r for r in cr if r],days)[0],'missing_executions':sum(r is None for r in cr)}
        matched_bm=pd.Series(0.,index=days)
        for day in selected:matched_bm.loc[day]=rawdaily.loc[day]
        rng=np.random.default_rng(400907);excess=(values-bm).to_numpy();means=[]
        for _ in range(5000):
            starts=rng.integers(0,len(days),math.ceil(len(days)/5));ix=((starts[:,None]+np.arange(5))%len(days)).ravel()[:len(days)];means.append(float(excess[ix].mean()))
        ci=[float(x) for x in np.quantile(means,[.025,.975])]
        admission={'beats_SPY_total_return':m['total_return']>benchmark['total_return'],'positive_lower95_mean_daily_excess':ci[0]>0,'cent_stress_profitable':sm['ending_cash']>100,'remove_top_ten_profitable':trimmed['ending_cash']>100}
        spread_drag=np.array([r['midpoint_return']-r['net_return'] for r in primary])
        results[name]={'start':days[0],'end':days[-1],'primary':m,'SPY_total_return_proxy':benchmark,'cent_stress':sm,'remove_top_ten':trimmed,'delays':delays,'controls':controls,'matched_session_SPY_close_to_close':metrics(matched_bm,[]),'bootstrap_mean_daily_excess_95':ci,'admission_gates':admission,'passed':all(admission.values()),'mean_midpoint_to_net_drag_bps':float(spread_drag.mean()*1e4),'max_entry_event_wait_seconds':max(r['entry_wait'] for r in primary),'max_exit_event_wait_seconds':max(r['exit_wait'] for r in primary),'directions':{symbol:metrics([r['net_return'] for r in primary if r['symbol']==symbol],[r for r in primary if r['symbol']==symbol]) for symbol in ['UPRO','SPXU']},'yearly':{str(y):summarize([r for r in primary if r['day'].startswith(str(y))],[d for d in days if d.startswith(str(y))])[0] for y in sorted({d[:4] for d in days})}}
        for r in primary:ledger.append(dict(r,stage=name))
        daily_evidence[name]={'strategy':values.to_dict(),'SPY':bm.to_dict()}
    unresolved=[d for d in gates['signals'] if '2023-03-28'<=d<='2026-07-24' and d not in gates['executable_signal_dates']]
    later_observed=[d for d in gates['executable_signal_dates'] if d>prefix_end]
    save('trade_ledger.json',ledger);save('daily_returns.json',daily_evidence)
    save('economic_result.json',{'stages':results,'unresolved_signal_dates':unresolved,'observed_signal_dates_after_complete_prefix_not_in_equity':later_observed,'decision':'pass_development_requires_further_validation' if results['development']['passed'] else 'reject_development_economics_no_tuning','later_stage_interpretation':'Descriptive contaminated history; cannot rescue development failure.','pnl_calculated':True})
    print(json.dumps({k:{'primary':v['primary'],'SPY_ending_cash':v['SPY_total_return_proxy']['ending_cash'],'passed':v['passed'],'admission_gates':v['admission_gates']} for k,v in results.items()},indent=2))

if __name__=='__main__':main()
