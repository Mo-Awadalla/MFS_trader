"""Describe audit outcomes and trace the severe 2022 complete-case coverage loss."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
from research.bitcoin_5m_probability_model import FEATURE_COLUMNS,_validate_metrics


def run():
    r=json.loads((HERE/'results.json').read_text())
    m=_validate_metrics(pd.read_parquet(ROOT/'data/parquet/binance_bitcoin_derivatives_public_v1/normalized/futures_metrics_5m.parquet'))
    panel=pd.read_parquet(ROOT/'data/parquet/bitcoin_5m_probability_binance_v1/panel.parquet')
    required=['sum_open_interest','count_toptrader_long_short_ratio','count_long_short_ratio','sum_taker_long_short_vol_ratio']
    rows=[]
    for month,g in m.loc[m.create_time.dt.year.eq(2022)].groupby(m.create_time.dt.strftime('%Y-%m')):
        h=panel.loc[panel.open_time.dt.strftime('%Y-%m').eq(month)]
        rows.append(dict(month=month,metric_records=len(g),eligible_panel_rows=len(h),
            invalid_by_column={c:int((g[c].isna()|g[c].le(0)|~np.isfinite(g[c])).sum()) for c in required}))
    by_year=[dict(year=int(y),records=len(g),
        missing={c:int(g[c].isna().sum()) for c in required},
        nonpositive={c:int(g[c].le(0).sum()) for c in required}) for y,g in m.groupby(m.create_time.dt.year)]
    missing_cols={c:int(m[c].isna().sum()) for c in m.columns if m[c].isna().any()}
    out=dict(metric_missing_counts=missing_cols,required_inputs_by_year=by_year,metrics_and_panel_by_month_2022=rows,
        refits=[dict(year=x['year'],confidence_rows=x['metrics']['confident_rows'],cal_slope=x['calibration_slope'],
            economics=x['economics'],confidence=x['metrics']['confident_uncertainty']) for x in r['refit_diagnostics']],
        frozen={k:dict(slope=v['calibrated']['posthoc_reliability_fit'],group_sensitivity=v['sensitivity'],
            positive_brier_months=sum(a['brier_improvement_over_half']>0 for a in v['monthly']),months=len(v['monthly']))
            for k,v in r['periods'].items()})
    (HERE/'coverage_details.json').write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
    print(json.dumps(out),flush=True)


if __name__=='__main__':
    run()
