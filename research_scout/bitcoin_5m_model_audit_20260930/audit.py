"""Read-only source audit and explicitly diagnostic refits of the frozen BTC model."""
from __future__ import annotations

import hashlib
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit, logit
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from threadpoolctl import threadpool_limits

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREV = HERE.parent / 'bitcoin_5m_exchange_20260930'
OLD = ROOT / 'data/parquet/bitcoin_5m_probability_binance_v1'
DERIV = ROOT / 'data/parquet/binance_bitcoin_derivatives_public_v1/normalized'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PREV))
from research.bitcoin_5m_probability_model import (
    FEATURE_COLUMNS, CalibratedLogisticProbabilityModel, build_dataset,
    _validate_bars, _validate_metrics,
)
from all_decisions_diagnostic import all_decisions
from run import ledger, summary

F = list(FEATURE_COLUMNS)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def boot_means(frame, values):
    days = pd.date_range(frame.open_time.min().normalize(), frame.open_time.max().normalize(), freq='D')
    v = pd.DataFrame(values).assign(day=frame.open_time.dt.normalize().to_numpy())
    sums = v.groupby('day').sum().reindex(days, fill_value=0)
    count = v.groupby('day').size().reindex(days, fill_value=0).to_numpy()
    rng = np.random.default_rng(93027)
    starts = rng.integers(0, len(days), size=(2000, int(np.ceil(len(days)/7))))
    ix = ((starts[:, :, None] + np.arange(7)) % len(days)).reshape(2000, -1)[:, :len(days)]
    den = count[ix].sum(axis=1)
    out = {}
    for col in sums:
        a = sums[col].to_numpy()[ix].sum(axis=1) / np.maximum(den, 1)
        out[col] = dict(mean=float(v[col].mean()), ci95=np.quantile(a[den > 0], [.025, .975]).tolist())
    return out


def metrics(frame, p, prior):
    y = frame.label.to_numpy()
    conf = np.maximum(p, 1-p)
    selected = conf >= .55
    correct = ((p >= .5) == y).astype(float)
    scored = dict(rows=len(frame), up_rate=float(y.mean()), accuracy=float(correct.mean()),
                  brier=float(brier_score_loss(y, p)), log_loss=float(log_loss(y, p)),
                  auc=float(roc_auc_score(y, p)), confident_rows=int(selected.sum()),
                  confident_accuracy=float(correct[selected].mean()) if selected.any() else None,
                  mean_confident_claim=float(conf[selected].mean()) if selected.any() else None,
                  brier_skill_vs_training_prior=float(1-brier_score_loss(y,p)/np.mean((prior-y)**2)))
    scored['block_uncertainty'] = boot_means(frame, dict(
        accuracy_advantage_over_half=correct-.5,
        brier_improvement_over_prior=(prior-y)**2-(p-y)**2,
        brier_improvement_over_half=(.5-y)**2-(p-y)**2,
    ))
    scored['confident_uncertainty'] = boot_means(frame.loc[selected].reset_index(drop=True), dict(
        accuracy_advantage_over_half=correct[selected]-.5,
        realized_minus_claimed_confidence=correct[selected]-conf[selected],
    )) if selected.any() else None
    scored['probability_quantiles'] = dict(zip(['min','p01','p10','p50','p90','p99','max'],
        np.quantile(p,[0,.01,.1,.5,.9,.99,1]).tolist()))
    bins = pd.cut(p, [0,.4,.45,.48,.5,.52,.55,.6,1], include_lowest=True)
    table = pd.DataFrame(dict(bucket=bins, p=p, y=y, r=frame.bar_return.to_numpy()*1e4))
    scored['calibration_buckets'] = [dict(bucket=str(k), rows=len(g), mean_prediction=float(g.p.mean()),
        observed_up_rate=float(g.y.mean()), mean_return_bps=float(g.r.mean()))
        for k,g in table.groupby('bucket',observed=True)]
    slope = LogisticRegression(C=1e6, max_iter=1000).fit(logit(np.clip(p,1e-6,1-1e-6)).reshape(-1,1),y)
    scored['posthoc_reliability_fit'] = dict(intercept=float(slope.intercept_[0]), slope=float(slope.coef_[0,0]),
        interpretation='Diagnostic fitted on evaluation outcomes; not deployed; perfect reliability intercept0 slope1')
    return scored


