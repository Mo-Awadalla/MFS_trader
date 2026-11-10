"""Inspect a returns-blind sample of SPY auction message fields."""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.vendor'))
import databento as db
P=ROOT/'external_artifacts/databento_cash_etf_budget_v1/ARCX.PILLAR/imbalance/spy_imbalance_2021-01-01_2026-07-27.dbn.zst'
frame=next(db.read_dbn(P).to_df(count=1_000_000,map_symbols=True))
event=pd.to_datetime(frame.ts_event,utc=True).dt.tz_convert('America/New_York')
frame=frame.assign(event_ny=event)
seconds=event.dt.hour*3600+event.dt.minute*60+event.dt.second
m=frame.loc[frame.auction_type.astype(str).eq('M') & seconds.between(9*3600,9.5*3600-1)].copy()
final=m.sort_values('event_ny').groupby(event.dt.strftime('%Y-%m-%d'),sort=True).tail(1)
cols=['event_ny','auction_type','side','ref_price','cont_book_clr_price','auct_interest_clr_price','ind_match_price','paired_qty','total_imbalance_qty','market_imbalance_qty','unpaired_qty','auction_status','freeze_status','collar_reference_price','lower_collar','upper_collar']
print('columns',list(frame.columns))
for c in cols:
 if c in final:
  s=final[c]
  print(c,'nonnull',int(s.notna().sum()),'positive',int((pd.to_numeric(s,errors='coerce')>0).sum()) if c not in {'event_ny','auction_type','side','auction_status','freeze_status'} else '', 'unique_sample',s.drop_duplicates().head(8).astype(str).tolist())
print(final[[c for c in cols if c in final]].head(10).to_string(index=False))
