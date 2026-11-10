"""Causal deployment check: predict tied outcome bars too, preserving the frozen model."""
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from run import OLD,DERIV,ledger,summary
from continuous_diagnostic import replay
from research.bitcoin_5m_probability_model import FEATURE_COLUMNS,build_dataset,_validate_bars,_validate_metrics,_zscore


def all_decisions(bars,metrics):
    b=_validate_bars(bars)
    m=_validate_metrics(metrics)
    close=b.close
    flow=2*b.taker_buy_base_volume/b.volume.replace(0,np.nan)-1
    f=pd.DataFrame()
    for n in [1,3,6,12]:
        f[f'log_return_{n}_bar' if n==1 else f'log_return_{n}_bars']=np.log(close).diff(n).shift(1)
    f['log_range_1_bar']=np.log(b.high/b.low).shift(1)
    f['log_body_1_bar']=np.log(b.close/b.open).shift(1)
    f['volume_zscore_288_bars']=_zscore(np.log1p(b.volume).shift(1),288)
    f['trade_count_zscore_288_bars']=_zscore(np.log1p(b.trade_count).shift(1),288)
    f['taker_flow_1_bar']=flow.shift(1)
    f['taker_flow_3_bar_mean']=flow.rolling(3,min_periods=3).mean().shift(1)
    left=pd.DataFrame(dict(open_time=b.open_time,metric_cutoff=b.open_time-pd.Timedelta(minutes=5)))
    j=pd.merge_asof(left,m,left_on='metric_cutoff',right_on='create_time',direction='backward',tolerance=pd.Timedelta(minutes=10))
    oi=j.sum_open_interest.where(j.sum_open_interest>0)
    for n in [12,48]:
        f[f'open_interest_log_change_{n}_bars']=np.log(oi).diff(n)
    for name,src in [('top_trader_long_short_log_ratio','count_toptrader_long_short_ratio'),
                     ('global_long_short_log_ratio','count_long_short_ratio'),
                     ('taker_long_short_log_ratio','sum_taker_long_short_vol_ratio')]:
        f[name]=np.log(j[src].where(j[src]>0))
    continuous=b.open_time.diff().eq(pd.Timedelta(minutes=5)).rolling(12,min_periods=12).sum().eq(12)
    available=(j.open_time-j.create_time).le(pd.Timedelta(minutes=10))
    finite=f[list(FEATURE_COLUMNS)].replace([np.inf,-np.inf],np.nan).notna().all(axis=1)
    selected=continuous & available & finite
    result=pd.concat([b[['open_time','open','close']],f],axis=1).loc[selected].reset_index(drop=True)
    result['label']=(result.close>result.open).astype(int)
    result['bar_return']=result.close/result.open-1
    return result


def run():
    old_b=pd.read_parquet(OLD/'bars_5m.parquet')
    old_m=pd.read_parquet(DERIV/'futures_metrics_5m.parquet')
    warm=pd.Timestamp('2025-11-01',tz='UTC')
    bars=pd.concat([old_b.loc[old_b.open_time>=warm],pd.read_parquet(HERE/'later_data/bars.parquet')])
    metrics=pd.concat([old_m.loc[old_m.create_time>=warm],pd.read_parquet(HERE/'later_data/metrics.parquet')])
    full=all_decisions(bars,metrics)
    original=build_dataset(bars,metrics)
    matched=full.set_index('open_time').loc[original.open_time,list(FEATURE_COLUMNS)]
    np.testing.assert_allclose(matched.to_numpy(),original[list(FEATURE_COLUMNS)].to_numpy(),rtol=0,atol=1e-12)
    full=full.loc[full.open_time>='2026-01-01'].reset_index(drop=True)
    with (OLD/'model.pkl').open('rb') as handle:
        model=pickle.load(handle)
    full['p_up']=model.predict_proba(full)
    funding=pd.read_parquet(HERE/'later_data/funding.parquet')
    rows=[]
    for threshold in [.5,.55]:
        for delay in [0,1]:
            tr=ledger(full,bars,funding,full.p_up,threshold,1,'probability',delay)
            row=summary(tr,full,ci=True)
            row.update(threshold=threshold,delay_bars=delay)
            rows.append(row)
    full.to_parquet(HERE/'later_all_decisions_predictions.parquet',index=False)
    carried=[replay(full,bars,funding,t,long_only=l) for t in [.5,.55] for l in [False,True]]
    result=dict(status='Diagnostic repairs realized-outcome tie exclusion in original scoring panel; model and decision thresholds unchanged.',
                rows=len(full),ties=int(full.open.eq(full.close).sum()),feature_replication='PASS <=1e-12 absolute error',
                fixed_horizon=rows,continuous=carried)
    (HERE/'all_decisions_diagnostic.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps(dict(rows=len(full),ties=result['ties'],economics=[dict(threshold=x['threshold'],delay=x['delay_bars'],
                     trades=x['trades'],gross_bps=x['gross_bps'],net4=x['net_bps']['4']) for x in rows],
                     continuous=[dict(threshold=x['threshold'],long_only=x['long_only_perp_proxy'],breakeven=x['breakeven_round_trip_bps']) for x in carried])),flush=True)


if __name__=='__main__':
    run()
