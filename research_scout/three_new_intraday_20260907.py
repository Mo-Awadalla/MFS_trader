"""Three frozen, offline bar-based hypotheses. No optimization or paid downloads."""
import json,hashlib,math
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import pandas as pd
import exchange_calendars as xc

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'research_scout/three_new_intraday_20260907'
STOCKROOT=ROOT/'data/parquet/vs_icsm_static20'
SPYBAR=ROOT/'data/parquet/market_intraday_momentum/alpaca_iex/SPY_30min.parquet'
DAILY=ROOT/'data/parquet/equity/yahoo_chart/SPY_1d.parquet'
FOMC=ROOT/'research_scout/fomc_statement_calendar_v45.json'
def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def freeze():
    OUT.mkdir(exist_ok=True)
    stockpaths=sorted(STOCKROOT.rglob('*_1h.parquet'))
    spec={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'frozen before strategy returns','hypotheses':{
    'V93':{'name':'Pre-FOMC uncertainty premium','mechanism':'Scheduled monetary-policy uncertainty may command an intraday equity premium before resolution; condition on elevated prior volatility rather than post-release direction.','signal':'Scheduled FOMC date in existing official calendar, prior-session SPY 20-day close-return standard deviation above median of 252 prior-session RV20 observations.','trade':'Long SPY at 10:00 bar open; exit 13:30 bar open, before 14:00 announcement.','cost_bps_each_side':3,'delay_entry':'10:30','control':'Unconditional pre-FOMC SPY with same clocks; report selected high-volatility subset versus excluded low-volatility dates.','novelty':'Exact volatility-conditioned rule not located in archive. DT8 proposed unconditional pre-FOMC; V45 tested post-release discovery. Not a claim of literature novelty.'},
    'V94':{'name':'Overnight-and-opening pressure reversal','mechanism':'Stock-specific selling through the opening half hour may temporarily depress prices and reverse later; this tests stock selection rather than index breadth.','signal':'At 10:00 compare each stock 09:00 hourly close (ends10:00) to previous full-session15:00 hourly close (ends16:00), minus SPY 09:30 half-hour close versus previous15:30 half-hour close. Eligible absolute stock return <=15%, positive prices/volumes, at least15 of fixed19 issuers. Select three lowest residuals only if all three are negative.','trade':'Equal-weight three stocks, long at11:00 hourly open, exit15:00 hourly open. One-hour buffer after signal.','universe':'Existing static20 SIP panel excluding GOOG to avoid double-counting Alphabet; fixed19 survivors, explicit selection bias.','cost_bps_each_side':5,'delay_entry':'12:00','control':'Equal-weight all eligible issuers on the same signal days and mirrored top-three residual selection.','novelty':'Related to unimplemented overnight-loser proposal and failed event/daily reversals; this exact non-event hourly stock-selection rule not found. It is not a renamed V75 index breadth vote.'},
    'V95':{'name':'Alphabet voting-share premium normalization','mechanism':'GOOG and GOOGL share issuer economics but can have changing voting/liquidity premiums. An unusually wide same-clock premium may normalize intraday; long cheaper class only, not riskless arbitrage.','signal':'At11:00 use GOOG/GOOGL ratio of10:00 hourly closes. Compare log ratio with median and1.4826*MAD of preceding20 same-clock observations, excluding current day. If abs deviation>2scaledMAD and MAD>0, buy relatively cheap class: GOOGL for high ratio, GOOG for low.','trade':'Enter12:00 hourly open, exit15:00 hourly open. One-hour buffer.','cost_bps_each_side':5,'delay_entry':'13:00','control':'Equal-weight both classes on same signal days; report selected-minus-control return to isolate selection from Alphabet beta.','novelty':'No exact dual-class rule located. Related to broad relative-value research, distinct from leverage-wrapper fair-value identities. Not a claim that share classes are freely convertible.'}},
    'common':{'development':'2021-01-04 through2023-12-29','later_descriptive':'2024-01-02 through2025-12-31; heavily exposed history, not pristine validation','capital':'$100 fully funded fractional long portfolio, weights sum1, cash on known no-signal days, zero cash interest; no shorting, leverage, overnight or external trading','inputs':'Use completed-bar features only; hourly bars start at timestamp. No high/low fill assumptions. All entries and exits use later bar opens.','execution':'Bar-open reference with adverse cost on both sides; all-in cost assumptions stand in for spread, fees and slippage, not historical observed quotes. Costs double in stress. Fractional fills/capacity/settlement unvalidated.','calendar':'NYSE regular full16:00 close sessions only for trading; full exchange calendar retained for strategy and SPY equity. Previous-session close features require prior full session. Missing feature/fill days remain explicit unknowns, not silently cash.','robustness':'Double cost, delayed entry, remove five best trade days, mechanism controls; 5000 five-session circular-block bootstrap draws, seed939495, paired daily excess against SPY and control. 98.333% intervals for three tested primary strategies (Bonferroni family alpha .05).','pass_definition':'Both development and later period: net compounded return beats matched-calendar SPY total return; doubled-cost and remove-five results positive; multiplicity-adjusted lower excess bound positive; no unresolved days. Positive bar results still require independent quote and point-in-time-universe validation. No old minimum-frequency veto: sparse hypotheses are tested and their limited samples reported.','benchmark':'Cached Yahoo adjusted OHLC total-return proxy; first calendar day adjusted open to close then adjusted close-to-close. No benchmark friction, conservative hurdle.','no_tuning':True},
    'sources':[{'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in stockpaths+[SPYBAR,DAILY,FOMC]],
    'official_context':['https://www.federalreserve.gov/newsevents/pressreleases/monetary20130313a.htm','https://www.sec.gov/Archives/edgar/data/1652044/000165204423000016/googexhibit420q42022.htm']}
    with (OUT/'specification.json').open('x',encoding='utf-8') as f:json.dump(spec,f,indent=2)
    return spec

def bars(path):
    d=pd.read_parquet(path);t=pd.to_datetime(d.timestamp,utc=True).dt.tz_convert('America/New_York')
    d=d.assign(day=t.dt.strftime('%Y-%m-%d'),clock=t.dt.strftime('%H:%M'),observed_start=t.astype(str))
    assert not d.duplicated(['day','clock']).any()
    return d.set_index(['day','clock']).sort_index()

def metrics(v,n):
    a=np.asarray(v,dtype=float);w=np.r_[100.,100*np.cumprod(1+a)];sd=a.std(ddof=1)
    return {'sessions':len(a),'trade_days':n,'ending_cash':float(w[-1]),'total_return':float(w[-1]/100-1),'fixed_100_pnl':float(a.sum()*100),'max_daily_drawdown':float((w/np.maximum.accumulate(w)-1).min()),'sharpe':float(a.mean()/sd*np.sqrt(252)) if sd else 0.}

def run():
    spec=freeze()
    stocks={p.name.split('_')[0]:bars(p) for p in STOCKROOT.rglob('*_1h.parquet')};sb=bars(SPYBAR)
    syms=sorted(set(stocks)-{'GOOG'});assert len(syms)==19
    spy=pd.read_parquet(DAILY);spy.index=pd.to_datetime(spy.timestamp,utc=True).dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d');spy=spy.sort_index()
    rv=spy.close.pct_change().rolling(20).std().shift(1);rvbase=rv.rolling(252).median()
    cal=xc.get_calendar('XNYS',start='2020-12-01',end='2025-12-31');sched=cal.schedule
    days=[d.strftime('%Y-%m-%d') for d in sched.index];previous={b:a for a,b in zip(days,days[1:])}
    full={d.strftime('%Y-%m-%d') for d,row in sched.iterrows() if pd.Timestamp(row['close']).tz_convert('America/New_York').strftime('%H:%M')=='16:00'}
    days=[d for d in days if '2021-01-04'<=d<='2025-12-31'];fomc={r['release_date'] for r in json.loads(FOMC.read_text())['events']}
    def get(frame,day,clock):
        if (day,clock) not in frame.index:return None
        r=frame.loc[(day,clock)]
        if not np.isfinite([r.open,r.close,r.volume]).all() or min(r.open,r.close,r.volume)<=0:return None
        return r
    signals={h:{} for h in spec['hypotheses']};controls={h:{} for h in signals};unknown={h:{} for h in signals};ratios=[]
    features={h:{} for h in signals}
    for day in days:
        if day not in full:continue
        if day in fomc:
            if day not in rv.index or pd.isna(rv.loc[day]) or pd.isna(rvbase.loc[day]):unknown['V93'][day]='volatility_history_missing'
            else:
                features['V93'][day]={'rv20_lag1':float(rv.loc[day]),'prior252_median':float(rvbase.loc[day])}
                controls['V93'][day]={'unconditional_FOMC':{'SPY':1.}}
                if rv.loc[day]>rvbase.loc[day]:signals['V93'][day]={'SPY':1.}
        prior=previous.get(day)
        if prior in full:
            sp=get(sb,day,'09:30');sprev=get(sb,prior,'15:30');res={}
            if sp is None or sprev is None:unknown['V94'][day]='SPY_signal_bar_missing'
            else:
                market=sp.close/sprev.close-1
                for symbol in syms:
                    a=get(stocks[symbol],day,'09:00');b=get(stocks[symbol],prior,'15:00')
                    if a is not None and b is not None:
                        move=a.close/b.close-1
                        if abs(move)<=.15:res[symbol]=float(move-market)
                if len(res)<15:unknown['V94'][day]='fewer_than15_feature_stocks'
                else:
                    ordered=sorted(res,key=lambda s:(res[s],s));features['V94'][day]={'residuals':res,'prior_session':prior}
                    if res[ordered[2]]<0:
                        signals['V94'][day]={s:1/3 for s in ordered[:3]}
                        controls['V94'][day]={'all_eligible_equal_weight':{s:1/len(res) for s in res},'top_three_residuals':{s:1/3 for s in ordered[-3:]}}
        a=get(stocks['GOOG'],day,'10:00');b=get(stocks['GOOGL'],day,'10:00')
        if a is None or b is None:unknown['V95'][day]='ratio_input_missing';continue
        ratio=float(np.log(a.close/b.close))
        if len(ratios)>=20:
            hist=np.array(ratios[-20:]);center=float(np.median(hist));scale=float(1.4826*np.median(abs(hist-center)))
            features['V95'][day]={'log_ratio':ratio,'prior20_median':center,'prior20_scaled_MAD':scale}
            if scale>0 and abs(ratio-center)>2*scale:
                symbol='GOOGL' if ratio>center else 'GOOG';signals['V95'][day]={symbol:1.}
                controls['V95'][day]={'equal_weight_both_classes':{'GOOG':.5,'GOOGL':.5}}
        ratios.append(ratio)
    # Signal artifact is saved before evaluating entry/exit returns.
    save('signals.json',{'signals':signals,'features':features,'unknown_feature_days':unknown,'controls':controls})
    fill_ledger=[];execution_missing={h:{} for h in signals}
    def portfolio(h,day,weights,cost_mult=1,delay=False,record=False):
        entry={'V93':'10:00','V94':'11:00','V95':'12:00'}[h];end='13:30' if h=='V93' else '15:00'
        if delay:entry=spec['hypotheses'][h]['delay_entry']
        rate=spec['hypotheses'][h]['cost_bps_each_side']*cost_mult/10000
        net=0.;gross=0.;legs=[]
        for symbol,weight in weights.items():
            frame=sb if symbol=='SPY' else stocks[symbol]
            a=get(frame,day,entry);b=get(frame,day,end)
            if a is None or b is None:return None
            buy=float(a.open)*(1+rate);sell=float(b.open)*(1-rate)
            ret=sell/buy-1;net+=weight*ret;gross+=weight*(b.open/a.open-1)
            legs.append({'symbol':symbol,'weight':weight,'entry_clock':entry,'exit_clock':end,'entry_reference':float(a.open),'exit_reference':float(b.open),'entry_fill':buy,'exit_fill':sell,'net_return':ret})
        if record:fill_ledger.append({'hypothesis':h,'day':day,'legs':legs,'net_return':float(net),'gross_return':float(gross)})
        return float(net)
    output={};daily_out={}
    for h in signals:
        net={};double={};delay={};ctrl={}
        for day,weights in signals[h].items():
            v=portfolio(h,day,weights,record=True)
            if v is None:execution_missing[h][day]='entry_or_exit_missing';continue
            net[day]=v;double[day]=portfolio(h,day,weights,cost_mult=2);delay[day]=portfolio(h,day,weights,delay=True)
        for day,cs in controls[h].items():
            for name,w in cs.items():ctrl.setdefault(name,{})[day]=portfolio(h,day,w)
        output[h]={}
        for stage,start,end in [('development','2021-01-04','2023-12-29'),('later_exposed','2024-01-02','2025-12-31')]:
            ds=[d for d in days if start<=d<=end];assert set(ds)<=set(spy.index)
            missing=sorted({d for d in unknown[h] if d in ds}|{d for d in execution_missing[h] if d in ds})
            # Explicitly labeled available-case path if unknowns exist. No missing
            # observation is represented as a known no-trade decision.
            valid=[d for d in ds if d not in missing]
            series=pd.Series({d:net.get(d,0.) for d in valid});n=sum(d in net for d in valid)
            bm=spy.loc[ds,'close'].pct_change();bm.iloc[0]=spy.loc[ds[0],'close']/spy.loc[ds[0],'open']-1
            sm=metrics(series,n);benchmark=metrics(bm,0)
            stresses=metrics([double.get(d,0.) for d in valid],n)
            delay_missing=[d for d in net if d in valid and delay[d] is None]
            delayed=metrics([delay.get(d,0.) for d in valid if d not in delay_missing],n-len(delay_missing))
            top=set(sorted([d for d in valid if d in net],key=lambda d:net[d],reverse=True)[:5]);removed=metrics([0. if d in top else series.loc[d] for d in valid],n-len(top))
            controls_summary={};control_series={}
            for name,vals in ctrl.items():
                cm=[d for d,v in vals.items() if d in valid and v is None];cv=pd.Series({d:vals.get(d,0.) for d in valid if d not in cm})
                controls_summary[name]={'metrics':metrics(cv,sum(d in vals and vals[d] is not None for d in valid)),'missing_dates':cm}
                control_series[name]=cv
            rng=np.random.default_rng(939495);a=(series-bm.loc[valid]).to_numpy();boot=[]
            for _ in range(5000):
                ix=((rng.integers(0,len(a),math.ceil(len(a)/5))[:,None]+np.arange(5))%len(a)).ravel()[:len(a)];boot.append(float(a[ix].mean()))
            ci=[float(x) for x in np.quantile(boot,[.05/6,1-.05/6])]
            checks={'beats_full_calendar_SPY':sm['total_return']>benchmark['total_return'],'doubled_cost_positive':stresses['ending_cash']>100,'remove_five_positive':removed['ending_cash']>100,'family_adjusted_excess_lower_bound_positive':ci[0]>0,'no_unknown_primary_days':not missing}
            output[h][stage]={'start':start,'end':end,'net':sm,'SPY':benchmark,'double_cost':stresses,'delay':delayed,'delay_missing':delay_missing,'remove_best_five':removed,'controls':controls_summary,'mean_daily_excess_family_adjusted_CI':ci,'unknown_days':missing,'coverage_note':'Available-case strategy and paired inference if unknown days exist; full-calendar SPY still shown; automatic failure, not comparable complete equity.' if missing else 'Complete primary daily accounting.','gates':checks,'passed':all(checks.values()),'yearly':{year:metrics(series.loc[[d for d in valid if d.startswith(year)]],sum(d.startswith(year) for d in net)) for year in sorted({d[:4] for d in valid})}}
            daily_out[h+'_'+stage]={'strategy':series.to_dict(),'SPY_full_calendar':bm.to_dict(),'controls':{k:v.to_dict() for k,v in control_series.items()}}
    save('trade_ledger.json',fill_ledger);save('daily_returns.json',daily_out);save('results.json',{'hypotheses':output,'execution_missing':execution_missing,'inputs_existing_only':True,'execution_quality':'bar-based scenario, no historical bid/ask validation','no_tuning':True})
    print(json.dumps({h:{s:{'net':r['net']['ending_cash'],'SPY':r['SPY']['ending_cash'],'trades':r['net']['trade_days'],'unknown':len(r['unknown_days']),'passed':r['passed']} for s,r in stages.items()} for h,stages in output.items()},indent=2))

if __name__=='__main__':run()
