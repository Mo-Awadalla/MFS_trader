"""Frozen original model on separately acquired 2026 data; no retraining."""
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from run import ROOT,OLD,DERIV,ledger,summary,sha
from research.bitcoin_5m_probability_model import build_dataset,evaluate_predictions


def run():
    dest=HERE/'later_baseline_results.json'
    if dest.exists():
        raise FileExistsError('later baseline already evaluated')
    fresh=HERE/'later_data'
    manifest=json.loads((fresh/'manifest.json').read_text())
    if manifest['failures']:
        raise ValueError('new data acquisition incomplete')
    old_bars=pd.read_parquet(OLD/'bars_5m.parquet')
    old_metrics=pd.read_parquet(DERIV/'futures_metrics_5m.parquet')
    warm=pd.Timestamp('2025-11-01',tz='UTC')
    bars=pd.concat([old_bars.loc[old_bars.open_time>=warm],
                    pd.read_parquet(fresh/'bars.parquet')],ignore_index=True)
    metrics=pd.concat([old_metrics.loc[old_metrics.create_time>=warm],
                       pd.read_parquet(fresh/'metrics.parquet')],ignore_index=True)
    panel=build_dataset(bars,metrics)
    panel=panel.loc[panel.open_time>='2026-01-01'].reset_index(drop=True)
    with (OLD/'model.pkl').open('rb') as handle:
        model=pickle.load(handle)
    # Confirm that dependency upgrades still reproduce stored original probabilities.
    original_panel=pd.read_parquet(OLD/'panel.parquet').tail(2000)
    original_predictions=pd.read_parquet(OLD/'predictions.parquet').set_index('open_time')
    difference=float(np.max(np.abs(model.predict_proba(original_panel)-original_predictions.loc[original_panel.open_time,'p_up'].to_numpy())))
    if difference>1e-10:
        raise ValueError('frozen model no longer reproduces original probabilities')
    probabilities=model.predict_proba(panel)
    funding=pd.read_parquet(fresh/'funding.parquet')
    rows=[]
    for threshold in [.5,.55]:
        for delay in [0,1]:
            print(f'2026 original threshold={threshold} delay={delay}',flush=True)
            tr=ledger(panel,bars,funding,probabilities,threshold,1,'probability',delay)
            sm=summary(tr,panel,ci=True)
            sm.update(threshold=threshold,delay_bars=delay)
            rows.append(sm)
            tr.to_parquet(HERE/f'later_baseline_{threshold}_{delay}_trades.parquet',index=False)
    report=dict(bounds=[panel.open_time.min().isoformat(),panel.open_time.max().isoformat()],rows=len(panel),
                prediction_metrics=evaluate_predictions(panel,probabilities,baseline_probability=.499343),economics=rows,
                archive_count=len(manifest['archives']),source_file_sha256={str(p.relative_to(ROOT)):sha(p) for p in
                    [fresh/'bars.parquet',fresh/'metrics.parquet',fresh/'funding.parquet',OLD/'model.pkl']},
                model_probability_reproduction_max_absolute_error=difference,
                status='Later historical transfer diagnostic; no parameter selection; no live or executable profit claim.')
    panel.assign(p_up=probabilities).to_parquet(HERE/'later_baseline_predictions.parquet',index=False)
    dest.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    for row in rows:
        print(json.dumps({k:row[k] for k in ['threshold','delay_bars','trades','gross_bps','net_bps','gross_plus_funding_ci95_bps']}),flush=True)


if __name__=='__main__':
    run()