def synthetic():
    n=430
    times=pd.date_range('2025-01-01',periods=n,freq='5min',tz='UTC')
    z=np.arange(n,dtype=float)
    op=100*np.exp(.0001*z)
    cl=op*(1+.0003*np.where(z%3==0,1,-1))
    b=pd.DataFrame(dict(open_time=times,open=op,close=cl,high=np.maximum(op,cl)*1.0002,
        low=np.minimum(op,cl)*.9998,volume=100+z,trade_count=20+z,taker_buy_base_volume=(100+z)*.52))
    m=pd.DataFrame(dict(create_time=times,sum_open_interest=10000+z,
        count_toptrader_long_short_ratio=1.1+z/10000,sum_toptrader_long_short_ratio=1.2+z/10000,
        count_long_short_ratio=1.3+z/10000,sum_taker_long_short_vol_ratio=.9+z/10000))
    return b,m


def robustness():
    b,m=synthetic()
    original=build_dataset(b,m).set_index('open_time')
    t=b.open_time.iloc[350]
    future=b.copy()
    future.loc[350:,['open','close','high','low','volume','trade_count','taker_buy_base_volume']]*=1.2
    altered=build_dataset(future,m).set_index('open_time')
    pd.testing.assert_frame_equal(original.loc[:t,F],altered.loc[:t,F])
    future_m=m.copy()
    future_m.loc[350:,m.columns.difference(['create_time'])]*=2
    altered_m=build_dataset(b,future_m).set_index('open_time')
    pd.testing.assert_frame_equal(original.loc[:t,F],altered_m.loc[:t,F])
    tied=b.copy()
    tied.loc[350,'close']=tied.loc[350,'open']
    tied_original=build_dataset(tied,m).set_index('open_time')
    causal_a=all_decisions(b,m).set_index('open_time')
    causal_b=all_decisions(tied,m).set_index('open_time')
    pd.testing.assert_series_equal(causal_a.loc[t,F],causal_b.loc[t,F])
    assert t in original.index and t not in tied_original.index and t in causal_b.index
    # Missing history is outside the twelve-bar guard but inside the 48/288-bar features.
    gap=build_dataset(b.drop(index=320),m.drop(index=320)).set_index('open_time')
    assert t in gap.index
    gap_delta=float(np.max(np.abs(original.loc[t,F].to_numpy()-gap.loc[t,F].to_numpy())))
    malformed={}
    bad=b.copy(); bad.loc[350,'high']=bad.loc[350,'low']*.5
    nan=b.copy(); nan.loc[350,'open']=np.nan
    inf=b.copy(); inf.loc[350,'close']=np.inf
    flow=b.copy(); flow.loc[350,'taker_buy_base_volume']=flow.loc[350,'volume']*2
    for name,a in [('high_below_low',bad),('nan_price',nan),('infinite_price',inf),('taker_volume_exceeds_total',flow)]:
        try:
            _validate_bars(a)
            malformed[name]='ACCEPTED'
        except ValueError:
            malformed[name]='REJECTED'
    return dict(price_feature_future_perturbation='PASS',metric_future_perturbation='PASS',
        tie_filter_future_dependency='CONFIRMED',causal_tie_feature_invariance='PASS',
        accepted_row_with_gap_in_long_lookback=True,long_lookback_feature_max_change=gap_delta,
        malformed_bar_validator=malformed)


def quality(b,m,full,original):
    numeric=['open','high','low','close','volume','trade_count','taker_buy_base_volume']
    finite=np.isfinite(b[numeric].to_numpy()).all(axis=1)
    inconsistent=(b.high<b[['open','close','low']].max(axis=1)) | (b.low>b[['open','close','high']].min(axis=1))
    flow=(b.taker_buy_base_volume<0)|(b.taker_buy_base_volume>b.volume)
    # Row-count-based lookbacks can silently span a clock gap; quantify actual exposure.
    contiguous=b.open_time.diff().eq(pd.Timedelta(minutes=5))
    good288=contiguous.rolling(288,min_periods=288).sum().eq(288)
    bytime=pd.Series(good288.to_numpy(),index=b.open_time)
    joins=pd.merge_asof(pd.DataFrame(dict(open_time=b.open_time,cutoff=b.open_time-pd.Timedelta(minutes=5))),
                        m,left_on='cutoff',right_on='create_time',direction='backward',tolerance=pd.Timedelta(minutes=10))
    age=(joins.open_time-joins.create_time).dt.total_seconds()/60
    selected_age=pd.Series(age.to_numpy(),index=joins.open_time).loc[full.open_time]
    coverage=[]
    for year,g in b.groupby(b.open_time.dt.year):
        a=full.loc[full.open_time.dt.year.eq(year)]
        o=original.loc[original.open_time.dt.year.eq(year)]
        coverage.append(dict(year=int(year),bars=len(g),causal_decisions=len(a),non_tie_panel=len(o),
            coverage=float(len(a)/len(g)),ties=int(g.open.eq(g.close).sum()),
            oldest_available_metric_minutes=float(age.loc[g.index].max()) if age.loc[g.index].notna().any() else None))
    metric_numeric=m.columns.difference(['create_time','symbol'])
    return dict(price_rows=len(b),metric_rows=len(m),nonfinite_price_rows=int((~finite).sum()),
        inconsistent_ohlc_rows=int(inconsistent.sum()),invalid_taker_volume_rows=int(flow.sum()),
        missing_grid_transitions=int((b.open_time.diff().dropna()!=pd.Timedelta(minutes=5)).sum()),
        nonfinite_metric_cells=int((~np.isfinite(m[metric_numeric].select_dtypes('number').to_numpy())).sum()),
        causal_eligible_rows_with_noncontinuous_288_history=int((~bytime.loc[full.open_time].to_numpy()).sum()),
        metric_age_on_eligible_minutes=dict(min=float(selected_age.min()),max=float(selected_age.max())),
        coverage=coverage)


