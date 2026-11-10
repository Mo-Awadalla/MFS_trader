"""Independent feature reconstruction, cash accounting, and registered controls."""
from pathlib import Path
from decimal import Decimal,getcontext
import json,math,hashlib
import pandas as pd
import numpy as np
from research_scout.three_new_intraday_20260907 import ROOT,OUT,STOCKROOT,SPYBAR,DAILY,bars

def main():
    getcontext().prec=40
    spec=json.loads((OUT/'specification.json').read_text());sig=json.loads((OUT/'signals.json').read_text());result=json.loads((OUT/'results.json').read_text());led=json.loads((OUT/'trade_ledger.json').read_text());daily=json.loads((OUT/'daily_returns.json').read_text())
    stocks={p.name.split('_')[0]:bars(p) for p in STOCKROOT.rglob('*_1h.parquet')};sp=bars(SPYBAR)
    # Independent rank-selection reconstruction for every eligible stock day.
    for day,ft in sig['features']['V94'].items():
        residual={}
        market=sp.loc[(day,'09:30'),'close']/sp.loc[(ft['prior_session'],'15:30'),'close']-1
        for symbol,value in ft['residuals'].items():
            raw=stocks[symbol].loc[(day,'09:00'),'close']/stocks[symbol].loc[(ft['prior_session'],'15:00'),'close']-1-market
            assert abs(raw-value)<1e-12;residual[symbol]=raw
        ranked=sorted(residual,key=lambda x:(residual[x],x));expected=ranked[:3] if residual[ranked[2]]<0 else []
        assert set(expected)==set(sig['signals']['V94'].get(day,{}))
    # Alphabet prior-window statistics reconstructed from raw full-session bars.
    import exchange_calendars as xc
    cal=xc.get_calendar('XNYS',start='2021-01-04',end='2025-12-31');history=[]
    for ts,row in cal.schedule.iterrows():
        day=ts.strftime('%Y-%m-%d')
        if pd.Timestamp(row['close']).tz_convert('America/New_York').strftime('%H:%M')!='16:00':continue
        if (day,'10:00') not in stocks['GOOG'].index or (day,'10:00') not in stocks['GOOGL'].index:continue
        a=stocks['GOOG'].loc[(day,'10:00')];b=stocks['GOOGL'].loc[(day,'10:00')]
        if min(a.open,a.close,a.volume,b.open,b.close,b.volume)<=0:continue
        value=float(np.log(a.close/b.close))
        if len(history)>=20:
            median=float(np.median(history[-20:]));mad=float(np.median(np.abs(np.array(history[-20:])-median))*1.4826)
            expected=({'GOOGL'} if value>median else {'GOOG'}) if mad>0 and abs(value-median)>2*mad else set()
            assert expected==set(sig['signals']['V95'].get(day,{}))
            saved=sig['features']['V95'][day];assert abs(saved['prior20_median']-median)<1e-12 and abs(saved['prior20_scaled_MAD']-mad)<1e-12
        history.append(value)
    df=pd.read_parquet(DAILY);df.index=pd.to_datetime(df.timestamp,utc=True).dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d');df=df.sort_index();rr=df.close.pct_change().to_numpy()
    for day,f in sig['features']['V93'].items():
        j=df.index.get_loc(day);v=float(np.std(rr[j-20:j],ddof=1));baseline=float(np.median([np.std(rr[k-19:k+1],ddof=1) for k in range(j-252,j)]))
        assert abs(v-f['rv20_lag1'])<1e-12 and abs(baseline-f['prior252_median'])<1e-12
        assert (v>baseline)==(day in sig['signals']['V93'])
    summaries={};cashledger=[];controls_evidence={};legcount=0
    for h,stages in result['hypotheses'].items():
        summaries[h]={}
        for stage,m in stages.items():
            rows=sorted([r for r in led if r['hypothesis']==h and m['start']<=r['day']<=m['end']],key=lambda r:r['day'])
            assert len(rows)==len({r['day'] for r in rows})
            cash=Decimal(100);gross=Decimal(100);rate=Decimal(str(spec['hypotheses'][h]['cost_bps_each_side']))/10000
            for r in rows:
                after=Decimal(0);gr=0
                assert abs(sum(t['weight'] for t in r['legs'])-1)<1e-12
                for t in r['legs']:
                    legcount+=1;frame=sp if t['symbol']=='SPY' else stocks[t['symbol']]
                    assert frame.loc[(r['day'],t['entry_clock']),'open']==t['entry_reference']
                    assert frame.loc[(r['day'],t['exit_clock']),'open']==t['exit_reference']
                    assert t['entry_clock']<t['exit_clock']
                    buy=Decimal(str(t['entry_reference']))*(1+rate);sell=Decimal(str(t['exit_reference']))*(1-rate)
                    after+=(cash*Decimal(str(t['weight']))/buy)*sell
                    gr+=t['weight']*(t['exit_reference']/t['entry_reference']-1)
                assert abs(float(after/cash-1)-r['net_return'])<1e-12
                cashledger.append({'hypothesis':h,'stage':stage,'day':r['day'],'before':float(cash),'after':float(after),'ending_positions':0})
                cash=after;gross*=Decimal(str(1+gr))
            assert abs(float(cash)-m['net']['ending_cash'])<1e-8
            summaries[h][stage]={'verified_net_cash':float(cash),'gross_bar_reference_cash':float(gross),'trade_days':len(rows),'mean_gross_bps':float(np.mean([r['gross_return'] for r in rows])*10000),'mean_net_bps':float(np.mean([r['net_return'] for r in rows])*10000)}
            panel=daily[h+'_'+stage];strategy=pd.Series(panel['strategy']);controls_evidence[h+'_'+stage]={}
            for name,values in panel['controls'].items():
                control=pd.Series(values);joint=strategy.index.intersection(control.index);difference=(strategy.loc[joint]-control.loc[joint]).to_numpy();rng=np.random.default_rng(939495);means=[]
                for _ in range(5000):
                    ix=((rng.integers(0,len(joint),math.ceil(len(joint)/5))[:,None]+np.arange(5))%len(joint)).ravel()[:len(joint)];means.append(difference[ix].mean())
                controls_evidence[h+'_'+stage][name]={'mean_daily_selection_excess':float(difference.mean()),'family_adjusted_interval':list(map(float,np.quantile(means,[.05/6,1-.05/6]))),'paired_days':len(joint),'interpretation':'Exploratory control comparison; three-primary adjustment does not cover every secondary control.'}
    assert all(hashlib.sha256((ROOT/s['path']).read_bytes()).hexdigest()==s['sha256'] for s in spec['sources'])
    verified={'passed':True,'errors':[],'portfolio_trade_days':len(led),'legs_checked':legcount,'independent_feature_reconstruction':True,'input_hashes_unchanged':True,'same_day_flat':True,'stages':summaries}
    for name,obj in [('verification.json',verified),('verified_cash_ledger.json',cashledger),('control_inference.json',controls_evidence)]: (OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
    print(json.dumps(verified,indent=2))

if __name__=='__main__':main()
