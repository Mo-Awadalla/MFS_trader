"""Run the fixed quarterly BTC model v2 repair diagnostic; no order capability."""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.bitcoin_5m_exchange_model import (
    PayoffAwareBitcoinModel, actionable_signals, attach_targets, build_decisions,
    chronological_partition, fit_windows, propose_trades,
)
from research.bitcoin_5m_exchange_validation import assess_admission, replay_trades, summarize_trades

DEFAULT_OUTPUT=ROOT/'research_scout/bitcoin_5m_repaired_v2_20260930'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(output: Path, spec_path: Path) -> dict:
    spec=json.loads(spec_path.read_text())
    if spec['specification_id']!='Bitcoin-5m-PayoffAware-v2-20260930':
        raise ValueError('this runner implements only the declared v2 specification')
    output.mkdir(parents=True,exist_ok=True)
    # Reserve the entire run before any result write; incomplete attempts also stay reviewable.
    reservation=output/'run_started.json'
    with reservation.open('x',encoding='utf-8') as h:
        json.dump(dict(spec_sha256=sha(spec_path),status='reserved; results.json appears only on completion'),h)
    old=ROOT/'data/parquet/bitcoin_5m_probability_binance_v1'
    deriv=ROOT/'data/parquet/binance_bitcoin_derivatives_public_v1/normalized'
    later=ROOT/'research_scout/bitcoin_5m_exchange_20260930/later_data'
    sources=[old/'bars_5m.parquet',deriv/'futures_metrics_5m.parquet',deriv/'funding_rate.parquet',
        later/'bars.parquet',later/'metrics.parquet',later/'funding.parquet',old/'model.pkl',old/'panel.parquet',
        old/'predictions.parquet',ROOT/'research/bitcoin_5m_probability_model.py',
        ROOT/'research_scout/bitcoin_5m_model_audit_20260930/results.json',
        ROOT/'research_scout/bitcoin_5m_exchange_20260930/results.json']
    hashes={str(p.relative_to(ROOT)):sha(p) for p in sources}
    bars=pd.concat([pd.read_parquet(old/'bars_5m.parquet'),pd.read_parquet(later/'bars.parquet')],ignore_index=True)
    metrics=pd.concat([pd.read_parquet(deriv/'futures_metrics_5m.parquet'),pd.read_parquet(later/'metrics.parquet')],ignore_index=True)
    funding=pd.concat([pd.read_parquet(deriv/'funding_rate.parquet'),pd.read_parquet(later/'funding.parquet')],ignore_index=True)
    print('Building repaired causal panel; retaining all outcomes and optional OI',flush=True)
    panel=attach_targets(build_decisions(bars,metrics),bars)
    panel.to_parquet(output/'panel.parquet',index=False)
    coverage=[dict(year=int(year),source_price_bars=len(g),decisions=int(panel.open_time.dt.year.eq(year).sum()),
                   labeled_rows=int((panel.open_time.dt.year.eq(year)&panel.target_return.notna()).sum()))
              for year,g in bars.groupby(bars.open_time.dt.year)]
    start=pd.Timestamp('2024-01-01',tz='UTC');end=pd.Timestamp('2026-09-01',tz='UTC')
    updates=pd.date_range(start,end,freq='QS',inclusive='left')
    folds=[];prediction_frames=[];shadow_frames=[];admitted_frames=[];delayed_frames=[]
    for update in updates:
        fold_end=min(update+pd.DateOffset(months=3),end)
        print(f'Quarterly update {update.date()}; training/calibration/admission partitions isolated',flush=True)
        w=fit_windows(update)
        training=chronological_partition(panel,w.training_start,w.calibration_start)
        calibration=chronological_partition(panel,w.calibration_start,w.admission_start)
        gate=panel.loc[(panel.open_time>=w.admission_start)&(panel.open_time<update)].reset_index(drop=True)
        evaluation=panel.loc[(panel.open_time>=update)&(panel.open_time<fold_end)].reset_index(drop=True)
        if len(training)<5000 or len(calibration)<1000 or evaluation.empty:
            raise ValueError('insufficient declared fit/evaluation data')
        model=PayoffAwareBitcoinModel().fit(training,calibration)
        gate_p=model.predict(gate)
        gate_trades=replay_trades(gate_p,bars,funding,propose_trades(gate_p),end_exclusive=update)
        gate_stats=summarize_trades(gate_trades,w.admission_start,update)
        admission=assess_admission(gate_stats)
        pred=model.predict(evaluation)
        pred['quarter_start']=update
        pred['admitted']=admission['admitted']
        pred['candidate_signal']=propose_trades(pred)
        pred['actionable_signal']=actionable_signals(pred,admitted=admission['admitted'])
        pred['target_return']=evaluation.target_return.to_numpy()
        shadow=replay_trades(pred,bars,funding,pred.candidate_signal.to_numpy(),end_exclusive=fold_end)
        admitted=replay_trades(pred,bars,funding,pred.actionable_signal.to_numpy(),end_exclusive=fold_end)
        delayed=replay_trades(pred,bars,funding,pred.candidate_signal.to_numpy(),delay_bars=1,end_exclusive=fold_end)
        for frame,collection in [(shadow,shadow_frames),(admitted,admitted_frames),(delayed,delayed_frames)]:
            if not frame.empty:
                frame['quarter_start']=update
                collection.append(frame)
        prediction_frames.append(pred)
        sm=summarize_trades(shadow,update,fold_end)
        fold=dict(update=update.isoformat(),evaluation_end=fold_end.isoformat(),training_rows=len(training),
            calibration_rows=len(calibration),training_start=w.training_start.isoformat(),
            last_training_target=training.target_end.max().isoformat(),calibration_start=w.calibration_start.isoformat(),
            last_calibration_target=calibration.target_end.max().isoformat(),admission_start=w.admission_start.isoformat(),
            admission_stats=gate_stats,admission=admission,shadow_economics=sm,
            admitted_economics=summarize_trades(admitted,update,fold_end),
            delayed_shadow_economics=summarize_trades(delayed,update,fold_end),
            magnitude_scales=model.magnitude_scales.tolist())
        folds.append(fold)
        (output/f'model_{update.date()}.pkl').write_bytes(pickle.dumps(model,protocol=pickle.HIGHEST_PROTOCOL))
        print(json.dumps(dict(update=str(update.date()),admitted=admission['admitted'],candidate_trades=sm['trades'],
            gross_bps=sm['gross_bps'],net6=sm['net_bps']['6'])),flush=True)
    predictions=pd.concat(prediction_frames,ignore_index=True)
    predictions.to_parquet(output/'predictions.parquet',index=False)
    empty=replay_trades(predictions.iloc[:0],bars,funding,np.array([],dtype=int))
    sets={name:pd.concat(frames,ignore_index=True) if frames else empty.copy() for name,frames in
          [('shadow',shadow_frames),('admitted',admitted_frames),('delayed_shadow',delayed_frames)]}
    for name,frame in sets.items():
        frame.to_parquet(output/f'{name}_trades.parquet',index=False)
    periods={}
    for year in (2024,2025,2026):
        year_start=pd.Timestamp(f'{year}-01-01',tz='UTC');year_end=min(year_start+pd.DateOffset(years=1),end)
        p=predictions.loc[predictions.open_time.dt.year.eq(year)]
        known=p.target_return.notna()
        y=p.loc[known,'target_return'].gt(0).astype(int)
        pp=p.loc[known,'p_up']
        periods[str(year)]=dict(rows=len(p),realized_rows=int(known.sum()),zero_return_outcomes=int(p.target_return.eq(0).sum()),
            directional_accuracy=float(((pp>=.5)==y).mean()),brier=float(brier_score_loss(y,pp)),auc=float(roc_auc_score(y,pp)),
            expected_return_rmse_bps=float(np.sqrt(np.mean((p.loc[known,'expected_return_bps']-p.loc[known,'target_return']*1e4)**2))),
            economics={name:summarize_trades(frame.loc[frame.entry_time.dt.year.eq(year)] if not frame.empty else frame,
                                             year_start,year_end) for name,frame in sets.items()})
    assert hashes=={str(p.relative_to(ROOT)):sha(p) for p in sources}
    result=dict(spec=spec,spec_sha256=sha(spec_path),source_sha256=hashes,
        code_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),
            ROOT/'research/bitcoin_5m_exchange_model.py',ROOT/'research/bitcoin_5m_exchange_validation.py']},
        source_preservation='PASS all legacy and previous evidence unchanged',coverage=coverage,folds=folds,periods=periods,
        admitted_quarters=sum(f['admission']['admitted'] for f in folds),
        admission_notice='Separate one-month diagnostic admission is not live or regulatory approval',
        status='COMPLETE historical repair diagnostic; no independent profitability confirmation')
    (output/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='COMPLETE',admitted_quarters=result['admitted_quarters'],coverage=coverage,
                         economics={k:v['economics'] for k,v in periods.items()})),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument('--spec',type=Path,default=DEFAULT_OUTPUT/'spec.json')
    args=parser.parse_args()
    with threadpool_limits(limits=4):
        run(args.output_dir,args.spec)


if __name__=='__main__':
    main()