def eval_economics(frame,p,bars,funding):
    return summary(ledger(frame,bars,funding,p,.55,1,'probability'),frame,ci=True)


def run():
    dest=HERE/'results.json'
    if dest.exists():
        raise FileExistsError('Audit results already exist; preserve them and use a new versioned directory')
    source=[ROOT/'research/bitcoin_5m_probability_model.py',ROOT/'research_scout/bitcoin_5m_probability_binance_v1.json',
            OLD/'model.pkl',OLD/'panel.parquet',OLD/'predictions.parquet',OLD/'report.json',OLD/'bars_5m.parquet',
            DERIV/'futures_metrics_5m.parquet',PREV/'later_data/bars.parquet',PREV/'later_data/metrics.parquet',
            PREV/'all_decisions_diagnostic.json',PREV/'results.json']
    hashes={str(p.relative_to(ROOT)):sha(p) for p in source}
    print('Loading source artifacts and rebuilding full causal panel',flush=True)
    b=pd.concat([pd.read_parquet(OLD/'bars_5m.parquet'),pd.read_parquet(PREV/'later_data/bars.parquet')],ignore_index=True)
    m=pd.concat([pd.read_parquet(DERIV/'futures_metrics_5m.parquet'),pd.read_parquet(PREV/'later_data/metrics.parquet')],ignore_index=True)
    b=_validate_bars(b);m=_validate_metrics(m)
    full=all_decisions(b,m)
    original=pd.read_parquet(OLD/'panel.parquet')
    matched=full.set_index('open_time').loc[original.open_time,F]
    np.testing.assert_allclose(matched.to_numpy(),original[F].to_numpy(),rtol=0,atol=1e-12)
    with (OLD/'model.pkl').open('rb') as h:
        model=pickle.load(h)
    saved=pd.read_parquet(OLD/'predictions.parquet').set_index('open_time')
    reproduction=float(np.max(np.abs(model.predict_proba(original)-saved.loc[original.open_time,'p_up'].to_numpy())))
    assert reproduction<1e-10
    scaler=model.base.named_steps['scale']
    clf=model.base.named_steps['logistic']
    prior=float(original.loc[original.open_time<'2023-07-01','label'].mean())
    coeff=[dict(feature=c,standardized_base_coefficient=float(w),
        calibrated_logit_coefficient=float(w*model.calibrator.coef_[0,0])) for c,w in zip(F,clf.coef_[0])]
    coeff.sort(key=lambda x:abs(x['calibrated_logit_coefficient']),reverse=True)
    train=original.loc[original.open_time<'2023-07-01',F]
    corr=train.corr()
    pairs=[dict(a=F[i],b=F[j],correlation=float(corr.iloc[i,j])) for i in range(len(F)) for j in range(i)
           if abs(corr.iloc[i,j])>=.8]
    groups=dict(price_returns_and_shape=F[:6],volume_and_trade_activity=F[6:8],taker_flow=F[8:10],
                open_interest=F[10:12],positioning_ratios=F[12:])
    report=dict(spec=json.loads((HERE/'spec.json').read_text()),source_sha256_before=hashes,
        reproduction=dict(feature_max_absolute_error=float(np.max(np.abs(matched.to_numpy()-original[F].to_numpy()))),
                          probability_max_absolute_error=reproduction),
        code_robustness=robustness(),data_quality=quality(b,m,full,original),
        architecture=dict(calibrator_slope=float(model.calibrator.coef_[0,0]),calibrator_intercept=float(model.calibrator.intercept_[0]),
            base_intercept=float(clf.intercept_[0]),fit_iterations=clf.n_iter_.tolist(),
            coefficients=coeff,high_feature_correlations=pairs,
            scaler_training_mean_max_difference=float(np.max(np.abs(train.mean().to_numpy()-scaler.mean_)))) ,
        periods={},refit_diagnostics=[])
    funding=pd.concat([pd.read_parquet(DERIV/'funding_rate.parquet'),pd.read_parquet(PREV/'later_data/funding.parquet')],ignore_index=True)
    for year in [2024,2025,2026]:
        print(f'Auditing original model, {year}',flush=True)
        # Direction scoring excludes ties explicitly; deployment and economics include them.
        allf=full.loc[full.open_time.dt.year.eq(year)].reset_index(drop=True)
        non_tie=allf.loc[allf.open!=allf.close].reset_index(drop=True)
        p=model.predict_proba(non_tie)
        raw=model.base.predict_proba(non_tie[F])[:,1]
        ap=model.predict_proba(allf)
        out=dict(calibrated=metrics(non_tie,p,prior),raw=metrics(non_tie,raw,prior),
                 economics_all_causal_decisions=eval_economics(allf,ap,b,funding),
                 causal_rows=len(allf),ties=int(allf.open.eq(allf.close).sum()),monthly=[],sensitivity=[])
        for month,g in non_tie.assign(p=p).groupby(non_tie.open_time.dt.strftime('%Y-%m')):
            conf=np.maximum(g.p,1-g.p)>=.55
            out['monthly'].append(dict(month=month,rows=len(g),accuracy=float(((g.p>=.5)==g.label).mean()),
                brier_improvement_over_half=float(np.mean(.25-(g.p-g.label)**2)),confident_rows=int(conf.sum()),
                confident_accuracy=float(((g.loc[conf,'p']>=.5)==g.loc[conf,'label']).mean()) if conf.any() else None))
        for name,cols in groups.items():
            a=non_tie.copy()
            for c in cols:
                a[c]=scaler.mean_[F.index(c)]
            v=model.predict_proba(a)
            out['sensitivity'].append(dict(group=name,brier=float(brier_score_loss(a.label,v)),
                brier_change=float(brier_score_loss(a.label,v)-brier_score_loss(non_tie.label,p)),
                accuracy=float(((v>=.5)==a.label).mean())))
        std=scaler.transform(non_tie[F])
        out['feature_drift']=[dict(feature=c,mean_training_sd=float(std[:,i].mean()),
            std_ratio=float(std[:,i].std()),fraction_beyond_5_training_sd=float((np.abs(std[:,i])>5).mean())) for i,c in enumerate(F)]
        report['periods'][str(year)]=out
    for year,train_end,cal_start,cal_end in [(2025,'2024-07-01','2024-07-01','2025-01-01'),
                                         (2026,'2025-07-01','2025-07-01','2026-01-01')]:
        print(f'Diagnostic refit with unchanged architecture, evaluate {year}',flush=True)
        nontie=full.loc[full.open!=full.close]
        tr=nontie.loc[nontie.open_time<train_end].reset_index(drop=True)
        cal=nontie.loc[(nontie.open_time>=cal_start)&(nontie.open_time<cal_end)].reset_index(drop=True)
        fitted=CalibratedLogisticProbabilityModel(C=.1,random_state=42).fit(tr,cal)
        allf=full.loc[full.open_time.dt.year.eq(year)].reset_index(drop=True)
        ev=allf.loc[allf.open!=allf.close].reset_index(drop=True)
        p=fitted.predict_proba(ev)
        result=dict(year=year,training_rows=len(tr),calibration_rows=len(cal),
            training_last=tr.open_time.max().isoformat(),calibration_first=cal.open_time.min().isoformat(),
            calibration_last=cal.open_time.max().isoformat(),evaluation_first=allf.open_time.min().isoformat(),
            calibration_slope=float(fitted.calibrator.coef_[0,0]),metrics=metrics(ev,p,float(tr.label.mean())),
            economics=eval_economics(allf,fitted.predict_proba(allf),b,funding))
        report['refit_diagnostics'].append(result)
    after={str(p.relative_to(ROOT)):sha(p) for p in source}
    assert hashes==after
    report['source_preservation']='PASS all original and prior experiment input hashes unchanged'
    dest.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='COMPLETE',robustness=report['code_robustness'],data_quality=report['data_quality'],
        architecture=report['architecture'],periods={k:dict(accuracy=v['calibrated']['accuracy'],
        brier_skill=v['calibrated']['brier_skill_vs_training_prior'],brier_ci=v['calibrated']['block_uncertainty'],
        confidence_gap=v['calibrated']['confident_uncertainty'],raw_brier=v['raw']['brier'],cal_brier=v['calibrated']['brier'],
        economics=v['economics_all_causal_decisions']['net_bps']) for k,v in report['periods'].items()},
        refits=[dict(year=x['year'],accuracy=x['metrics']['accuracy'],brier=x['metrics']['brier'],
        gross=x['economics']['gross_bps'],net4=x['economics']['net_bps']['4']) for x in report['refit_diagnostics']])),flush=True)


if __name__=='__main__':
    with threadpool_limits(limits=4):
        run()
