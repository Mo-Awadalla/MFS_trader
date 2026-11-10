"""Source-level missingness checks and coverage-only diagnostic; no new fitted model."""
import csv
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PREV=HERE.parent/'bitcoin_5m_exchange_20260930'
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(PREV))
from all_decisions_diagnostic import all_decisions


def run():
    rawroot=ROOT/'data/parquet/binance_bitcoin_derivatives_public_v1/raw/futures_metrics_5m'
    sources=[]
    for date in ['2022-02-01','2022-07-01','2022-11-15']:
        archive=rawroot/f'BTCUSDT-metrics-{date}.zip'
        with zipfile.ZipFile(archive) as z:
            text=z.read(z.namelist()[0]).decode('utf-8-sig')
        rows=list(csv.DictReader(io.StringIO(text)))
        checksum=archive.with_name(archive.name+'.CHECKSUM')
        expected=checksum.read_text().split()[0].lower()
        actual=hashlib.sha256(archive.read_bytes()).hexdigest()
        assert expected==actual
        sources.append(dict(date=date,archive=str(archive.relative_to(ROOT)),checksum_verified=True,
            rows=len(rows),first_raw_record=rows[0],
            blank_or_nan_toptrader_records=sum(x['count_toptrader_long_short_ratio'].strip().lower() in ['', 'nan'] for x in rows)))
    b=pd.read_parquet(ROOT/'data/parquet/bitcoin_5m_probability_binance_v1/bars_5m.parquet')
    m=pd.read_parquet(ROOT/'data/parquet/binance_bitcoin_derivatives_public_v1/normalized/futures_metrics_5m.parquet')
    start=pd.Timestamp('2021-11-01',tz='UTC');end=pd.Timestamp('2023-01-01',tz='UTC')
    b=b.loc[(b.open_time>=start)&(b.open_time<end)].copy()
    m=m.loc[(m.create_time>=start)&(m.create_time<end)].copy()
    original=all_decisions(b,m)
    # Constants neutralize availability of the optional ratio inputs solely to count
    # potential rows. They do not infer missing ratios or produce a new trade result.
    for c in ['count_toptrader_long_short_ratio','count_long_short_ratio','sum_taker_long_short_vol_ratio']:
        m[c]=1.0
    reduced=all_decisions(b,m)
    select=lambda a:a.loc[a.open_time.dt.year.eq(2022)]
    result=dict(raw_source_checks=sources,coverage_only_ratio_feature_removal=dict(
        year=2022,price_bars=len(select(b)),original_causal_rows=len(select(original)),
        potential_causal_rows_without_ratio_feature_requirements=len(select(reduced)),
        interpretation='Coverage arithmetic only; no model fitting, imputation recommendation, predictions or trade results'))
    (HERE/'source_missingness.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    run()
