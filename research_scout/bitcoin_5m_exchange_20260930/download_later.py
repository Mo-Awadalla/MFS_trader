"""Acquire only public BTC inputs in a separate cache; preserve historical data."""
import hashlib
import io
import json
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from data.binance_public_archive import normalize_kline_csv

OUT=Path(__file__).resolve().parent/'later_data'
BASE='https://data.binance.vision/data/futures/um'


def fetch(product,key):
    url=f'{BASE}/{product}/{key}'
    target=OUT/'raw'/key
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() and target.with_suffix('.zip.CHECKSUM').exists():
        content=target.read_bytes()
        check=target.with_suffix('.zip.CHECKSUM').read_text()
    else:
        r=requests.get(url,timeout=30)
        r.raise_for_status()
        content=r.content
        r=requests.get(url+'.CHECKSUM',timeout=30)
        r.raise_for_status()
        check=r.text
        target.write_bytes(content)
        target.with_suffix('.zip.CHECKSUM').write_text(check)
    actual=hashlib.sha256(content).hexdigest()
    if actual!=check.split()[0].lower():
        raise ValueError('checksum mismatch '+key)
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        if len(z.infolist())!=1 or z.infolist()[0].file_size>100_000_000:
            raise ValueError('unexpected archive layout')
        raw=z.read(z.namelist()[0])
    if '/klines/' in product:
        frame=normalize_kline_csv(raw,symbol='BTCUSDT',interval='5m')
    else:
        frame=pd.read_csv(io.BytesIO(raw))
    return frame,dict(key=key,url=url,checksum_sha256=actual,bytes=len(content),rows=len(frame))


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    jobs=[]
    for month in pd.period_range('2026-01','2026-08',freq='M').astype(str):
        jobs.extend([('bars',f'monthly/klines/BTCUSDT/5m',f'BTCUSDT-5m-{month}.zip'),
                     ('funding','monthly/fundingRate/BTCUSDT',f'BTCUSDT-fundingRate-{month}.zip')])
    for day in pd.date_range('2026-01-01','2026-08-31').strftime('%Y-%m-%d'):
        jobs.append(('metrics','daily/metrics/BTCUSDT',f'BTCUSDT-metrics-{day}.zip'))
    records=[]
    failures=[]
    frames={k:[] for k in ['bars','funding','metrics']}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures={pool.submit(fetch,p,k):(kind,k) for kind,p,k in jobs}
        for i,f in enumerate(as_completed(futures),1):
            kind,key=futures[f]
            try:
                frame,record=f.result()
                frames[kind].append(frame)
                records.append(record)
            except Exception as e:
                failures.append(dict(key=key,error=str(e)))
            if i%25==0 or i==len(jobs):
                print(f'public archives {i}/{len(jobs)} failures={len(failures)}',flush=True)
    manifest=dict(requested_bounds=['2026-01-01','2026-08-31'],archives=records,failures=failures,
                  decision='Later-period frozen baseline only. No candidate tuning using these outcomes.')
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    for kind,values in frames.items():
        if not values:
            continue
        df=pd.concat(values,ignore_index=True)
        if kind=='metrics':
            df['create_time']=pd.to_datetime(df.create_time,utc=True)
            if df.create_time.duplicated().any():
                raise ValueError('duplicate metric rows')
            df=df.sort_values('create_time')
        elif kind=='funding':
            df['calc_time']=pd.to_datetime(df.calc_time,unit='ms',utc=True)
            df=df.sort_values('calc_time').drop_duplicates('calc_time')
        else:
            df=df.sort_values('open_time')
            if df.open_time.duplicated().any():
                raise ValueError('duplicate bars')
        df.to_parquet(OUT/f'{kind}.parquet',index=False)
    print('public data manifest saved',flush=True)


if __name__=='__main__':
    run()
