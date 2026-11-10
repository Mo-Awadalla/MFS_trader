"""Bounded, chronological BTC model and exchange-cost diagnostic. No orders."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.bitcoin_5m_probability_model import FEATURE_COLUMNS, build_dataset

OUT = Path(__file__).resolve().parent
OLD = ROOT / 'data/parquet/bitcoin_5m_probability_binance_v1'
DERIV = ROOT / 'data/parquet/binance_bitcoin_derivatives_public_v1/normalized'
COSTS = [0, 2, 4, 6, 12, 24, 50]
PARAMS = dict(max_iter=120, max_leaf_nodes=15, max_depth=4, learning_rate=0.05,
              l2_regularization=10, min_samples_leaf=300, random_state=93026,
              early_stopping=False)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def enhanced_features(bars):
    b = bars.sort_values('open_time').set_index('open_time')
    r = np.log(b.close).diff()
    f = pd.DataFrame(index=b.index)
    for n in (12, 48, 288):
        f[f'vol_{n}'] = r.rolling(n, min_periods=n).std().shift(1)
        f[f'scaled_return_{n}'] = np.log(b.close).diff(n).shift(1) / (
            f[f'vol_{n}'] * np.sqrt(n)).replace(0, np.nan)
    f['flow_return_interaction'] = ((2*b.taker_buy_base_volume/b.volume.replace(0,np.nan)-1)*r).shift(1)
    f['body_range_ratio'] = ((b.close-b.open)/(b.high-b.low).replace(0,np.nan)).shift(1)
    for clock, period in [('minute',1440), ('weekday',7)]:
        x = b.index.hour*60+b.index.minute if clock == 'minute' else b.index.dayofweek
        f[f'{clock}_sin'] = np.sin(2*np.pi*x/period)
        f[f'{clock}_cos'] = np.cos(2*np.pi*x/period)
    f.index = pd.to_datetime(f.index, utc=True)
    return f


def target_prices(panel, bars, h, delay=0):
    idx = pd.DatetimeIndex(pd.to_datetime(panel.open_time, utc=True))
    price = bars.set_index('open_time').open
    entry_t = idx + pd.Timedelta(minutes=5*delay)
    exit_t = idx + pd.Timedelta(minutes=5*(delay+h))
    entry = price.reindex(entry_t).to_numpy(float)
    exit_ = price.reindex(exit_t).to_numpy(float)
    # Never allow a position to bridge a missing full-grid price observation.
    valid = np.ones(len(idx), dtype=bool)
    for k in range(delay+h+1):
        valid &= price.reindex(idx+pd.Timedelta(minutes=5*k)).notna().to_numpy()
    return entry_t, exit_t, entry, exit_, valid


def ledger(panel, bars, funding, values, threshold, h, kind, delay=0, long_only=False):
    values = np.asarray(values)
    if kind == 'probability':
        signals = np.where(values>=threshold, 1, np.where(values<=1-threshold,-1,0))
    else:
        signals = np.where(values>=threshold/1e4,1,np.where(values<=-threshold/1e4,-1,0))
    if long_only:
        signals = np.maximum(signals,0)
    et, xt, entry, exit_, valid = target_prices(panel,bars,h,delay)
    # Entries require strictly earlier signal features; delay=0 is an optimistic reference.
    end = panel.open_time.max().normalize()+pd.Timedelta(days=1)
    valid &= xt < end
    funding=funding.loc[(funding.calc_time>=bars.open_time.min()) &
                        (funding.calc_time<=bars.open_time.max())]
    ft=pd.DatetimeIndex(funding.calc_time)
    fr=funding.last_funding_rate.to_numpy(float)
    mark=bars.set_index('open_time').open.reindex(ft.floor('5min')).to_numpy(float)
    if not np.isfinite(mark).all():
        raise ValueError('missing settlement price reference')
    selected=[]
    next_free_ns=np.iinfo(np.int64).min
    en=et.as_unit('ns').asi8
    ex=xt.as_unit('ns').asi8
    for i in np.flatnonzero((signals!=0)&valid):
        if en[i]>=next_free_ns:
            selected.append(i)
            next_free_ns=ex[i]
    ix=np.asarray(selected,dtype=int)
    if not len(ix):
        return pd.DataFrame()
    a=ft.searchsorted(et[ix],side='right')
    z=ft.searchsorted(xt[ix],side='left')
    cum=np.r_[0,np.cumsum(fr*mark)]
    fc=-signals[ix]*(cum[z]-cum[a])/entry[ix]
    gross=signals[ix]*(exit_[ix]/entry[ix]-1)
    fee_factor=(1+exit_[ix]/entry[ix])/2
    return pd.DataFrame(dict(decision_time=panel.open_time.iloc[ix].to_numpy(),entry_time=et[ix],exit_time=xt[ix],
                           direction=signals[ix],entry_price=entry[ix],exit_price=exit_[ix],
                           gross_return=gross,funding_return=fc,fee_factor=fee_factor,
                           gross_bps=gross*1e4,net_12bps=gross+fc-.0012*fee_factor))


def summary(trades, panel, ci=False):
    if trades.empty:
        return dict(trades=0,days=0,gross_bps=None,funding_bps=None,net_bps={str(c):None for c in COSTS})
    g=trades.gross_return.to_numpy()
    f=trades.funding_return.to_numpy()
    ff=trades.fee_factor.to_numpy()
    days=pd.date_range(panel.open_time.min().normalize(),panel.open_time.max().normalize(),freq='D')
    daily=trades.assign(day=trades.exit_time.dt.normalize()).groupby('day').agg(
        gross=('gross_return','sum'),funding=('funding_return','sum'),fee=('fee_factor','sum'),count=('gross_return','size'))
    daily=daily.reindex(days,fill_value=0)
    net=daily.gross+daily.funding-.0012*daily.fee
    cumul=net.cumsum()
    dd=cumul-np.maximum.accumulate(np.r_[0,cumul.to_numpy()])[1:]
    result=dict(trades=len(trades),days=int((daily['count']>0).sum()),calendar_days=len(days),
                gross_bps=float(g.mean()*1e4),funding_bps=float(f.mean()*1e4),
                breakeven_round_trip_bps=float((g+f).sum()/ff.sum()*1e4),
                win_rate=float((g>0).mean()),mean_win_bps=float(g[g>0].mean()*1e4) if (g>0).any() else None,
                mean_loss_bps=float(g[g<=0].mean()*1e4) if (g<=0).any() else None,
                net_bps={str(c):float(np.mean(g+f-c/1e4*ff)*1e4) for c in COSTS},
                fixed_initial_notional_total_return_12bps=float(net.sum()),
                fixed_initial_notional_drawdown_12bps=float(dd.min()),
                annualized_daily_sharpe_12bps=float(net.mean()/net.std(ddof=1)*np.sqrt(365)) if net.std()>0 else None,
                halves_12bps={str(k):float(v.net_12bps.mean()*1e4) for k,v in trades.groupby(trades.entry_time.dt.month.le(6))},
                months_12bps={str(k):float(v.net_12bps.mean()*1e4) for k,v in trades.groupby(trades.entry_time.dt.strftime('%Y-%m'))})
    if ci:
        rng=np.random.default_rng(93026)
        starts=rng.integers(0,len(days),size=(2000,int(np.ceil(len(days)/7))))
        ix=((starts[:,:,None]+np.arange(7))%len(days)).reshape(2000,-1)[:,:len(days)]
        sums=(daily.gross+daily.funding).to_numpy()[ix].sum(axis=1)
        fees=daily.fee.to_numpy()[ix].sum(axis=1)
        count=daily['count'].to_numpy()[ix].sum(axis=1)
        ok=count>0
        gross=sums[ok]/count[ok]*1e4
        result['gross_plus_funding_ci95_bps']=np.quantile(gross,[.025,.975]).tolist()
        result['net_12bps_ci95_bps']=np.quantile((sums[ok]-.0012*fees[ok])/count[ok]*1e4,[.025,.975]).tolist()
        result['net_12bps_adjusted_lower_bps']=float(np.quantile((sums[ok]-.0012*fees[ok])/count[ok]*1e4,.05/9))
        result['net_2bps_ci95_bps']=np.quantile((sums[ok]-.0002*fees[ok])/count[ok]*1e4,[.025,.975]).tolist()
    return result


def baseline(predictions, bars, funding):
    out=[]
    for split in ['internal_validation','final_holdout']:
        p=predictions.loc[predictions.split.eq(split)].reset_index(drop=True)
        for threshold in [.5,.55]:
            for delay in [0,1]:
                print(f'Baseline {split} threshold={threshold} delay={delay}',flush=True)
                trades=ledger(p,bars,funding,p.p_up,threshold,1,'probability',delay)
                rec=summary(trades,p,ci=True)
                rec.update(split=split,threshold=threshold,delay_bars=delay)
                trades.to_parquet(OUT/f'baseline_{split}_{threshold}_{delay}.parquet',index=False)
                out.append(rec)
    return out


def run():
    report_path=OUT/'results.json'
    if report_path.exists():
        raise FileExistsError('immutable result exists; choose a separately versioned directory')
    spec=json.loads((OUT/'spec.json').read_text())
    bars=pd.read_parquet(OLD/'bars_5m.parquet').sort_values('open_time').reset_index(drop=True)
    funding=pd.read_parquet(DERIV/'funding_rate.parquet')
    predictions=pd.read_parquet(OLD/'predictions.parquet')
    panel=pd.read_parquet(OLD/'panel.parquet')
    enriched=panel.merge(enhanced_features(bars).reset_index(),on='open_time',how='left')
    extra=[c for c in enriched if c not in panel.columns]
    features=list(FEATURE_COLUMNS)+extra
    enriched=enriched.replace([np.inf,-np.inf],np.nan).dropna(subset=features).reset_index(drop=True)
    results=dict(spec=spec,spec_sha256=sha(OUT/'spec.json'),
                 input_sha256={str(p.relative_to(ROOT)):sha(p) for p in
                    [OLD/'bars_5m.parquet',OLD/'panel.parquet',OLD/'predictions.parquet',OLD/'model.pkl',DERIV/'funding_rate.parquet']},
                 baseline=baseline(predictions,bars,funding),candidates=[])
    (OUT/'baseline.json').write_text(json.dumps(results['baseline'],indent=2))
    print('Frozen baseline economics saved.',flush=True)
    for h in spec['horizons_bars']:
        _,xt,entry,exit_,valid=target_prices(enriched,bars,h)
        data=enriched.loc[valid].copy()
        data['target']= (exit_/entry-1)[valid]
        data['target_end']=xt[valid]
        train=data.loc[(data.open_time>='2021-07-01')&(data.target_end<'2023-07-01')]
        cal=data.loc[(data.open_time>='2023-07-01')&(data.target_end<'2024-01-01')]
        selection=data.loc[(data.open_time>='2024-01-01')&(data.target_end<'2025-01-01')].reset_index(drop=True)
        test=data.loc[(data.open_time>='2025-01-01')&(data.target_end<'2026-01-01')].reset_index(drop=True)
        for name in ['recent_logistic','nonlinear_direction','nonlinear_return']:
            cols=list(FEATURE_COLUMNS) if name=='recent_logistic' else features
            if name=='recent_logistic':
                model=make_pipeline(StandardScaler(),LogisticRegression(C=.1,max_iter=1000,random_state=93026))
            elif name=='nonlinear_direction':
                model=HistGradientBoostingClassifier(**PARAMS)
            else:
                model=HistGradientBoostingRegressor(loss='squared_error',**PARAMS)
            isprob=name!='nonlinear_return'
            yt=(train.target>0).astype(int) if isprob else train.target.clip(*train.target.quantile([.005,.995]))
            with threadpool_limits(limits=4):
                model.fit(train[cols],yt)
                if isprob:
                    def raw(frame):
                        p=np.clip(model.predict_proba(frame[cols])[:,1],1e-6,1-1e-6)
                        return np.log(p/(1-p)).reshape(-1,1)
                    calibrator=LogisticRegression(C=1,max_iter=1000).fit(raw(cal),(cal.target>0).astype(int))
                    pv=calibrator.predict_proba(raw(selection))[:,1]
                    pt=calibrator.predict_proba(raw(test))[:,1]
                else:
                    calibrator=LinearRegression().fit(model.predict(cal[cols]).reshape(-1,1),cal.target)
                    pv=calibrator.predict(model.predict(selection[cols]).reshape(-1,1))
                    pt=calibrator.predict(model.predict(test[cols]).reshape(-1,1))
            thresholds=spec['thresholds']['probability' if isprob else 'predicted_return_bps']
            kind='probability' if isprob else 'return'
            choices=[]
            for threshold in thresholds:
                tr=ledger(selection,bars,funding,pv,threshold,h,kind)
                sm=summary(tr,selection)
                sm.update(threshold=threshold)
                choices.append(sm)
            eligible=[c for c in choices if c['trades']>=500]
            # Selection uses only 2024. Diagnostic comparison retained even if admission fails.
            chosen=max(eligible,key=lambda c:c['net_bps']['12']) if eligible else choices[0]
            threshold=chosen['threshold']
            tr=ledger(test,bars,funding,pt,threshold,h,kind)
            te=summary(tr,test,ci=True)
            delay=summary(ledger(test,bars,funding,pt,threshold,h,kind,delay=1),test)
            long=summary(ledger(test,bars,funding,pt,threshold,h,kind,long_only=True),test)
            gate=chosen['trades']>=500 and chosen['net_bps']['12']>0
            passed= bool(gate and te['trades']>=500 and te['net_12bps_adjusted_lower_bps']>0
                         and all(v>0 for v in te['halves_12bps'].values()) and delay['net_bps']['12']>0)
            row=dict(model=name,horizon_minutes=h*5,threshold=threshold,selection_choices=choices,
                     development_admitted=gate,diagnostic_test=te,delayed_test=delay,long_only_perp_proxy=long,
                     gate_passed=passed,rows=dict(train=len(train),calibration=len(cal),selection=len(selection),test=len(test)))
            if isprob:
                row['test_prediction_metrics']=dict(accuracy=float(((pt>=.5)==(test.target>0)).mean()),
                    brier=float(brier_score_loss((test.target>0).astype(int),pt)),
                    auc=float(roc_auc_score((test.target>0).astype(int),pt)))
            else:
                row['test_prediction_metrics']=dict(return_correlation=float(np.corrcoef(pt,test.target)[0,1]),
                    predicted_return_min_bps=float(pt.min()*1e4),predicted_return_max_bps=float(pt.max()*1e4))
            results['candidates'].append(row)
            pd.DataFrame(dict(open_time=test.open_time,prediction=pt,target=test.target)).to_parquet(OUT/f'{name}_{h}_predictions.parquet',index=False)
            tr.to_parquet(OUT/f'{name}_{h}_trades.parquet',index=False)
            print(json.dumps(dict(model=name,horizon=h*5,threshold=threshold,selection_net12=chosen['net_bps']['12'],
                    test_trades=te['trades'],test_gross=te['gross_bps'],test_net2=te['net_bps']['2'],passed=passed)),flush=True)
    results['verdict']='SURVIVOR_REQUIRES_EXECUTABLE_CONFIRMATION' if any(x['gate_passed'] for x in results['candidates']) else 'NO_VALIDATED_PROFITABLE_EXCHANGE_STRATEGY'
    results['limitations']=[
        'Binance bar references are not executable quotes or Coinbase contract prices. A failing cheap reference scenario is evidence against this signal, not a backtest on every exchange.',
        'Historical data were already exposed. No retrospective result constitutes independent prospective confirmation.',
        'Funding uses settlement rates and Binance trade-price reference rather than historical mark prices; exact boundary events excluded under reference convention.',
        'Fixed-initial-notional P&L may fall below -100% in stress; that means insolvency/stop before full replay. It is not a feasible compound account return.',
        'No liquidity, queue, maker fills, market impact or liquidation simulation. Zero-fee rows are mathematical sensitivity only.',
        'Selection thresholds and horizon comparisons are nine model/horizon trials, each with three 2024 thresholds; Bonferroni interval is a diagnostic family correction, not correction for the repository entire research history.'
    ]
    report_path.write_text(json.dumps(results,indent=2,allow_nan=False)+'\n')
    print(results['verdict'],flush=True)


if __name__=='__main__':
    run()
