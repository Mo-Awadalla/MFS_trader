"""Explicit post-result accounting diagnostic: net adjacent same-side orders."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from run import OLD,DERIV


def replay(predictions,bars,funding,threshold,long_only=False):
    start=predictions.open_time.min().normalize()
    end=predictions.open_time.max().normalize()+pd.Timedelta(days=1)
    # End at the last observed exit price; never substitute cash for an unknown final return.
    end=min(end,bars.open_time.max())
    grid=pd.date_range(start,end-pd.Timedelta(minutes=5),freq='5min')
    price=bars.set_index('open_time').open
    entry=price.reindex(grid).to_numpy(float)
    exit_=price.reindex(grid+pd.Timedelta(minutes=5)).to_numpy(float)
    valid=np.isfinite(entry)&np.isfinite(exit_)
    if not valid.all():
        raise ValueError('internal price gap prevents complete position accounting')
    p=predictions.set_index('open_time').p_up.reindex(grid).to_numpy(float)
    w=np.where(p>=threshold,1,np.where(p<=1-threshold,-1,0))
    if long_only:
        w=np.maximum(w,0)
    w[~valid]=0
    # Fixed initial notional, full target notional each bar. Rebalance only net quantity changes.
    q=np.divide(w,entry,out=np.zeros(len(w)),where=np.isfinite(entry))
    traded=np.abs(q-np.r_[0,q[:-1]])*entry
    traded[-1]+=abs(q[-1])*exit_[-1]
    gross=np.where(valid,q*(exit_-entry),0)
    ff=np.zeros(len(grid))
    events=funding.loc[(funding.calc_time>=start)&(funding.calc_time<end)]
    ft=pd.DatetimeIndex(events.calc_time)
    ix=grid.searchsorted(ft,side='right')-1
    marks=price.reindex(ft.floor('5min')).to_numpy(float)
    if not np.isfinite(marks).all():
        raise ValueError('funding reference price missing')
    # At an exact rebalance/funding boundary use prior position; do not omit carried funding.
    exact=ft.isin(grid)
    qi=ix-exact.astype(int)
    fq=np.where(qi>=0,q[np.maximum(qi,0)],0)
    np.add.at(ff,ix,-fq*marks*events.last_funding_rate.to_numpy(float))
    total=(gross+ff).sum()
    turnovers=traded.sum()
    days=pd.DataFrame(dict(day=grid.normalize(),gross=gross,funding=ff,turnover=traded)).groupby('day').sum()
    rng=np.random.default_rng(93026)
    starts=rng.integers(0,len(days),(2000,int(np.ceil(len(days)/7))))
    bi=((starts[:,:,None]+np.arange(7))%len(days)).reshape(2000,-1)[:,:len(days)]
    gs=(days.gross+days.funding).to_numpy()[bi].sum(axis=1)
    ts=days.turnover.to_numpy()[bi].sum(axis=1)
    out=dict(threshold=threshold,long_only_perp_proxy=long_only,calendar_bars=len(grid),missing_prices=int((~valid).sum()),
             signal_missing_bars=int(np.isnan(p).sum()),gross_fixed_notional_return=float(gross.sum()),
             funding_fixed_notional_return=float(ff.sum()),
             equivalent_round_trips=float(turnovers/2),
             breakeven_round_trip_bps=float(total/(turnovers/2)*1e4),
             breakeven_round_trip_ci95_bps=np.quantile(gs/ts*2e4,[.025,.975]).tolist(),
             net_fixed_notional_return={str(c):float(total-turnovers*c/2e4) for c in [0,2,4,6,12]})
    return out


def run():
    result=[]
    old=pd.read_parquet(OLD/'predictions.parquet')
    later=pd.read_parquet(HERE/'later_baseline_predictions.parquet')
    bars=pd.concat([pd.read_parquet(OLD/'bars_5m.parquet'),pd.read_parquet(HERE/'later_data/bars.parquet')])
    funding=pd.concat([pd.read_parquet(DERIV/'funding_rate.parquet'),pd.read_parquet(HERE/'later_data/funding.parquet')])
    for name,p in [('2025',old.loc[old.split.eq('final_holdout')]),('2026_Jan_Aug',later)]:
        for threshold in [.5,.55]:
            for long_only in [False,True]:
                row=replay(p,bars,funding,threshold,long_only)
                row['period']=name
                result.append(row)
                print(json.dumps(row),flush=True)
    (HERE/'continuous_diagnostic.json').write_text(json.dumps(dict(
        status='Post-result diagnostic of execution netting, not a separately preregistered survivor.',rows=result),indent=2,allow_nan=False))


if __name__=='__main__':
    run()
